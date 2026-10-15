"""Validated persistent operations: history and profiles never execute imported code."""
from contextlib import contextmanager
from datetime import datetime, timezone
import dataclasses
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

STATE = Path('/var/lib/zapret2-manager')
IP_OVERLAY = Path('/etc/zapret2-manager/ipset-all.txt')


def backend():
    import zapret_manager
    return zapret_manager


def atomic_bytes(path, content, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.zaper-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


@contextmanager
def operation():
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o755)
    with (STATE / 'operation.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Дождитесь завершения другой операции Zaper') from None
        yield


def snapshot(reason):
    zm = backend()
    folder = STATE / 'history'
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o755)
    identity = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:10]
    try:
        saved = {'settings': dataclasses.asdict(zm.load_settings())}
    except (ValueError, TypeError):
        saved = {'raw_settings_base64': base64.b64encode(zm.CONFIG.read_bytes()).decode()}
    payload = {'schema': 1, 'id': identity, 'reason': reason, 'utc': datetime.now(timezone.utc).isoformat(),
               **saved}
    atomic_bytes(folder / (identity + '.json'), (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode())
    return identity


def save_settings(settings, reason='configure'):
    zm = backend()
    settings.validate()
    with operation():
        zm.validate_engine(settings)
        identity = snapshot(reason)
        zm.atomic_save(settings, zm.CONFIG)
    return identity


def history():
    folder = STATE / 'history'
    rows = []
    for path in sorted(folder.glob('*.json'), reverse=True):
        try:
            value = json.loads(path.read_text())
            rows.append({k: value[k] for k in ('id', 'reason', 'utc')})
        except (ValueError, KeyError):
            continue
    return rows


def restore(identity):
    if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{10}', identity):
        raise ValueError('Недопустимый номер записи истории')
    data = json.loads((STATE / 'history' / (identity + '.json')).read_text())
    settings = backend().Settings(**data['settings']).validate()
    return save_settings(settings, 'restore:' + identity)


def profile(settings, name='Мой профиль'):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ValueError('Имя профиля должно содержать от 1 до 120 символов')
    return {'schema': 1, 'application': 'Zaper', 'platform': 'linux', 'name': name,
            'settings': dataclasses.asdict(settings.validate())}


def import_profile(value):
    zm = backend()
    skipped = []
    if not isinstance(value, dict):
        raise ValueError('Ожидается JSON-объект профиля')
    if 'Settings' in value:  # Existing Windows SavedProfile JSON.
        source = value['Settings']
        if not isinstance(source, dict):
            raise ValueError('Некорректный Windows-профиль')
        settings = zm.Settings(game=source.get('Game', 'off'), ipset=source.get('IPSet', 'none'),
                               strategy=source.get('StrategyId', 'current'),
                               game_udp_preset=source.get('GameUdpPreset', 'native'))
        apps = value.get('Applications') or []
        if not isinstance(apps, list) or any(not isinstance(x, str) for x in apps):
            raise ValueError('Некорректный список EXE')
        skipped = [x.replace('\\', '/').split('/')[-1] for x in apps]
    else:
        if value.get('schema') != 1 or value.get('platform') != 'linux' or value.get('application') != 'Zaper':
            raise ValueError('Неизвестный формат профиля Zaper')
        settings = zm.Settings(**value['settings'])
    settings.validate()
    return settings, skipped


def preset(name):
    zm = backend()
    settings = zm.load_settings()
    if name not in ('normal', 'gaming'):
        raise ValueError('Неизвестный готовый профиль')
    settings.game = 'udp' if name == 'gaming' else 'off'
    settings.ipset = 'loaded'
    settings.game_udp_preset = 'alt12-exp' if name == 'gaming' else 'native'
    return settings


def redact(text):
    text = re.sub(r'/home/[^/\s"<>]+|/Users/[^/\s"<>]+', '[USER]', text)
    text = re.sub(r'(?im)(authorization\s*:\s*)[^\r\n]+', r'\1[REDACTED]', text)
    return re.sub(r'''(?ix)((?:password|passwd|secret|token|api[_-]?key)["']?\s*[=:]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)''', r'\1[REDACTED]', text)
