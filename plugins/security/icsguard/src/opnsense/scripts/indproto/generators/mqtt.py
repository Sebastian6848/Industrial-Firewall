from collections import defaultdict

from generators import build, header, msg


DEFAULT_PORT = 1883
MANAGES_DEFAULT_POLICY = True
PROTECTED_OPERATIONS = ("CONNECT", "PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE")
BLOCKED_FLOWBIT = "indproto.mqtt.blocked"


def legacy_operations(access):
    if access == "read":
        return ("SUBSCRIBE", "UNSUBSCRIBE")
    if access == "write":
        return ("PUBLISH",)
    if access == "readwrite":
        return ("PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE")
    raise ValueError("unsupported access value %r" % access)


def operations(rule):
    if not rule.get("mqtt_operations_present"):
        return legacy_operations((rule.get("access") or "readwrite").lower())
    valid = {
        "publish": "PUBLISH",
        "subscribe": "SUBSCRIBE",
        "unsubscribe": "UNSUBSCRIBE",
    }
    configured = []
    for value in (rule.get("mqtt_operations") or "").split(","):
        value = value.strip().lower()
        if not value:
            continue
        if value not in valid:
            raise ValueError("unsupported MQTT operation %r" % value)
        configured.append(valid[value])
    return tuple(dict.fromkeys(configured))


def enabled(value):
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def encoded_content(value, negated=False):
    encoded = (value or "").encode("utf-8")
    if not encoded:
        return None
    operator = "!" if negated else ""
    return 'content:%s"|%s|"; startswith; endswith' % (
        operator,
        " ".join("%02x" % byte for byte in encoded),
    )


def topic_buffer(operation):
    return {
        "PUBLISH": "mqtt.publish.topic",
        "SUBSCRIBE": "mqtt.subscribe.topic",
        "UNSUBSCRIBE": "mqtt.unsubscribe.topic",
    }[operation]


def exact_topic_options(operation, topic):
    content = encoded_content(topic)
    return [] if content is None else [topic_buffer(operation), content]


def excluded_topics_options(operation, topics):
    options = [topic_buffer(operation)]
    options.extend(encoded_content(topic, negated=True) for topic in sorted(topics))
    return options


def connect_options(rule):
    options = ["mqtt.type:CONNECT"]
    for field, buffer_name in (
        ("mqtt_client_id", "mqtt.connect.clientid"),
        ("mqtt_username", "mqtt.connect.username"),
    ):
        content = encoded_content(rule.get(field))
        if content is not None:
            options.extend([buffer_name, content])
    return options


def common_options():
    return ["flow:to_server,established", "app-layer-protocol:mqtt"]


def scope(rule):
    return header(rule, "tcp", DEFAULT_PORT)


def build_rule(action_value, rule_scope, message, sid, options):
    src_ip, dst_ip, dst_port = rule_scope
    options = list(options)
    if action_value == "drop" and not any(option.startswith("flowbits:set,") for option in options):
        options.append("flowbits:set,%s" % BLOCKED_FLOWBIT)
    return build(action_value, "tcp", src_ip, dst_ip, dst_port, message, sid, options)


def blocked_flow_guard(sid):
    return build(
        "drop",
        "tcp",
        "any",
        "any",
        "any",
        "IndProto MQTT blocked flow guard",
        sid,
        ["flow:to_server,established", "flowbits:isset,%s" % BLOCKED_FLOWBIT],
    )


def validate_qos(rule):
    qos = (rule.get("mqtt_qos") or "").strip()
    if qos not in ("", "0", "1", "2"):
        raise ValueError("unsupported MQTT QoS value %r" % qos)
    return qos


def audit_rules(rule, sid):
    rule_scope = scope(rule)
    if enabled(rule.get("mqtt_tls")):
        return [build_rule(
            "alert",
            rule_scope,
            msg(rule, "TLS PASS AUDIT"),
            sid,
            ["flow:to_server", "flags:S"],
        )]

    result = []
    common = common_options()
    if enabled(rule.get("mqtt_allow_connect")):
        result.append(build_rule(
            "alert", rule_scope, msg(rule, "PASS AUDIT CONNECT"), sid, common + connect_options(rule)
        ))
        sid += 1
    elif rule.get("mqtt_client_id") or rule.get("mqtt_username"):
        raise ValueError("MQTT client ID and username require Allow MQTT CONNECT")

    qos = validate_qos(rule)
    for operation in operations(rule):
        options = common + ["mqtt.type:%s" % operation]
        options.extend(exact_topic_options(operation, rule.get("mqtt_topic")))
        if operation == "PUBLISH" and qos:
            options.append("mqtt.qos:%s" % qos)
        result.append(build_rule(
            "alert", rule_scope, msg(rule, "PASS AUDIT %s" % operation), sid, options
        ))
        sid += 1
    return result


def blocking_rules(rule, sid):
    rule_scope = scope(rule)
    if enabled(rule.get("mqtt_tls")):
        return [build_rule(
            "drop", rule_scope, msg(rule, "TLS BLOCK"), sid, ["flow:to_server,established"]
        )]

    result = []
    common = common_options()
    # This field always means "allow CONNECT", regardless of the rule action.
    # A topic block must not become a connection-level block unless the user
    # explicitly clears Allow CONNECT.
    if not enabled(rule.get("mqtt_allow_connect")):
        result.append(build_rule(
            "drop", rule_scope, msg(rule, "BLOCK CONNECT"), sid, common + connect_options(rule)
        ))
        sid += 1
    qos = validate_qos(rule)
    for operation in operations(rule):
        options = common + ["mqtt.type:%s" % operation]
        options.extend(exact_topic_options(operation, rule.get("mqtt_topic")))
        if operation == "PUBLISH" and qos:
            options.append("mqtt.qos:%s" % qos)
        result.append(build_rule("drop", rule_scope, msg(rule, "BLOCK %s" % operation), sid, options))
        sid += 1
    return result


