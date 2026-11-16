#!/usr/local/bin/python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline Suricata IPS regression: real protocol bytes, segmentation and reuse.

No live interface or firewall settings are changed. Requires installed Suricata.
"""
import importlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_rules


def checksum(data):
    data += b'\0' if len(data) % 2 else b''
    total = sum(struct.unpack('!%dH' % (len(data) // 2), data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


class Capture:
    def __init__(self, path):
        self.stream = path.open('wb')
        self.stream.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        self.time = 1700000000

    def packet(self, source_port, dest_port, seq, ack, flags, payload=b'', reverse=False):
        source, dest = ('198.18.231.10', '198.18.230.10') if not reverse else ('198.18.230.10', '198.18.231.10')
        sport, dport = (source_port, dest_port) if not reverse else (dest_port, source_port)
        ips, ipd = socket.inet_aton(source), socket.inet_aton(dest)
        tcp = struct.pack('!HHIIBBHHH', sport, dport, seq, ack, 0x50, flags, 65535, 0, 0)
        pseudo = ips + ipd + struct.pack('!BBH', 0, 6, len(tcp) + len(payload))
        tcp = tcp[:16] + struct.pack('!H', checksum(pseudo + tcp + payload)) + tcp[18:]
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 40 + len(payload), 1, 0, 64, 6, 0, ips, ipd)
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        packet = bytes.fromhex('00112233445566778899aabb0800') + ip + tcp + payload
        self.stream.write(struct.pack('<IIII', self.time, 0, len(packet), len(packet)) + packet)
        self.time += 1

    def flow(self, sport, dport, requests, server_responses=None):
        self.packet(sport, dport, 100, 0, 2)
        self.packet(sport, dport, 500, 101, 18, reverse=True)
        self.packet(sport, dport, 101, 501, 16)
        seq, server_seq = 101, 501
        for index, payload in enumerate(requests):
            self.packet(sport, dport, seq, server_seq, 24, payload)
            seq += len(payload)
            response = (server_responses or {}).get(index, b'')
            self.packet(sport, dport, server_seq, seq, 24 if response else 16, response, reverse=True)
            server_seq += len(response)


def dnp3(function):
    def crc(data):
        result = 0
        for byte in data:
            result ^= byte
            for _ in range(8):
                result = (result >> 1) ^ (0xa6bc if result & 1 else 0)
        return struct.pack('<H', (~result) & 65535)
    data = bytes([0xc0, 0xc0, function]) + (b'\x3c\x02\x06' if function == 1 else b'')
    header = bytes([5, 100, 5 + len(data), 0xc4, 1, 0, 0, 4])
    return header + crc(header) + data + crc(data)


def mqtt_publish(topic):
    content = topic.encode()
    body = struct.pack('!H', len(content)) + content + b'1'
    return bytes([0x30, len(body)]) + body


def s7(function):
    params = bytes([function, 1]) + bytes.fromhex('120a10020001000083000000')
    data = bytes.fromhex('000400100001') if function == 5 else b''
    body = b'\x02\xf0\x80' + struct.pack('!BBHHHH', 0x32, 1, 0, 1, len(params), len(data)) + params + data
    return b'\x03\x00' + struct.pack('!H', len(body) + 4) + body


def run(directory):
    directory.mkdir(parents=True, exist_ok=True)
    config = ET.fromstring('<IndProto><general><enabled>1</enabled><default_action>block</default_action></general><rules/></IndProto>')
    for protocol, port, extras in [
        ('modbus', 502, {'access': 'read', 'modbus_function_codes': '3'}),
        ('dnp3', 20000, {'access': 'read', 'dnp3_function_codes': '1'}),
        ('s7comm', 102, {'access': 'read'}),
        ('mqtt', 1883, {'mqtt_allow_connect': '1', 'mqtt_operations': 'publish', 'mqtt_topic': 'factory/allowed'}),
        ('nclink', 1884, {'nclink_operations': 'sample', 'nclink_device_uuid': 'machine-01'}),
    ]:
        node = ET.SubElement(config.find('rules'), 'rule')
        for key, val in dict(enabled='1', description='transaction_review', protocol=protocol,
                            src_ip='any', dst_ip='any', dst_port=str(port), action='pass', **extras).items():
            ET.SubElement(node, key).text = val
    rules, _, _ = generate_rules.render_rules(config)
    (directory / 'policy.rules').write_text('\n'.join(rules) + '\n')
    capture = Capture(directory / 'transactions.pcap')
    read = struct.pack('!HHHBBHH', 1, 0, 6, 1, 3, 0, 1)
    write = struct.pack('!HHHBBHH', 2, 0, 6, 1, 6, 0, 1)
    # Each clean control must remain allowed; forbidden operations must drop.
    capture.flow(41001, 502, [read])
    capture.flow(41002, 502, [read, write])
    capture.flow(41003, 502, [read[:5], read[5:], write])
    capture.flow(41004, 502, [read + write])
    capture.flow(41005, 20000, [dnp3(1), dnp3(2)])
    capture.flow(41006, 102, [s7(4), s7(5)])
    capture.flow(41007, 102, [s7(4)])
    connect = bytes.fromhex('100f00044d5154540402003c00036e632d')
    capture.flow(41008, 1883, [connect, mqtt_publish('factory/allowed')], {0: b'\x20\x02\x00\x00'})
    capture.flow(41009, 1883, [connect, mqtt_publish('factory/allowed'), mqtt_publish('factory/denied')], {0: b'\x20\x02\x00\x00'})
    capture.flow(41010, 1884, [connect, mqtt_publish('Sample/machine-01'), mqtt_publish('Set/Request/machine-01')], {0: b'\x20\x02\x00\x00'})
    capture.stream.close()
    yaml = '''%YAML 1.1
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
    modbus:
      enabled: yes
      detection-ports:
        dp: 502
    dnp3:
      enabled: yes
      detection-ports:
        dp: "[20000]"
    mqtt:
      enabled: yes
      detection-ports:
        dp: "[1883,1884]"
'''
    (directory / 'suricata.yaml').write_text(yaml)
    command = ['suricata', '-c', str(directory / 'suricata.yaml'), '-S', str(directory / 'policy.rules'),
               '-r', str(directory / 'transactions.pcap'), '-l', str(directory), '--runmode', 'single', '--simulate-ips', '--init-errors-fatal']
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    (directory / 'engine.log').write_text(result.stdout)
    if result.returncode:
        print(result.stdout)
        raise RuntimeError('Suricata replay failed')
    alerts = [json.loads(line) for line in (directory / 'eve.json').read_text().splitlines()]
    blocked = {r.get('src_port') for r in alerts if r.get('alert', {}).get('action') == 'blocked'}
    expected_blocked = {41002, 41003, 41004, 41005, 41006, 41009, 41010}
    expected_allowed = {41001, 41007, 41008}
    report = {'blocked': sorted(blocked), 'expected_blocked': sorted(expected_blocked),
              'clean_controls': sorted(expected_allowed), 'rules': len(rules)}
    (directory / 'result.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    assert expected_blocked <= blocked, 'A forbidden industrial transaction was not blocked'
    assert not expected_allowed & blocked, 'A clean control was incorrectly blocked'
    print('PASS: five protocols; connection reuse, segmentation and coalescing checked')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: replay_transactions.py /absolute/output/directory')
    run(Path(sys.argv[1]).resolve())
