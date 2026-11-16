#!/usr/local/bin/python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline engine test of all new protocol policies and full NC-Link topics."""

import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_rules
from replay_transactions import Capture, checksum, mqtt_publish


def enip(command, service=14, response=False):
    if command == 101:
        body = struct.pack("<HH", 1, 0)
    elif command in (4, 99, 102):
        body = b""
    else:
        cip = (
            bytes([service | 128, 0, 0, 0])
            if response
            else bytes([service, 3, 0x20, 1, 0x24, 1, 0x30, 1])
        )
        body = struct.pack("<IHHHHHH", 0, 0, 2, 0, 0, 0xB2, len(cip)) + cip
    return (
        struct.pack(
            "<HHII8sI",
            command,
            len(body),
            1 if command != 101 or response else 0,
            0,
            b"\0" * 8,
            0,
        )
        + body
    )


def iec(code):
    asdu = bytes([code, 1, 6, 0, 1, 0, 0, 0, 0, 20 if code == 100 else 1])
    return bytes([0x68, len(asdu) + 4]) + b"\0" * 4 + asdu


def fins(command):
    body = (
        bytes.fromhex("80000200010000020001")
        + int(command, 16).to_bytes(2, "big")
        + bytes.fromhex("820000000001")
    )
    if command == "0102":
        body += b"\x00\x01"
    return b"FINS" + struct.pack("!III", len(body) + 8, 2, 0) + body


def melsec(command):
    body = (
        b"\x08\0"
        + int(command, 16).to_bytes(2, "little")
        + b"\0\0"
        + bytes.fromhex("0a0000a80100")
    )
    if command == "1401":
        body += b"\x01\0"
    return bytes.fromhex("500000ffff0300") + struct.pack("<H", len(body)) + body


def ua(code):
    endpoint = b"opc.tcp://198.18.230.10:4840"
    body = (
        struct.pack("<IIIII", 0, 65536, 65536, 0, 0)
        + struct.pack("<I", len(endpoint))
        + endpoint
        if code == "HEL"
        else b"\0" * 16
    )
    return code.encode() + b"F" + struct.pack("<I", len(body) + 8) + body


def bacnet(service=12, function=10):
    body = bytes([1, 4, 0, 5, 1, service]) + bytes.fromhex("0c000000011955")
    return bytes([0x81, function]) + struct.pack("!H", len(body) + 4) + body


def udp(capture, sport, dport, payload):
    ips = socket.inet_aton("198.18.231.10")
    ipd = socket.inet_aton("198.18.230.10")
    datagram = struct.pack("!HHHH", sport, dport, len(payload) + 8, 0) + payload
    ip = struct.pack(
        "!BBHHHBBH4s4s", 0x45, 0, len(datagram) + 20, 1, 0, 64, 17, 0, ips, ipd
    )
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    packet = bytes.fromhex("00112233445566778899aabb0800") + ip + datagram
    capture.stream.write(
        struct.pack("<IIII", capture.time, 0, len(packet), len(packet)) + packet
    )
    capture.time += 1


def subscribe(topic):
    body = b"\0\1"
    for item in topic if isinstance(topic, list) else [topic]:
        value = item.encode()
        body += struct.pack("!H", len(value)) + value + b"\0"
    return b"\x82" + bytes([len(body)]) + body


