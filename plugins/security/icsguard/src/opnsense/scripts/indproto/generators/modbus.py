from generators import action, build, csv_ints, header, msg


READ_FUNCTION_CODES = (1, 2, 3, 4, 7, 11, 17, 24)
WRITE_FUNCTION_CODES = (5, 6, 15, 16, 22, 23)
DEFAULT_PORT = 502
MANAGES_DEFAULT_POLICY = True
PROTOCOL_LABEL = 'Modbus'


def function_codes(rule):
    configured = csv_ints(
        rule.get("modbus_function_codes") or rule.get("function_codes"),
        "Modbus function code",
    )
    if configured:
        return configured

    access = (rule.get("access") or "readwrite").lower()
    if access == "read":
        return READ_FUNCTION_CODES
    if access == "write":
        return WRITE_FUNCTION_CODES
    if access == "readwrite":
        return []
    raise ValueError("unsupported access value %r" % access)


def unit_values(value):
    value = (value or "").strip()
    if not value:
        return [None]
    if "-" in value:
        start, end = value.split("-", 1)
        start = int(start, 10)
        end = int(end, 10)
        if start > end or start < 0 or end > 255:
            raise ValueError("invalid Modbus unit range %r" % value)
        return list(range(start, end + 1))
    unit = int(value, 10)
    if not 0 <= unit <= 255:
        raise ValueError('Modbus unit must be between 0 and 255')
    return [unit]


def byte_value(value, field_name):
    if value < 0 or value > 255:
        raise ValueError("%s out of range: %d" % (field_name, value))
    return "%02x" % value


def modbus_options(function_code=None, unit_id=None):
    options = ['app-layer-protocol:modbus']
    values = []
    if unit_id is not None:
        byte_value(unit_id, 'Modbus unit id')
        values.append('unit %d' % unit_id)
    if function_code is not None:
        if not 1 <= function_code <= 127:
            raise ValueError('Modbus request function must be between 1 and 127')
        values.append('function %d' % function_code)
    if values:
        options.append('modbus: ' + ', '.join(values))
    return options


def denied_transactions(allowed):
    unit_functions = {unit: set() for unit in range(256)}
    for rule in allowed:
        functions = set(function_codes(rule) or range(1, 128))
        for unit in unit_values(rule.get('modbus_unit_id')):
            for value in range(256) if unit is None else [unit]:
                if not 0 <= value <= 255:
                    raise ValueError('Modbus unit must be between 0 and 255')
                unit_functions[value].update(functions)
    # Coalesce units sharing the same permissions to keep rule counts bounded.
    start = 0
    while start < 256:
        end = start
        functions = unit_functions[start]
        while end < 255 and unit_functions[end + 1] == functions:
            end += 1
        selectors = []
        if start == 0 and end == 255:
            selectors = ['']
        elif start == end:
            selectors = ['unit %d' % start]
        else:
            # Suricata's <> range excludes endpoints.
            selectors = ['unit %d' % start, 'unit %d' % end]
            if end - start > 1:
                selectors.append('unit %d<>%d' % (start, end))
        for selector in selectors:
            if not functions:
                yield ['flow:to_server,established', 'app-layer-protocol:modbus'] + (['modbus: ' + selector] if selector else [])
            elif len(functions) < 127:
                for code in sorted(set(range(1, 128)) - functions):
                    yield ['flow:to_server,established', 'app-layer-protocol:modbus',
                           'modbus: ' + ((selector + ', ') if selector else '') + 'function %d' % code]
        start = end + 1


def generate_policy(rules, sid_base, default_action):
    from generators.transaction_policy import policy
    return policy(__import__(__name__, fromlist=['']), rules, sid_base, default_action)


def generate(rule_index, rule):
    src_ip, dst_ip, dst_port = header(rule, "tcp", DEFAULT_PORT)
    act = action(rule)
    result = []
    units = unit_values(rule.get("modbus_unit_id"))
    functions = function_codes(rule)
    sequence = functions or [None]

    serial = 0
    for unit_id in units:
        for function_code in sequence:
            options = ["flow:to_server,established"]
            options.extend(modbus_options(function_code, unit_id))
            suffix = ""
            if function_code is not None:
                suffix += " fc %d" % function_code
            if unit_id is not None:
                suffix += " unit %d" % unit_id
            result.append(build(
                act,
                "tcp",
                src_ip,
                dst_ip,
                dst_port,
                msg(rule, suffix.strip()),
                int(rule["sid_base"]) + serial,
                options,
            ))
            serial += 1
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
        "IndProto default Modbus block",
        sid,
        ["flow:to_server,established", 'content:"|00 00|"; offset:2; depth:2'],
    )]
