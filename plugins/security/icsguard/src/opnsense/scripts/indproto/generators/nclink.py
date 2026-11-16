# SPDX-License-Identifier: BSD-2-Clause
"""NC-Link MQTT business-topic permissions, with endpoint/channel suffixes.

This authorizes topic semantics at the broker ingress, not arbitrary JSON PDUs.
A permissive topic never creates a connection-wide Suricata pass rule.
"""

from collections import defaultdict
from generators import build, header, msg
from generators.mqtt import encoded_content

DEFAULT_PORT = 1883
MANAGES_DEFAULT_POLICY = True
BLOCKED_FLOWBIT = "indproto.nclink.blocked"
FAMILIES = {
    "register": [("request", "Register/Request"), ("response", "Register/Response/")],
    "version_probe": [
        ("response", "Probe/Version/Response/"),
        ("request", "Probe/Version/"),
    ],
    "model_query": [
        ("request", "Probe/Query/Request/"),
        ("response", "Probe/Query/Response/"),
    ],
    "model_set": [
        ("request", "Probe/Set/Request/"),
        ("response", "Probe/Set/Response/"),
    ],
    "data_query": [("request", "Query/Request/"), ("response", "Query/Response/")],
    "data_set": [("request", "Set/Request/"), ("response", "Set/Response/")],
    "sample": [("publish", "Sample/")],
    "sample_register": [
        ("request", "Register/Sample/Request/"),
        ("response", "Register/Sample/Response/"),
    ],
    "sample_unregister": [
        ("request", "Unregister/Sample/Request/"),
        ("response", "Unregister/Sample/Response/"),
    ],
    "method_call": [("request", "Method/Call/")],
    "method_control": [
        ("request", "Method/Control/Request/"),
        ("response", "Method/Control/Response/"),
    ],
    "method_status": [("response", "Method/Status/")],
    "method_result": [("response", "Method/Result/")],
    "event_register": [
        ("request", "Register/Event/Request/"),
        ("response", "Register/Event/Response/"),
    ],
    "event_unregister": [
        ("request", "Unregister/Event/Request/"),
        ("response", "Unregister/Event/Response/"),
    ],
    "event": [("publish", "Event/")],
    "state_notify": [("publish", "Notify/State/")],
    "discovery": [("request", "Discovery/Request/"), ("response", "Discovery/Response/")],
}
# Preserve existing policies: an empty legacy selection keeps the original nine operations.
DEFAULT_OPERATIONS = tuple(list(FAMILIES)[:9])
OPERATION_TOPICS = {
    name: next(
        (prefix for direction, prefix in families if direction != "response"),
        families[0][1],
    )
    for name, families in FAMILIES.items()
}
COMPONENT = r"[^/\x00+#]+"


def enabled(value):
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def operations(rule):
    configured = (rule.get("nclink_operations") or "").strip()
    if not configured:
        return DEFAULT_OPERATIONS
    result = tuple(
        dict.fromkeys(
            value.strip().lower() for value in configured.split(",") if value.strip()
        )
    )
    if set(result) - FAMILIES.keys():
        raise ValueError("unsupported NC-Link operation")
    return result


def validate_device_uuid(value):
    value = (value or "").strip()
    if (
        any(char in value for char in ("/", "+", "#", "\x00"))
        or len(value.encode()) > 255
    ):
        raise ValueError(
            "NC-Link device UUID or endpoint may not contain slash, plus, hash or null; maximum 255 bytes"
        )
    return value


def regex_bytes(value):
    return "".join(r"\x%02x" % byte for byte in value.encode("utf-8"))


def topic_root(value):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value.encode()) > 255 or any(
        not part or any(c in part for c in ("+", "#", "\x00", "\r", "\n", ","))
        for part in value.split("/")
    ):
        raise ValueError("invalid NC-Link topic root")
    return value


def subscription_patterns(rule):
    """Authorize literal MQTT subscription filters separately from publications.

    A broad read filter is an explicit grant, never inferred from a publish rule.
    Do not combine it with a device/endpoint condition that it could circumvent.
    """
    root = topic_root(rule.get("nclink_topic_root"))
    result = []
    filters = rule.get("nclink_subscribe_filters") or ""
    if len(filters.encode()) > 2048:
        raise ValueError("NC-Link subscription filters exceed 2048 bytes")
    for value in filters.split(","):
        value = value.strip()
        if not value:
            continue
        if len(value.encode()) > 255 or value.startswith("$share/") or any(
            not part or "\x00" in part or "\n" in part or "\r" in part
            or ("+" in part and part != "+")
            or ("#" in part and (part != "#" or i != len(value.split("/")) - 1))
            for i, part in enumerate(value.split("/"))
        ):
            raise ValueError("invalid NC-Link subscription filter")
        if rule.get("nclink_device_uuid") or rule.get("nclink_endpoint"):
            raise ValueError("explicit subscriptions require a separate rule without device/endpoint conditions")
        result.append(regex_bytes((root + "/" if root else "") + value))
    return result


