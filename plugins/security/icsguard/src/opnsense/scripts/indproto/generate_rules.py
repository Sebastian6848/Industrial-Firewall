#!/usr/local/bin/python3

import importlib
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, time
from pathlib import Path

from resolution import PolicyValueResolver
from protocols import PROFILES


DEFAULT_CONFIG_PATH = Path("/conf/config.xml")
LEGACY_CONFIG_PATH = Path("/usr/local/etc/OPNsense/IndProto/IndProto.xml")
CONFIG_PATH = Path(os.environ["INDPROTO_CONFIG"]) if "INDPROTO_CONFIG" in os.environ else None
RULES_PATH = Path(os.environ.get(
    "INDPROTO_RULES",
    "/usr/local/etc/suricata/rules/indproto.rules",
))
CRON_PATH = Path(os.environ.get("INDPROTO_CRON", "/etc/cron.d/indproto"))

SID_RANGES = {
    "modbus": 1000000,
    "nclink": 2000000,
    "dnp3": 3000000,
    "s7comm": 4000000,
    "mqtt": 5000000,
    "enip": 6000000,
    "iec104": 7000000,
    "fins": 8000000,
    "melsec": 11000000,
    "bacnet": 12000000,
    "opcua": 13000000,
}
DEFAULT_BLOCK_SID = 9990000
PROTOCOLS = tuple(SID_RANGES.keys())


def text(node, name, default=""):
    found = node.find(name)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def is_enabled(value):
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_config(path):
    if path is None:
        path = DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError("%s not found" % path)
    root = ET.parse(path).getroot()
    indproto = root if root.tag == "IndProto" else root.find("./OPNsense/IndProto")
    if indproto is None:
        indproto = root.find("./IndProto")
    if indproto is None:
        indproto = root.find(".//IndProto")
    if indproto is None:
        raise ValueError("missing <IndProto> configuration node")
    return indproto


def parse_clock(value):
    if value == "":
        return None
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    except ValueError as exc:
        raise ValueError("invalid time range value %r, expected HH:MM" % value) from exc


def in_time_range(start_value, end_value, now=None):
    start = parse_clock(start_value)
    end = parse_clock(end_value)
    if start is None and end is None:
        return True

    current = (now or datetime.now()).time()
    if start is None:
        return current <= end
    if end is None:
        return current >= start
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def node_to_rule(node, rule_index):
    protocol = text(node, "protocol", "modbus").lower()
    if protocol not in PROTOCOLS:
        raise ValueError("unsupported protocol %r in rule %d" % (protocol, rule_index))

    rule = {"uuid": node.get("uuid", "")}
    for name in (
        "enabled",
        "description",
        "protocol",
        "src_ip",
        "dst_ip",
        "dst_port",
        "action",
        "access",
        "function_codes",
        "modbus_function_codes",
        "dnp3_function_codes",
        "dnp3_object_group",
        "modbus_unit_id",
        "time_range_start",
        "time_range_end",
        "log_only",
        "mqtt_allow_connect",
        "mqtt_operations",
        "mqtt_topic",
        "mqtt_client_id",
        "mqtt_username",
        "mqtt_qos",
        "mqtt_tls",
        "nclink_operations",
        "nclink_device_uuid",
        "nclink_endpoint",
        "nclink_direction",
        "nclink_packets",
        "nclink_topic_root",
        "nclink_subscribe_filters",
        "protocol_operations",
        "enip_services",
    ):
        rule[name] = text(node, name, "")
    rule["mqtt_operations_present"] = node.find("mqtt_operations") is not None
    rule["protocol"] = protocol
    return rule


def update_cron(time_rules_present):
    if not time_rules_present:
        if CRON_PATH.exists():
            CRON_PATH.unlink()
        return False

    content = (
        "SHELL=/bin/sh\n"
        "PATH=/etc:/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin\n"
        "* * * * * root /usr/local/sbin/configctl indproto reload\n"
    )
    CRON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CRON_PATH.exists() or CRON_PATH.read_text() != content:
        CRON_PATH.write_text(content)
        return True
    return False


