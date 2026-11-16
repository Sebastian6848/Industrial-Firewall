#!/usr/local/bin/python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exercise a local HTTP fixture through the configured explicit antivirus proxy."""
import http.client
import http.server
import ipaddress
import json
import re
import subprocess
import threading
import xml.etree.ElementTree as ET

# Standard, non-executable antivirus test string; never written to disk.
EICAR = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = EICAR if self.path.startswith('/infected') else b'Antivirus gateway clean fixture\n'
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


def probe():
    root = ET.parse('/conf/config.xml').getroot()
    proxy = root.find('OPNsense/proxy')
    if proxy is None or proxy.findtext('general/enabled') != '1':
        raise ValueError('请先启用并应用下载防病毒。')
    addresses = {}
    for node in root.findall('interfaces/*'):
        value = '127.0.0.1' if node.tag == 'lo0' else node.findtext('ipaddr', '')
        try:
            address = ipaddress.ip_address(value)
            if address.version == 4:
                addresses[node.tag] = value
        except ValueError:
            # A DHCP management interface still has a usable runtime address.
            physical = node.findtext('if', '')
            if physical:
                output = subprocess.run(['/sbin/ifconfig', physical, 'inet'], capture_output=True,
                                        text=True, timeout=3, check=False).stdout
                match = re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+)', output)
                if match:
                    addresses[node.tag] = str(ipaddress.IPv4Address(match[1]))
    # Use a non-loopback fixture to avoid the proxy's intentional localhost destination protection.
    fixture_ip = next((value for value in addresses.values() if not ipaddress.ip_address(value).is_loopback), None)
    listener = next((addresses[key] for key in proxy.findtext('forward/interfaces', '').split(',') if key in addresses), None)
    if fixture_ip is None or listener is None:
        raise ValueError('链路自检需要一个具有 IPv4 地址的本机接口及 IPv4 代理监听地址。')
    server = http.server.ThreadingHTTPServer((fixture_ip, 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        results = []
        for path, expected in [('/clean', 200), ('/infected', 403)]:
            connection = http.client.HTTPConnection(listener, int(proxy.findtext('forward/port', '3128')), timeout=20,
                                                    source_address=('127.0.0.1', 0))
            try:
                connection.request('GET', f'http://{fixture_ip}:{server.server_port}{path}', headers={'Cache-Control': 'no-cache'})
                response = connection.getresponse()
                body = response.read(131072)
                results.append(response.status)
                if response.status != expected or (expected == 403 and b'EICAR' not in body.upper()):
                    raise ValueError(f'链路验证失败：{path} 返回 HTTP/{response.status}，期望 {expected}。请检查诊断日志和客户端访问权限。')
            finally:
                connection.close()
        return {'status': 'ok', 'message': '完整扫描链路正常：普通下载通过，EICAR 测试样本已拦截。',
                'clean_http': results[0], 'infected_http': results[1]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == '__main__':
    try:
        result = probe()
    except Exception as error:
        result = {'status': 'error', 'message': str(error)}
    print(json.dumps(result, ensure_ascii=False))
