#!/usr/local/bin/python3
# SPDX-License-Identifier: BSD-2-Clause
"""Privileged operations. Configuration is read from OPNsense, never shell code."""
import base64
import concurrent.futures
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CONFIG = Path('/conf/config.xml')
STATE = Path('/var/db/industrial-suite')
MAX_LOG = 2 * 1024 * 1024


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.suite-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


@contextlib.contextmanager
def lock():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'operations.lock').open('a') as stream:
        os.chmod(stream.name, 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def audit(event, details):
    path = STATE / 'audit.jsonl'
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > MAX_LOG:
        path.replace(STATE / 'audit.previous.jsonl')
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'a') as stream:
        stream.write(json.dumps({'time': int(time.time()), 'event': event, **details}, ensure_ascii=False) + '\n')


def value(node, name, default=''):
    return node.findtext(name, default).strip() if node is not None else default


def entries(node, name):
    return [dict(uuid=n.get('uuid', ''), **{c.tag: (c.text or '').strip() for c in n})
            for n in node.findall(name)] if node is not None else []


def configuration():
    root = ET.parse(CONFIG).getroot()
    node = root.find('OPNsense/IndustrialSuite')
    isolation = node.find('isolation') if node is not None else None
    return {
        'integrity_enabled': value(node, 'integrity/enabled', '0'),
        'files': value(node, 'integrity/files', '/usr/local/www/index.php'),
        'policy': {
            'enabled': value(isolation, 'enabled', '0'),
            'management': value(isolation, 'management'),
            'groups': entries(isolation, 'groups/group'),
            'rules': entries(isolation, 'rules/rule'),
        },
        'nodes': entries(node, 'nodes/node'),
    }


def enabled(item):
    return str(item) in ('1', 'true', 'yes')


def networks(text):
    items = re.split(r'[\s,;]+', text.strip())
    if not items or any(not x for x in items):
        raise ValueError('At least one explicit host or network is required')
    result = sorted({str(ipaddress.ip_network(x, strict=False)) for x in items})
    if len(result) > 128:
        raise ValueError('At most 128 network entries are supported')
    if any(ipaddress.ip_network(x).prefixlen == 0 for x in result):
        raise ValueError('Unrestricted /0 networks are not accepted')
    return result


def compile_policy(policy):
    """Compile only gateway transit traffic. Never overwrite manual rules."""
    if not enabled(policy.get('enabled', '0')):
        return []
    management = networks(str(policy.get('management', '')))
    groups = {}
    for group in policy.get('groups', []):
        if not enabled(group.get('enabled', '1')):
            continue
        key = group.get('uuid', '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', key) or key in groups:
            raise ValueError('Group identifiers must be unique')
        groups[key] = networks(str(group.get('members', '')))
    if not groups:
        raise ValueError('Enabled isolation requires at least one group')
    if len(groups) > 64:
        raise ValueError('At most 64 groups are supported')
    all_nets = []
    for name, nets in groups.items():
        for net in nets:
            network = ipaddress.ip_network(net)
            for other_name, other in all_nets:
                if network.version == other.version and network.overlaps(other):
                    raise ValueError('Overlapping group networks: %s / %s' % (name, other_name))
            all_nets.append((name, network))
            if len(all_nets) > 128:
                raise ValueError('At most 128 total managed networks are supported')
    result = []

    def emit(source, dest, action, protocol='any', port='', label=''):
        if dest != '(self)' and ipaddress.ip_network(source).version != ipaddress.ip_network(dest).version:
            return
        if len(result) >= 10000:
            raise ValueError('Expanded policy exceeds 10000 rules')
        result.append({'type': action, 'from': source, 'to': dest,
                       'ipprotocol': 'inet6' if ':' in source else 'inet',
                       'protocol': '' if protocol == 'any' else protocol, 'to_port': port, 'direction': 'in',
                       'quick': True, 'log': True, 'statetype': 'keep',
                       'descr': 'Industrial isolation ' + label})

    # Management exceptions target the firewall itself, never transit hosts.
    for net in management:
        emit(net, '(self)', 'pass', 'tcp', '22,80,443', 'management')
    active = [r for r in policy.get('rules', []) if enabled(r.get('enabled', '1'))]
    if len(active) > 512:
        raise ValueError('At most 512 access rules are supported')
    # Explicit denials precede allows; broad existing user rules come later.
    for rule in sorted(active, key=lambda r: r.get('action') != 'block'):
        src, dst = rule.get('source'), rule.get('destination')
        if src not in groups or dst not in groups:
            raise ValueError('Access rule references an unknown or disabled group')
        proto, action = rule.get('protocol', 'tcp'), rule.get('action', 'pass')
        if proto not in ('tcp', 'udp', 'icmp', 'any') or action not in ('pass', 'block'):
            raise ValueError('Invalid access rule action or protocol')
        port = str(rule.get('ports', '')).strip()
        if port:
            if proto not in ('tcp', 'udp'):
                raise ValueError('Ports require TCP or UDP')
            for item in port.split(','):
                pair = item.split('-')
                if len(pair) > 2 or not all(x.isdigit() and 1 <= int(x) <= 65535 for x in pair):
                    raise ValueError('Invalid port or port range')
                if len(pair) == 2 and int(pair[0]) > int(pair[1]):
                    raise ValueError('Reversed port range')
            port = port.replace('-', ':')
        for source in groups[src]:
            for dest in groups[dst]:
                # PF has a distinct IPv6 ICMP protocol identifier.
                actual_proto = 'ipv6-icmp' if proto == 'icmp' and ':' in source else proto
                emit(source, dest, action, actual_proto, port, '%s to %s' % (src, dst))
    for _, source in all_nets:
        for _, dest in all_nets:
            emit(str(source), str(dest), 'block', label='default deny')
    if len(result) > 10000:
        raise ValueError('Expanded policy exceeds 10000 rules')
    return result


