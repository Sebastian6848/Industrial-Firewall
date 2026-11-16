"""Normalize standard NC-Link MQTT topics and small, safe JSON audit fields."""

import json


from generators.nclink import FAMILIES, topic_root

TOPIC_FAMILIES = tuple(sorted(
    ((op,kind,prefix) for op,items in FAMILIES.items() for kind,prefix in items),
    key=lambda item: len(item[2]), reverse=True))

SIGNATURE_OPERATIONS = {
    "REGISTER": "register",
    "VERSION_PROBE": "version_probe",
    "MODEL_QUERY": "model_query",
    "MODEL_SET": "model_set",
    "DATA_QUERY": "data_query",
    "DATA_SET": "data_set",
    "SAMPLE_REGISTER": "sample_register",
    "SAMPLE_UNREGISTER": "sample_unregister",
    "SAMPLE": "sample",
    **{name.upper(): name for name in FAMILIES},
}


def classify_topic(topic, topic_roots=()):
    if not isinstance(topic, str) or not topic:
        return {}
    # Only strip roots explicitly configured by an administrator. Prefer the
    # longest root; never treat an arbitrary vendor prefix as NC-Link.
    original_topic = topic
    matched_root = ""
    for root in sorted(set(topic_roots), key=len, reverse=True):
        root = topic_root(root)
        if root and topic.startswith(root + "/"):
            matched_root, topic = root, topic[len(root) + 1:]
            break
    for operation, direction, prefix in TOPIC_FAMILIES:
        if prefix.endswith("/"):
            if not topic.startswith(prefix):
                continue
            parts = topic[len(prefix):].split('/')
            if not 1 <= len(parts) <= 2 or any(not p or any(c in p for c in ('+','#','\x00')) for p in parts):
                continue
            device_uuid = parts[0]
            endpoint = parts[1] if len(parts) == 2 else ''
            if operation == 'version_probe' and direction == 'request' and device_uuid == 'Response':
                continue
        elif topic == prefix:
            device_uuid = ""
            endpoint = ""
        else:
            continue
        return {
            "nclink_operation": operation,
            "nclink_direction": direction,
            "nclink_device_uuid": device_uuid,
            "nclink_topic": original_topic,
            "nclink_topic_root": matched_root,
            "nclink_endpoint": endpoint,
        }
    return {}


def operation_from_signature(signature):
    upper = (signature or "").upper()
    if "NC-LINK" not in upper:
        return ""
    # Longest names first so SAMPLE does not consume SAMPLE_REGISTER.
    for marker in sorted(SIGNATURE_OPERATIONS, key=len, reverse=True):
        if marker in upper:
            return SIGNATURE_OPERATIONS[marker]
    return ""


def _first_string(data, names, depth=0):
    if depth > 8:
        return ""
    if isinstance(data, dict):
        for key, value in list(data.items())[:128]:
            if str(key).lower() in names and isinstance(value, (str, int, float)):
                return str(value)[:256]
        for value in list(data.values())[:128]:
            found = _first_string(value, names, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for value in data[:128]:
            found = _first_string(value, names, depth + 1)
            if found:
                return found
    return ""


def payload_audit(payload):
    if not payload:
        return {}
    if isinstance(payload, str):
        if len(payload) > 1048576:
            return {}
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, RecursionError):
            return {}
    if not isinstance(payload, (dict, list)):
        return {}
    result = {
        key: value for key, value in {
            "nclink_request_id": _first_string(
                payload, {"requestid", "request_id", "messageid", "message_id"}
            ),
            "nclink_pdu_operation": _first_string(
                payload, {"operation", "method", "action", "command"}
            ),
            "nclink_object_id": _first_string(
                payload, {"objectid", "object_id", "dataitemid", "data_item_id"}
            ),
            "nclink_result": _first_string(
                payload, {"result", "resultcode", "result_code", "code"}
            ),
        }.items() if value
    }
    if isinstance(payload, dict):
        def scalar(value):
            return str(value)[:256] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""
        for field, names in {
            "nclink_request_id": ("@id", "requestId", "request_id"),
            "nclink_payload_device_uuid": ("guid", "cli_uuid", "dev_uuid"),
            "nclink_channel_id": ("id",),
            "nclink_sample_time": ("timestamp", "startTime", "beginTime"),
        }.items():
            for name in names:
                value = scalar(payload.get(name))
                if value:
                    result[field] = value
                    break
        objects = []
        for key in ("ids", "values", "results"):
            entries = payload.get(key)
            if isinstance(entries, list):
                for entry in entries[:32]:
                    value = scalar(entry.get("id")) if isinstance(entry, dict) else scalar(entry)
                    if value and value not in objects:
                        objects.append(value)
        if objects:
            result["nclink_object_id"] = ",".join(objects)[:1024]
    return result