def patterns(rule):
    direction = rule.get("nclink_direction") or "request"
    if direction not in ("request", "response", "both"):
        raise ValueError("invalid NC-Link direction")
    device = validate_device_uuid(rule.get("nclink_device_uuid"))
    endpoint = validate_device_uuid(rule.get("nclink_endpoint"))
    if endpoint and not device:
        raise ValueError("NC-Link endpoint/channel requires an explicit device UUID")
    root = topic_root(rule.get("nclink_topic_root"))
    result = []
    for operation in operations(rule):
        for kind, prefix in FAMILIES[operation]:
            if kind != "publish" and direction not in (kind, "both"):
                continue
            if not prefix.endswith("/"):
                pattern = regex_bytes(prefix)
            else:
                pattern = regex_bytes(prefix) + (
                    regex_bytes(device) if device else COMPONENT
                )
                pattern += (
                    (r"/" + regex_bytes(endpoint))
                    if endpoint
                    else r"(?:/" + COMPONENT + r")?"
                )
                # Probe/Version/Response/... must not masquerade as a request with UUID "Response".
                if operation == "version_probe" and kind == "request":
                    pattern = (
                        regex_bytes(prefix)
                        + r"(?!Response/|Response$)"
                        + (regex_bytes(device) if device else COMPONENT)
                        + (
                            r"/" + regex_bytes(endpoint)
                            if endpoint
                            else r"(?:/" + COMPONENT + r")?"
                        )
                    )
            result.append((operation, kind, prefix, (regex_bytes(root + "/") if root else "") + pattern))
    if not result:
        raise ValueError(
            "selected NC-Link operations do not match the selected request/response direction"
        )
    return result


def packet_types(rule):
    value = rule.get("nclink_packets") or "publish"
    if value not in ("publish", "subscribe", "both"):
        raise ValueError("invalid NC-Link MQTT packet selection")
    return ("PUBLISH", "SUBSCRIBE") if value == "both" else (value.upper(),)


def common_options(packet="PUBLISH"):
    return [
        "flow:to_server,established",
        "app-layer-protocol:mqtt",
        "mqtt.type:" + packet,
    ]


def topic_options(operation, device_uuid="", negated=False):
    # Kept for integrations using the old helper; policy compilation below uses complete topic regexes.
    prefix = OPERATION_TOPICS[operation]
    value = prefix + device_uuid if prefix.endswith("/") else prefix
    content = encoded_content(value, negated=negated)
    if prefix.endswith("/") and not device_uuid:
        content = content.replace("; endswith", "")
    return ["mqtt.publish.topic", content]


def build_rule(act, scope, message, sid, options):
    if act == "drop":
        options = list(options) + ["flowbits:set," + BLOCKED_FLOWBIT]
    return build(act, "tcp", *scope, message, sid, options)


def flow_guard(sid):
    return build(
        "drop",
        "tcp",
        "any",
        "any",
        "any",
        "IndProto NC-Link blocked flow guard",
        sid,
        ["flow:to_server,established", "flowbits:isset," + BLOCKED_FLOWBIT],
    )


def topic_match(packet, pattern, negate=False):
    buffer = "mqtt.publish.topic" if packet == "PUBLISH" else "mqtt.subscribe.topic"
    if negate:
        pattern = "(?!(?:" + pattern + ")$).+"
    return [buffer, 'pcre:"/^' + pattern.replace("/", r"\/") + '$/s"']


def generate_policy(rules, sid_base, default_action):
    result = []
    sid = sid_base
    groups = defaultdict(list)
    for rule in rules:
        groups[header(rule, "tcp", DEFAULT_PORT)].append(rule)
    for scope, scoped in groups.items():
        allowed = defaultdict(list)
        protected = set()
        for rule in scoped:
            packets = packet_types(rule)
            protected.update(packets)
            if not rule.get("_active"):
                continue
            items = patterns(rule)
            explicit_subscriptions = subscription_patterns(rule)
            if explicit_subscriptions and packets == ("PUBLISH",):
                raise ValueError("subscription filters require SUBSCRIBE packet selection")
            audit = enabled(rule.get("log_only"))
            act = "drop" if rule.get("action") == "block" and not audit else "alert"
            for packet in packets:
                if rule.get("action", "pass") == "pass" and not audit:
                    allowed[packet].extend(item[3] for item in items)
                for operation, kind, prefix, pattern in items:
                    label = (
                        "BLOCK"
                        if act == "drop"
                        else "LOG_ONLY" if audit else "PASS AUDIT"
                    )
                    options = common_options(packet) + topic_match(packet, pattern)
                    result.append(
                        build_rule(
                            act,
                            scope,
                            msg(
                                rule,
                                "%s NC-LINK %s %s %s"
                                % (label, operation.upper(), kind, packet),
                            ),
                            sid,
                            options,
                        )
                    )
                    sid += 1
                if packet == "SUBSCRIBE":
                    for pattern in explicit_subscriptions:
                        if rule.get("action", "pass") == "pass" and not audit:
                            allowed[packet].append(pattern)
                        result.append(build_rule(
                            act, scope, msg(rule, label + " NC-LINK EXPLICIT SUBSCRIPTION"),
                            sid, common_options(packet) + topic_match(packet, pattern),
                        ))
                        sid += 1
        if default_action == "block":
            for packet in sorted(protected):
                union = (
                    "(?:" + "|".join(sorted(set(allowed[packet]))) + ")"
                    if allowed[packet]
                    else "(?!)"
                )
                result.append(
                    build_rule(
                        "drop",
                        scope,
                        "IndProto NC-Link default block unapproved " + packet,
                        sid,
                        common_options(packet) + topic_match(packet, union, True),
                    )
                )
                sid += 1
    if any(line.startswith("drop ") for line in result):
        result.append(flow_guard(sid))
    return result


def generate(rule_index, rule):
    return generate_policy([dict(rule, _active=True)], int(rule["sid_base"]), "pass")
