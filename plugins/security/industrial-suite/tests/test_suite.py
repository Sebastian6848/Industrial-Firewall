# SPDX-License-Identifier: BSD-2-Clause
import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock

SCRIPT = Path(__file__).resolve().parents[1] / 'src/opnsense/scripts/industrialsuite/suite.py'
spec = importlib.util.spec_from_file_location('suite', SCRIPT)
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


def policy():
    return {'enabled': '1', 'management': '192.0.2.10/32',
            'groups': [{'uuid': 'plc', 'members': '10.1.0.0/24'}, {'uuid': 'hmi', 'members': '10.2.0.0/24'}],
            'rules': [{'source': 'hmi', 'destination': 'plc', 'action': 'pass', 'protocol': 'tcp', 'ports': '502'}]}


class IsolationTest(unittest.TestCase):
    def test_disabled_does_not_change_existing_firewall(self):
        self.assertEqual(suite.compile_policy({'enabled': '0'}), [])

    def test_default_deny_and_management_exception_do_not_open_transit(self):
        rules = suite.compile_policy(policy())
        self.assertEqual(rules[0]['to'], '(self)')
        allowed = [r for r in rules if r['type'] == 'pass' and r['to'] != '(self)']
        self.assertEqual([(r['from'], r['to'], r['to_port']) for r in allowed], [('10.2.0.0/24', '10.1.0.0/24', '502')])
        denied = {(r['from'], r['to']) for r in rules if r['type'] == 'block'}
        self.assertIn(('10.1.0.0/24', '10.2.0.0/24'), denied)

    def test_injection_invalid_ports_unknown_groups_rejected(self):
        for item in ['502; pass all', '0', '65536', '80-1']:
            candidate = policy();candidate['rules'][0]['ports'] = item
            with self.assertRaises(ValueError): suite.compile_policy(candidate)
        candidate = policy();candidate['rules'][0]['destination'] = 'unknown'
        with self.assertRaises(ValueError): suite.compile_policy(candidate)

    def test_overlapping_networks_and_unrestricted_management_rejected(self):
        candidate = policy();candidate['groups'][1]['members'] = '10.1.0.1'
        with self.assertRaises(ValueError): suite.compile_policy(candidate)
        candidate = policy();candidate['management'] = '0.0.0.0/0'
        with self.assertRaises(ValueError): suite.compile_policy(candidate)

    def test_deny_precedes_allow(self):
        candidate = policy();candidate['rules'].append(dict(candidate['rules'][0], action='block'))
        rules = suite.compile_policy(candidate)
        self.assertEqual(rules[1]['type'], 'block')

    def test_ipv6_does_not_emit_mixed_address_families(self):
        candidate = policy();candidate['groups'][0]['members'] += '\n2001:db8:1::/64';candidate['groups'][1]['members'] += '\n2001:db8:2::/64'
        rules = suite.compile_policy(candidate)
        for r in rules:
            if r['to'] != '(self)':self.assertEqual(':' in r['from'], ':' in r['to'])
        self.assertTrue(any(r['ipprotocol'] == 'inet6' for r in rules))


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
        self.state = patch.object(suite, 'STATE', self.root / 'state');self.state.start()
        self.file = self.root / 'protected';self.file.write_text('approved content')
        self.config = patch.object(suite, 'configuration', return_value={'files': str(self.file), 'policy': policy()});self.config.start()

    def tearDown(self):
        self.config.stop();self.state.stop();self.tmp.cleanup()

    def test_check_never_trusts_files_without_explicit_baseline(self):
        self.assertEqual(suite.integrity()['status'], 'uninitialized')
        self.assertFalse((suite.STATE / 'integrity-baseline.json').exists())

    def test_detects_change_missing_file_and_permissions(self):
        suite.integrity(True);self.assertTrue(suite.integrity()['healthy'])
        self.file.chmod(0o600);self.assertFalse(suite.integrity()['healthy'])
        self.file.write_text('tampered');self.assertFalse(suite.integrity()['healthy'])
        self.file.unlink();self.assertEqual(suite.integrity()['changes'][0]['reason'], 'missing or unreadable')

    def test_rejects_symlink_and_fifo(self):
        link = self.root / 'link';link.symlink_to(self.file)
        with self.assertRaises(OSError):suite.file_measure(link)
        fifo = self.root / 'fifo';os.mkfifo(fifo)
        with self.assertRaises(ValueError):suite.file_measure(fifo)

    def test_failed_reload_restores_previous_policy(self):
        suite.atomic(suite.STATE / 'isolation-active.json', [{'previous': True}])
        with patch.object(suite, 'reload_filter', side_effect=[RuntimeError('fail'), None]):
            with self.assertRaises(RuntimeError):suite.isolation_apply(policy())
        self.assertEqual(suite.read_json(suite.STATE / 'isolation-active.json'), [{'previous': True}])

    def test_successful_apply_then_rollback(self):
        with patch.object(suite, 'reload_filter'):
            suite.isolation_apply({'enabled': '0'})
            suite.isolation_apply(policy())
            suite.isolation_apply(rollback=True)
        self.assertEqual(suite.read_json(suite.STATE / 'isolation-active.json'), [])
        self.assertEqual((suite.STATE / 'isolation-active.json').stat().st_mode & 0o777, 0o600)

    def test_fleet_one_failed_node_does_not_hide_other_result(self):
        nodes = [{'uuid': 'one', 'name': 'a'}, {'uuid': 'two', 'name': 'b'}]
        with patch.object(suite, 'configuration', return_value={'nodes': nodes}), patch.object(suite, 'remote', side_effect=[TimeoutError(), {'status': 'ok'}]):
            result = suite.fleet('fleet_status')
        self.assertEqual({r['status'] for r in result['nodes']}, {'ok', 'error'})

    def test_fleet_deploy_requires_explicit_targets(self):
        with self.assertRaises(ValueError):suite.fleet('fleet_deploy')

    def test_credentials_are_not_sent_to_http_or_embedded_credentials(self):
        for url in ['http://example.com', 'https://user:secret@example.com', 'https://example.com/api?key=secret']:
            with self.assertRaises(ValueError):suite.remote({'url': url}, 'status')

    def test_get_request_has_no_empty_json_content_type(self):
        client = MagicMock()
        client.open.return_value.__enter__.return_value.read.return_value = b'{"status":"ok"}'
        with patch.object(suite.urllib.request, 'build_opener', return_value=client):
            suite.remote({'url': 'https://firewall.example', 'key': 'key', 'secret': 'secret'}, 'status')
        request = client.open.call_args.args[0]
        self.assertIsNone(request.get_header('Content-type'))
        self.assertEqual(request.get_method(), 'GET')


if __name__ == '__main__':
    unittest.main()