def reload_filter():
    proc = subprocess.run(['/usr/local/etc/rc.filter_configure'], capture_output=True, text=True, timeout=60)
    # rules.error is historical and persists after a later successful reload.
    if proc.returncode or Path('/tmp/rules.debug.error').exists():
        raise RuntimeError('Firewall reload failed; previous project policy will be restored')


def isolation_apply(policy=None, rollback=False):
    target = STATE / 'isolation-active.json'
    previous = STATE / 'isolation-previous.json'
    with lock():
        old = read_json(target, [])
        candidate = read_json(previous) if rollback else compile_policy(policy or configuration()['policy'])
        if candidate is None:
            raise ValueError('No previous isolation policy')
        atomic(target, candidate)
        try:
            reload_filter()
        except Exception:
            atomic(target, old)
            reload_filter()
            raise
        atomic(previous, old)
        audit('isolation_rollback' if rollback else 'isolation_apply', {'rule_count': len(candidate)})
    return {'status': 'ok', 'rule_count': len(candidate), 'existing_states': 'Existing PF sessions expire normally; new sessions use the new policy'}


def file_measure(path):
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Integrity paths must be absolute')
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024 * 1024:
            raise ValueError('Integrity targets must be regular files below 128 MiB')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}


def integrity(baseline=False):
    path = STATE / 'integrity-baseline.json'
    with lock():
        if baseline:
            files = sorted(set(configuration()['files'].split()))
            if not files or len(files) > 512:
                raise ValueError('Specify 1 to 512 integrity targets')
            data = {name: file_measure(Path(name)) for name in files}
            atomic(path, {'created': int(time.time()), 'files': data})
            audit('integrity_baseline', {'file_count': len(data)})
            return {'status': 'ok', 'file_count': len(data), 'hardware_anchored': False}
        data = read_json(path)
        if not data:
            return {'status': 'uninitialized', 'message': 'An administrator must create a baseline first', 'hardware_anchored': False}
        changes = []
        for name, expected in data['files'].items():
            try:
                current = file_measure(Path(name))
                if current != expected:
                    changes.append({'path': name, 'reason': 'changed', 'expected': expected, 'actual': current})
            except (OSError, ValueError):
                changes.append({'path': name, 'reason': 'missing or unreadable'})
        result = {'status': 'ok', 'checked_at': int(time.time()), 'file_count': len(data['files']),
                  'changes': changes, 'healthy': not changes, 'hardware_anchored': False}
        atomic(STATE / 'integrity-last.json', result)
        if changes:
            audit('integrity_alert', {'paths': [r['path'] for r in changes]})
        return result


