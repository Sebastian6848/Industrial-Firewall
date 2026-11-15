#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Deploy committed core/plugin revisions to the review VM, without an ISO."""
import argparse
from pathlib import Path
import shlex
import subprocess

REMOTE = r'''
set -eu
core_revision=$1
plugin_revision=$2
accept_baseline=$3
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
test -d /usr/plugins/.git || git clone https://gitee.com/xwy6848/plugins.git /usr/plugins
for spec in /root/core-review /usr/plugins; do
    if [ -n "$(git -C "$spec" status --porcelain -uno)" ]; then
        echo "Tracked modifications in $spec; preserving them and stopping deployment." >&2
        exit 1
    fi
done
git -C /root/core-review remote set-url origin https://gitee.com/xwy6848/core.git
git -C /usr/plugins remote set-url origin https://gitee.com/xwy6848/plugins.git
git -C /root/core-review fetch origin
git -C /usr/plugins fetch origin
git -C /root/core-review merge --ff-only "$core_revision"
git -C /usr/plugins merge --ff-only "$plugin_revision"
test "$(git -C /root/core-review rev-parse HEAD)" = "$core_revision"
test "$(git -C /usr/plugins rev-parse HEAD)" = "$plugin_revision"
make -C /root/core-review install CORE_VERSION=26.1.11 CORE_REVISION=6 > "$backup/core-install.log" 2>&1
for plugin in net/app-identification security/icsguard security/industrial-suite security/clamav; do
    source=/usr/plugins/$plugin
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
printf 'Core source: %s\nPlugin source: %s\nDeployment record: %s\n' "$core_revision" "$plugin_revision" "$backup"
printf '%s\n' "$core_revision" > "$backup/core-commit.txt"
printf '%s\n' "$plugin_revision" > "$backup/plugins-commit.txt"
printf '%s\n' "$backup" > /root/.industrial-feature-latest-deploy
'''


def revision(path):
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '-uno'], text=True).strip():
        raise SystemExit('Commit tracked changes before deploying: ' + str(path))
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='opnsense-dev')
    parser.add_argument('--plugins', type=Path)
    parser.add_argument('--accept-baseline', action='store_true', help='Explicitly trust the protected files in this deployed revision')
    args = parser.parse_args()
    if args.host.startswith('-'):
        parser.error('SSH host must not be an option')
    core = Path(__file__).resolve().parents[1]
    plugins = args.plugins or core.parent / 'plugins'
    command = shlex.join(['/bin/sh', '-s', '--', revision(core), revision(plugins), '1' if args.accept_baseline else '0'])
    subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', args.host, command], input=REMOTE, text=True, check=True)
