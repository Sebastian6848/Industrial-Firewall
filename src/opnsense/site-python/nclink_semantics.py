"""
NC-Link business semantic extraction helpers.
"""

import json
import re


MESSAGE_CLASSES = {
    'REGMSG': 'registration',
    'REMSG': 'resource',
    'PRK': 'process',
    'SPSK': 'sample',
}

# NC-Link interface topics from the terminal and interface definition.  Longest
# prefixes must be checked first because several families share a root.
INTERFACE_PATTERNS = (
    (('probe', 'version', 'response'), 'version', 'response', ('device_id', 'client_id')),
    (('probe', 'query', 'request'), 'model', 'request', ('device_id', 'client_id')),
    (('probe', 'query', 'response'), 'model', 'response', ('device_id', 'client_id')),
    (('probe', 'set', 'request'), 'model', 'request', ('device_id', 'client_id')),
    (('probe', 'set', 'response'), 'model', 'response', ('device_id', 'client_id')),
    (('register', 'sample', 'request'), 'sample_registration', 'request', ('device_id', 'client_id')),
    (('register', 'sample', 'response'), 'sample_registration', 'response', ('device_id', 'client_id')),
    (('unregister', 'sample', 'request'), 'sample_registration', 'unregister_request', ('device_id', 'client_id')),
    (('unregister', 'sample', 'response'), 'sample_registration', 'unregister_response', ('device_id', 'client_id')),
    (('register', 'event', 'request'), 'event_registration', 'request', ('device_id', 'client_id')),
    (('register', 'event', 'response'), 'event_registration', 'response', ('device_id', 'client_id')),
    (('unregister', 'event', 'request'), 'event_registration', 'unregister_request', ('device_id', 'client_id')),
    (('unregister', 'event', 'response'), 'event_registration', 'unregister_response', ('device_id', 'client_id')),
    (('method', 'control', 'request'), 'method', 'control_request', ('device_id', 'client_id')),
    (('method', 'control', 'response'), 'method', 'control_response', ('device_id', 'client_id')),
    (('register', 'request'), 'registration', 'request', ()),
    (('register', 'response'), 'registration', 'response', ('client_id',)),
    (('discovery', 'request'), 'discovery', 'request', ('client_id',)),
    (('discovery', 'response'), 'discovery', 'response', ('client_id',)),
    (('query', 'request'), 'data_query', 'request', ('device_id', 'client_id')),
    (('query', 'response'), 'data_query', 'response', ('device_id', 'client_id')),
    (('set', 'request'), 'data_set', 'request', ('device_id', 'client_id')),
    (('set', 'response'), 'data_set', 'response', ('device_id', 'client_id')),
    (('notify', 'state'), 'state', 'notify', ('terminal_id',)),
    (('method', 'call'), 'method', 'call', ('device_id', 'client_id')),
    (('method', 'status'), 'method', 'status', ('device_id', 'client_id')),
    (('method', 'result'), 'method', 'result', ('device_id', 'client_id')),
    (('probe', 'version'), 'version', 'request', ('device_id',)),
    (('event',), 'event', 'publish', ('device_id', 'client_id')),
    (('sample',), 'sample', 'publish', ()),
)

IDENTITY_KEYS = {
    'deviceid': 'device_id',
    'device_id': 'device_id',
    'machineid': 'machine_id',
    'machine_id': 'machine_id',
    'cncid': 'cnc_id',
    'cnc_id': 'cnc_id',
    'gatewayid': 'gateway_id',
    'gateway_id': 'gateway_id',
    'lineid': 'line_id',
    'line_id': 'line_id',
    'workshopid': 'workshop_id',
    'workshop_id': 'workshop_id',
    'cli_uuid': 'client_id',
    'clientid': 'client_id',
    'client_id': 'client_id',
    'dev_uuid': 'device_id',
    'deviceuuid': 'device_id',
    'ex_cid': 'client_id',
    'terminalid': 'terminal_id',
    'terminal_id': 'terminal_id',
    'tid': 'terminal_id',
}

