# SPDX-License-Identifier: BSD-2-Clause
"""Scoped command policies; raw signatures are explicitly labelled BETA.

TCP signatures search reassembled stream data, including coalesced messages.
They do not replace complete protocol parsers or validate arbitrary frame bodies.
"""

from collections import defaultdict
from generators import build, header, msg
from protocols import PROFILES


def codes(protocol, rule):
    profile = PROFILES[protocol]
    value = (rule.get("protocol_operations") or "").strip()
    if value:
        result = list(
            dict.fromkeys(part.strip() for part in value.split(",") if part.strip())
        )
    else:
        access = rule.get("access") or "readwrite"
        if access not in ("read", "write", "readwrite"):
            raise ValueError("invalid operation preset")
        result = (
            list(dict.fromkeys(profile["read"] + profile["write"]))
            if access == "readwrite"
            else profile[access]
        )
    if not result or set(result) - profile["operations"].keys():
        raise ValueError("unsupported %s operation codes: %s" % (protocol, value))
    return result


def encoded(value):
    return "".join(r"\x%02x" % byte for byte in value)


def signature(protocol, selected, negate=False):
    selected = sorted(selected)
    if protocol == "iec104":
        even = "[" + "".join(r"\x%02x" % n for n in range(0, 256, 2)) + "]"
        prefix = r"\x68[\x0a-\xfd]" + even + r".{3}"
        magic = "68"
        values = [encoded(bytes([int(code)])) for code in selected]
        suffix = r".{5}"
    elif protocol == "fins":
        prefix = r"FINS.{4}\x00\x00\x00\x02\x00{4}[\x80-\xbf].{9}"
        magic = "46 49 4e 53"
        values = [encoded(int(code, 16).to_bytes(2, "big")) for code in selected]
        suffix = ""
    elif protocol == "melsec":
        prefix = r"\x50\x00.{9}"
        magic = "50 00"
        values = [encoded(int(code, 16).to_bytes(2, "little")) for code in selected]
        suffix = r".{2}"
    elif protocol == "opcua":
        prefix = ""
        magic = None
        values = selected
        suffix = r"[FCA].{4}"
    else:
        raise ValueError("no raw signature for " + protocol)
    union = "(?:" + "|".join(values) + ")" if values else "(?!)"
    # A lookahead binds the denial to this frame's command, rather than allowing
    # an earlier permitted command to mask a forbidden coalesced request.
    if negate:
        width = {"iec104": 1, "fins": 2, "melsec": 2, "opcua": 3}[protocol]
        command = (
            "(?!"
            + union
            + ")"
            + ("[A-Z]{3}" if protocol == "opcua" else ".{%d}" % width)
        )
    else:
        command = union
    options = ["flow:to_server,established"]
    if magic:
        options += ['content:"|%s|"' % magic]
    options += ['pcre:"/%s%s%s/s"' % (prefix, command, suffix)]
    return options


def bacnet_signature(selected, negate=False):
    # BVLC Original-Unicast/Broadcast + local NPDU only. Deny unsupported
    # routing/segmentation layouts instead of accidentally authorizing them.
    prefix = r"\x81[\x0a\x0b].{2}\x01[\x00\x04]"
    choices = []
    for code in sorted(selected):
        if code.startswith("c"):
            choices.append(r"[\x00-\x03].{2}" + encoded(bytes([int(code[1:])])))
        else:
            choices.append(r"\x10" + encoded(bytes([int(code[1:])])))
    allowed = prefix + "(?:" + "|".join(choices) + ")" if choices else "(?!)"
    regex = "^" + ("(?!(?:" + allowed + "))" + r"\x81" if negate else allowed)
    return ['content:"|81|"; offset:0; depth:1', 'pcre:"/%s/s"' % regex]


def ranges_missing(allowed, maximum):
    start = 0
    for value in sorted(set(allowed)):
        if start < value:
            yield start, value - 1
        start = value + 1
    if start <= maximum:
        yield start, maximum


def enip_command(value):
    return [
        "flow:to_server,established",
        "app-layer-protocol:enip",
        "enip_command:%s" % value,
    ]


