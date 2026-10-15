"""Feature command router; input profiles/Hosts are passed on stdin, never shell code."""
import argparse
import base64
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

COMMANDS = {'history', 'restore', 'profile-export', 'profile-import', 'preset', 'repair', 'update-ips',
            'hosts-read', 'hosts-preview', 'hosts-save', 'diagnostics-export', 'monitor', 'app-updates', 'measure', 'faceit', 'faceit-exclude', 'autotune', 'tune-cancel', 'tune-recover', 'tune-results',
            'proxy-start', 'proxy-stop', 'proxy-status', 'proxy-recover', 'fake-list', 'app-download'}


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
    elif command in ('faceit', 'faceit-exclude'):
        parser.add_argument('--server', default='', required=command=='faceit-exclude')
        if command=='faceit-exclude': parser.add_argument('--remove', action='store_true')
    elif command=='app-download':
        parser.add_argument('--directory',required=True)
    elif command=='proxy-start':
        parser.add_argument('--rate',type=int,default=17)
        parser.add_argument('--port',type=int,default=10819)
        parser.add_argument('--upstream',type=int,default=10809)
        parser.add_argument('--desktop',choices=['manual','gnome','kde'],default='manual')
    if command in ('restore','preset','profile-import','faceit-exclude'):parser.add_argument('--apply',action='store_true')
    args = parser.parse_args(argv[1:])
    try:
        if command in ('restore', 'profile-import', 'preset', 'repair', 'update-ips', 'hosts-save', 'autotune', 'tune-cancel', 'tune-recover', 'faceit-exclude'):
            zm.require_root()
        if command.startswith('proxy-'):
            import zaper_proxy as proxy
            if command=='proxy-start': result=proxy.start(args.rate,args.port,args.upstream,args.desktop)
            elif command=='proxy-stop': result=proxy.stop()
            elif command=='proxy-recover': result=proxy.recover()
            else: result=proxy.status()
        elif command in ('autotune','tune-cancel','tune-recover','tune-results','measure','faceit','faceit-exclude'):
            import zaper_network as network
            import zaper_tune as tune
            import threading, signal, os
            event=threading.Event()
            previous={sig:signal.signal(sig,lambda *a:event.set()) for sig in (signal.SIGTERM,signal.SIGINT)}
            try:
                if command=='autotune':
                    def progress(percent,message):
                        print(json.dumps({'progress':percent,'message':message},ensure_ascii=False),flush=True)
                    result=tune.tune(event,progress)
                elif command=='tune-cancel': result=tune.cancel()
                elif command=='tune-recover': result=tune.recover(force=True)
                elif command=='tune-results': result=json.loads(tune.results_path().read_text()) if tune.results_path().exists() else []
                elif command=='measure': result=network.measure(2,event)
                elif command=='faceit': result=network.faceit(args.server,event,__import__('zaper_proxy').detected_proxy())
                else:
                    address,_=network.parse_server(args.server)
                    def changed(settings):
                        settings.faceit_servers=[x for x in settings.faceit_servers if x!=address]
                        if not args.remove: settings.faceit_servers.append(address)
                        settings.faceit_server_exclusions=True
                        return settings
                    result={'backup':state.save_settings(changed,'faceit-server-exclusion',apply=args.apply),'restart_required':True}
                if command in ('measure','faceit'):
                    # Diagnostics are unprivileged; exported data belongs to this user.
                    from zaper_proxy import home
                    state.atomic_bytes(home().parent/(command+'-results.json'),json.dumps(result,ensure_ascii=False).encode(),0o600)
            finally:
                for sig,handler in previous.items(): signal.signal(sig,handler)
        elif command=='fake-list':
            result=sorted(p.name for p in (zm.RUNTIME/'files').glob('*.bin'))
        elif command == 'history':
            result = state.history()
        elif command == 'restore':
            result = {'backup_before_restore': state.restore(args.identity,apply=args.apply), 'restart_required': not args.apply}
        elif command == 'preset':
            result = {'backup': state.save_settings(lambda old:state.preset(args.name,old), 'preset:' + args.name,apply=args.apply), 'restart_required': not args.apply}
        elif command == 'profile-export':
            result = state.profile(zm.load_settings(), args.name)
        elif command in ('profile-import', 'hosts-save'):
            raw = sys.stdin.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError('Входной документ больше 1 МиБ')
            data = json.loads(raw.lstrip('\ufeff'))
            if command == 'profile-import':
                settings, skipped = state.import_profile(data)
                result = {'backup': state.save_settings(settings, 'import-profile',apply=args.apply), 'skipped_windows_exe': skipped, 'restart_required': not args.apply}
            else:
                result = {'backup': maintenance.save_hosts(data['text'], data['sha256'])}
        elif command == 'repair':
            result = maintenance.repair()
        elif command == 'update-ips':
            raw=sys.stdin.read(8193) if not sys.stdin.isatty() else ''
            if len(raw)>8192:raise ValueError('Слишком длинный запрос proxy')
            proxy=json.loads(raw).get('proxy') if raw.strip() else None
            if proxy is not None and (not isinstance(proxy,str) or len(proxy)>4096 or '\n' in proxy):raise ValueError('Некорректный proxy')
            result = maintenance.update_ips(proxy)
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
        elif command in ('app-updates','app-download'):
            import zaper_updates as updates
            raw=sys.stdin.read(8193) if not sys.stdin.isatty() else ''
            if len(raw)>8192: raise ValueError('Слишком длинный запрос обновления')
            token=json.loads(raw).get('token','') if raw.strip() else ''
            if not isinstance(token,str): raise ValueError('Некорректный токен')
            result=updates.check(token) if command=='app-updates' else updates.download(args.directory,token)
            result['installed']=zm.VERSION
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, __import__('subprocess').SubprocessError) as exc:
        print('Ошибка: ' + str(exc), file=sys.stderr)
        return 1
