#!/usr/bin/env python3
"""Zaper desktop frontend: all commands run in workers, Tk stays responsive."""
import base64
import dataclasses
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

HOME = Path(__file__).resolve().parent
sys.path.insert(0, str(HOME))
from zaper_version import APP_VERSION, VERSION
from zaper_preferences import Preferences, load as load_preferences, save as save_preferences

INSTALLED = Path('/usr/local/bin/zapret2-manager')
LOCAL = HOME / 'zapret_manager.py'
STRATEGIES = ('current', 'udp-2', 'udp-6', 'split', 'disorder', 'fake-md5', 'fake-ts', 'host-ts', 'host-seq')


class App:
    def __init__(self, root, start_in_tray=False, smoke=False):
        self.root, self.smoke = root, smoke
        self.busy = False
        self.buttons = []
        self.events = queue.Queue()
        self.tray = None
        self.closed = False
        self.settings_data = {}
        self.samples = []
        try:
            self.preferences = load_preferences()
        except (ValueError, OSError, TypeError):
            self.preferences = Preferences()
        root.title('Zaper — Linux ' + APP_VERSION)
        root.geometry('960x800')
        root.minsize(780, 730)
        self.image = tk.PhotoImage(file=str(HOME / 'zaper.png'))
        root.iconphoto(True, self.image)
        style = ttk.Style(root)
        style.theme_use('clam')
        for kind in ('TFrame', 'TLabel', 'TCheckbutton'):
            style.configure(kind, background='#141b2b', foreground='#edf2ff')
        style.configure('Title.TLabel', font=('Sans', 22, 'bold'))
        style.configure('TButton', padding=8, background='#27364f', foreground='#edf2ff')
        style.map('TButton', background=[('active', '#355078'), ('disabled', '#202a3c')], foreground=[('disabled', '#8390a8')])
        style.configure('TNotebook', background='#141b2b')
        style.configure('TNotebook.Tab', background='#27364f', foreground='#edf2ff', padding=(12, 6))
        style.map('TNotebook.Tab', background=[('selected', '#355078')])
        main = ttk.Frame(root, padding=20)
        main.pack(fill='both', expand=True)
        header = ttk.Frame(main)
        header.pack(fill='x')
        ttk.Label(header, image=self.image).pack(side='left', padx=(0, 12))
        ttk.Label(header, text='Zaper', style='Title.TLabel').pack(side='left')
        self.status = tk.StringVar(value='Проверка состояния…')
        ttk.Label(main, textvariable=self.status).pack(anchor='w', pady=(8, 10))
        controls = ttk.Frame(main)
        controls.pack(fill='x')
        for label, command in (('Включить', 'start'), ('Выключить', 'stop'), ('Перезапустить', 'restart')):
            self.button(controls, label, lambda cmd=command: self.run([cmd], privileged=True)).pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='Выход из панели', command=self.quit).pack(side='right')
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill='both', expand=True, pady=12)
        settings = self.page('Настройки')
        self.game, self.ipset, self.strategy, self.udp = (tk.StringVar(value=x) for x in ('off', 'none', 'current', 'native'))
        for n, (label, variable, values) in enumerate((
                ('Обработка игр', self.game, ('off', 'tcp', 'udp', 'all')),
                ('Область IPSet', self.ipset, ('none', 'loaded', 'any')),
                ('Стратегия TLS/UDP', self.strategy, STRATEGIES),
                ('Игровой UDP-профиль', self.udp, ('native', 'alt12-exp')))):
            ttk.Label(settings, text=label).grid(row=n, column=0, sticky='w', pady=7)
            ttk.Combobox(settings, textvariable=variable, values=values, state='readonly').grid(row=n, column=1, sticky='ew', padx=12)
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text='Игровой режим работает при IPSet loaded/any. Сохранение не перезапускает движок.').grid(row=4, column=0, columnspan=2, sticky='w', pady=10)
        self.button(settings, 'Сохранить и проверить', self.save).grid(row=5, column=0, sticky='w', pady=7)
        self.button(settings, 'Исключения доменов / IP / UID', self.exclusions).grid(row=5, column=1, sticky='w')
        self.button(settings, 'Настройки запуска и трея', self.launch_dialog).grid(row=6, column=0, columnspan=2, sticky='w', pady=7)
        profiles = self.page('Профили и история')
        for label, action in (
                ('Обычный профиль', lambda: self.run(['preset', 'normal'], True, after=self.refresh)),
                ('Игры + Discord', lambda: self.run(['preset', 'gaming'], True, after=self.refresh)),
                ('Экспорт JSON-профиля', self.export_profile), ('Импорт JSON-профиля', self.import_profile),
                ('История настроек / откат', self.history_dialog)):
            self.button(profiles, label, action).pack(anchor='w', pady=7)
        ttk.Label(profiles, text='Каждое сохранение создаёт запись истории. После отката или импорта нужен перезапуск.\nWindows-профили конвертируются; EXE-исключения пропускаются с отчётом.').pack(anchor='w', pady=12)
        diagnostics = self.page('Диагностика')
        for label, command in (('Проверить конфигурацию', 'check'), ('Соединения сервисов (HTTPS)', 'probe'),
                               ('Проверить зависимости', 'diagnose')):
            self.button(diagnostics, label, lambda cmd=command: self.run([cmd])).pack(anchor='w', pady=5)
        self.button(diagnostics, 'Экспорт ZIP диагностики', self.export_diagnostics).pack(anchor='w', pady=5)
        self.target = tk.StringVar(value='1.1.1.1')
        row = ttk.Frame(diagnostics); row.pack(fill='x', pady=6)
        ttk.Entry(row, textvariable=self.target, width=22).pack(side='left', padx=(0, 8))
        self.button(row, 'Измерить задержку / нагрузку', lambda: self.run(['monitor', '--target', self.target.get()], after=self.draw_sample)).pack(side='left')
        self.chart = tk.Canvas(diagnostics, height=95, bg='#0c1220', highlightthickness=0)
        self.chart.pack(fill='x', pady=6)
        ttk.Label(diagnostics, text='Интерфейс выбирается по текущему маршруту. ICMP/HTTPS не подтверждают матч или Anti-Cheat.').pack(anchor='w')
        maintenance = self.page('Обслуживание')
        for label, command in (('Проверить и исправить runtime', 'repair'), ('Обновить IP-список', 'update-ips')):
            self.button(maintenance, label, lambda cmd=command: self.run([cmd], True)).pack(anchor='w', pady=7)
        self.button(maintenance, 'Редактор системного Hosts', self.hosts_dialog).pack(anchor='w', pady=7)
        self.button(maintenance, 'Релизы / обновление приложения', lambda: webbrowser.open('https://github.com/ivanmorkovka1-ux/zaper2/releases')).pack(anchor='w', pady=7)
        self.button(maintenance, 'О приложении', self.about).pack(anchor='w', pady=7)
        ttk.Label(main, text='Журнал операций').pack(anchor='w', pady=(0, 4))
        self.log = tk.Text(main, height=6, bg='#0c1220', fg='#cbd7f0', wrap='word', state='disabled')
        self.log.pack(fill='x')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        root.after(80, self.poll)
        if not smoke:
            root.after(200, lambda: self.setup_tray(start_in_tray or self.preferences.start_in_tray))
        root.after(3000, self.refresh_status)

    def page(self, title):
        page = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(page, text=title)
        return page

    def button(self, parent, title, callback):
        button = ttk.Button(parent, text=title, command=callback)
        self.buttons.append(button)
        return button

    def write(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text.rstrip() + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def run(self, args, privileged=False, after=None, payload=None, quiet=False, background=False):
        if self.busy and not background:
            return
        if not background:
            self.busy = True
            for button in self.buttons:
                button.state(['disabled'])
        def worker():
            try:
                if privileged:
                    if not INSTALLED.exists() or not shutil.which('pkexec'):
                        raise RuntimeError('Нужны установленный Zaper и polkit/pkexec; команды также доступны через sudo в терминале')
                    command = ['pkexec', str(INSTALLED)] + args
                else:
                    command = ['/usr/bin/python3', '-I', str(LOCAL)] + args
                result = subprocess.run(command, input=payload, capture_output=True, text=True, timeout=120)
                self.events.put(('result', result.returncode, result.stdout + result.stderr, after, quiet, background))
            except Exception as exc:
                self.events.put(('result', 1, str(exc), None, False, background))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        for _ in range(20):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == 'action':
                self.tray_action(event[1]); continue
            if event[0] == 'tray-ready':
                if event[1]: self.root.withdraw()
                continue
            _, code, output, callback, quiet, background = event
            if not background:
                self.busy = False
                for button in self.buttons: button.state(['!disabled'])
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
        self.root.after(80, self.poll)

    def refresh(self, output=None):
        self.run(['show'], after=self.loaded, quiet=True)

    def loaded(self, output):
        self.settings_data = json.loads(output)
        for key, variable in (('game', self.game), ('ipset', self.ipset), ('strategy', self.strategy), ('game_udp_preset', self.udp)):
            variable.set(self.settings_data.get(key, 'native'))

    def refresh_status(self):
        if self.closed: return
        def update(output):
            label = {'active': 'включён', 'running': 'включён', 'inactive': 'выключен', 'stopped': 'выключен', 'failed': 'ошибка'}.get(output.strip(), output.strip())
            self.status.set('Состояние: ' + label)
        self.run(['status'], after=update, quiet=True, background=True)
        self.root.after(3000, self.refresh_status)

    def save(self):
        self.run(['configure', '--game', self.game.get(), '--ipset', self.ipset.get(), '--strategy', self.strategy.get(), '--game-udp-preset', self.udp.get()], True)

    def exclusions(self):
        def opened(output):
            data = json.loads(output)
            dialog = tk.Toplevel(self.root); dialog.title('Zaper — исключения'); dialog.transient(self.root)
            fields = {}
            for n, (key, title) in enumerate((('domains', 'Домены через запятую'), ('ips', 'IP/CIDR через запятую'), ('uids', 'UID через запятую'))):
                ttk.Label(dialog, text=title).grid(row=n, column=0, padx=12, pady=10)
                variable = tk.StringVar(value=', '.join(map(str, data.get('excluded_' + key, []))))
                ttk.Entry(dialog, textvariable=variable, width=42).grid(row=n, column=1, padx=12)
                fields[key] = variable
            def save():
                args = ['configure', '--clear-exclusions']
                for key, variable in fields.items():
                    for value in variable.get().split(','):
                        if value.strip(): args += ['--exclude-' + {'domains': 'domain', 'ips': 'ip', 'uids': 'uid'}[key], value.strip()]
                self.run(args, True); dialog.destroy()
            ttk.Button(dialog, text='Сохранить', command=save).grid(row=3, column=0, columnspan=2, pady=12)
        self.run(['show'], after=opened, quiet=True)

    def export_profile(self):
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            self.run(['profile-export'], after=lambda output: Path(path).write_text(output), quiet=True)

    def import_profile(self):
        path = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if path:
            try:
                if Path(path).stat().st_size > 1024 * 1024: raise ValueError('Профиль больше 1 МиБ')
                self.run(['profile-import'], True, payload=Path(path).read_text(), after=self.refresh)
            except Exception as exc: self.write('Ошибка: ' + str(exc))

    def history_dialog(self):
        def opened(output):
            rows = json.loads(output)
            dialog = tk.Toplevel(self.root); dialog.title('Zaper — история'); dialog.geometry('650x380')
            listing = tk.Listbox(dialog)
            listing.pack(fill='both', expand=True, padx=12, pady=12)
            for row in rows: listing.insert('end', row['utc'] + ' — ' + row['reason'])
            def restore():
                selection = listing.curselection()
                if selection:
                    self.run(['restore', rows[selection[0]]['id']], True, after=self.refresh)
                    dialog.destroy()
            ttk.Button(dialog, text='Вернуть выбранные настройки', command=restore).pack(pady=12)
        self.run(['history'], after=opened, quiet=True)

    def export_diagnostics(self):
        path = filedialog.asksaveasfilename(defaultextension='.zip', filetypes=[('ZIP', '*.zip')])
        if path:
            self.run(['diagnostics-export'], after=lambda output: Path(path).write_bytes(base64.b64decode(json.loads(output)['zip_base64'])), quiet=True)

    def hosts_dialog(self):
        def opened(output):
            current = json.loads(output)
            dialog = tk.Toplevel(self.root); dialog.title('Zaper — Hosts'); dialog.geometry('850x620')
            ttk.Label(dialog, text='Загрузка меняет только предпросмотр. Перед сохранением — резервная копия и проверка сторонних изменений.').pack(padx=12, pady=12)
            editor = tk.Text(dialog, wrap='none'); editor.pack(fill='both', expand=True, padx=12)
            editor.insert('1.0', current['text'])
            row = ttk.Frame(dialog); row.pack(padx=12, pady=12)
            def preview(output):
                proposed = json.loads(output)
                # Do not reset expected hash: external changes must still be rejected.
                editor.delete('1.0', 'end'); editor.insert('1.0', proposed['text'])
            self.button(row, 'Загрузить предложенные', lambda: self.run(['hosts-preview'], after=preview, quiet=True, payload=json.dumps({'text': editor.get('1.0', 'end-1c')}))).pack(side='left', padx=6)
            def save():
                text = editor.get('1.0', 'end-1c')
                def saved(output):
                    current['sha256'] = hashlib.sha256(text.encode()).hexdigest()
                self.run(['hosts-save'], True, payload=json.dumps({'text': text, 'sha256': current['sha256']}), after=saved)
            self.button(row, 'Сохранить', save).pack(side='left', padx=6)
            dialog.bind('<Destroy>', lambda event: self.buttons.__setitem__(slice(None), [b for b in self.buttons if b.winfo_exists()]) if event.widget == dialog else None)
        self.run(['hosts-read'], after=opened, quiet=True)

    def draw_sample(self, output):
        data = json.loads(output); self.samples.append(data); self.samples = self.samples[-25:]
        self.chart.delete('all')
        self.chart.create_text(10, 12, anchor='w', fill='#edf2ff', text=f"{data['interface']}: RX {data['rx_mbps']:.2f} / TX {data['tx_mbps']:.2f} Мбит/с; ping {data['latency_ms']} мс")
        values = [(i, x['latency_ms']) for i, x in enumerate(self.samples) if x['latency_ms'] is not None]
        maximum = max([x[1] for x in values] + [1])
        points = [point for i, value in values for point in (12 + i * 25, 86 - value / maximum * 50)]
        if len(points) >= 4: self.chart.create_line(*points, fill='#68b5ff', width=2)

    def launch_dialog(self):
        dialog = tk.Toplevel(self.root); dialog.title('Zaper — настройки запуска и трея'); dialog.transient(self.root)
        fields = {}
        for n, (key, label) in enumerate((('start_in_tray', 'Запускать панель в трее (при доступном трее)'), ('panel_autostart', 'Автозапуск панели при входе пользователя'), ('notify_errors', 'Уведомления об ошибках'))):
            variable = tk.BooleanVar(value=getattr(self.preferences, key)); fields[key] = variable
            ttk.Checkbutton(dialog, text=label, variable=variable).grid(row=n, column=0, columnspan=2, sticky='w', padx=16, pady=10)
        ttk.Label(dialog, text='Автозапуск службы (отдельно от панели; без перезапуска):').grid(row=3, column=0, columnspan=2, padx=16, pady=8)
        self.button(dialog, 'Включить службу при загрузке', lambda: self.run(['enable'], True)).grid(row=4, column=0, padx=8)
        self.button(dialog, 'Отключить автозапуск службы', lambda: self.run(['disable'], True)).grid(row=4, column=1, padx=8)
        def save():
            try:
                preferences = Preferences(**{key: value.get() for key, value in fields.items()})
                save_preferences(preferences); self.preferences = preferences; self.write('Настройки панели сохранены'); dialog.destroy()
            except Exception as exc: self.write('Ошибка: ' + str(exc))
        ttk.Button(dialog, text='Сохранить настройки панели', command=save).grid(row=5, column=0, columnspan=2, pady=16)
        dialog.bind('<Destroy>', lambda event: self.buttons.__setitem__(slice(None), [b for b in self.buttons if b.winfo_exists()]) if event.widget == dialog else None)

    def setup_tray(self, hide=False):
        try:
            from zaper_tray import Tray
            self.tray = Tray(lambda action: self.events.put(('action', action)), HOME / 'zaper.png', lambda: self.events.put(('tray-ready', hide)))
        except Exception as exc:
            if hide: self.write('Трей недоступен — окно оставлено видимым: ' + str(exc))

    def tray_action(self, action):
        if action == 'show': self.root.deiconify(); self.root.lift()
        elif action == 'quit': self.quit()
        else: self.run([action], True)

    def close(self):
        if self.busy:
            self.write('Дождитесь завершения операции; панель остаётся доступной')
        elif self.tray:
            self.root.withdraw()
        else:
            self.quit()

    def quit(self):
        if self.busy and not self.smoke:
            self.write('Дождитесь завершения операции'); return
        self.closed = True
        if self.tray: self.tray.stop()
        self.root.destroy()

    def about(self):
        messagebox.showinfo('О приложении Zaper', 'Zaper ' + VERSION + '\nНативный Linux-порт для x86_64/ARM64\nДвижок nfqws2 1.0.5.2\nMIT; лицензии движка включены в архив.\nHTTPS/ICMP не подтверждают работу Anti-Cheat.')


if __name__ == '__main__':
    root = tk.Tk()
    smoke = '--smoke-test' in sys.argv
    app = App(root, '--tray' in sys.argv, smoke)
    if smoke: root.after(1000, app.quit)
    root.mainloop()
