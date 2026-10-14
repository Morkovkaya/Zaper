#!/usr/bin/env python3
"""Native Linux backend. No third-party Python dependencies."""
import argparse
import dataclasses
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

VERSION = '3.6.3-linux.1'
HOME = Path(__file__).resolve().parent
RUNTIME = HOME / 'runtime'
CONFIG = Path('/etc/zapret2-manager/settings.json')
SERVICE = 'zapret2-manager.service'
TABLE = 'zapret2_manager'
QUEUE = 200
MARK = '0x40000000'


@dataclasses.dataclass
class Settings:
    game: str = 'off'
    ipset: str = 'none'
    strategy: str = 'current'
    excluded_uids: list = dataclasses.field(default_factory=list)
    excluded_ips: list = dataclasses.field(default_factory=list)
    excluded_domains: list = dataclasses.field(default_factory=list)

    def validate(self):
        if self.game not in ('off', 'tcp', 'udp', 'all'):
            raise ValueError('Неизвестный игровой режим')
        if self.ipset not in ('none', 'loaded', 'any'):
            raise ValueError('Неизвестная область IPSet')
        if self.strategy not in ('current', 'split', 'disorder'):
            raise ValueError('Неизвестная стратегия')
        if len(self.excluded_uids) > 128 or any(type(x) is not int or not 0 <= x < 2**32 for x in self.excluded_uids):
            raise ValueError('UID должен быть целым числом от 0 до 4294967295')
        for value in self.excluded_ips:
            ipaddress.ip_network(value, strict=False)
        import re
        if any(not isinstance(x, str) or not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?', x) for x in self.excluded_domains):
            raise ValueError('Недопустимый домен исключения')
        return self


def load_settings(path=CONFIG):
    return Settings(**json.loads(path.read_text())).validate() if path.exists() else Settings()


def atomic_save(settings, path=CONFIG):
    settings.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.settings-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(dataclasses.asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def engine(runtime=RUNTIME):
    arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    if arch is None:
        raise RuntimeError('Поддерживаются Linux x86_64 и ARM64; для другой архитектуры соберите nfqws2 из исходников')
    binary = runtime / 'bin' / arch / 'nfqws2'
    if not binary.is_file():
        raise RuntimeError('Нет Linux runtime. Сначала выполните scripts/package-linux.py или скачайте готовый архив')
    return binary


def verify_runtime(runtime=RUNTIME):
    manifest = json.loads((runtime / 'sha256.json').read_text())
    if not manifest:
        raise RuntimeError('Пустой манифест runtime')
    for name, expected in manifest.items():
        path = runtime / name
        if not path.resolve().is_relative_to(runtime.resolve()):
            raise RuntimeError('Недопустимый путь в манифесте')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Повреждён runtime: ' + name)
    return engine(runtime)


def build_args(settings, runtime=RUNTIME):
    """Translate WinDivert template into argv, preserving paths with spaces."""
    settings.validate()
    text = (runtime / 'manager-base.template').read_text()
    text = text.replace('%ROOT%\\', str(runtime) + '/').replace('\\', '/')
    args = [x for x in shlex.split(text) if not x.startswith('--wf-')]
    args[:0] = [f'--qnum={QUEUE}', f'--fwmark={MARK}']
    for blob in ('quic_google', 'discord_udp'):
        args = [x + ':payload=all' if x == f'--lua-desync=fake:blob={blob}:repeats=4' else x for x in args]
    if settings.strategy != 'current':
        sections = [[]]
        for arg in args:
            if arg == '--new':
                sections.append([])
            else:
                sections[-1].append(arg)
        for section in sections:
            if '--filter-l7=tls' in section and '--payload=tls_client_hello' in section:
                section[:] = [x for x in section if not x.startswith('--lua-desync=')]
                section.append('--lua-desync=' + ('multisplit:pos=1,midsld' if settings.strategy == 'split' else 'multidisorder:pos=midsld'))
        args = []
        for section in sections:
            if args:
                args.append('--new')
            args.extend(section)
    exclude = [f'--hostlist-exclude={runtime}/lists/{x}.txt' for x in ('list-exclude', 'list-exclude-user')]
    ip_exclude = [f'--ipset-exclude={runtime}/lists/{x}.txt' for x in ('ipset-exclude', 'ipset-exclude-user')]
    scope = [f'--ipset={runtime}/lists/ipset-all.txt'] if settings.ipset == 'loaded' else []
    if settings.ipset != 'none':
        args += ['--new', '--filter-tcp=80,443,8443'] + scope + exclude + ip_exclude + [
            '--out-range=-d10', '--payload=tls_client_hello,http_req',
            '--lua-desync=fake:blob=tls_max:tcp_ts=-600000:tcp_ts_up:repeats=4',
            '--lua-desync=multisplit:pos=1:seqovl=480:seqovl_pattern=stun2:tcp_ts_up',
            '--new', '--filter-udp=443'] + scope + exclude + ip_exclude + [
            '--payload=quic_initial', '--lua-desync=fake:blob=quic_google:repeats=11']
        if settings.game in ('tcp', 'all'):
            args += ['--new', '--filter-tcp=1024-65535'] + scope + exclude + ip_exclude + [
                '--out-range=-n4', '--payload=all',
                '--lua-desync=fake:blob=tls_max:tcp_ts=-600000:tcp_ts_up:repeats=8:payload=all',
                '--lua-desync=multisplit:pos=1:seqovl=664:seqovl_pattern=tls_max:tcp_ts_up:payload=all']
        if settings.game in ('udp', 'all'):
            args.insert(2, f'--blob=game_udp:@{runtime}/files/ACTIVE_GAME_UDP.bin')
            args += ['--new', '--filter-udp=1024-65535'] + scope + ip_exclude + [
                '--out-range=-n4', '--payload=all',
                '--lua-desync=fake:blob=quic_google:repeats=5:payload=all',
                '--lua-desync=fake:blob=game_udp:repeats=5:payload=all']
    # Apply exclusions to each profile, including the first. No temporary user files.
    global_ex = []
    if settings.excluded_ips:
        global_ex.append('--ipset-exclude-ip=' + ','.join(settings.excluded_ips))
    if settings.excluded_domains:
        global_ex.append('--hostlist-exclude-domains=' + ','.join(settings.excluded_domains))
    result = list(global_ex)
    for arg in args:
        result.append(arg)
        if arg == '--new':
            result.extend(global_ex)
    return result


def checked(command, **kwargs):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True, timeout=30, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{command[0]} (exit {result.returncode}):\n{result.stdout}{result.stderr}')
    return result.stdout


def validate_engine(settings, runtime=RUNTIME):
    binary = verify_runtime(runtime)
    return checked([binary, '--dry-run'] + build_args(settings, runtime))


def nft_rules(settings):
    """Dedicated inet table; never flush rules or assume interface names."""
    settings.validate()
    tcp = '80, 443, 2053, 2083, 2087, 2096, 8443'
    if settings.ipset != 'none' and settings.game in ('tcp', 'all'):
        tcp = '80, 443, 1024-65535'
    skip = ''
    if settings.excluded_uids:
        skip = 'meta skuid { ' + ', '.join(map(str, settings.excluded_uids)) + ' } ct mark set ct mark | 0x20000000 return\n'
    return f'''table inet {TABLE} {{
 comment "Zapret2 Manager owned table v1"
 chain output {{
  type filter hook output priority mangle; policy accept;
  meta mark & {MARK} != 0 return
  {skip}
  ct mark & 0x20000000 != 0 return
  tcp dport {{ {tcp} }} ct original packets <= 12 counter queue num {QUEUE} bypass
  meta l4proto udp ct original packets <= 12 counter queue num {QUEUE} bypass
 }}
 chain input {{
  type filter hook prerouting priority mangle; policy accept;
  ct mark & 0x20000000 != 0 return
  tcp sport {{ {tcp} }} ct reply packets <= 12 counter queue num {QUEUE} bypass
  meta l4proto udp ct reply packets <= 12 counter queue num {QUEUE} bypass
 }}
}}
'''


def queue_owner(path=Path('/proc/net/netfilter/nfnetlink_queue')):
    try:
        for line in path.read_text().splitlines():
            fields = line.split()
            if len(fields) >= 2 and int(fields[0]) == QUEUE:
                return int(fields[1])
    except FileNotFoundError:
        pass
    return None


def remove_table():
    result = subprocess.run(['nft', '-j', 'list', 'table', 'inet', TABLE], capture_output=True, text=True)
    if result.returncode:
        # Missing table is harmless; all other errors must be reported.
        if 'No such file or directory' in result.stderr:
            return
        raise RuntimeError(result.stderr)
    data = json.loads(result.stdout)
    if not any(x.get('table', {}).get('comment') == 'Zapret2 Manager owned table v1' for x in data['nftables']):
        raise RuntimeError('Имя таблицы занято другой программой; удаление запрещено')
    checked(['nft', 'delete', 'table', 'inet', TABLE])


def supervise(settings, runtime=RUNTIME):
    require_root()
    if not shutil.which('nft'):
        raise RuntimeError('Установите nftables')
    validate_engine(settings, runtime)
    Path('/run/zapret2-manager').mkdir(mode=0o755, exist_ok=True)
    with open('/run/zapret2-manager/lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Zapret2 Manager уже запущен') from None
        if queue_owner() is not None:
            raise RuntimeError(f'Очередь {QUEUE} занята другой программой')
        remove_table()  # Recover an owned table left after power loss or SIGKILL.
        stopping = False
        def stop(signum, frame):
            nonlocal stopping
            stopping = True
        previous = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
        process = None
        try:
            # stdout is inherited by journald or terminal; no pipe can fill up.
            process = subprocess.Popen([str(engine(runtime))] + build_args(settings, runtime))
            deadline = time.monotonic() + 10
            while queue_owner() != process.pid:
                if stopping:
                    return
                if process.poll() is not None:
                    raise RuntimeError(f'nfqws2 завершился: {process.returncode}')
                if time.monotonic() > deadline:
                    raise RuntimeError('nfqws2 не открыл NFQUEUE за 10 секунд')
                time.sleep(.05)
            rules = nft_rules(settings)
            checked(['nft', '-c', '-f', '-'], input=rules)
            checked(['nft', '-f', '-'], input=rules)
            print('READY: Zapret2 Manager, IPv4/IPv6', flush=True)
            while not stopping:
                if process.poll() is not None:
                    raise RuntimeError(f'nfqws2 завершился: {process.returncode}')
                time.sleep(.2)
        finally:
            try:
                remove_table()
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                for signum, handler in previous.items():
                    signal.signal(signum, handler)


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError('Нужны права администратора: sudo zapret2-manager <команда>')


def service(action):
    require_root()
    if not Path('/run/systemd/system').exists():
        raise RuntimeError('systemd не запущен. Используйте sudo zapret2-manager run; Ctrl+C выключает обработку')
    checked(['systemctl', action, SERVICE])


def network_probes():
    """Direct HTTPS diagnostics; never interpret an HTTP response as match access."""
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    results = []
    targets = (
        ('YouTube', 'https://www.youtube.com/', 'youtube'),
        ('YouTube API', 'https://youtubei.googleapis.com/generate_204', 'empty'),
        ('Discord Gateway', 'https://discord.com/api/v10/gateway', 'gateway'),
        ('FACEIT', 'https://www.faceit.com/', 'http'),
    )
    for name, url, kind in targets:
        start = time.monotonic()
        row = {'target': name, 'url': url, 'success': False, 'http': 0}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Zapret2Manager/' + VERSION})
            with opener.open(request, timeout=6) as response:
                row['http'] = response.status
                body = response.read(1024 * 1024)
                row['success'] = (response.status == 204 if kind == 'empty' else
                    response.status == 200 and (b'ytInitial' in body or b'INNERTUBE' in body) if kind == 'youtube' else
                    response.status == 200 and json.loads(body).get('url', '').startswith('wss://') if kind == 'gateway' else
                    response.status == 200)
        except Exception as exc:
            row['http'] = getattr(exc, 'code', 0)
            row['error'] = str(exc)
        row['seconds'] = round(time.monotonic() - start, 3)
        results.append(row)
    return {'probes': results, 'note': 'HTTPS only. Discord voice, screen sharing and FACEIT match/Anti-Cheat are not verified.'}


def diagnostics():
    result = {'version': VERSION, 'architecture': platform.machine(), 'python': platform.python_version(),
              'nft': shutil.which('nft'), 'systemd': Path('/run/systemd/system').exists(), 'queue_owner': queue_owner()}
    try:
        result['engine'] = checked([verify_runtime(), '--version']).strip()
    except Exception as exc:
        result['engine_error'] = str(exc)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Zapret 2 Manager — Linux')
    parser.add_argument('--version', action='version', version=VERSION)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'show', 'diagnose', 'run', 'start', 'stop', 'restart', 'enable', 'disable', 'status', 'probe'):
        commands.add_parser(name)
    config = commands.add_parser('configure')
    config.add_argument('--game', choices=['off', 'tcp', 'udp', 'all'])
    config.add_argument('--ipset', choices=['none', 'loaded', 'any'])
    config.add_argument('--strategy', choices=['current', 'split', 'disorder'])
    config.add_argument('--exclude-uid', type=int, action='append')
    config.add_argument('--exclude-ip', action='append')
    config.add_argument('--exclude-domain', action='append')
    config.add_argument('--clear-exclusions', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'probe':
            result = network_probes()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if all(row['success'] for row in result['probes']) else 1
        elif args.command == 'diagnose':
            print(json.dumps(diagnostics(), ensure_ascii=False, indent=2))
        elif args.command == 'status':
            if Path('/run/systemd/system').exists():
                result = subprocess.run(['systemctl', 'is-active', SERVICE], text=True, capture_output=True)
                print(result.stdout.strip() or 'inactive')
            else:
                print('running' if queue_owner() else 'stopped')
        elif args.command in ('start', 'stop', 'restart', 'enable', 'disable'):
            service(args.command)
        else:
            settings = load_settings()
            if args.command == 'show':
                print(json.dumps(dataclasses.asdict(settings), ensure_ascii=False, indent=2))
            elif args.command == 'check':
                print(validate_engine(settings))
            elif args.command == 'run':
                supervise(settings)
            elif args.command == 'configure':
                require_root()
                for key in ('game', 'ipset', 'strategy'):
                    if getattr(args, key) is not None:
                        setattr(settings, key, getattr(args, key))
                if args.clear_exclusions:
                    settings.excluded_uids = []
                    settings.excluded_ips = []
                    settings.excluded_domains = []
                for key in ('uid', 'ip', 'domain'):
                    values = getattr(args, 'exclude_' + key)
                    if values:
                        setattr(settings, 'excluded_' + ('uids' if key == 'uid' else 'ips' if key == 'ip' else 'domains'), values)
                validate_engine(settings)
                atomic_save(settings)
                print('Настройки проверены и сохранены. Перезапустите службу, чтобы применить их.')
        return 0
    except (ValueError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print('Ошибка: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
