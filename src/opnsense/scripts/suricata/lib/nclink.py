"""
    Copyright (c) 2026
    All rights reserved.

    Helper functions to enrich Suricata EVE MQTT records with NC-Link
    application metadata.
"""

import base64
import json
import os
import re
import sys

SITE_PYTHON = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'site-python'))
if SITE_PYTHON not in sys.path:
    sys.path.insert(0, SITE_PYTHON)

from nclink_semantics import parse_business_semantics


_NCLINK_RE = re.compile(r'nc[-_ ]?link', re.IGNORECASE)
_PAYLOAD_MARKER_RE = re.compile(r'\b(REGMSG|REMSG|PRK|SPSK)\b', re.IGNORECASE)


def _decode_payload(value):
    if not isinstance(value, str):
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
        if decoded:
            return decoded.decode('utf-8', 'ignore')
    except Exception:
        pass
    return value


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


def _string_values(values):
    result = []
    for value in values:
        if isinstance(value, str) and value != '':
            result.append(value)
        elif isinstance(value, (int, float)):
            result.append(str(value))
    return result


def _json_payload(value):
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def enrich(record):
    mqtt = record.get('mqtt')
    if not isinstance(mqtt, dict):
        return record

    topics = _string_values(_find_keys(mqtt, {'topic'}))
    client_ids = _string_values(_find_keys(mqtt, {'client_id', 'clientid'}))
    payloads = []
    for key in {'message', 'payload', 'payload_printable', 'payload_base64'}:
        payloads.extend(_string_values(_find_keys(mqtt, {key})))
    payloads = [_decode_payload(payload) for payload in payloads]
    payloads = [payload for payload in payloads if payload]

    text_fields = topics + client_ids + payloads
    markers = []
    for value in text_fields:
        if _NCLINK_RE.search(value) and 'NC-Link' not in markers:
            markers.append('NC-Link')
        for marker in _PAYLOAD_MARKER_RE.findall(value):
            marker = marker.upper()
            if marker not in markers:
                markers.append(marker)

    json_fields = {}
    semantics = {}
    for payload in payloads:
        payload_json = _json_payload(payload)
        if isinstance(payload_json, dict):
            for key in ['REGMSG', 'REMSG', 'PRK', 'SPSK', 'deviceId', 'machineId', 'cncId']:
                for value in _find_keys(payload_json, {key.lower()}):
                    if isinstance(value, (str, int, float)):
                        json_fields[key] = str(value)
            parsed_semantics = parse_business_semantics(
                payload_json,
                topic=topics[0] if topics else None,
                client_id=client_ids[0] if client_ids else None,
            )
            if parsed_semantics:
                semantics = parsed_semantics

    if not semantics:
        semantics = parse_business_semantics(
            {},
            topic=topics[0] if topics else None,
            client_id=client_ids[0] if client_ids else None,
        )

    if markers or any(_NCLINK_RE.search(value) for value in topics + client_ids) or semantics.get('detected'):
        record['nclink_detected'] = True
        if topics:
            record['nclink_topic'] = topics[0]
        if client_ids:
            record['nclink_client_id'] = client_ids[0]
        if markers:
            record['nclink_markers'] = ','.join(markers)
        for key, value in json_fields.items():
            record['nclink_%s' % key.lower()] = value
        if semantics:
            record['nclink_semantics'] = semantics
            if semantics.get('message_types'):
                record['nclink_message_types'] = ','.join(semantics['message_types'])
            if semantics.get('message_class'):
                record['nclink_message_class'] = semantics['message_class']
            if semantics.get('interface', {}).get('name'):
                record['nclink_interface'] = semantics['interface']['name']
            if semantics.get('timestamp'):
                record['nclink_timestamp'] = semantics['timestamp']
            if semantics.get('sequence'):
                record['nclink_sequence'] = semantics['sequence']
            for key, value in semantics.get('identities', {}).items():
                record['nclink_%s' % key] = value
            if semantics.get('data_points'):
                record['nclink_data_points'] = len(semantics['data_points'])
            if semantics.get('alarms'):
                record['nclink_alarms'] = len(semantics['alarms'])

    return record
