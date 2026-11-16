#!/usr/bin/env python3
"""Package the tracked installer fork without editing the signed vendor archive."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pkg', default='/usr/local/sbin/pkg')
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--work', required=True, type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parent / 'src'
args.work.mkdir(parents=True, exist_ok=False)
payload = args.work / 'root'
shutil.copytree(source, payload)
for script in (payload / 'usr/libexec/bsdinstall').iterdir():
    script.chmod(0o555)
manifest = {
    'name': 'opnsense-installer', 'origin': 'opnsense/installer',
    'version': '25.1_3', 'comment': 'Industrial Firewall installer',
    'maintainer': 'xuwuyu26@163.com', 'www': 'https://gitee.com/xwy6848/core',
    'abi': 'FreeBSD:14:*', 'arch': 'freebsd:14:*', 'prefix': '/usr',
    'licenselogic': 'single', 'licenses': ['BSD2CLAUSE'],
    'desc': 'Industrial Firewall installer based on OPNsense installer 25.1_2; upstream copyright and license retained.',
    'deps': {'cpdup': {'origin': 'sysutils/cpdup', 'version': '1.22_1'}},
    'categories': ['sysutils'],
}
metadata = args.work / 'metadata'
metadata.mkdir()
(metadata / '+MANIFEST').write_text(json.dumps(manifest))
files = sorted('/' + path.relative_to(payload).as_posix()
               for path in payload.rglob('*') if path.is_file())
(metadata / 'plist').write_text('\n'.join(files) + '\n')
args.output.mkdir(parents=True, exist_ok=True)
subprocess.run([args.pkg, 'create', '-m', str(metadata), '-r', str(payload),
                '-p', str(metadata / 'plist'), '-o', str(args.output)], check=True)