def logs(limit=100):
    path = STATE / 'audit.jsonl'
    if not path.exists():
        return []
    from collections import deque
    with path.open() as stream:
        return [json.loads(x) for x in deque(stream, maxlen=min(max(int(limit), 1), 500))]


def remote(node, endpoint, payload=None):
    url = urllib.parse.urlsplit(node.get('url', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        raise ValueError('Managed nodes require a plain HTTPS origin without embedded credentials')
    credentials = '%s:%s' % (node.get('key', ''), node.get('secret', ''))
    headers = {'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode(),
               'Accept': 'application/json'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(
        node['url'].rstrip('/') + '/api/industrialsuite/agent/' + endpoint,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers)
    context = ssl.create_default_context()
    if not enabled(node.get('verify_tls', '1')):
        context = ssl._create_unverified_context()
    # Never send management credentials through environment proxies or redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            raise ValueError('Managed node redirected the request')
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                        urllib.request.HTTPSHandler(context=context))
    with client.open(request, timeout=8) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError('Managed node response too large')
        return json.loads(body)


def fleet(action, node_ids=None):
    config = configuration()
    allowed = {'fleet_status': 'status', 'fleet_logs': 'logs', 'fleet_preview': 'preview', 'fleet_deploy': 'deploy'}
    endpoint = allowed[action]
    if node_ids is not None and (not isinstance(node_ids, list) or not all(isinstance(n, str) for n in node_ids)):
        raise ValueError('Target nodes must be an array of node identifiers')
    if action in ('fleet_preview', 'fleet_deploy') and not node_ids:
        raise ValueError('Select target nodes explicitly before distributing policy')
    payload = {'policy': config['policy']} if action in ('fleet_preview', 'fleet_deploy') else None
    if payload is not None:
        compile_policy(config['policy'])
    nodes = [n for n in config['nodes'] if enabled(n.get('enabled', '1')) and (not node_ids or n['uuid'] in node_ids)]
    if len(nodes) > 64:
        raise ValueError('At most 64 managed nodes are supported')
    def call(node):
        result = {'uuid': node['uuid'], 'name': node.get('name', '')}
        try:
            result['data'] = remote(node, endpoint, payload)
            result['status'] = result['data'].get('status', 'ok')
        except Exception as error:
            # Do not echo response bodies or credentials into logs.
            result.update(status='error', message=type(error).__name__)
            if isinstance(error, urllib.error.HTTPError):
                result['http_status'] = error.code
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(call, nodes))
    if action == 'fleet_deploy':
        with lock():
            audit(action, {'nodes': [{'uuid': n['uuid'], 'status': n['status']} for n in results]})
    return {'status': 'ok', 'nodes': results}


def dispatch(action, request=None):
    request = request or {}
    if action == 'status':
        return {'status': 'ok', 'integrity': read_json(STATE / 'integrity-last.json', {'status': 'uninitialized'}),
                'isolation_rule_count': len(read_json(STATE / 'isolation-active.json', [])),
                'hardware_trusted_computing': 'not implemented', 'vpn_6000': 'not tested'}
    if action == 'logs':
        return {'status': 'ok', 'rows': logs()}
    if action == 'integrity_baseline':
        return integrity(True)
    if action == 'integrity_check':
        return integrity()
    if action == 'isolation_preview':
        rules = compile_policy(request.get('policy', configuration()['policy']))
        return {'status': 'ok', 'rule_count': len(rules), 'rules': rules}
    if action in ('isolation_apply', 'isolation_rollback'):
        return isolation_apply(rollback=action.endswith('rollback'))
    if action.startswith('fleet_') and action in ('fleet_status', 'fleet_logs', 'fleet_preview', 'fleet_deploy'):
        return fleet(action, request.get('node_ids'))
    raise ValueError('Unknown industrial suite operation')


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'watch':
        while True:
            try:
                if enabled(configuration()['integrity_enabled']):
                    integrity()
            except Exception as error:
                print('Integrity monitor:', type(error).__name__, file=sys.stderr, flush=True)
            time.sleep(300)
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    try:
        request = json.loads(base64.b64decode(sys.argv[2], validate=True)) if len(sys.argv) > 2 else {}
        result = dispatch(action, request)
    except Exception as error:
        result = {'status': 'error', 'message': str(error)}
    # configd must receive structured errors even when a command fails.
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
