"""Exercise the complete GTK frontend under X11 or native Wayland."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zapret_gui import App, Gtk, Gdk, GLib, text_of


def descendants(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children(): yield from descendants(child)


def drain():
    context = GLib.MainContext.default()
    while context.pending(): context.iteration(False)


def wait(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate():
        drain()
        if time.monotonic() > deadline: raise AssertionError('GTK wait timeout')
        time.sleep(.01)
    drain()


errors = []
previous_hook = sys.excepthook
sys.excepthook = lambda *error: errors.append(error)
root = Gtk.Window()
app = App(root, smoke=True)
try:
    display = Gdk.Display.get_default()
    assert display is not None
    if '--wayland' in sys.argv:
        assert not os.environ.get('DISPLAY'), 'DISPLAY must be absent during native Wayland tests'
        assert 'Wayland' in display.__gtype__.name, display.__gtype__.name
    else: assert 'X11' in display.__gtype__.name, display.__gtype__.name
    wait(lambda: not app.busy and len(app.game_fake.values) > 1)
    assert root.get_title().startswith('Zaper') and app.tabs.get_n_pages() == 5
    assert root.get_window() is not None and root.get_mapped()
    if os.environ.get('ZAPER_TEST_SCALE'): assert root.get_scale_factor() == int(os.environ['ZAPER_TEST_SCALE'])
    for page in range(5): app.tabs.set_current_page(page); drain()
    app.exclusions(); wait(lambda: not app.busy)
    assert len(app.dialogs) == 1
    app.dialogs[0].destroy(); drain()
    window = app.launch_dialog(); drain(); window.destroy(); drain()
    token_window = app.update_dialog(); token_window.token.set('fixture-secret'); drain()
    install_button = next(widget for widget in descendants(token_window) if isinstance(widget, Gtk.Button) and widget.get_label() == 'Установить обновление')
    with patch.object(app, 'run') as command:
        install_button.emit('clicked')
        assert command.call_args.args == (['app-install'], True)
        assert json.loads(command.call_args.kwargs['payload']) == {'token':'fixture-secret'}
    token_window.destroy(); drain()
    assert token_window.token.get() == ''
    faceit_window = app.faceit_dialog(); drain(); faceit_window.destroy(); drain()
    app.history_dialog(); wait(lambda: not app.busy)
    app.dialogs[0].destroy(); drain()
    app.hosts_dialog(); wait(lambda: not app.busy)
    window = app.dialogs[0]
    assert 'Hosts' in window.get_title() and 'localhost' in text_of(window.editor)
    # Draft Hosts text and conflict hash must survive the toolkit migration.
    original_hosts = text_of(window.editor)
    draft = original_hosts + '\n192.0.2.1 fixture.example\n'
    window.editor.get_buffer().set_text(draft)
    save = next(widget for widget in descendants(window) if isinstance(widget, Gtk.Button) and widget.get_label() == 'Сохранить')
    with patch.object(app, 'run') as command:
        save.emit('clicked')
        payload = json.loads(command.call_args.kwargs['payload'])
        assert payload['text'] == draft and 'sha256' in payload
        command.call_args.kwargs['after']('{}')
        save.emit('clicked')
        import hashlib
        assert json.loads(command.call_args.kwargs['payload'])['sha256'] == hashlib.sha256(draft.encode()).hexdigest()
    window.destroy(); drain()
    # Save must retain all settings, flags and selected fake files and apply transactionally.
    app.game.set('udp'); app.ipset.set('loaded'); app.strategy.set('split'); app.auto_check.set(True)
    with patch.object(app, 'run') as command:
        app.save()
        args = command.call_args.args[0]
        assert '--apply' in args and args[args.index('--game') + 1] == 'udp'
        assert args[args.index('--auto-check') + 1] == 'yes'
        assert '--discord-fake' in args and command.call_args.args[1] is True
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'profile.json'
        with patch.object(app, 'picker', return_value=str(path)):
            app.export_profile(); wait(lambda: not app.busy)
            assert json.loads(path.read_text())['platform'] == 'linux'
            with patch.object(app, 'run') as command:
                app.import_profile()
                assert command.call_args.args[0] == ['profile-import', '--apply']
                assert json.loads(command.call_args.kwargs['payload'])['platform'] == 'linux'
    app.result_dialog('Тест результата', 'Пример\nРезультаты диагностики'); drain()
    app.dialogs[0].destroy(); drain()
    app.about(); drain(); app.dialogs[0].destroy(); drain()
    app.run(['show'], quiet=True); wait(lambda: not app.busy)
    assert all(button.get_sensitive() for button in app.buttons)
    for value in (1.5, 2):
        app.draw_sample(json.dumps({'interface':'portable-test','latency_ms':value,'rx_mbps':.1,'tx_mbps':.2}))
    app.tabs.set_current_page(3); drain()
    assert len(app.samples) == 2 and 'portable-test' in app.chart_label.get_text()
    app.events.put(('progress', {'progress':45,'message':'Fixture progress'}))
    wait(lambda: app.progress.get_fraction() == .45)
    beats = []
    original = subprocess.run
    def delayed(*args, **kwargs):
        time.sleep(.25); return original(*args, **kwargs)
    with patch('zapret_gui.subprocess.run', side_effect=delayed):
        app.run(['show'], quiet=True)
        GLib.timeout_add(30, lambda: beats.append(True) and False)
        wait(lambda: not app.busy)
    assert beats, 'worker blocked GTK event loop'
    app.busy = True; app.close(); assert root.get_visible() and not app.closed; app.busy = False
    # Exercise an actual native chooser and cancel it through GTK, without selecting files.
    native_new = Gtk.FileChooserNative.new
    def chooser(*args):
        dialog = native_new(*args)
        GLib.timeout_add(150, lambda: dialog.emit('response', Gtk.ResponseType.CANCEL) or False)
        return dialog
    with patch.object(Gtk.FileChooserNative, 'new', side_effect=chooser):
        assert app.picker('Проверка диалога', suffix='json') is None
    if '--tray' in sys.argv:
        app.setup_tray(True)
        try: wait(lambda: app.tray is not None and app.tray.ready and not root.get_visible())
        except AssertionError:
            print(text_of(app.log), flush=True); raise
        tray = app.tray
        marker = os.environ.get('ZAPER_TRAY_ACTION_FILE')
        if marker:
            Path(marker).touch()
            wait(lambda: root.get_visible() and Path(marker + '.delivered').exists())
        else: app.tray_action('show'); drain(); assert root.get_visible()
        app.close(); drain(); assert not root.get_visible()
        app.tray_action('show'); drain(); assert root.get_visible()
        if '--wayland' in sys.argv:
            assert tray.native and tray.legacy is None
            # Protocol fixture will remove its host on demand; UI must recover visibility.
            marker = os.environ.get('ZAPER_TRAY_DROP_FILE')
            if marker:
                app.close(); assert not root.get_visible()
                Path(marker).touch()
                wait(lambda: root.get_visible() and app.tray is None)
                assert tray.stopped
        print('PASS: actual tray ready, hide, restore and close-to-tray; host-loss recovery', flush=True)
    else:
        with patch('zaper_tray.Tray', side_effect=RuntimeError('tray unavailable')):
            app.setup_tray(True)
        assert root.get_visible()
        print('PASS: missing tray keeps native window reachable', flush=True)
    assert not errors, errors
    print('PASS:', display.__gtype__.name, 'scale', root.get_scale_factor(), 'five tabs, dialogs/file chooser, settings, progress, chart and responsive workers', flush=True)
finally:
    app.busy = False
    tray = app.tray
    app.quit(); drain()
    assert app.closed and not app.sources
    if tray: assert tray.stopped and tray.source is None
    sys.excepthook = previous_hook