TIME_KEYS = {'time', 'timestamp', 'ts', 'eventtime', 'event_time', 'collecttime', 'collect_time'}
SEQUENCE_KEYS = {'seq', 'sequence', 'sequenceid', 'sequence_id', 'msgid', 'messageid', 'message_id'}
NAME_KEYS = {'name', 'key', 'code', 'id', 'tag', 'point', 'metric', 'param', 'parameter'}
VALUE_KEYS = {'value', 'val', 'data', 'v'}
UNIT_KEYS = {'unit', 'u'}
QUALITY_KEYS = {'quality', 'q', 'status'}
ALARM_KEYS = {'alarm', 'alarms', 'fault', 'faults', 'warning', 'warnings'}
COMMAND_KEYS = {'cmd', 'command', 'commandtype', 'action', 'operation'}
STATE_KEYS = {'state', 'status', 'mode', 'runningstate', 'runstate', 'workstate'}


def _lower_key(value):
    return re.sub(r'[^a-z0-9_]', '', str(value).replace('-', '_').lower())


def _stringify(value):
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _append_unique(items, value):
    if value not in items:
        items.append(value)


def _walk(data, path=None):
    path = path or []
    yield path, data
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _walk(value, path + [str(key)])
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _walk(value, path + [str(index)])


def _match_interface(levels, lower):
    for pattern, family, operation, identity_names in INTERFACE_PATTERNS:
        size = len(pattern)
        for start in range(0, len(lower) - size + 1):
            if tuple(lower[start:start + size]) != pattern:
                continue
            if start != 0 and 'nclink' not in lower[:start]:
                continue
            suffix = levels[start + size:]
            names = identity_names
            if pattern == ('sample',):
                names = ('device_id', 'client_id', 'sample_channel_id') if len(suffix) >= 3 else (
                    'device_id', 'sample_channel_id'
                )
            identities = {
                name: suffix[index]
                for index, name in enumerate(names)
                if index < len(suffix) and suffix[index]
            }
            return {
                'name': '/'.join(levels[start:start + size]),
                'family': family,
                'operation': operation,
                'identities': identities,
            }
    return {}


def _topic_semantics(topic):
    if not isinstance(topic, str) or not topic:
        return {}
    levels = [item for item in topic.split('/') if item]
    result = {'raw': topic, 'levels': levels}
    lower = [item.lower() for item in levels]
    interface = _match_interface(levels, lower)
    if interface:
        result['interface'] = interface
        result['nclink'] = True
    if 'nclink' in lower:
        result['protocol_level'] = lower.index('nclink')
        result['nclink'] = True
    for index, item in enumerate(levels):
        key = item.lower()
        if key in {'regmsg', 'remsg', 'prk', 'spsk'}:
            result['message_hint'] = key.upper()
        elif key in {'status', 'state', 'alarm', 'event', 'command', 'data'}:
            result['channel'] = key
        elif index > 0 and lower[index - 1] in {'device', 'machine', 'cnc', 'gateway'}:
            result['%s_id' % lower[index - 1]] = item
    return result


def _message_types(payload):
    result = []
    for path, value in _walk(payload):
        if path:
            upper = str(path[-1]).upper()
            if upper in MESSAGE_CLASSES:
                _append_unique(result, upper)
        if isinstance(value, str) and value.upper() in MESSAGE_CLASSES:
            _append_unique(result, value.upper())
    return result


def _extract_identities(payload, topic_info):
    identities = {}
    identities.update(topic_info.get('interface', {}).get('identities', {}))
    for key, value in topic_info.items():
        if key in IDENTITY_KEYS.values():
            identities[key] = value
    for path, value in _walk(payload):
        if not path or isinstance(value, (dict, list)):
            continue
        mapped = IDENTITY_KEYS.get(_lower_key(path[-1]))
        if mapped and value not in ('', None):
            identities[mapped] = _stringify(value)
    return identities


