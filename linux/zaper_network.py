"""Bounded, cancellable network diagnostics shared by the GUI and auto-tuner."""
import concurrent.futures
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import tempfile
import threading
import time


class Cancelled(RuntimeError):
    pass


def checkpoint(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('Операция отменена')


def run(command, cancel=None, timeout=10):
    checkpoint(cancel)
    # Files avoid pipe deadlocks and retain bounded subprocess lifetimes.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        process = subprocess.Popen([str(x) for x in command], stdout=output, stderr=error)
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                checkpoint(cancel)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Истекло время сетевой проверки')
                if cancel is not None: cancel.wait(.05)
                else: time.sleep(.05)
            output.seek(0); error.seek(0)
            return process.returncode, output.read(1024 * 1024).decode(errors='replace'), error.read(8192).decode(errors='replace')
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()


def sample(name, core=False):
    return dict(target=name, core=core, success=False, unknown=False, http=0, seconds=6., error='')


def http(name, url, kind='any', core=False, cancel=None, proxy=None, http3=False):
    row = sample(name, core)
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as temp:
            body = Path(temp) / 'body'
            cmd = ['curl', '--silent', '--show-error', '--location', '--proto', '=http,https',
                   '--proto-redir', '=http,https', '--connect-timeout', '3', '--max-time', '8',
                   '--max-filesize', '4194304', '--header', 'Cache-Control: no-cache',
                   '--output', body, '--write-out', '%{http_code} %{http_version}']
            cmd += ['--noproxy', '*'] if not proxy else ['--noproxy', '', '--proxy', proxy]
            cmd += ['--http3-only'] if http3 else ['--http1.1', '--tlsv1.2']
            code, output, error = run(cmd + [url], cancel, 10)
            parts = output.split()
            if parts and parts[0].isdigit(): row['http'] = int(parts[0])
            content = body.read_bytes() if body.exists() else b''
            status = row['http']
            row['success'] = code == 0 and (status == 204 if kind == 'empty' else status in (200, 403, 404) if kind == 'cdn' else status > 0 if kind == 'any' else status == 200)
            if row['success']:
                if kind == 'youtube': row['success'] = bool(re.search(b'ytInitial|INNERTUBE|youtube', content))
                elif kind == 'jpeg': row['success'] = len(content) > 1000 and content.startswith(b'\xff\xd8')
                elif kind == 'gateway': row['success'] = str(json.loads(content).get('url', '')).startswith('wss://')
                elif kind == 'oidc':
                    data = json.loads(content)
                    row['success'] = data.get('issuer') == 'https://api.faceit.com/auth' and str(data.get('token_endpoint', '')).startswith('https://api.faceit.com/')
                if http3: row['success'] = status == 200 and len(parts) > 1 and parts[1] == '3'
            row['error'] = error.strip() if not row['success'] else ''
    except Cancelled: raise
    except (OSError, ValueError, TimeoutError) as exc: row['error'] = str(exc)
    row['seconds'] = time.monotonic() - started
    return row


def resolve(host, cancel=None):
    try: return str(ipaddress.ip_address(host))
    except ValueError: pass
    code, output, error = run(['getent', 'ahostsv4', host], cancel, 3)
    if code or not output.strip(): raise RuntimeError('DNS: ' + (error.strip() or host))
    return str(ipaddress.ip_address(output.split()[0]))


def udp_request(host, port, request, cancel=None, timeout=2.2):
    address = resolve(host, cancel)
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as client:
        client.connect((address, port)); client.settimeout(.1); client.send(request)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            checkpoint(cancel)
            try: return client.recv(65536)
            except socket.timeout: pass
    raise TimeoutError('Нет UDP-ответа')


def valid_stun(response, request):
    return len(response) >= 20 and response[:2] == b'\x01\x01' and len(response) - 20 == int.from_bytes(response[2:4], 'big') and response[4:20] == request[4:20]


def stun(host, port, cancel=None):
    row = sample('UDP STUN direct: ' + host)
    started = time.monotonic()
    request = b'\x00\x01\x00\x00\x21\x12\xa4\x42' + secrets.token_bytes(12)
    try: row['success'] = valid_stun(udp_request(host, port, request, cancel), request)
    except Cancelled: raise
    except (OSError, RuntimeError, TimeoutError) as exc: row['error'] = str(exc)
    row['seconds'] = time.monotonic() - started
    return row


def parallel(jobs):
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(jobs))) as pool:
        return list(pool.map(lambda fn: fn(), jobs))


def measure(rounds=2, cancel=None):
    rows = []
    targets = [('YouTube', 'https://www.youtube.com/', 'youtube', True),
               ('YouTube images', 'https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg', 'jpeg', True),
               ('YouTube API', 'https://youtubei.googleapis.com/generate_204', 'empty', True),
               ('Discord Gateway', 'https://discord.com/api/v10/gateway', 'gateway', True),
               ('Discord CDN (TLS)', 'https://cdn.discordapp.com/', 'cdn', False)]
    for _ in range(rounds):
        checkpoint(cancel)
        rows += parallel([lambda t=t: http(*t, cancel=cancel) for t in targets])
    code, features, _ = run(['curl', '--version'], cancel, 3)
    if code == 0 and 'HTTP3' in features:
        rows.append(http('YouTube QUIC HTTP/3 direct', 'https://www.youtube.com/', 'youtube', True, cancel, http3=True))
    else:
        rows.append(dict(sample('YouTube QUIC HTTP/3 direct'), unknown=True, error='Установленный curl собран без HTTP/3; QUIC не проверен'))
    rows += parallel([lambda: stun('stun.l.google.com', 19302, cancel), lambda: stun('stun.cloudflare.com', 3478, cancel)])
    return summary(rows)


