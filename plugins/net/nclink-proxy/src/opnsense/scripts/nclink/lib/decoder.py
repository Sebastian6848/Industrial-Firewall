"""
MQTT/NC-Link decoder used by IDS enrichment and the transparent observer proxy.
"""

import base64
import json
import re

from .semantics import parse_business_semantics


PACKET_TYPES = {
    1: 'CONNECT',
    2: 'CONNACK',
    3: 'PUBLISH',
    4: 'PUBACK',
    5: 'PUBREC',
    6: 'PUBREL',
    7: 'PUBCOMP',
    8: 'SUBSCRIBE',
    9: 'SUBACK',
    10: 'UNSUBSCRIBE',
    11: 'UNSUBACK',
    12: 'PINGREQ',
    13: 'PINGRESP',
    14: 'DISCONNECT',
    15: 'AUTH',
}

_NCLINK_RE = re.compile(r'nc[-_ ]?link', re.IGNORECASE)
_PAYLOAD_MARKER_RE = re.compile(r'\b(REGMSG|REMSG|PRK|SPSK)\b', re.IGNORECASE)


class MQTTDecodeError(ValueError):
    pass


def _decode_remaining_length(data, offset=1):
    multiplier = 1
    value = 0
    consumed = 0
    while True:
        if offset + consumed >= len(data):
            return None
        encoded = data[offset + consumed]
        value += (encoded & 127) * multiplier
        consumed += 1
        if multiplier > 128 * 128 * 128:
            raise MQTTDecodeError('malformed remaining length')
        if (encoded & 128) == 0:
            return value, consumed
        multiplier *= 128


def _read_string(data, offset):
    if offset + 2 > len(data):
        raise MQTTDecodeError('truncated mqtt string')
    length = int.from_bytes(data[offset:offset + 2], 'big')
    offset += 2
    if offset + length > len(data):
        raise MQTTDecodeError('truncated mqtt string data')
    try:
        value = data[offset:offset + length].decode('utf-8')
    except UnicodeDecodeError as error:
        raise MQTTDecodeError('invalid utf-8 mqtt string') from error
    return value, offset + length


def iter_packets(data):
    offset = 0
    while offset < len(data):
        remaining = _decode_remaining_length(data, offset + 1)
        if remaining is None:
            break
        packet_len, remaining_len_bytes = remaining
        header_len = 1 + remaining_len_bytes
        end = offset + header_len + packet_len
        if end > len(data):
            break
        yield data[offset:end]
        offset = end


def split_packets(data):
    packets = []
    offset = 0
    while offset < len(data):
        remaining = _decode_remaining_length(data, offset + 1)
        if remaining is None:
            break
        packet_len, remaining_len_bytes = remaining
        header_len = 1 + remaining_len_bytes
        end = offset + header_len + packet_len
        if end > len(data):
            break
        packets.append(data[offset:end])
        offset = end
    return packets, data[offset:]


def decode_stream(data):
    return [decode_packet(packet) for packet in iter_packets(data)]


def decode_packet(packet):
    if not packet:
        raise MQTTDecodeError('empty packet')
    remaining = _decode_remaining_length(packet, 1)
    if remaining is None:
        raise MQTTDecodeError('truncated packet')
    packet_len, remaining_len_bytes = remaining
    packet_type_id = packet[0] >> 4
    if packet_type_id == 0:
        raise MQTTDecodeError('reserved mqtt packet type')
    flags = packet[0] & 0x0f
    header_len = 1 + remaining_len_bytes
    if header_len + packet_len > len(packet):
        raise MQTTDecodeError('truncated packet body')
    body = packet[header_len:header_len + packet_len]
    result = {
        'packet_type': PACKET_TYPES.get(packet_type_id, 'UNKNOWN'),
        'packet_type_id': packet_type_id,
        'flags': flags,
        'length': packet_len,
    }

    if packet_type_id == 1:
        result.update(_decode_connect(body))
    elif packet_type_id == 3:
        result.update(_decode_publish(body, flags))
    elif packet_type_id == 8:
        result.update(_decode_subscribe(body))
    elif packet_type_id == 10:
        result.update(_decode_unsubscribe(body))

    return enrich(result)


