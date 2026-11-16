from generators import action, build, header, msg


DEFAULT_PORT = 102
MANAGES_DEFAULT_POLICY = True
PROTOCOL_LABEL = 'S7comm'


def transaction_options(function_byte):
    # Search TPKT + COTP + S7 Job headers in the reassembled TCP stream.
    # Relative offsets also detect coalesced requests and split TCP segments.
    return ['flow:to_server,established', 'content:"|03 00|"',
            'content:"|02 f0 80 32 01|"; distance:2; within:5',
            'content:"|%s|"; distance:8; within:1' % function_byte]


def denied_transactions(allowed):
    functions = {int(code, 16) for rule in allowed for _, code in operations((rule.get('access') or 'readwrite').lower())}
    for code in sorted(set(range(256)) - functions):
        yield transaction_options('%02x' % code)


def generate_policy(rules, sid_base, default_action):
    from generators.transaction_policy import policy
    return policy(__import__(__name__, fromlist=['']), rules, sid_base, default_action)


def operations(access):
    if access == "read":
        return (("read", "04"),)
    if access == "write":
        return (("write", "05"),)
    if access == "readwrite":
        return (("read", "04"), ("write", "05"))
    raise ValueError("unsupported access value %r" % access)


def generate(rule_index, rule):
    src_ip, dst_ip, dst_port = header(rule, "tcp", DEFAULT_PORT)
    act = action(rule)
    result = []
    for index, item in enumerate(operations((rule.get("access") or "readwrite").lower())):
        name, function_byte = item
        result.append(build(
            act,
            "tcp",
            src_ip,
            dst_ip,
            dst_port,
            msg(rule, "[BETA] %s" % name),
            int(rule["sid_base"]) + index,
            transaction_options(function_byte),
        ))
    return result


def default_block(sid, default_action):
    if default_action != "block":
        return []
    return [build(
        "drop",
        "tcp",
        "any",
        "any",
        str(DEFAULT_PORT),
        "IndProto default S7comm block [BETA]",
        sid,
        ["flow:to_server,established", 'content:"|03|"; depth:1', 'content:"|32|"; offset:7; depth:1'],
    )]
