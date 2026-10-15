"""Maintenance operations with validation, bounded downloads and explicit writes."""
import base64
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from zaper_state import atomic_bytes, backend, operation, redact
from zaper_version import VERSION

IP_SOURCES = (
    'https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/ipset-service.txt',
    'https://api.github.com/repos/Flowseal/zapret-discord-youtube/contents/.service/ipset-service.txt',
)
HOSTS_SOURCE = 'https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/main/.service/hosts'
MAX_DOWNLOAD = 4 * 1024 * 1024


def download(url, timeout=18):
    """Direct route then environment proxy, with total curl timeout and size bound."""
    if not url.startswith('https://'):
        raise ValueError('Загрузка разрешена только по HTTPS')
    errors = []
    # curl also supports HTTPS/SOCKS system environment proxies without storing credentials.
    for direct in (True, False):
        command = ['curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
                   '--silent', '--show-error', '--connect-timeout', '5', '--max-time', str(timeout),
                   '--max-filesize', str(MAX_DOWNLOAD), '--user-agent', 'Zaper/' + VERSION]
        if direct:
            command += ['--noproxy', '*']
        try:
            result = subprocess.run(command + [url], capture_output=True, timeout=timeout + 3)
            if result.returncode == 0 and 0 < len(result.stdout) <= MAX_DOWNLOAD:
                return result.stdout.decode('utf-8-sig')
            errors.append(f'curl exit {result.returncode}')
        except subprocess.TimeoutExpired:
            errors.append('timeout')
        except FileNotFoundError:
            raise RuntimeError('Для загрузки установите curl') from None
    raise RuntimeError('Источник недоступен напрямую и через proxy; прежние файлы сохранены (' + ', '.join(errors) + ')')


def validate_ipset(text):
    count = 0
    for number, raw in enumerate(text.splitlines(), 1):
        value = raw.split('#', 1)[0].strip()
        if value:
            try:
                ipaddress.ip_network(value, strict=False)
            except ValueError:
                raise ValueError(f'IP-список: ошибка в строке {number}') from None
            count += 1
    if not count:
        raise ValueError('Пустой IP-список')
    return count


def service_active():
    if not Path('/run/systemd/system').exists():
        return False
    return subprocess.run(['systemctl', 'is-active', '--quiet', backend().SERVICE], timeout=5).returncode == 0


def update_ips():
    from zaper_state import IP_OVERLAY
    text = None
    for url in IP_SOURCES:
        try:
            value = download(url)
            if 'api.github.com' in url:
                value = base64.b64decode(json.loads(value)['content'], validate=False).decode('utf-8-sig')
            validate_ipset(value)
            text = value
            break
        except (ValueError, KeyError, RuntimeError, UnicodeError):
            continue
    if text is None:
        raise RuntimeError('Оба источника IP-списка недоступны или вернули неверные данные. Прежний список сохранён')
    zm = backend()
    with operation():
        active = service_active()
        if zm.queue_owner() is not None and not active:
            raise RuntimeError('Сначала остановите foreground-движок; файл не изменён')
        IP_OVERLAY.parent.mkdir(parents=True, exist_ok=True)
        IP_OVERLAY.parent.chmod(0o755)
        old = IP_OVERLAY.read_bytes() if IP_OVERLAY.exists() else None
        if old is not None:
            atomic_bytes(IP_OVERLAY.with_suffix('.previous'), old)
        try:
            atomic_bytes(IP_OVERLAY, text.encode())
            zm.validate_engine(zm.load_settings())
            if active:
                zm.service('restart')
        except BaseException:
            if old is None:
                IP_OVERLAY.unlink(missing_ok=True)
            else:
                atomic_bytes(IP_OVERLAY, old)
            if active:
                zm.service('restart')
            raise
    return {'networks': validate_ipset(text), 'applied_to_running_service': active}


def validate_hosts(text):
    count = 0
    for number, raw in enumerate(text.splitlines(), 1):
        fields = raw.split('#', 1)[0].split()
        if not fields:
            continue
        try:
            ipaddress.ip_address(fields[0])
        except ValueError:
            raise ValueError(f'Hosts, строка {number}: неверный IP') from None
        if len(fields) < 2 or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', x) for x in fields[1:]):
            raise ValueError(f'Hosts, строка {number}: неверное имя узла')
        count += 1
    return count


def merge_hosts(original, proposed):
    validate_hosts(proposed)
    if not proposed.strip():
        raise ValueError('Пустые предложенные Hosts')
    names = {x.lower() for line in proposed.splitlines() for x in line.split('#', 1)[0].split()[1:]}
    kept = []
    for line in original.splitlines():
        data, marker, comment = line.partition('#')
        fields = data.split()
        if len(fields) < 2 or not any(x.lower() in names for x in fields[1:]):
            kept.append(line)
        else:
            left = [x for x in fields[1:] if x.lower() not in names]
            if left:
                kept.append(fields[0] + '\t' + ' '.join(left) + (' #' + comment if marker else ''))
            elif marker:
                kept.append('#' + comment)
    return '\n'.join(kept).rstrip() + '\n\n' + proposed.strip() + '\n'


