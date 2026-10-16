"""Root-only installer transaction; retain owned files and service state on failure."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

OWNED = ('opt/zapret2-manager', 'usr/local/bin/zapret2-manager',
         'usr/local/bin/zapret2-manager-gui', 'usr/local/bin/zaper', 'usr/local/bin/zaper-gui',
         'etc/systemd/system/zapret2-manager.service',
         'usr/share/applications/zapret2-manager.desktop',
         'usr/share/icons/hicolor/32x32/apps/zaper.png')
SERVICE = 'zapret2-manager.service'


def service(*args, check=True):
    return subprocess.run(['systemctl', *args, SERVICE], check=check, capture_output=True, text=True)


def remove(path):
    if path.is_symlink() or path.is_file(): path.unlink()
    elif path.exists(): shutil.rmtree(path)


def snapshot(root, backup):
    for name in OWNED:
        source = root/name; target = backup/name
        if source.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True); target.symlink_to(os.readlink(source))
        elif source.is_dir(): shutil.copytree(source, target, symlinks=True)
        elif source.exists():
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)


def restore(root, backup):
    for name in OWNED: remove(root/name)
    snapshot(backup, root)


def install(source, mode):
    if os.geteuid()!=0: raise PermissionError('Installation requires root')
    state=Path('/var/lib/zapret2-manager');state.mkdir(parents=True, exist_ok=True);state.chmod(0o755)
    with (state/'operation.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another Zaper operation is active; wait before installing/removing')
        if (state/'tune-pending.json').exists(): raise RuntimeError('Recover interrupted tuning first: sudo zaper tune-recover')
        app=Path('/opt/zapret2-manager')
        if app.is_symlink() or app.exists() and not (app/'.zapret2-manager-install').is_file():
            raise RuntimeError('Install path is occupied or a symlink')
        managed=Path('/run/systemd/system').is_dir()
        running=managed and service('is-active','--quiet',check=False).returncode==0
        if mode=='uninstall':
            subprocess.run(['/bin/sh',str(source/'install.sh'),mode,'--files-only'],check=True)
            return
        # Validate before stopping a working version. Keep /etc and /var/lib untouched.
        subprocess.run(['/usr/bin/python3','-I',str(source/'zapret_manager.py'),'verify'],check=True,capture_output=True)
        temp=Path(tempfile.mkdtemp(prefix='zaper-install-',dir='/var/tmp'))
        retain=False
        try:
            backup=temp/'backup';backup.mkdir()
            snapshot(Path('/'),backup)
            try:
                subprocess.run(['/bin/sh',str(source/'install.sh'),'install','--files-only'],check=True)
                if running: service('start')
            except BaseException:
                try:
                    if managed: service('stop',check=False)
                    restore(Path('/'),backup)
                    if managed:
                        subprocess.run(['systemctl','daemon-reload'],check=True)
                        if running: service('start')
                except BaseException as error:
                    retain=True
                    raise RuntimeError('Rollback incomplete; backup retained at '+str(backup)) from error
                raise
        finally:
            if not retain: shutil.rmtree(temp)


if __name__=='__main__':
    try: install(Path(sys.argv[1]).resolve(), sys.argv[2])
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise SystemExit('Installation failed: '+str(exc))
