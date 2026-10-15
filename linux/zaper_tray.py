"""Optional desktop integration. Never hide Tk until a usable tray is present."""
from pathlib import Path
import threading


class Tray:
    def __init__(self, dispatch, image, on_ready):
        import pystray
        from PIL import Image
        self.icon = None
        module = pystray.Icon.__module__
        if module.endswith('_xorg'):
            from Xlib.display import Display
            display = Display()
            try:
                owner = display.get_selection_owner(display.intern_atom('_NET_SYSTEM_TRAY_S' + str(display.get_default_screen())))
                if not owner:
                    raise RuntimeError('В этом окружении нет системного трея')
            finally:
                display.close()
        if module.endswith('_gtk'):
            raise RuntimeError('Для надёжного скрытия панели нужен AppIndicator или X11-трей')
        if module.endswith('_appindicator'):
            import shutil, subprocess
            if not shutil.which('gdbus'):
                raise RuntimeError('Не удалось проверить доступность системного трея')
            owner = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.NameHasOwner', 'org.kde.StatusNotifierWatcher'], capture_output=True, text=True, timeout=2)
            if 'true' not in owner.stdout:
                raise RuntimeError('В окружении не запущен StatusNotifierWatcher')
        self.icon = pystray.Icon('zaper', Image.open(image), 'Zaper', menu=pystray.Menu(
            pystray.MenuItem('Открыть Zaper', lambda icon, item: dispatch('show'), default=True),
            pystray.MenuItem('Включить', lambda icon, item: dispatch('start')),
            pystray.MenuItem('Выключить', lambda icon, item: dispatch('stop')),
            pystray.MenuItem('Выход из панели', lambda icon, item: dispatch('quit'))))
        def ready(icon):
            icon.visible = True
            on_ready()
        self.icon.run_detached(setup=ready)

    def stop(self):
        if self.icon:
            self.icon.stop()
            self.icon = None

    def notify(self, message):
        if self.icon and self.icon.HAS_NOTIFICATION:
            self.icon.notify(message[:200], 'Zaper')