def run(directory):
    directory.mkdir(parents=True, exist_ok=True)
    config = ET.fromstring(
        "<IndProto><general><enabled>1</enabled><default_action>block</default_action></general><rules/></IndProto>"
    )
    entries = [
        ("enip", 44818, {"protocol_operations": "101,111", "enip_services": "14"}),
        ("iec104", 2404, {"protocol_operations": "100"}),
        ("fins", 9600, {"protocol_operations": "0101"}),
        ("melsec", 5000, {"protocol_operations": "0401"}),
        ("bacnet", 47808, {"protocol_operations": "c12"}),
        ("opcua", 4840, {"protocol_operations": "HEL,OPN"}),
        (
            "nclink",
            1885,
            {
                "nclink_operations": "data_query,sample,method_call",
                "nclink_device_uuid": "machine-01",
                "nclink_endpoint": "app-01",
                "nclink_direction": "both",
                "nclink_packets": "both",
            },
        ),
        ("nclink", 1886, {
            "nclink_operations": "sample,state_notify,discovery",
            "nclink_device_uuid": "machine-01", "nclink_topic_root": "factory/nclink",
            "nclink_direction": "both", "nclink_packets": "both",
        }),
        ("nclink", 1887, {
            "nclink_operations": "sample", "nclink_topic_root": "factory/nclink",
            "nclink_packets": "both", "nclink_subscribe_filters": "Probe/#,Sample/#",
        }),
    ]
    for protocol, port, extras in entries:
        node = ET.SubElement(config.find("rules"), "rule")
        for key, value in dict(
            enabled="1",
            description="extended_review",
            protocol=protocol,
            src_ip="any",
            dst_ip="any",
            dst_port=str(port),
            action="pass",
            access="read",
            **extras
        ).items():
            ET.SubElement(node, key).text = value
    rules, _, _ = generate_rules.render_rules(config)
    (directory / "policy.rules").write_text("\n".join(rules) + "\n")
    capture = Capture(directory / "extended.pcap")
    allowed = set()
    blocked = set()

    def flow(port, dest, requests, deny=False, responses=None):
        capture.flow(port, dest, requests, responses)
        (blocked if deny else allowed).add(port)

    register = enip(101)
    response = enip(101, response=True)
    flow(
        42001,
        44818,
        [register, enip(111, 14)],
        responses={0: response, 1: enip(111, 14, True)},
    )
    flow(
        42002,
        44818,
        [register, enip(111, 14), enip(111, 16)],
        True,
        {0: response, 1: enip(111, 14, True)},
    )
    flow(
        42003,
        44818,
        [register, enip(111, 14)[:12], enip(111, 14)[12:], enip(111, 16)],
        True,
        {0: response},
    )
    flow(42004, 44818, [register, enip(102)], True, {0: response})
    flow(42005, 44818, [register, enip(99)], True, {0: response})
    for index, (dest, good, bad) in enumerate(
        [
            (2404, iec(100), iec(45)),
            (9600, fins("0101"), fins("0102")),
            (5000, melsec("0401"), melsec("1401")),
            (4840, ua("HEL"), ua("MSG")),
        ]
    ):
        base = 42100 + index * 10
        flow(base, dest, [good])
        flow(base + 1, dest, [good, bad], True)
        flow(base + 2, dest, [good + bad], True)
        flow(base + 3, dest, [good[:3], good[3:], bad[:2], bad[2:]], True)
    udp(capture, 42200, 47808, bacnet())
    allowed.add(42200)
    udp(capture, 42201, 47808, bacnet(15))
    blocked.add(42201)
    udp(capture, 42202, 47808, bacnet(12, 11))
    allowed.add(42202)
    udp(capture, 42203, 47808, bytes.fromhex("810a000a012400000000"))
    blocked.add(42203)
    connect = bytes.fromhex("100f00044d5154540402003c00036e632d")
    connack = b"\x20\x02\0\0"
    for port, topic, deny, sub in [
        (42300, "Query/Request/machine-01/app-01", False, False),
        (42301, "Query/Response/machine-01/app-01", False, False),
        (42302, "Sample/machine-01/app-01", False, False),
        (42303, "Query/Request/machine-01/other-app", True, False),
        (42304, "Query/Request/other-machine/app-01", True, False),
        (42305, "Method/Control/Request/machine-01/app-01", True, False),
        (42306, "Method/Call/machine-01/app-01", False, False),
        (42307, "Sample/+/+", True, True),
        (42308, "Sample/machine-01/app-01", False, True),
        (42309, "Unknown/machine-01/app-01", True, False),
        (42310, "Sample/machine-01/app-01/extra", True, False),
        (42311, ["Sample/machine-01/app-01", "#"], True, True),
        (42313, "Sample/machine-01", True, False),
    ]:
        flow(
            port,
            1885,
            [connect, subscribe(topic) if sub else mqtt_publish(topic)],
            deny,
            {0: connack},
        )
    flow(
        42312,
        1885,
        [
            connect,
            mqtt_publish("Sample/machine-01/app-01")
            + mqtt_publish("Unknown/machine-01/app-01"),
        ],
        True,
        {0: connack},
    )
    for port, dest, topic, deny, sub in [
        (42400,1886,'factory/nclink/Sample/machine-01/c0',False,False),
        (42401,1886,'factory/nclink/Notify/State/machine-01',False,False),
        (42402,1886,'factory/nclink/Discovery/Request/machine-01',False,False),
        (42403,1886,'factory/nclink/Discovery/Response/machine-01',False,False),
        (42404,1886,'Sample/machine-01/c0',True,False),
        (42405,1886,'other/nclink/Sample/machine-01/c0',True,False),
        (42406,1886,'factory/nclink/Notify/State/other',True,False),
        (42407,1886,'factory/nclink/Sample/+/+',True,True),
        (42408,1887,'factory/nclink/Probe/#',False,True),
        (42409,1887,'factory/nclink/Sample/#',False,True),
        (42410,1887,'factory/nclink/Probe/Query/Request/machine-01',True,False),
        (42411,1887,'factory/nclink/#',True,True),
        (42412,1887,['factory/nclink/Probe/#','factory/nclink/#'],True,True),
    ]:
        flow(port,dest,[connect,subscribe(topic) if sub else mqtt_publish(topic)],deny,{0:connack})
    capture.stream.close()
    yaml = """%YAML 1.1
---
vars:
  address-groups:
    HOME_NET: "any"
    EXTERNAL_NET: "any"
outputs:
  - eve-log:
      enabled: yes
      filetype: regular
      filename: eve.json
      types: [alert, drop, flow]
stream:
  checksum-validation: no
  reassembly:
    depth: 0
app-layer:
  protocols:
    enip:
      enabled: yes
      detection-ports:
        dp: "[44818]"
    mqtt:
      enabled: yes
      detection-ports:
        dp: "[1885,1886,1887]"
"""
    (directory / "suricata.yaml").write_text(yaml)
    result = subprocess.run(
        [
            "suricata",
            "-c",
            str(directory / "suricata.yaml"),
            "-S",
            str(directory / "policy.rules"),
            "-r",
            str(directory / "extended.pcap"),
            "-l",
            str(directory),
            "--runmode",
            "single",
            "--simulate-ips",
            "--init-errors-fatal",
        ],
        capture_output=True,
        text=True,
        timeout=90,
    )
    (directory / "engine.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    alerts = [
        json.loads(line) for line in (directory / "eve.json").read_text().splitlines()
    ]
    actual = {
        r.get("src_port")
        for r in alerts
        if r.get("alert", {}).get("action") == "blocked"
    }
    report = {
        "rules": len(rules),
        "blocked": sorted(actual),
        "missing_blocks": sorted(blocked - actual),
        "false_blocks": sorted(allowed & actual),
        "allowed_controls": sorted(allowed),
    }
    (directory / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    assert not blocked - actual, "A forbidden transaction was not detected"
    assert not allowed & actual, "A permitted transaction was incorrectly blocked"
    print(
        "PASS: six new protocols and full NC-Link topics; split/coalesced/reused TCP and UDP controls",
        flush=True,
    )


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
