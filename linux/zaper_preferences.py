"""Per-user panel launch preferences, separate from the system engine startup."""
import dataclasses
import json
import os
from pathlib import Path


@dataclasses.dataclass
class Preferences:
    start_in_tray: bool = False
    panel_autostart: bool = False
    notify_errors: bool = True

    def validate(self):
        if any(type(x) is not bool for x in dataclasses.asdict(self).values()):
            raise ValueError('Параметры запуска должны быть логическими')
        return self


def config_home():
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))


def load(root=None):
    path = (root or config_home()) / 'zaper/preferences.json'
    return Preferences(**json.loads(path.read_text())).validate() if path.exists() else Preferences()


def save(preferences, root=None):
    from zaper_state import atomic_bytes
    preferences.validate()
    root = root or config_home()
    path = root / 'zaper/preferences.json'
    autostart = root / 'autostart/zaper.desktop'
    old_settings = path.read_bytes() if path.exists() else None
    old_autostart = autostart.read_bytes() if autostart.exists() else None
    try:
        if preferences.panel_autostart:
            atomic_bytes(autostart, b'[Desktop Entry]\nType=Application\nName=Zaper\nExec=/usr/local/bin/zapret2-manager-gui --tray\nIcon=zaper\nTerminal=false\nX-GNOME-Autostart-enabled=true\n')
        else:
            autostart.unlink(missing_ok=True)
        atomic_bytes(path, (json.dumps(dataclasses.asdict(preferences), indent=2) + '\n').encode())
    except BaseException:
        for target, previous in ((autostart, old_autostart), (path, old_settings)):
            if previous is None:
                target.unlink(missing_ok=True)
            elif not target.exists() or target.read_bytes() != previous:
                atomic_bytes(target, previous)
        raise
