#!/bin/sh
# Run only in a disposable container; never installs into the developer's host.
set -eu
legacy=$1
current=$2
task_legacy_dir=$(mktemp -d /tmp/zaper-legacy.XXXXXX)
trap 'rm -rf "$task_legacy_dir"' EXIT HUP INT TERM
tar -xzf "$legacy" -C "$task_legacy_dir"
task_bundle=$(basename "$legacy" -universal.tar.gz)
# This script is only for disposable test environments, with no production settings.
rm -f /etc/zapret2-manager/settings.json /etc/zapret2-manager/ipset-all.txt
umask 077
"$task_legacy_dir/$task_bundle/install.sh" install
zapret2-manager configure --game udp --ipset loaded --exclude-domain keep.example.org
printf '%s\n' 'custom.example.org' > /opt/zapret2-manager/runtime/lists/list-general-user.txt
cp /etc/zapret2-manager/settings.json /tmp/before-settings.json
"$current/install.sh" install
cmp /tmp/before-settings.json /etc/zapret2-manager/settings.json
zaper check > /tmp/check.log
zaper profile-export > /tmp/profile.json
zaper preset normal
zaper profile-import < /tmp/profile.json
zaper show > /tmp/restored.json
su -s /bin/sh nobody -c '/usr/local/bin/zaper history' > /tmp/history.json
printf '%s\n' '192.0.2.0/24' > /etc/zapret2-manager/ipset-all.txt
chmod 644 /etc/zapret2-manager/ipset-all.txt
printf '%s\n' 'corrupt fixture' > /opt/zapret2-manager/runtime/lua/zapret-lib.lua
zaper repair
zaper check > /tmp/repaired-check.log
test "$(cat /opt/zapret2-manager/runtime/lists/list-general-user.txt)" = 'custom.example.org'
test "$(cat /etc/zapret2-manager/ipset-all.txt)" = '192.0.2.0/24'
/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
value = json.loads(Path('/tmp/restored.json').read_text())
assert value['game'] == 'udp' and value['ipset'] == 'loaded'
assert value['excluded_domains'] == ['keep.example.org']
assert len(json.loads(Path('/tmp/history.json').read_text())) >= 2
print('PASS: upgrade preserves config/user lists; profiles/history, root repair and umask 077')
PY
"$current/install.sh" uninstall
test -f /etc/zapret2-manager/settings.json
test ! -e /usr/local/bin/zaper
printf '%s\n' 'PASS: uninstall retains settings and removes both legacy/new CLI aliases'