def summary(rows):
    times = sorted(x['seconds'] for x in rows if x['success'] and x['seconds'] > 0)
    mandatory = [x for x in rows if x['core']]
    return dict(samples=rows, good=sum(x['success'] for x in rows),
                valid=bool(mandatory) and all(x['success'] for x in mandatory),
                median=times[int((len(times)-1)*.5)] if times else 6.,
                p90=times[int((len(times)-1)*.9)] if times else 6.)


def parse_server(value):
    value = re.sub(r'^connect\s+', '', value.strip())
    host, port = value.rsplit(':', 1)
    address = ipaddress.IPv4Address(host)
    if not port.isdigit() or not 1 <= int(port) <= 65535: raise ValueError('Введите IPv4:порт сервера матча')
    return str(address), int(port)


def a2s(server, cancel=None):
    host, port = parse_server(server)
    base = b'\xff\xff\xff\xffTSource Engine Query\0'
    # Challenge retries must use the same UDP socket; challenges may be bound to its port.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.connect((host, port)); client.settimeout(.1)
        request = base
        for _ in range(2):
            checkpoint(cancel); client.send(request)
            deadline = time.monotonic() + 2.5
            while True:
                checkpoint(cancel)
                if time.monotonic() > deadline: return 'UDP без ответа; допуск в матч не установлен'
                try: response = client.recv(65536); break
                except socket.timeout: pass
            if response.startswith(b'\xff\xff\xff\xffI') and len(response) >= 6:
                return 'A2S_INFO ответил; вход требует CS2 и Anti-Cheat'
            if response.startswith(b'\xff\xff\xff\xffA') and len(response) == 9: request = base + response[5:]
            else: return 'Неожиданный UDP-ответ; допуск в матч не установлен'
    return 'Не пройден A2S challenge; допуск в матч не установлен'


def region(name, host, cancel=None):
    row = dict(name=name, address=host, kind='region', ping_ms=None, loss_percent=100)
    try:
        ip = resolve(host, cancel); row['address'] += ' / ' + ip
        code, output, _ = run(['ping', '-n', '-c', '6', '-i', '.15', '-W', '1', ip], cancel, 9)
        times = sorted(float(x) for x in re.findall(r'time[=<]([\d.]+)', output))
        row.update(ping_ms=times[(len(times)-1)//2] if times else None,
                   loss_percent=round((6-len(times))*100/6),
                   result='Диагностический узел доступен; вход в матч не проверен' if times else 'ICMP не отвечает; блокировка игры не доказана')
    except Cancelled: raise
    except (OSError, RuntimeError, TimeoutError) as exc: row['result'] = str(exc)
    return row


def faceit(server='', cancel=None, proxy=None):
    ids = ('finland', 'germany', 'sweden', 'netherlands', 'france', 'uk', 'moscow', 'kazakhstan')
    rows = parallel([lambda host=host: region(host, host+'.eu.ping.faceit.com', cancel) for host in ids] +
                    [lambda: region('Cloudflare DNS', '1.1.1.1', cancel), lambda: region('Google DNS', '8.8.8.8', cancel)])
    targets = [('FACEIT', 'https://www.faceit.com/', 'any'),
               ('FACEIT OIDC', 'https://api.faceit.com/auth/v1/openid_configuration', 'oidc'),
               ('Anti-Cheat HTTPS', 'https://ac-client-ws.faceit.com/', 'any'),
               ('Discord', 'https://discord.com/api/v10/gateway', 'gateway'),
               ('YouTube', 'https://www.youtube.com/', 'youtube')]
    jobs = [lambda t=t, route=route: http(t[0]+(' · Proxy' if route else ' · Прямой'), t[1], t[2], cancel=cancel, proxy=route)
            for t in targets for route in ([None, proxy] if proxy else [None])]
    for row in parallel(jobs):
        status = row['http']
        row['result'] = ('HTTPS доступен; HTTP '+str(status)+'. Доступ аккаунта/Anti-Cheat не проверен' if status in (401,403,404,429) or status >= 500 else
                         'Проверка HTTPS пройдена; матч не проверен' if row['success'] else 'Проверка не пройдена: '+str(status)+' '+row['error'])
        rows.append(row)
    if server:
        started=time.monotonic()
        rows.append(dict(name='Сервер матча', address=server, kind='game', result=a2s(server,cancel), milliseconds=round((time.monotonic()-started)*1000)))
    return dict(rows=rows, note='ICMP/HTTPS/A2S не подтверждают вход в матч или работу Anti-Cheat')
