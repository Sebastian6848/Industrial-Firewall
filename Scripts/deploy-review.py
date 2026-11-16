#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Deploy a committed monorepo revision to the review VM, without an ISO."""
import argparse
from pathlib import Path
import shlex
import subprocess

REMOTE = r'''
set -eu
core_revision=$1
accept_baseline=$2
if mount -p | awk '$3 == "unionfs" {found=1} END {exit !found}'; then
    echo 'Review deployment requires an unmounted system. Do not install over unionfs.' >&2
    exit 1
fi
backup=/root/backups/feature-review-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -m 700 "$backup"
cp -p /conf/config.xml "$backup/config.xml"
pkg query '%n %v' > "$backup/packages.txt"
dataset=$(mount -p | awk '$2 == "/" && $3 == "zfs" {print $1}')
if [ -n "$dataset" ]; then
    zfs snapshot "$dataset@feature-review-$(date -u +%Y%m%dT%H%M%SZ)"
fi
test -d /root/core-review/.git || git clone https://gitee.com/xwy6848/core.git /root/core-review
if [ -n "$(git -C /root/core-review status --porcelain -uno)" ]; then
    echo "Tracked modifications in /root/core-review; preserving them and stopping deployment." >&2
    exit 1
fi
git -C /root/core-review remote set-url origin https://gitee.com/xwy6848/core.git
git -C /root/core-review fetch origin
git -C /root/core-review merge --ff-only "$core_revision"
test "$(git -C /root/core-review rev-parse HEAD)" = "$core_revision"
plugin_tree=$(git -C /root/core-review rev-parse HEAD:plugins)
make -C /root/core-review install CORE_VERSION=26.1.11 CORE_REVISION=6 > "$backup/core-install.log" 2>&1
# Plugin dependency resolution must not replace the customized product core.
pkg lock -y opnsense
for plugin in net/app-identification security/icsguard security/industrial-suite www/squid security/clamav; do
    source=/root/core-review/plugins/$plugin
    name=$(basename "$plugin")
    make -C "$source" package PLUGIN_DEVEL= > "$backup/$name-build.log" 2>&1
    package_name=$(make -C "$source" -v PLUGIN_PKGNAME PLUGIN_DEVEL=)
    package_version=$(make -C "$source" -v PLUGIN_PKGVERSION PLUGIN_DEVEL=)
    pkg add -f "$source/work/pkg/$package_name-$package_version.pkg" > "$backup/$name-install.log" 2>&1
done
service configd restart
pluginctl -cq cache_flush
/usr/local/etc/rc.restart_webgui
configctl template reload OPNsense/ClamAV
configctl template reload OPNsense/CICAP
configctl template reload OPNsense/Proxy
service industrial_suite onerestart
configctl indproto apply > "$backup/industrial-policy-result.json"
configctl industrialsuite isolation_apply e30= > "$backup/isolation-result.json"
python3 - "$backup" <<'PY'
import json,sys
from pathlib import Path
for name in ['industrial-policy-result.json','isolation-result.json']:
    result=json.loads((Path(sys.argv[1])/name).read_text())
    if result.get('status')!='ok':raise SystemExit(name+': '+str(result))
PY
if [ "$accept_baseline" = 1 ]; then
    configctl industrialsuite integrity_baseline e30=
fi
configctl industrialsuite integrity_check e30=
printf 'Source: %s\nPlugin tree: %s\nDeployment record: %s\n' "$core_revision" "$plugin_tree" "$backup"
printf '%s\n' "$core_revision" > "$backup/core-commit.txt"
printf '%s\n' "$plugin_tree" > "$backup/plugins-tree.txt"
printf '%s\n' "$backup" > /root/.industrial-feature-latest-deploy
'''


def revision(path):
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '-uno'], text=True).strip():
        raise SystemExit('Commit tracked changes before deploying: ' + str(path))
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='opnsense-dev')
    parser.add_argument('--accept-baseline', action='store_true', help='Explicitly trust the protected files in this deployed revision')
    args = parser.parse_args()
    if args.host.startswith('-'):
        parser.error('SSH host must not be an option')
    core = Path(__file__).resolve().parents[1]
    command = shlex.join(['/bin/sh', '-s', '--', revision(core), '1' if args.accept_baseline else '0'])
    subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', args.host, command], input=REMOTE, text=True, check=True)