def _decode_connect(body):
    offset = 0
    protocol, offset = _read_string(body, offset)
    if offset + 4 > len(body):
        raise MQTTDecodeError('truncated connect variable header')
    version = body[offset]
    connect_flags = body[offset + 1]
    keepalive = int.from_bytes(body[offset + 2:offset + 4], 'big')
    offset += 4
    client_id = ''
    if offset < len(body):
        client_id, offset = _read_string(body, offset)
    return {
        'protocol': protocol,
        'version': version,
        'connect_flags': connect_flags,
        'keepalive': keepalive,
        'client_id': client_id,
    }


def _decode_publish(body, flags):
    topic, offset = _read_string(body, 0)
    qos = (flags >> 1) & 0x03
    if qos == 3:
        raise MQTTDecodeError('invalid publish qos')
    packet_id = None
    if qos:
        if offset + 2 > len(body):
            raise MQTTDecodeError('truncated publish packet id')
        packet_id = int.from_bytes(body[offset:offset + 2], 'big')
        offset += 2
    payload = body[offset:]
    payload_text = payload.decode('utf-8', 'ignore')
    result = {
        'topic': topic,
        'qos': qos,
        'payload': payload_text,
        'payload_base64': base64.b64encode(payload).decode('ascii'),
    }
    if packet_id is not None:
        result['packet_id'] = packet_id
    return result


def _decode_subscribe(body):
    if len(body) < 2:
        raise MQTTDecodeError('truncated subscribe packet id')
    offset = 2
    topics = []
    while offset < len(body):
        topic, offset = _read_string(body, offset)
        if offset >= len(body):
            raise MQTTDecodeError('truncated subscribe qos')
        topics.append({'topic': topic, 'qos': body[offset]})
        offset += 1
    return {'packet_id': int.from_bytes(body[0:2], 'big'), 'topics': topics}


def _decode_unsubscribe(body):
    if len(body) < 2:
        raise MQTTDecodeError('truncated unsubscribe packet id')
    offset = 2
    topics = []
    while offset < len(body):
        topic, offset = _read_string(body, offset)
        topics.append(topic)
    return {'packet_id': int.from_bytes(body[0:2], 'big'), 'topics': topics}


def _payload_json(payload):
    if not payload:
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return None


def _find_keys(data, keys):
    result = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key.lower() in keys:
                result.append(value)
            result.extend(_find_keys(value, keys))
    elif isinstance(data, list):
        for item in data:
            result.extend(_find_keys(item, keys))
    return result


def enrich(record):
    text_fields = []
    topic_candidates = []
    if record.get('topic'):
        text_fields.append(record['topic'])
        topic_candidates.append(record['topic'])
    if record.get('client_id'):
        text_fields.append(record['client_id'])
    for topic in record.get('topics', []):
        if isinstance(topic, dict):
            text_fields.append(topic.get('topic', ''))
            topic_candidates.append(topic.get('topic', ''))
        else:
            text_fields.append(topic)
            topic_candidates.append(topic)
    if record.get('payload'):
        text_fields.append(record['payload'])

    markers = []
    for value in text_fields:
        if not isinstance(value, str):
            continue
        if _NCLINK_RE.search(value) and 'NC-Link' not in markers:
            markers.append('NC-Link')
        for marker in _PAYLOAD_MARKER_RE.findall(value):
            marker = marker.upper()
            if marker not in markers:
                markers.append(marker)

    payload_json = _payload_json(record.get('payload'))
    nclink_fields = {}
    if isinstance(payload_json, dict):
        for key in ['REGMSG', 'REMSG', 'PRK', 'SPSK', 'deviceId', 'machineId', 'cncId']:
            values = _find_keys(payload_json, {key.lower()})
            if values:
                value = values[0]
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
                nclink_fields[key.lower()] = str(value)
        semantic_payload = payload_json
    else:
        semantic_payload = {}

    semantics = {}
    for topic in topic_candidates or [None]:
        candidate = parse_business_semantics(
            semantic_payload,
            topic=topic,
            client_id=record.get('client_id'),
        )
        if not semantics or candidate.get('detected'):
            semantics = candidate
        if candidate.get('detected'):
            break

    if markers or nclink_fields or semantics.get('detected'):
        record['nclink_detected'] = True
        record['nclink_markers'] = markers
        record['nclink'] = nclink_fields
        if semantics:
            record['nclink_semantics'] = semantics

    return record
