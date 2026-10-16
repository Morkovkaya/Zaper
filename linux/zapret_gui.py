#!/usr/bin/env python3
"""Native GTK desktop for Wayland and X11; command I/O stays off the UI thread."""
import base64
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser

HOME = Path(__file__).resolve().parent
sys.path.insert(0, str(HOME))
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_foreign('cairo')
    from gi.repository import Gtk, Gdk, GLib
except (ImportError, ValueError) as exc:
    raise SystemExit('Для панели Zaper установите GTK 3 и PyGObject: Arch — gtk3 python-gobject python-cairo; Debian/Ubuntu — python3-gi python3-gi-cairo gir1.2-gtk-3.0. CLI работает отдельно.') from exc

from zaper_version import APP_VERSION, VERSION
from zaper_preferences import Preferences, load as load_preferences, save as save_preferences

INSTALLED = Path('/usr/local/bin/zapret2-manager')
LOCAL = HOME / 'zapret_manager.py'
STRATEGIES = ('current', 'udp-2', 'udp-6', 'split', 'disorder', 'fake-md5', 'fake-ts', 'host-ts', 'host-seq')


class Choice(Gtk.ComboBoxText):
    def __init__(self, values, value=None):
        super().__init__()
        self.values = []
        self.replace(values, value)

    def replace(self, values, value=None):
        previous = value if value is not None else self.get()
        self.remove_all(); self.values = list(values)
        for item in self.values: self.append(item, item)
        if previous not in self.values and self.values: previous = self.values[0]
        self.set_active_id(previous)

    def get(self): return self.get_active_id() or ''
    def set(self, value):
        if value not in self.values:
            self.values.append(value); self.append(value, value)
        self.set_active_id(value)


class Entry(Gtk.Entry):
    def __init__(self, value='', secret=False):
        super().__init__(); self.set_text(str(value)); self.set_visibility(not secret)
    def get(self): return self.get_text()
    def set(self, value): self.set_text(str(value))


class Flag(Gtk.CheckButton):
    def __init__(self, label, value=False):
        super().__init__(label=label); self.set_active(value)
    def get(self): return self.get_active()
    def set(self, value): self.set_active(bool(value))


def box(horizontal=False, spacing=10):
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL, spacing=spacing)


def label(text):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_line_wrap(True); widget.set_max_width_chars(85)
    return widget