def _extract_scalars(payload):
    timestamps = []
    sequences = []
    commands = []
    states = {}
    for path, value in _walk(payload):
        if not path or isinstance(value, (dict, list)) or value in ('', None):
            continue
        key = _lower_key(path[-1])
        if path[-1] == '@id':
            _append_unique(sequences, _stringify(value))
        elif key in TIME_KEYS:
            _append_unique(timestamps, _stringify(value))
        elif key in SEQUENCE_KEYS:
            _append_unique(sequences, _stringify(value))
        elif key in COMMAND_KEYS:
            _append_unique(commands, _stringify(value))
        elif key in STATE_KEYS:
            states['.'.join(path)] = _stringify(value)
    return timestamps, sequences, commands, states


def _looks_like_point(item):
    if not isinstance(item, dict):
        return False
    keys = {_lower_key(key) for key in item}
    return bool(keys & NAME_KEYS and keys & VALUE_KEYS)


def _extract_data_points(payload):
    points = []
    for path, value in _walk(payload):
        if _looks_like_point(value):
            point = {'path': '.'.join(path)}
            for key, item in value.items():
                normalized = _lower_key(key)
                if normalized in NAME_KEYS and 'name' not in point:
                    point['name'] = _stringify(item)
                elif normalized in VALUE_KEYS and 'value' not in point:
                    point['value'] = item
                elif normalized in UNIT_KEYS and 'unit' not in point:
                    point['unit'] = _stringify(item)
                elif normalized in QUALITY_KEYS and 'quality' not in point:
                    point['quality'] = _stringify(item)
                elif normalized in TIME_KEYS and 'timestamp' not in point:
                    point['timestamp'] = _stringify(item)
            points.append(point)
        elif path and not isinstance(value, (dict, list)) and not path[-1].isdigit():
            key = _lower_key(path[-1])
            parent = _lower_key(path[-2]) if len(path) > 1 else ''
            if key not in IDENTITY_KEYS and key not in TIME_KEYS and parent in {'axis', 'spindle', 'feed', 'override'}:
                points.append({'path': '.'.join(path), 'name': path[-1], 'value': value})
    return points


def _extract_alarms(payload):
    alarms = []
    for path, value in _walk(payload):
        if not path:
            continue
        if _lower_key(path[-1]) not in ALARM_KEYS:
            continue
        if isinstance(value, list):
            for item in value:
                alarms.append(item if isinstance(item, dict) else {'message': _stringify(item)})
        elif isinstance(value, dict):
            alarms.append(value)
        elif value not in ('', None):
            alarms.append({'message': _stringify(value)})
    return alarms


def _message_bodies(payload, message_types):
    result = {}
    if not isinstance(payload, dict):
        return result
    for message_type in message_types:
        for key, value in payload.items():
            if str(key).upper() == message_type:
                result[message_type.lower()] = value
    return result


def parse_business_semantics(payload, topic=None, client_id=None):
    topic_info = _topic_semantics(topic)
    message_types = _message_types(payload)
    if topic_info.get('message_hint'):
        _append_unique(message_types, topic_info['message_hint'])

    timestamps, sequences, commands, states = _extract_scalars(payload)
    identities = _extract_identities(payload, topic_info)
    interface = topic_info.get('interface', {})
    detected = bool(
        topic_info.get('nclink') or
        message_types or
        (isinstance(client_id, str) and re.search(r'nc[-_ ]?link', client_id, re.IGNORECASE))
    )
    result = {
        'protocol': 'NC-Link' if detected else None,
        'detected': detected,
        'message_types': message_types,
        'message_class': MESSAGE_CLASSES.get(message_types[0], 'unknown') if message_types else interface.get('family'),
        'interface': interface,
        'topic': topic_info,
        'identities': identities,
        'data_points': _extract_data_points(payload),
        'alarms': _extract_alarms(payload),
        'states': states,
        'commands': commands,
        'messages': _message_bodies(payload, message_types),
    }
    if client_id:
        result['client_id'] = client_id
        identities.setdefault('client_id', client_id)
    if timestamps:
        result['timestamp'] = timestamps[0]
        result['timestamps'] = timestamps
    if sequences:
        result['sequence'] = sequences[0]
        result['sequences'] = sequences

    return {key: value for key, value in result.items() if value not in ({}, [], None)}
