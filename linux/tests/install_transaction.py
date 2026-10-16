#!/usr/bin/env python3
"""Root fixture on disposable CI only: real files, injected installer failure, fake service."""
import io
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

if os.environ.get('ZAPRET_ISOLATED_TEST')!='1' or os.geteuid()!=0:
    raise SystemExit('Disposable root test only')
source=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(source))
import zaper_install as installer


def digest_tree(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob('*') if path.is_file() and '__pycache__' not in path.parts}


with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);fakebin=root/'bin';fakebin.mkdir()
    state=root/'service-state';state.write_text('active')
    fake=fakebin/'systemctl'
    fake.write_text('''#!/usr/bin/python3
import os,sys
from pathlib import Path
state=Path(os.environ['ZAPER_FIXTURE_SERVICE'])
args=sys.argv[1:]
if args[0]=='is-active':sys.exit(0 if state.read_text()=='active' else 3)
if args[0]=='start':state.write_text('active')
if args[0]=='stop':state.write_text('inactive')
''');fake.chmod(0o755)
    os.environ['PATH']=str(fakebin)+':'+os.environ['PATH'];os.environ['ZAPER_FIXTURE_SERVICE']=str(state)
    subprocess.run(['/bin/sh',str(source/'install.sh'),'install'],check=True)
    subprocess.run(['zaper','configure','--game','udp','--exclude-domain','keep.example.org'],check=True)
    config=Path('/etc/zapret2-manager/settings.json');before_config=config.read_bytes()
    user=Path('/opt/zapret2-manager/runtime/lists/list-general-user.txt');user.write_text('keep.example.org\n')
    before=digest_tree(Path('/opt/zapret2-manager'))
    broken=root/'broken';shutil.copytree(source,broken)
    script=broken/'install.sh';text=script.read_text().replace("    echo 'Installed.","    exit 71\n    echo 'Installed.");script.write_text(text)
    # Pretend systemd is present even inside containers, using only the fake service.
    original_is_dir=Path.is_dir
    def is_dir(path):return True if str(path)=='/run/systemd/system' else original_is_dir(path)
    with patch.object(Path,'is_dir',is_dir):
        try:installer.install(broken,'install')
        except subprocess.CalledProcessError:pass
        else:raise AssertionError('Injected installer failure was ignored')
        assert state.read_text()=='active','Previous running service was not restored'
        assert digest_tree(Path('/opt/zapret2-manager'))==before,'Previous installed bytes changed'
        assert config.read_bytes()==before_config and user.read_text()=='keep.example.org\n'
        installer.install(source,'install')
        assert state.read_text()=='active','Running service was not restarted after upgrade'
        state.write_text('inactive');installer.install(source,'install')
        assert state.read_text()=='inactive','Stopped service unexpectedly started'
    if len(sys.argv)>1:
        import zaper_updates as updates
        import zaper_version
        data=Path(sys.argv[1]).read_bytes()
        release=dict(tag='v'+zaper_version.VERSION,name='Zaper-'+zaper_version.VERSION+'-universal.tar.gz',id=1,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        with patch.object(zaper_version,'VERSION','1.0.0-linux.1'),patch.object(updates,'check',return_value=release),patch.object(updates,'request',side_effect=lambda *args:io.BytesIO(data)):
            result=updates.install()
        assert result['updated'] and result['verified']
        assert config.read_bytes()==before_config and user.read_text()=='keep.example.org\n'
        print('PASS: root updater downloads, verifies, extracts, installs dependencies and upgrades without manual extraction')
    subprocess.run(['zaper','verify'],check=True)
    subprocess.run(['/bin/sh',str(source/'install.sh'),'uninstall'],check=True)
print('PASS: failed install restores bytes/settings/lists/running service; successful upgrade retains running/stopped state')