def text_view(text='', editable=False):
    widget = Gtk.TextView(editable=editable, cursor_visible=editable, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    widget.set_left_margin(8); widget.set_right_margin(8)
    widget.get_buffer().set_text(text)
    return widget


def text_of(widget):
    buffer = widget.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


def scroll(child, height=None):
    widget = Gtk.ScrolledWindow()
    widget.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    if height: widget.set_min_content_height(height)
    widget.add(child)
    return widget


class App:
    def __init__(self, root, start_in_tray=False, smoke=False):
        self.root, self.smoke = root, smoke
        self.busy = self.closed = False
        self.buttons, self.dialogs, self.samples = [], [], []
        self.events = queue.Queue(); self.tray = None; self.settings_data = {}
        self.sources = set()
        try: self.preferences = load_preferences()
        except (ValueError, OSError, TypeError): self.preferences = Preferences()
        GLib.set_application_name('Zaper')
        GLib.set_prgname('zapret2-manager')  # Matches the installed .desktop ID on Wayland.
        root.set_title('Zaper — Linux ' + APP_VERSION)
        root.set_default_size(1000, 780); root.set_size_request(720, 560)
        root.set_icon_from_file(str(HOME / 'zaper.png'))
        self.style(root)
        root.connect('delete-event', lambda *_: self.close())
        root.connect('destroy', self.destroyed)
        main = box(); main.set_border_width(18); root.add(main)
        heading = box(True)
        heading.pack_start(Gtk.Image.new_from_file(str(HOME / 'zaper.png')), False, False, 0)
        title = label('Zaper'); title.get_style_context().add_class('title')
        heading.pack_start(title, False, False, 0); main.pack_start(heading, False, False, 0)
        self.status = label('Проверка состояния…'); main.pack_start(self.status, False, False, 0)
        controls = box(True)
        for title, command in (('Включить', 'start'), ('Выключить', 'stop'), ('Перезапустить', 'restart')):
            controls.pack_start(self.button(title, lambda cmd=command: self.run([cmd], True)), False, False, 0)
        controls.pack_end(self.button('Выход из панели', self.quit, managed=False), False, False, 0)
        main.pack_start(controls, False, False, 0)
        self.tabs = Gtk.Notebook(scrollable=True)
        main.pack_start(self.tabs, True, True, 0)
        self.settings_page(); self.profiles_page(); self.tuning_page(); self.diagnostics_tab(); self.maintenance_page()
        main.pack_start(label('Журнал операций'), False, False, 0)
        self.log = text_view(); main.pack_start(scroll(self.log, 88), False, False, 0)
        root.show_all()
        self.refresh(); self.refresh_status(); self.later(60, self.poll, repeat=True)
        self.later(3000, self.refresh_status, repeat=True)
        if not smoke:
            self.later(200, lambda: self.setup_tray(start_in_tray or self.preferences.start_in_tray))
            self.later(4000, self.chart_tick, repeat=True)

    def style(self, window):
        window.get_style_context().add_class('zaper')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        if hasattr(self, 'css'): return
        self.css = Gtk.CssProvider()
        self.css.load_from_data(b'.zaper {background: #141b2b; color: #edf2ff;} .zaper .title {font-size: 24px; font-weight: bold;} .zaper button {padding: 7px 10px;} .zaper combobox button {padding: 2px 10px;} .zaper textview text {background: #0c1220; color: #dbe5ff;}')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def later(self, milliseconds, callback, repeat=False):
        def dispatch():
            if self.closed: self.sources.discard(identity); return False
            if not repeat: self.sources.discard(identity)
            callback()
            return repeat and not self.closed
        identity = GLib.timeout_add(milliseconds, dispatch)
        self.sources.add(identity)
        return identity

    def page(self, title):
        content = box(); content.set_border_width(16)
        page = scroll(content); content.zaper_page = page; self.tabs.append_page(page, Gtk.Label(label=title))
        return content

    def button(self, title, callback, managed=True):
        widget = Gtk.Button(label=title)
        widget.connect('clicked', lambda *_: callback())
        if managed:
            self.buttons.append(widget)
            widget.connect('destroy', lambda button: self.buttons.remove(button) if button in self.buttons else None)
        return widget

    def row(self, parent, *widgets):
        row = box(True)
        for widget in widgets: row.pack_start(widget, False, False, 0)
        parent.pack_start(row, False, False, 0)
        return row

    def settings_page(self):
        page = self.page('Настройки'); grid = Gtk.Grid(column_spacing=16, row_spacing=8)
        self.game = Choice(('off', 'tcp', 'udp', 'all'))
        self.ipset = Choice(('none', 'loaded', 'any'))
        self.strategy = Choice(STRATEGIES)
        self.udp = Choice(('native', 'alt12-exp'))
        self.discord_fake = Choice(('ACTIVE_DISCORD_UDP.bin',))
        self.game_fake = Choice(('ACTIVE_GAME_UDP.bin',))
        for index, (title, field) in enumerate((('Обработка игр', self.game), ('Область IPSet', self.ipset),
                ('Стратегия TLS/UDP', self.strategy), ('Игровой UDP-профиль', self.udp),
                ('UDP-пакет Discord', self.discord_fake), ('UDP-пакет игр', self.game_fake))):
            grid.attach(label(title), 0, index, 1, 1); field.set_hexpand(True); grid.attach(field, 1, index, 1, 1)
        page.pack_start(grid, False, False, 0)
        self.auto_check = Flag('Проверять сеть после сохранения')
        self.faceit_exclusions = Flag('Исключать выбранные серверы FACEIT из UDP', True)
        self.row(page, self.auto_check, self.faceit_exclusions)
        page.pack_start(label('Игровой режим работает при IPSet loaded/any. Применение сохраняет прежнее состояние службы; ошибка возвращает настройки.'), False, False, 0)
        self.row(page, self.button('Сохранить и проверить', self.save), self.button('Исключения доменов / IP / UID', self.exclusions))
        self.row(page, self.button('Настройки запуска и трея', self.launch_dialog))

    def profiles_page(self):
        page = self.page('Профили и история')
        for title, action in (('Обычный профиль', lambda: self.run(['preset', 'normal', '--apply'], True, after=self.refresh)),
                ('Игры + Discord', lambda: self.run(['preset', 'gaming', '--apply'], True, after=self.refresh)),
                ('Экспорт JSON-профиля', self.export_profile), ('Импорт JSON-профиля', self.import_profile),
                ('История настроек / откат', self.history_dialog)):
            self.row(page, self.button(title, action))
        page.pack_start(label('Каждое сохранение создаёт запись истории. Активная служба перезапускается при применении. Windows-профили конвертируются; EXE-исключения пропускаются с отчётом.'), False, False, 0)

    def tuning_page(self):
        page = self.page('Подбор и прокси')
        page.pack_start(label('Автоподбор проверяет 9 стратегий и повторно проверяет финалистов. При ошибке или отмене возвращаются настройки и прежнее состояние службы.'), False, False, 0)
        self.row(page, self.button('Начать подбор', lambda: self.run(['autotune'], True, after=self.refresh)),
                 self.button('Отменить подбор', lambda: self.run(['tune-cancel'], True, background=True), managed=False))
        self.progress = Gtk.ProgressBar(); page.pack_start(self.progress, False, False, 0)
        self.row(page, self.button('Вернуть предыдущую', lambda: self.run(['tune-recover'], True, after=self.refresh)),
                 self.button('Результаты подбора', lambda: self.run(['tune-results'], after=lambda output: self.result_dialog('Результаты подбора', output), quiet=True)))
        page.pack_start(Gtk.Separator(), False, False, 6)
        page.pack_start(label('Ограничитель исходящего трафика через HTTP/SOCKS-прокси на 127.0.0.1. В ручном режиме укажите 127.0.0.1:10819 в приложении; GNOME/KDE переключаются автоматически.'), False, False, 0)
        self.rate = Entry(17); self.rate.set_width_chars(6)
        self.upstream = Entry(10809); self.upstream.set_width_chars(7)
        self.proxy_desktop = Choice(('manual', 'gnome', 'kde'))
        self.row(page, label('Мбит/с'), self.rate, label('Порт исходного прокси'), self.upstream, self.proxy_desktop)
        self.row(page, self.button('Включить лимит', self.proxy_start), self.button('Выключить / восстановить', lambda: self.run(['proxy-stop'])), self.button('Состояние', lambda: self.run(['proxy-status'])))

    def diagnostics_tab(self):
        page = self.page('Диагностика'); self.diagnostics_page = page
        for title, command in (('Проверить конфигурацию', 'check'), ('Сеть: HTTPS / HTTP3 / STUN', 'measure'), ('Проверить зависимости', 'diagnose')):
            self.row(page, self.button(title, lambda cmd=command: self.run([cmd])))
        self.row(page, self.button('Соединения FACEIT / сервер CS2', self.faceit_dialog), self.button('Экспорт ZIP диагностики', self.export_diagnostics))
        self.target = Entry('1.1.1.1'); self.target.set_width_chars(20)
        self.row(page, self.target, self.button('Измерить задержку / нагрузку', lambda: self.run(['monitor', '--target', self.target.get()], after=self.draw_sample)))
        self.chart_label = label('Нет измерений'); page.pack_start(self.chart_label, False, False, 0)
        self.chart = Gtk.DrawingArea(); self.chart.set_size_request(-1, 110); self.chart.connect('draw', self.paint_chart)
        page.pack_start(self.chart, False, False, 0)
        page.pack_start(label('Интерфейс выбирается по текущему маршруту. ICMP/HTTPS не подтверждают матч или Anti-Cheat.'), False, False, 0)

    def maintenance_page(self):
        page = self.page('Обслуживание')
        for title, command in (('Проверить и исправить runtime', 'repair'), ('Обновить IP-список', 'update-ips')):
            self.row(page, self.button(title, lambda cmd=command: self.run([cmd], True)))
        self.row(page, self.button('Редактор системного Hosts', self.hosts_dialog))
        self.row(page, self.button('Релизы / обновление приложения', self.update_dialog))
        self.row(page, self.button('О приложении', self.about))

    def write(self, text):
        buffer = self.log.get_buffer(); buffer.insert(buffer.get_end_iter(), text.rstrip() + '\n')
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.log.scroll_mark_onscreen(mark); buffer.delete_mark(mark)

    def run(self, args, privileged=False, after=None, payload=None, quiet=False, background=False):
        if self.closed or self.busy and not background: return
        if not background:
            self.busy = True
            for button in self.buttons: button.set_sensitive(False)
        def worker():
            try:
                worker_payload = payload
                if args[0] == 'update-ips':
                    from zaper_proxy import detected_proxy
                    worker_payload = json.dumps({'proxy': detected_proxy()})
                if privileged:
                    if not INSTALLED.exists() or not shutil.which('pkexec'):
                        raise RuntimeError('Нужны установленный Zaper и polkit/pkexec; команды также доступны через sudo в терминале')
                    command = ['pkexec', str(INSTALLED)] + args
                else: command = ['/usr/bin/python3', '-I', str(LOCAL)] + args
                if args[0] == 'autotune':
                    with tempfile.TemporaryFile(mode='w+') as error:
                        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=error, text=True)
                        output = []
                        try:
                            for line in process.stdout:
                                try:
                                    progress = json.loads(line)
                                    if isinstance(progress, dict) and 'progress' in progress:
                                        self.events.put(('progress', progress)); continue
                                except ValueError: pass
                                output.append(line)
                            process.wait()
                        finally:
                            process.stdout.close()
                            if process.poll() is None: process.terminate(); process.wait(timeout=10)
                        error.seek(0)
                        result = subprocess.CompletedProcess(command, process.returncode, ''.join(output), error.read())
                else:
                    result = subprocess.run(command, input=worker_payload, capture_output=True, text=True, timeout=300 if args[0] == 'app-download' else 120)
                self.events.put(('result', result.returncode, result.stdout + result.stderr, after, quiet, background))
            except Exception as exc: self.events.put(('result', 1, str(exc), None, False, background))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        for _ in range(30):
            try: event = self.events.get_nowait()
            except queue.Empty: break
            if event[0] == 'progress':
                self.progress.set_fraction(max(0, min(100, event[1]['progress'])) / 100)
                self.write(event[1]['message']); continue
            if event[0] == 'action': self.tray_action(event[1]); continue
            if event[0] == 'tray-failed':
                if self.tray: self.tray.stop()
                self.tray = None; self.root.show_all(); self.root.present()
                self.write('Трей недоступен — окно оставлено видимым: ' + event[1]); continue
            if event[0] == 'tray-ready':
                if event[1]: self.root.hide()
                continue
            _, code, output, callback, quiet, background = event
            if not background:
                self.busy = False
                for button in self.buttons: button.set_sensitive(True)
            if code:
                self.write('Ошибка: ' + output)
                if self.tray and self.preferences.notify_errors:
                    try: self.tray.notify(output)
                    except Exception: pass
            else:
                if not quiet: self.write(output)
                if callback:
                    try: callback(output)
                    except Exception as exc: self.write('Ошибка: ' + str(exc))

    def refresh(self, output=None): self.run(['show'], after=self.loaded, quiet=True)

    def loaded(self, output):
        self.settings_data = json.loads(output)
        for key, field in (('game', self.game), ('ipset', self.ipset), ('strategy', self.strategy), ('game_udp_preset', self.udp), ('discord_fake', self.discord_fake), ('game_fake', self.game_fake), ('auto_check', self.auto_check), ('faceit_server_exclusions', self.faceit_exclusions)):
            field.set(self.settings_data[key])
        self.run(['fake-list'], after=self.loaded_fakes, quiet=True)

    def loaded_fakes(self, output):
        for field in (self.discord_fake, self.game_fake): field.replace(json.loads(output))

    def refresh_status(self):
        def update(output):
            state = {'active': 'включён', 'running': 'включён', 'inactive': 'выключен', 'stopped': 'выключен', 'failed': 'ошибка'}.get(output.strip(), output.strip())
            self.status.set_text('Состояние: ' + state)
        self.run(['status'], after=update, quiet=True, background=True)

    def save(self):
        self.run(['configure', '--apply', '--game', self.game.get(), '--ipset', self.ipset.get(), '--strategy', self.strategy.get(), '--game-udp-preset', self.udp.get(), '--discord-fake', self.discord_fake.get(), '--game-fake', self.game_fake.get(), '--auto-check', 'yes' if self.auto_check.get() else 'no', '--faceit-server-exclusions', 'yes' if self.faceit_exclusions.get() else 'no'], True)

    def dialog(self, title, width=760, height=400):
        window = Gtk.Window(title='Zaper — ' + title, transient_for=self.root, destroy_with_parent=True)
        window.set_default_size(width, height); self.style(window)
        content = box(); content.set_border_width(16); window.add(content)
        self.dialogs.append(window)
        window.connect('destroy', lambda dialog: self.dialogs.remove(dialog) if dialog in self.dialogs else None)
        return window, content

    def result_dialog(self, title, output):
        window, content = self.dialog(title, 900, 580)
        content.pack_start(scroll(text_view(output)), True, True, 0); window.show_all()
        return window

    def picker(self, title, save=False, suffix=None, directory=False):
        action = Gtk.FileChooserAction.SELECT_FOLDER if directory else Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN
        picker = Gtk.FileChooserNative.new(title, self.root, action, 'Выбрать' if directory else 'Сохранить' if save else 'Открыть', 'Отмена')
        if save: picker.set_do_overwrite_confirmation(True)
        if suffix:
            filt = Gtk.FileFilter(); filt.set_name(suffix.upper()); filt.add_pattern('*.' + suffix); picker.add_filter(filt)
            if save: picker.set_current_name('Zaper.' + suffix)
        try: return picker.get_filename() if picker.run() == Gtk.ResponseType.ACCEPT else None
        finally: picker.destroy()

    def exclusions(self):
        def opened(output):
            data = json.loads(output); window, content = self.dialog('Исключения', 760, 270)
            fields = {}
            for key, title in (('domains', 'Домены через запятую'), ('ips', 'IP/CIDR через запятую'), ('uids', 'UID через запятую')):
                field = Entry(', '.join(map(str, data.get('excluded_' + key, []))))
                content.pack_start(label(title), False, False, 0); content.pack_start(field, False, False, 0); fields[key] = field
            def save():
                args = ['configure', '--apply', '--clear-exclusions']
                for key, field in fields.items():
                    for value in field.get().split(','):
                        if value.strip(): args += ['--exclude-' + {'domains': 'domain', 'ips': 'ip', 'uids': 'uid'}[key], value.strip()]
                self.run(args, True); window.destroy()
            self.row(content, self.button('Сохранить', save)); window.show_all()
        self.run(['show'], after=opened, quiet=True)

    def export_profile(self):
        path = self.picker('Экспорт JSON-профиля', save=True, suffix='json')
        if path: self.run(['profile-export'], after=lambda output: Path(path).write_text(output), quiet=True)

    def import_profile(self):
        path = self.picker('Импорт JSON-профиля', suffix='json')
        if path:
            try:
                if Path(path).stat().st_size > 1024 * 1024: raise ValueError('Профиль больше 1 МиБ')
                self.run(['profile-import', '--apply'], True, payload=Path(path).read_text(), after=self.refresh)
            except Exception as exc: self.write('Ошибка: ' + str(exc))

    def history_dialog(self):
        def opened(output):
            rows = json.loads(output); window, content = self.dialog('История', 760, 400)
            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
            for row in rows: listing.add(label(row['utc'] + ' — ' + row['reason']))
            content.pack_start(scroll(listing), True, True, 0)
            def restore():
                selected = listing.get_selected_row()
                if selected is not None:
                    self.run(['restore', rows[selected.get_index()]['id'], '--apply'], True, after=self.refresh); window.destroy()
            self.row(content, self.button('Вернуть выбранные настройки', restore)); window.show_all()
        self.run(['history'], after=opened, quiet=True)

    def export_diagnostics(self):
        path = self.picker('Экспорт ZIP диагностики', save=True, suffix='zip')
        if path: self.run(['diagnostics-export'], after=lambda output: Path(path).write_bytes(base64.b64decode(json.loads(output)['zip_base64'])), quiet=True)

    def hosts_dialog(self):
        def opened(output):
            current = json.loads(output); window, content = self.dialog('Hosts', 850, 620)
            content.pack_start(label('Загрузка меняет только предпросмотр. Перед сохранением — резервная копия и проверка сторонних изменений.'), False, False, 0)
            editor = text_view(current['text'], editable=True); content.pack_start(scroll(editor), True, True, 0)
            window.editor = editor
            def preview(output): editor.get_buffer().set_text(json.loads(output)['text'])
            def save():
                text = text_of(editor)
                def saved(output): current['sha256'] = hashlib.sha256(text.encode()).hexdigest()
                self.run(['hosts-save'], True, payload=json.dumps({'text': text, 'sha256': current['sha256']}), after=saved)
            self.row(content, self.button('Загрузить предложенные', lambda: self.run(['hosts-preview'], after=preview, quiet=True, payload=json.dumps({'text': text_of(editor)}))), self.button('Сохранить', save))
            window.show_all()
        self.run(['hosts-read'], after=opened, quiet=True)

    def faceit_dialog(self):
        window, content = self.dialog('FACEIT / CS2', 760, 220)
        content.pack_start(label('Сервер CS2 IPv4:порт (необязательно для диагностики)'), False, False, 0)
        server = Entry(); content.pack_start(server, False, False, 0)
        self.row(content, self.button('Проверить', lambda: self.run(['faceit', '--server', server.get()], after=lambda output: self.result_dialog('Соединения серверов', output), quiet=True)),
                 self.button('Исключить из UDP', lambda: self.run(['faceit-exclude', '--server', server.get(), '--apply'], True, after=self.refresh)),
                 self.button('Вернуть обработку', lambda: self.run(['faceit-exclude', '--server', server.get(), '--remove', '--apply'], True, after=self.refresh)))
        window.show_all(); return window

    def update_dialog(self):
        window, content = self.dialog('Обновление приложения', 780, 260)
        content.pack_start(label('Публичный GitHub доступен без токена. Для приватного нужен Contents:read; токен не сохраняется.'), False, False, 0)
        token = Entry(secret=True); token.set_placeholder_text('Токен необязателен'); content.pack_start(token, False, False, 0)
        window.token = token
        details = label('Установлено: ' + VERSION); content.pack_start(details, False, False, 0)
        window.connect('destroy', lambda *_: token.set(''))
        def checked(output):
            data = json.loads(output)
            if window in self.dialogs: details.set_text(data['tag'] + '; SHA256 ' + data['sha256'][:16] + '…')
        def download():
            directory = self.picker('Каталог для обновления', directory=True)
            if directory: self.run(['app-download', '--directory', directory], payload=json.dumps({'token': token.get()}), after=lambda output: self.result_dialog('Проверенный архив', output), quiet=True)
        self.row(content, self.button('Проверить релиз', lambda: self.run(['app-updates'], payload=json.dumps({'token': token.get()}), after=checked, quiet=True)), self.button('Скачать с SHA256', download), self.button('Открыть Releases', lambda: webbrowser.open('https://github.com/Morkovkaya/Zaper/releases'), managed=False))
        window.show_all(); return window

    def launch_dialog(self):
        window, content = self.dialog('Настройки запуска и трея', 760, 340)
        fields = {}
        for key, title in (('start_in_tray', 'Запускать панель в трее (при доступном трее)'), ('panel_autostart', 'Автозапуск панели при входе пользователя'), ('notify_errors', 'Уведомления об ошибках')):
            flag = Flag(title, getattr(self.preferences, key)); fields[key] = flag; content.pack_start(flag, False, False, 0)
        content.pack_start(label('Автозапуск службы — отдельно от панели, без перезапуска:'), False, False, 0)
        self.row(content, self.button('Включить при загрузке', lambda: self.run(['enable'], True)), self.button('Отключить автозапуск службы', lambda: self.run(['disable'], True)))
        def save():
            try:
                preferences = Preferences(**{key: value.get() for key, value in fields.items()})
                save_preferences(preferences); self.preferences = preferences; self.write('Настройки панели сохранены'); window.destroy()
            except Exception as exc: self.write('Ошибка: ' + str(exc))
        self.row(content, self.button('Сохранить настройки панели', save)); window.show_all(); return window

    def proxy_start(self):
        try:
            rate, upstream = int(self.rate.get()), int(self.upstream.get())
            self.run(['proxy-start', '--rate', str(rate), '--upstream', str(upstream), '--desktop', self.proxy_desktop.get()])
        except ValueError as exc: self.write('Ошибка: ' + str(exc))

    def chart_tick(self):
        page = self.tabs.get_nth_page(self.tabs.get_current_page())
        if not self.busy and page is self.diagnostics_page.zaper_page:
            self.run(['monitor', '--target', self.target.get()], after=self.draw_sample, quiet=True, background=True)

    def draw_sample(self, output):
        data = json.loads(output); self.samples = (self.samples + [data])[-25:]
        self.chart_label.set_text(f"{data['interface']}: RX {data['rx_mbps']:.2f} / TX {data['tx_mbps']:.2f} Мбит/с; ping {data['latency_ms']} мс")
        self.chart.queue_draw()

    def paint_chart(self, widget, context):
        context.set_source_rgb(.05, .07, .12); context.paint()
        values = [(index, row['latency_ms']) for index, row in enumerate(self.samples) if row['latency_ms'] is not None]
        if not values: return False
        maximum = max([value for _, value in values] + [1])
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        context.set_source_rgb(.4, .7, 1); context.set_line_width(2)
        for n, (index, value) in enumerate(values):
            x, y = 10 + index * max(1, width - 20) / 24, height - 10 - value / maximum * (height - 20)
            if n: context.line_to(x, y)
            else: context.move_to(x, y)
        context.stroke(); return False

    def setup_tray(self, hide=False):
        try:
            from zaper_tray import Tray
            self.tray = Tray(lambda action: self.events.put(('action', action)), HOME / 'zaper.png', lambda: self.events.put(('tray-ready', hide)), lambda error: self.events.put(('tray-failed', str(error))))
        except Exception as exc:
            self.root.show_all()
            if hide: self.write('Трей недоступен — окно оставлено видимым: ' + str(exc))

    def tray_action(self, action):
        token = action.get('activation_token') if isinstance(action, dict) else None
        action = action['command'] if isinstance(action, dict) else action
        if action == 'show':
            self.root.show_all()
            if token and 'Wayland' in Gdk.Display.get_default().__gtype__.name:
                self.root.get_window().set_startup_id(token)
            self.root.present()
        elif action == 'quit': self.quit()
        else: self.run([action], True)

    def close(self):
        if self.busy: self.write('Дождитесь завершения операции; панель остаётся доступной')
        elif self.tray and self.tray.ready: self.root.hide()
        else: self.quit()
        return True

    def destroyed(self, *_):
        self.closed = True
        for source in list(self.sources): GLib.source_remove(source)
        self.sources.clear()
        if self.tray: self.tray.stop()
        if Gtk.main_level(): Gtk.main_quit()

    def quit(self):
        if self.busy and not self.smoke:
            self.write('Дождитесь завершения операции'); return
        self.root.destroy()

    def about(self):
        window = self.result_dialog('О приложении', 'Zaper ' + VERSION + '\nНативный GTK-интерфейс: Wayland и X11\nДвижок nfqws2 1.0.5.2\nMIT; лицензии движка включены в архив.\nHTTPS/ICMP не подтверждают работу Anti-Cheat.')
        window.set_default_size(640, 280)


def main():
    ok, _ = Gtk.init_check()
    if not ok:
        print('Не удалось открыть графический сеанс GTK. Проверьте WAYLAND_DISPLAY/DISPLAY; CLI: zaper.', file=sys.stderr)
        return 1
    app = App(Gtk.Window(), '--tray' in sys.argv, '--smoke-test' in sys.argv)
    if app.smoke: app.later(1000, app.quit)
    Gtk.main()
    return 0


if __name__ == '__main__': sys.exit(main())
