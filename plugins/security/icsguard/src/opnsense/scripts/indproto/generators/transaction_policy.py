# SPDX-License-Identifier: BSD-2-Clause
"""Compile transaction permissions to audits and complementary drop rules.

Suricata pass must never authorize the remainder of a persistent connection.
The default is applied within each configured source/destination/port scope.
"""
from collections import defaultdict

from generators import build, header, msg


def policy(module, rules, sid_base, default_action):
    grouped = defaultdict(list)
    for rule in rules:
        grouped[header(rule, 'tcp', module.DEFAULT_PORT)].append(rule)
    result = []
    sid = sid_base
    for scope, scoped in grouped.items():
        active = [r for r in scoped if r.get('_active')]
        for rule in active:
            item = dict(rule, sid_base=sid)
            emitted = module.generate(0, item)
            # Positive permissions audit a transaction; they never bypass IPS.
            emitted = ['alert ' + line[5:] if line.startswith('pass ') else line for line in emitted]
            result.extend(emitted)
            sid += len(emitted)
        if default_action == 'block':
            allowed = [r for r in active if r.get('action', 'pass') == 'pass'
                       and r.get('log_only', '') not in ('1', 'true', 'yes', 'on')]
            for options in module.denied_transactions(allowed):
                result.append(build('drop', 'tcp', *scope, 'IndProto default %s block' % module.PROTOCOL_LABEL, sid, options))
                sid += 1
    return result