def save_hosts(text, expected_hash, path=Path('/etc/hosts')):
    from zaper_state import STATE
    validate_hosts(text)
    with operation():
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest() != expected_hash:
            raise RuntimeError('Hosts изменён другой программой. Откройте редактор заново')
        backup = STATE / 'hosts-backups' / (str(time.time_ns()) + '.txt')
        atomic_bytes(backup, original, 0o600)
        # Preserve inode, file mode, owner and symlink/bind-mount behavior of /etc/hosts.
        with path.open('r+b') as stream:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
            if hashlib.sha256(stream.read()).hexdigest() != expected_hash:
                raise RuntimeError('Hosts изменён во время сохранения')
            try:
                stream.seek(0)
                stream.write(text.encode())
                stream.truncate()
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.seek(0)
                stream.write(original)
                stream.truncate()
                stream.flush()
                raise
    return str(backup)


def repair():
    zm = backend()
    archive = zm.HOME / 'runtime-repair.tar.gz'
    expected = (zm.HOME / 'runtime-repair.sha256').read_text().strip()
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Копия восстановления повреждена; повторите установку полного архива')
    with operation(), tempfile.TemporaryDirectory(prefix='.zaper-repair-', dir=zm.HOME) as temp:
        temp = Path(temp)
        # Python 3.10-compatible safe extraction: permit only ordinary files/directories.
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            for member in tar.getmembers():
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Небезопасный путь в копии восстановления')
            tar.extractall(temp, filter='data') if hasattr(tarfile, 'data_filter') else tar.extractall(temp)
        restored = temp / 'runtime'
        # data_filter intentionally omits directory modes; umask 077 must not hide
        # runtime from nfqws2 after it drops its UID.
        restored.chmod(0o755)
        for directory in restored.rglob('*'):
            if directory.is_dir(): directory.chmod(0o755)
        zm.verify_runtime(restored)
        active = service_active()
        if zm.queue_owner() is not None and not active:
            raise RuntimeError('Сначала остановите foreground-движок')
        if active:
            zm.service('stop')
        # Keep non-immutable user lists. The IP overlay is outside runtime and untouched.
        previous = temp / 'previous'
        manifest = json.loads((restored / 'sha256.json').read_text())
        for path in (zm.RUNTIME / 'lists').glob('*'):
            relative = str(path.relative_to(zm.RUNTIME))
            if path.is_file() and relative not in manifest:
                shutil.copy2(path, restored / relative)
        try:
            zm.RUNTIME.rename(previous)
            restored.rename(zm.RUNTIME)
            zm.validate_engine(zm.load_settings())
            if active:
                zm.service('start')
        except BaseException:
            if previous.exists():
                if zm.RUNTIME.exists():
                    shutil.rmtree(zm.RUNTIME)
                previous.rename(zm.RUNTIME)
            if active:
                zm.service('start')
            raise
    return {'repaired': True, 'service_restarted': active, 'settings_preserved': True}


def diagnostics_zip():
    """Return a bounded zip in memory; GUI writes it as the ordinary user."""
    zm = backend()
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        summary = {'application': 'Zaper', **zm.diagnostics()}
        archive.writestr('summary.json', redact(json.dumps(summary, ensure_ascii=False, indent=2)))
        archive.writestr('settings.json', redact(json.dumps(__import__('dataclasses').asdict(zm.load_settings()), indent=2)))
        if shutil.which('journalctl'):
            result = subprocess.run(['journalctl', '-u', zm.SERVICE, '-n', '300', '--no-pager'], capture_output=True, text=True, timeout=8)
            archive.writestr('journal.txt', redact(result.stdout[-128000:] + result.stderr[-4000:]))
    return output.getvalue()


def default_interface(target='1.1.1.1'):
    result = backend().checked(['ip', '-j', 'route', 'get', target])
    rows = json.loads(result)
    return rows[0].get('dev', '') if rows else ''


def monitor_sample(target='1.1.1.1'):
    ipaddress.ip_address(target)
    interface = default_interface(target)
    if not re.fullmatch(r'[A-Za-z0-9_.:-]+', interface):
        raise ValueError('Не удалось определить интерфейс интернет-маршрута')
    stats = Path('/sys/class/net') / interface / 'statistics'
    before = [int((stats / name).read_text()) for name in ('rx_bytes', 'tx_bytes')]
    start = time.monotonic()
    ping = subprocess.run(['ping', '-n', '-c', '1', '-W', '1', target], capture_output=True, text=True, timeout=3)
    time.sleep(max(0, 1 - (time.monotonic() - start)))
    elapsed = time.monotonic() - start
    after = [int((stats / name).read_text()) for name in ('rx_bytes', 'tx_bytes')]
    latency = re.search(r'time[=<]([0-9.]+)', ping.stdout)
    return {'interface': interface, 'target': target, 'latency_ms': float(latency[1]) if latency else None,
            'rx_mbps': max(0, after[0] - before[0]) * 8 / elapsed / 1000000,
            'tx_mbps': max(0, after[1] - before[1]) * 8 / elapsed / 1000000,
            'note': 'ICMP timeout does not prove that a service or game is blocked'}