def enip_entries(scoped, sid, default_action):
    result = []
    allowed_commands = set()
    allowed_services = defaultdict(set)
    for rule in scoped:
        if not rule.get("_active"):
            continue
        commands = [int(x) for x in codes("enip", rule)]
        raw = (rule.get("enip_services") or "").strip()
        services = (
            [int(x.strip()) for x in raw.split(",") if x.strip()]
            if raw
            else (
                [1, 3, 14, 76]
                if rule.get("access") == "read"
                else (
                    [2, 4, 16, 77]
                    if rule.get("access") == "write"
                    else [1, 2, 3, 4, 14, 16, 76, 77]
                )
            )
        )
        if any(not 0 <= value <= 127 for value in services):
            raise ValueError("CIP services must be decimal 0..127")
        log_only = rule.get("log_only") in ("1", "true", "yes", "on")
        act = "drop" if rule.get("action") == "block" and not log_only else "alert"
        if rule.get("action", "pass") == "pass" and not log_only:
            allowed_commands.update(commands)
            for command in commands:
                allowed_services[command].update(services)
        for command in commands:
            for service in services if command in (111, 112) else [None]:
                opts = enip_command(command) + (
                    ["cip_service:%d" % service] if service is not None else []
                )
                result.append(
                    (
                        rule,
                        act,
                        opts,
                        "ENIP command %d%s"
                        % (
                            command,
                            (" CIP %d" % service) if service is not None else "",
                        ),
                    )
                )
    if default_action == "block":
        for lo, hi in ranges_missing(allowed_commands, 65535):
            opts = ["flow:to_server,established", "app-layer-protocol:enip"]
            opts += (
                ["enip_command:%d" % lo]
                if lo == hi
                else (["enip_command:>%d" % (lo - 1)] if lo else [])
                + (["enip_command:<%d" % (hi + 1)] if hi < 65535 else [])
            )
            result.append((None, "drop", opts, "ENIP default BLOCK command"))
        for command in allowed_commands & {111, 112}:
            for service in sorted(set(range(128)) - allowed_services[command]):
                result.append(
                    (
                        None,
                        "drop",
                        enip_command(command) + ["cip_service:%d" % service],
                        "ENIP default BLOCK CIP %d" % service,
                    )
                )
    return result


def generate_policy(protocol, rules, sid_base, default_action):
    profile = PROFILES[protocol]
    transport = profile["transport"]
    grouped = defaultdict(list)
    for rule in rules:
        # Blank port keeps the legacy explicit any-port semantics; defaults are offered in the UI.
        grouped[header(rule, transport, profile["port"])].append(rule)
    result = []
    sid = sid_base
    for scope, scoped in grouped.items():
        entries = []
        if protocol == "enip":
            entries = enip_entries(scoped, sid, default_action)
        else:
            allowed = set()
            for rule in scoped:
                if not rule.get("_active"):
                    continue
                selected = codes(protocol, rule)
                audit = rule.get("log_only") in ("1", "true", "yes", "on")
                act = "drop" if rule.get("action") == "block" and not audit else "alert"
                if rule.get("action", "pass") == "pass" and not audit:
                    allowed.update(selected)
                opts = (
                    bacnet_signature(selected)
                    if protocol == "bacnet"
                    else signature(protocol, selected)
                )
                entries.append(
                    (rule, act, opts, profile["name"] + " " + ",".join(selected))
                )
            if default_action == "block":
                opts = (
                    bacnet_signature(allowed, True)
                    if protocol == "bacnet"
                    else signature(protocol, allowed, True)
                )
                entries.append((None, "drop", opts, profile["name"] + " default BLOCK"))
        for rule, act, opts, label in entries:
            if rule is None:
                message = "IndProto " + protocol + " " + label
            else:
                message = msg(
                    rule,
                    (
                        "BLOCK "
                        if act == "drop"
                        else (
                            "LOG_ONLY "
                            if rule.get("log_only") in ("1", "true", "yes", "on")
                            else "PASS AUDIT "
                        )
                    )
                    + protocol
                    + " "
                    + label,
                )
            result.append(build(act, transport, *scope, message, sid, opts))
            sid += 1
    return result
