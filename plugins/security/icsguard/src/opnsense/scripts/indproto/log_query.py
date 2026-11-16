#!/usr/local/bin/python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from nclink_semantics import classify_topic, operation_from_signature, payload_audit


EVE_PATH = Path(os.environ.get("INDPROTO_EVE_LOG", "/var/log/suricata/eve.json"))
MAX_LIMIT = 1000


def parse_time(value):
    value = (value or "").strip()
    if value in ("", "-"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError("invalid timestamp %r" % value)


def line_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def before(left, right):
    try:
        return left.timestamp() < right.timestamp()
    except (TypeError, OSError):
        return left.replace(tzinfo=None) < right.replace(tzinfo=None)


def after(left, right):
    try:
        return left.timestamp() > right.timestamp()
    except (TypeError, OSError):
        return left.replace(tzinfo=None) > right.replace(tzinfo=None)


def effective_protocol(row):
    """Return the product protocol before applying user-facing filters."""
    signature = ((row.get("alert") or {}).get("signature") or "").lower()
    normalized_signature = signature.replace("-", "").replace("_", "")
    if "nclink" in normalized_signature:
        return "nclink"
    for candidate in ("modbus", "dnp3", "s7comm", "iec104", "fins", "melsec", "bacnet", "opcua", "enip"):
        if candidate in normalized_signature:
            return candidate
    return (row.get("app_proto") or row.get("proto") or "").lower()


def reverse_lines(path, block_size=65536):
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        while position > 0:
            read_size = min(block_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]
            for line in reversed(lines[1:]):
                if line:
                    yield line.decode("utf-8", "replace")
        if buffer:
            yield buffer.decode("utf-8", "replace")


def match(row, args, start_time, end_time):
    event_type = row.get("event_type")
    if event_type not in ("alert", "drop"):
        return False

    alert = row.get("alert") or {}
    signature = alert.get("signature", "")
    if "IndProto" not in signature:
        return False

    if args.proto not in ("-", "all") and args.proto:
        if args.proto.lower() != effective_protocol(row):
            return False

    if args.src_ip != "-" and args.src_ip and row.get("src_ip") != args.src_ip:
        return False
    if args.dst_ip != "-" and args.dst_ip and row.get("dest_ip") != args.dst_ip:
        return False

    timestamp = line_timestamp(row.get("timestamp"))
    if start_time is not None and timestamp is not None and before(timestamp, start_time):
        return False
    if end_time is not None and timestamp is not None and after(timestamp, end_time):
        return False
    return True


def normalize_action(signature, eve_action, event_type):
    """Return the IndProto policy decision, with EVE as a fallback.

    Audited allow rules are Suricata ``alert`` signatures, so EVE's event type
    alone cannot distinguish them from log-only alerts.
    """
    upper = (signature or "").upper()
    if "[LOG_ONLY]" in upper:
        return "alert"
    if "PASS AUDIT" in upper:
        return "pass"
    if (
        " BLOCK " in " %s " % upper
        or "DEFAULT BLOCK" in upper
        or "BLOCKED FLOW GUARD" in upper
    ):
        return "drop"

    action = (eve_action or event_type or "").strip().lower()
    return {
        "allowed": "pass",
        "blocked": "drop",
        "reject": "drop",
    }.get(action, action or "alert")


def normalize(row, topic_roots=()):
    alert = row.get("alert") or {}
    signature = alert.get("signature", "")
    action = normalize_action(signature, alert.get("action"), row.get("event_type"))
    proto = effective_protocol(row)
    normalized = {
        "timestamp": row.get("timestamp", ""),
        "src_ip": row.get("src_ip", ""),
        "dest_ip": row.get("dest_ip", ""),
        "dest_port": row.get("dest_port", ""),
        "proto": proto,
        "signature": signature,
        "action": action,
        "enforcement": "blocked" if alert.get("action") == "blocked" else "observed",
    }
    mqtt = row.get("mqtt") or {}
    publish = mqtt.get("publish") or {} if isinstance(mqtt, dict) else {}
    topic = ""
    payload = None
    if isinstance(publish, dict):
        topic = publish.get("topic") or ""
        # Suricata names the MQTT PUBLISH body "message".  Accept payload as
        # well for compatibility with older/custom EVE producers.
        payload = publish.get("message")
        if payload is None:
            payload = publish.get("payload")
    if not topic and isinstance(mqtt, dict):
        topic = mqtt.get("topic") or ""
        payload = payload if payload is not None else mqtt.get("payload")
    semantics = classify_topic(topic, topic_roots)
    if not semantics and proto == "nclink":
        semantics["nclink_operation"] = operation_from_signature(signature)
    normalized.update(semantics)
    normalized.update(payload_audit(payload))
    return normalized


def query(args):
    limit = max(1, min(args.limit, MAX_LIMIT))
    start_time = parse_time(args.start_time)
    end_time = parse_time(args.end_time)
    result = []
    if not EVE_PATH.exists():
        return result

    from generate_rules import load_config, text
    try:
        topic_roots = [text(n, "nclink_topic_root") for n in load_config(None).findall("./rules/rule")
                       if text(n, "protocol") == "nclink" and text(n, "nclink_topic_root")]
    except (OSError, ValueError):
        topic_roots = []

    for line in reverse_lines(EVE_PATH):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if match(row, args, start_time, end_time):
            result.append(normalize(row, topic_roots))
            if len(result) >= limit:
                break
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proto", default="-")
    parser.add_argument("--src_ip", default="-")
    parser.add_argument("--dst_ip", default="-")
    parser.add_argument("--start_time", default="-")
    parser.add_argument("--end_time", default="-")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    try:
        print(json.dumps(query(args)))
        return 0
    except Exception as exc:
        print("indproto log query failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
