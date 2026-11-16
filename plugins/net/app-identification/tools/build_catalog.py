#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Import named service lists, excluding categories, aliases and regex guesses."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess


def build(source):
    apps = []
    for path in sorted((source / 'data').iterdir()):
        if path.name.startswith(('category-', 'geolocation-', 'tld-')) or path.name in ('cn', 'private'):
            continue
        domains = set()
        for raw in path.read_text().splitlines():
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            token = line.split()[0]
            if token.startswith(('include:', 'keyword:', 'regexp:')):
                continue
            mode = 'exact' if token.startswith('full:') else 'suffix'
            domain = token.removeprefix('full:').removeprefix('domain:').lower().rstrip('.')
            if re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', domain) and '.' in domain:
                domains.add((domain, mode))
        if domains:
            apps.append({'id': path.name, 'name': path.name,
                         'domains': [{'value': x, 'mode': m} for x, m in sorted(domains)]})
    # Identical lists are aliases, not additional applications.
    seen, unique = set(), []
    for app in apps:
        signature = tuple((d['value'], d['mode']) for d in app['domains'])
        if signature not in seen:
            unique.append(app)
            seen.add(signature)
    counts = Counter((d['value'], d['mode']) for a in unique for d in a['domains'])
    unique = [a for a in unique if any(counts[(d['value'], d['mode'])] == 1 for d in a['domains'])]
    return {'schema': 1, 'source': {'repository': 'https://github.com/v2fly/domain-list-community',
            'commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
            'license': 'MIT', 'scope': 'domain-based application and service identification; not content decryption'},
            'applications': unique}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('Named application/service entries:', len(result['applications']))
