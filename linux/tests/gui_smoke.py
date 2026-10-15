"""Exercise Tk interactions using a virtual display, without privileged actions."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zapret_gui import App


def wait(root, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        root.update()
        if time.monotonic() > deadline: raise AssertionError('GUI wait timeout')
        time.sleep(.02)
    root.update()


root = tk.Tk()
errors = []
root.report_callback_exception = lambda *error: errors.append(error)
app = App(root, smoke=True)
try:
    wait(root, lambda: not app.busy)
    assert root.title().startswith('Zaper') and '2 Manager' not in root.title()
    assert len(app.tabs.tabs()) == 5
    for tab in app.tabs.tabs():
        app.tabs.select(tab)
        root.update()
    app.exclusions()
    wait(root, lambda: not app.busy)
    dialogs = [x for x in root.winfo_children() if isinstance(x, tk.Toplevel)]
    assert len(dialogs) == 1
    dialogs[0].destroy()
    app.faceit_dialog()
    root.update()
    next(x for x in root.winfo_children() if isinstance(x,tk.Toplevel)).destroy()
    app.launch_dialog()
    root.update()
    dialog = next(x for x in root.winfo_children() if isinstance(x, tk.Toplevel))
    # Closing an auxiliary dialog must leave no dead controls in the operation lock.
    dialog.destroy()
    app.run(['show'], quiet=True)
    wait(root, lambda: not app.busy)
    app.hosts_dialog()
    wait(root, lambda: not app.busy)
    dialog = next(x for x in root.winfo_children() if isinstance(x, tk.Toplevel))
    assert 'Hosts' in dialog.title()
    dialog.destroy()
    app.draw_sample(json.dumps({'interface': 'portable-test', 'latency_ms': 1.5, 'rx_mbps': .1, 'tx_mbps': .2}))
    app.draw_sample(json.dumps({'interface': 'portable-test', 'latency_ms': 2, 'rx_mbps': .2, 'tx_mbps': .3}))
    assert len(app.chart.find_all()) >= 2
    # A slow command must not block the Tk event loop.
    beats = []
    original = __import__('subprocess').run
    def delayed(*args, **kwargs):
        time.sleep(.3)
        return original(*args, **kwargs)
    with patch('zapret_gui.subprocess.run', side_effect=delayed):
        app.run(['show'], quiet=True)
        root.after(30, lambda: beats.append(True))
        wait(root, lambda: not app.busy)
    assert beats
    if '--tray' in sys.argv:
        app.setup_tray(True)
        try:
            wait(root, lambda: app.tray is not None and root.state() == 'withdrawn', timeout=8)
        except AssertionError:
            print(app.log.get('1.0', 'end'), flush=True)
            raise
        app.tray_action('show')
        root.update()
        assert root.state() == 'normal'
        app.close()
        root.update()
        assert root.state() == 'withdrawn'
        app.tray_action('show')
        print('PASS: real tray startup, hide, restore and close-to-tray')
    else:
        with patch('zaper_tray.Tray', side_effect=RuntimeError('tray unavailable')):
            app.setup_tray(True)
        assert root.state() != 'withdrawn'
        print('PASS: unavailable tray keeps the window reachable')
    assert not errors, errors
    print('PASS: GUI pages, profiles, exclusions, launch dialog, Hosts, chart, responsive workers and window lifecycle')
finally:
    app.busy = False
    app.quit()
    if app.tray: assert app.tray.process.poll() is not None