def default_block_rules(enabled_protocols, default_action, allocated_sids):
    if default_action != "block":
        return []

    result = []
    for index, protocol in enumerate(sorted(enabled_protocols)):
        if protocol in PROFILES:
            continue
        module = importlib.import_module("generators.%s" % protocol)
        if getattr(module, "MANAGES_DEFAULT_POLICY", False):
            continue
        if hasattr(module, "default_block"):
            sid = DEFAULT_BLOCK_SID + index
            if sid in allocated_sids:
                raise ValueError("duplicate generated sid %d" % sid)
            allocated_sids.add(sid)
            result.extend(module.default_block(sid, default_action))
    return result


def validate_unique_sids(rules):
    seen = set()
    for rule in rules:
        marker = "sid:"
        start = rule.find(marker)
        if start < 0:
            raise ValueError("generated rule has no sid: %s" % rule)
        end = rule.find(";", start)
        sid = int(rule[start + len(marker):end], 10)
        if sid in seen:
            raise ValueError("duplicate generated sid %d" % sid)
        seen.add(sid)
    return seen


def render_rules(indproto):
    general = indproto.find("general")
    if general is None:
        raise ValueError("missing <general> configuration node")

    default_action = text(general, "default_action", "pass").lower()
    if default_action not in ("pass", "block"):
        raise ValueError("unsupported default_action %r" % default_action)

    rules = []
    config_file = CONFIG_PATH or (DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else LEGACY_CONFIG_PATH)
    resolver = PolicyValueResolver(config_file)
    configured_protocols = set()
    next_sid = dict(SID_RANGES)
    time_rules_present = False
    policy_rules = {protocol: [] for protocol in PROTOCOLS}
    for rule_index, node in enumerate(indproto.findall("./rules/rule")):
        if not is_enabled(text(node, "enabled", "0")):
            continue

        rule = node_to_rule(node, rule_index)
        rule["src_ip"] = resolver.address(rule["src_ip"])
        rule["dst_ip"] = resolver.address(rule["dst_ip"])
        rule["dst_port"] = resolver.port(rule["dst_port"])
        configured_protocols.add(rule["protocol"])
        has_time_range = bool(rule["time_range_start"] or rule["time_range_end"])
        time_rules_present = time_rules_present or has_time_range
        active_now = not has_time_range or in_time_range(rule["time_range_start"], rule["time_range_end"])
        if rule["protocol"] in policy_rules:
            rule["_active"] = active_now
            policy_rules[rule["protocol"]].append(rule)
            continue
        if not active_now:
            continue

        rule["sid_base"] = next_sid[rule["protocol"]]
        module = importlib.import_module("generators.%s" % rule["protocol"])
        generated = module.generate(rule_index, rule)
        if generated:
            rules.extend(generated)
            next_sid[rule["protocol"]] += len(generated)

    for protocol, scoped_rules in policy_rules.items():
        if scoped_rules:
            if protocol in PROFILES:
                from generators.extended import generate_policy
                generated = generate_policy(protocol, scoped_rules, next_sid[protocol], default_action)
            else:
                module = importlib.import_module("generators.%s" % protocol)
                generated = module.generate_policy(scoped_rules, next_sid[protocol], default_action)
            rules.extend(generated)
            next_sid[protocol] += len(generated)

    allocated_sids = validate_unique_sids(rules)
    rules.extend(default_block_rules(configured_protocols, default_action, allocated_sids))
    validate_unique_sids(rules)
    return rules, configured_protocols, time_rules_present


def write_rules(rules):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RULES_PATH.with_name(".%s.tmp" % RULES_PATH.name)
    temporary.write_text("\n".join(rules) + ("\n" if rules else ""))
    temporary.replace(RULES_PATH)


def main():
    try:
        indproto = load_config(CONFIG_PATH)
        general = indproto.find("general")
        if general is None:
            raise ValueError("missing <general> configuration node")

        if not is_enabled(text(general, "enabled", "0")):
            write_rules([])
            update_cron(False)
            print("generated 0 indproto rules")
            return 0

        rules, _protocols, time_rules_present = render_rules(indproto)
        write_rules(rules)
        cron_updated = update_cron(time_rules_present)
        suffix = ""
        if cron_updated:
            suffix += " and updated cron"
        print("generated %d indproto rules%s" % (len(rules), suffix))
        return 0
    except Exception as exc:
        print("indproto rule generation failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