def complement_rules(rule_scope, allow_rules, sid):
    result = []
    common = common_options()
    allowed_by_operation = defaultdict(list)
    for rule in allow_rules:
        if enabled(rule.get("mqtt_allow_connect")):
            allowed_by_operation["CONNECT"].append(rule)
        for operation in operations(rule):
            allowed_by_operation[operation].append(rule)

    connect_rules = allowed_by_operation["CONNECT"]
    if not connect_rules:
        result.append(build_rule(
            "drop", rule_scope, "IndProto MQTT default block CONNECT", sid,
            common + ["mqtt.type:CONNECT"],
        ))
        sid += 1
    else:
        identity_pairs = {
            (rule.get("mqtt_client_id") or "", rule.get("mqtt_username") or "")
            for rule in connect_rules
        }
        if len(identity_pairs) > 1 and all(client_id and username for client_id, username in identity_pairs):
            raise ValueError(
                "MQTT default-block policy cannot safely combine multiple client ID/username pairs in one scope"
            )
        for field, buffer_name, label in (
            ("mqtt_client_id", "mqtt.connect.clientid", "client ID"),
            ("mqtt_username", "mqtt.connect.username", "username"),
        ):
            values = {rule.get(field) for rule in connect_rules if rule.get(field)}
            if values and all(rule.get(field) for rule in connect_rules):
                options = common + ["mqtt.type:CONNECT", buffer_name]
                options.extend(encoded_content(value, negated=True) for value in sorted(values))
                result.append(build_rule(
                    "drop", rule_scope, "IndProto MQTT default block CONNECT %s" % label, sid, options
                ))
                sid += 1
                if field == "mqtt_username":
                    result.append(build_rule(
                        "drop", rule_scope, "IndProto MQTT default block CONNECT missing username", sid,
                        common + ["mqtt.type:CONNECT", "mqtt.connect.flags:!username"],
                    ))
                    sid += 1

    for operation in ("PUBLISH", "SUBSCRIBE", "UNSUBSCRIBE"):
        operation_rules = allowed_by_operation[operation]
        if not operation_rules:
            result.append(build_rule(
                "drop", rule_scope, "IndProto MQTT default block %s" % operation, sid,
                common + ["mqtt.type:%s" % operation],
            ))
            sid += 1
            continue

        topics = {rule.get("mqtt_topic") for rule in operation_rules if rule.get("mqtt_topic")}
        unrestricted_topic = any(not rule.get("mqtt_topic") for rule in operation_rules)
        if topics and not unrestricted_topic:
            result.append(build_rule(
                "drop", rule_scope, "IndProto MQTT default block other %s topics" % operation, sid,
                common + ["mqtt.type:%s" % operation] + excluded_topics_options(operation, topics),
            ))
            sid += 1

        if operation == "PUBLISH":
            topic_groups = defaultdict(list)
            for rule in operation_rules:
                topic_groups[rule.get("mqtt_topic") or ""].append(validate_qos(rule))
            if "" in topic_groups and topics:
                raise ValueError(
                    "MQTT default-block policy cannot mix unrestricted and exact PUBLISH topics in one scope"
                )
            for topic, qos_values in topic_groups.items():
                if "" in qos_values or len(set(qos_values)) == 3:
                    continue
                options = common + ["mqtt.type:PUBLISH"]
                options.extend(exact_topic_options("PUBLISH", topic))
                options.extend("mqtt.qos:!%s" % qos for qos in sorted(set(qos_values)))
                result.append(build_rule(
                    "drop", rule_scope, "IndProto MQTT default block other PUBLISH QoS", sid, options
                ))
                sid += 1
    return result


def generate_policy(rules, sid_base, default_action):
    result = []
    next_sid = sid_base
    groups = defaultdict(list)
    for rule in rules:
        groups[scope(rule)].append(rule)

    for rule_scope, scoped_rules in groups.items():
        active = [rule for rule in scoped_rules if rule.get("_active")]
        allow_rules = [
            rule for rule in active
            if (rule.get("action") or "pass").lower() == "pass" and not enabled(rule.get("log_only"))
            and not enabled(rule.get("mqtt_tls"))
        ]
        for rule in active:
            action_value = (rule.get("action") or "pass").lower()
            if enabled(rule.get("log_only")) or action_value == "pass":
                generated = audit_rules(rule, next_sid)
            elif action_value == "block":
                generated = blocking_rules(rule, next_sid)
            else:
                raise ValueError("unsupported MQTT action %r" % action_value)
            result.extend(generated)
            next_sid += len(generated)

        if default_action == "block" and any(not enabled(rule.get("mqtt_tls")) for rule in scoped_rules):
            generated = complement_rules(rule_scope, allow_rules, next_sid)
            result.extend(generated)
            next_sid += len(generated)
    if any(rule.startswith("drop ") for rule in result):
        result.append(blocked_flow_guard(next_sid))
    return result


def generate(rule_index, rule):
    return generate_policy([dict(rule, _active=True)], int(rule["sid_base"]), "pass")
