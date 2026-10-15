"""Feature command router; input profiles/Hosts are passed on stdin, never shell code."""
import argparse
import base64
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

COMMANDS = {'history', 'restore', 'profile-export', 'profile-import', 'preset', 'repair', 'update-ips',
            'hosts-read', 'hosts-preview', 'hosts-save', 'diagnostics-export', 'monitor', 'app-updates'}


def run(argv):
    if not argv or argv[0] not in COMMANDS:
        return None
    import zapret_manager as zm
    import zaper_state as state
    import zaper_maintenance as maintenance
    parser = argparse.ArgumentParser(prog='zaper ' + argv[0])
    command = argv[0]
    if command == 'restore':
        parser.add_argument('identity')
    elif command == 'preset':
        parser.add_argument('name', choices=['normal', 'gaming'])
    elif command == 'profile-export':
        parser.add_argument('--name', default='Мой профиль')
    elif command == 'monitor':
        parser.add_argument('--target', default='1.1.1.1')
    args = parser.parse_args(argv[1:])
    try:
        if command in ('restore', 'profile-import', 'preset', 'repair', 'update-ips', 'hosts-save'):
            zm.require_root()
        if command == 'history':
            result = state.history()
        elif command == 'restore':
            result = {'backup_before_restore': state.restore(args.identity), 'restart_required': True}
        elif command == 'preset':
            result = {'backup': state.save_settings(state.preset(args.name), 'preset:' + args.name), 'restart_required': True}
        elif command == 'profile-export':
            result = state.profile(zm.load_settings(), args.name)
        elif command in ('profile-import', 'hosts-save'):
            raw = sys.stdin.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Входной документ больше 1 МиБ')
            data = json.loads(raw.lstrip('\ufeff'))
            if command == 'profile-import':
                settings, skipped = state.import_profile(data)
                result = {'backup': state.save_settings(settings, 'import-profile'), 'skipped_windows_exe': skipped, 'restart_required': True}
            else:
                result = {'backup': maintenance.save_hosts(data['text'], data['sha256'])}
        elif command == 'repair':
            result = maintenance.repair()
        elif command == 'update-ips':
            result = maintenance.update_ips()
        elif command in ('hosts-read', 'hosts-preview'):
            raw = Path('/etc/hosts').read_bytes()
            text = raw.decode('utf-8-sig')
            if command == 'hosts-preview':
                if not sys.stdin.isatty():
                    draft = sys.stdin.read(1024 * 1024 + 1)
                    if len(draft) > 1024 * 1024: raise ValueError('Hosts больше 1 МиБ')
                    if draft.strip():
                        text = json.loads(draft)['text']
                        if not isinstance(text, str): raise ValueError('Ожидается текст Hosts')
                text = maintenance.merge_hosts(text, maintenance.download(maintenance.HOSTS_SOURCE))
            result = {'text': text, 'sha256': hashlib.sha256(raw).hexdigest(), 'saved': False}
        elif command == 'diagnostics-export':
            result = {'zip_base64': base64.b64encode(maintenance.diagnostics_zip()).decode()}
        elif command == 'monitor':
            result = maintenance.monitor_sample(args.target)
        elif command == 'app-updates':
            # A private repository requires browser authentication. Do not persist tokens.
            result = {'installed': zm.VERSION, 'url': 'https://github.com/ivanmorkovka1-ux/zaper2/releases',
                      'note': 'Выберите Linux-релиз; распакуйте и запустите install.sh install. Служба и настройки сохраняются.'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, __import__('subprocess').SubprocessError) as exc:
        print('Ошибка: ' + str(exc), file=sys.stderr)
        return 1
