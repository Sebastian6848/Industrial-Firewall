#!/usr/bin/env python3
"""Generate installation defaults from the tracked sample and application rules."""

import json
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[2]
config = ET.parse(root / 'src/etc/config.xml.sample')
system = config.find('system')
system.find('hostname').text = 'Industrial-Firewall'
ET.SubElement(system, 'language').text = 'zh_CN'
system.find('timezone').text = 'Asia/Shanghai'

def node(parent, name, fields, **attributes):
    child = ET.SubElement(parent, name, attributes)
    for field, value in fields.items():
        ET.SubElement(child, field).text = str(value)
    return child

def stable_id(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'https://gitee.com/xwy6848/core/factory/' + name))

models = ET.SubElement(config.getroot(), 'OPNsense')
filter_model = ET.parse(root / 'src/opnsense/mvc/app/models/OPNsense/Firewall/Filter.xml')
firewall = ET.SubElement(models, 'Firewall')
migrated = ET.SubElement(firewall, 'Filter', version=filter_model.findtext('version'))
rules = ET.SubElement(migrated, 'rules')
for i, (family, description) in enumerate([
    ('inet', 'Default allow LAN to any rule'),
    ('inet6', 'Default allow LAN IPv6 to any rule'),
], start=1):
    node(rules, 'rule', {
        'enabled': 1, 'sequence': 100 * i, 'action': 'pass', 'quick': 1,
        'interface': 'lan', 'direction': 'in', 'ipprotocol': family,
        'protocol': 'any', 'source_net': 'lan', 'statetype': 'keep',
        'description': description,
    }, uuid=stable_id('firewall/' + family))
config.getroot().remove(config.find('filter'))

app_model = ET.parse(root / (
    'plugins/net/app-identification/src/opnsense/mvc/app/models/'
    'OPNsense/AppIdentification/AppIdentification.xml'
))
app = node(ET.SubElement(models, 'AppIdentification'), 'general', {
    'rest_host': '127.0.0.1', 'rest_scheme': 'http', 'rest_port': 3000, 'ifid': 1,
}, version=app_model.findtext('version'))
rules = ET.SubElement(app, 'rules')
seen = set()
source = root / 'examples/app-identification/chinese-applications.json'
for row in json.loads(source.read_text(encoding='utf-8')):
    values = [v.strip() for v in re.split(r'[\r\n|]+', row['match_value']) if v.strip()]
    key = row['match_type'].lower() + '\n' + '|'.join(sorted({v.lower() for v in values}))
    if key in seen:
        continue
    seen.add(key)
    node(rules, 'rule', {**row, 'match_value': '\n'.join(values)}, uuid=stable_id('app/' + key))
if len(seen) != 614:
    raise SystemExit(f'Unexpected number of distinct application match conditions: {len(seen)}')
ET.indent(config, space='  ')
config.write(sys.argv[1], encoding='utf-8', xml_declaration=True)
