"""Optional tray owns its native event loop in a reaped helper process."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading


class Tray:
    def __init__(self, dispatch, image, on_ready, on_error=None):
        self.ready = False
        self.stopping = False
        self.process = subprocess.Popen(['/usr/bin/python3', '-I', str(Path(__file__).resolve()), '--helper', str(image)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, bufsize=1)
        def messages():
            try:
                for line in self.process.stdout:
                    event = json.loads(line)
                    if event['kind'] == 'ready':
                        self.ready = True
                        on_ready()
                    elif event['kind'] == 'action':
                        dispatch(event['value'])
                    elif event['kind'] == 'error' and on_error:
                        on_error(event['value'])
            except (OSError, ValueError):
                pass
            finally:
                self.ready = False
                if not self.stopping and on_error: on_error('Процесс трея завершился; окно восстановлено')
        threading.Thread(target=messages, daemon=True).start()

    def stop(self):
        self.stopping = True
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.ready = False
        for stream in (self.process.stdin, self.process.stdout):
            if stream: stream.close()

    def notify(self, message):
        if self.ready and self.process.stdin:
            try:
                self.process.stdin.write(json.dumps({'notify': message[:200]}) + '\n')
                self.process.stdin.flush()
            except (OSError, ValueError):
                pass


def helper(image):
    def emit(kind, value=None):
        print(json.dumps({'kind': kind, 'value': value}), flush=True)
    try:
        import pystray
        from PIL import Image
        module = pystray.Icon.__module__
        if module.endswith('_xorg'):
            from Xlib.display import Display
            display = Display()
            try:
                owner = display.get_selection_owner(display.intern_atom('_NET_SYSTEM_TRAY_S' + str(display.get_default_screen())))
                if not owner: raise RuntimeError('В окружении нет системного трея')
            finally: display.close()
        elif module.endswith('_gtk'):
            raise RuntimeError('Для надёжного скрытия нужен AppIndicator или X11-трей')
        elif module.endswith('_appindicator'):
            import shutil
            if not shutil.which('gdbus'): raise RuntimeError('Не удалось проверить системный трей')
            result = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path',
                '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.NameHasOwner', 'org.kde.StatusNotifierWatcher'],
                capture_output=True, text=True, timeout=2)
            if 'true' not in result.stdout: raise RuntimeError('В окружении не запущен StatusNotifierWatcher')
        icon = pystray.Icon('zaper', Image.open(image), 'Zaper', menu=pystray.Menu(
            pystray.MenuItem('Открыть Zaper', lambda icon, item: emit('action', 'show'), default=True),
            pystray.MenuItem('Включить', lambda icon, item: emit('action', 'start')),
            pystray.MenuItem('Выключить', lambda icon, item: emit('action', 'stop')),
            pystray.MenuItem('Выход из панели', lambda icon, item: emit('action', 'quit'))))
        def ready(icon):
            icon.visible = True
            emit('ready')
        def requests():
            for line in sys.stdin:
                try:
                    request = json.loads(line)
                    if 'notify' in request and icon.HAS_NOTIFICATION: icon.notify(request['notify'], 'Zaper')
                except (ValueError, OSError): pass
            icon.stop()  # Parent exited or closed the control pipe.
        threading.Thread(target=requests, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: icon.stop())
        icon.run(setup=ready)
        return 0
    except Exception as exc:
        emit('error', str(exc))
        return 1


if __name__ == '__main__':
    sys.exit(helper(sys.argv[2]))
