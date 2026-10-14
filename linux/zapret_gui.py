#!/usr/bin/env python3
"""Unprivileged Tk frontend; only fixed installed commands request elevation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk

INSTALLED = Path('/usr/local/bin/zapret2-manager')
LOCAL = Path(__file__).resolve().with_name('zapret_manager.py')


class App:
    def __init__(self, root):
        self.root = root
        root.title('Zapret 2 Manager — Linux 3.6.3')
        root.geometry('850x630')
        root.minsize(680, 540)
        self.busy = False
        self.results = __import__('queue').Queue()
        self.status = tk.StringVar(value='Проверка состояния…')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#141b2b')
        style.configure('TLabel', background='#141b2b', foreground='#edf2ff')
        style.configure('Title.TLabel', font=('Sans', 22, 'bold'))
        style.configure('TButton', padding=9)
        main = ttk.Frame(root, padding=24)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='ZAPRET 2 / Linux', style='Title.TLabel').pack(anchor='w')
        ttk.Label(main, textvariable=self.status).pack(anchor='w', pady=(8, 15))
        row = ttk.Frame(main)
        row.pack(fill='x')
        self.buttons = []
        for label, command in [('Включить', 'start'), ('Выключить', 'stop'), ('Перезапустить', 'restart')]:
            self.button(row, label, lambda cmd=command: self.run([cmd], privileged=True)).pack(side='left', padx=(0, 8))
        tabs = ttk.Notebook(main)
        tabs.pack(fill='both', expand=True, pady=16)
        settings = ttk.Frame(tabs, padding=16)
        diagnostics = ttk.Frame(tabs, padding=16)
        tabs.add(settings, text='Настройки')
        tabs.add(diagnostics, text='Диагностика')
        self.game = tk.StringVar(value='off')
        self.ipset = tk.StringVar(value='none')
        self.strategy = tk.StringVar(value='current')
        for n, (label, variable, values) in enumerate([
            ('Обработка игр', self.game, ('off', 'tcp', 'udp', 'all')),
            ('Область IPSet', self.ipset, ('none', 'loaded', 'any')),
            ('Стратегия TLS', self.strategy, ('current', 'split', 'disorder'))]):
            ttk.Label(settings, text=label).grid(row=n, column=0, sticky='w', pady=7)
            ttk.Combobox(settings, textvariable=variable, values=values, state='readonly').grid(row=n, column=1, sticky='ew', padx=14)
        settings.columnconfigure(1, weight=1)
        ttk.Label(settings, text='Режим игр работает при IPSet loaded или any.\nИсключения доменов, IP/CIDR и UID доступны через CLI.').grid(row=3, column=0, columnspan=2, sticky='w', pady=12)
        self.button(settings, 'Сохранить и проверить', self.save).grid(row=4, column=0, columnspan=2, sticky='w')
        auto = ttk.Frame(settings)
        auto.grid(row=5, column=0, columnspan=2, sticky='w', pady=10)
        self.button(auto, 'Включить автозапуск', lambda: self.run(['enable'], privileged=True)).pack(side='left', padx=(0, 8))
        self.button(auto, 'Отключить автозапуск', lambda: self.run(['disable'], privileged=True)).pack(side='left')
        self.button(diagnostics, 'Проверить конфигурацию', lambda: self.run(['check'])).pack(anchor='w', pady=6)
        self.button(diagnostics, 'Проверить зависимости', lambda: self.run(['diagnose'])).pack(anchor='w', pady=6)
        ttk.Label(diagnostics, text='HTTPS и вход в матч зависят от провайдера и сервисов.\nFACEIT Anti-Cheat для Linux этим портом не предоставляется.').pack(anchor='w', pady=12)
        self.log = tk.Text(main, height=7, bg='#0c1220', fg='#cbd7f0', wrap='word', state='disabled')
        self.log.pack(fill='x')
        self.run(['show'], settings=True)
        root.after(100, self.poll)

    def button(self, parent, text, action):
        button = ttk.Button(parent, text=text, command=action)
        self.buttons.append(button)
        return button

    def save(self):
        self.run(['configure', '--game', self.game.get(), '--ipset', self.ipset.get(), '--strategy', self.strategy.get()], privileged=True)

    def run(self, args, privileged=False, settings=False):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.state(['disabled'])
        def worker():
            try:
                if privileged:
                    if not INSTALLED.exists():
                        raise RuntimeError('Сначала установите приложение: sudo ./install.sh install')
                    if not shutil.which('pkexec'):
                        raise RuntimeError('Нет polkit/pkexec. Выполните команду через sudo в терминале.')
                    command = ['pkexec', str(INSTALLED)] + args
                else:
                    command = ['/usr/bin/python3', '-I', str(LOCAL)] + args
                result = subprocess.run(command, capture_output=True, text=True, timeout=120)
                self.results.put((settings, result.returncode, result.stdout + result.stderr))
            except Exception as exc:
                self.results.put((False, 1, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            settings, code, output = self.results.get_nowait()
        except __import__('queue').Empty:
            pass
        else:
            self.busy = False
            for button in self.buttons:
                button.state(['!disabled'])
            if settings and code == 0:
                data = json.loads(output)
                for name in ('game', 'ipset', 'strategy'):
                    getattr(self, name).set(data[name])
            else:
                self.log.configure(state='normal')
                self.log.insert('end', ('Ошибка: ' if code else '') + output.strip() + '\n')
                self.log.see('end')
                self.log.configure(state='disabled')
            try:
                result = subprocess.run(['/usr/bin/python3', '-I', str(LOCAL), 'status'], capture_output=True, text=True, timeout=2)
                self.status.set('Состояние: ' + (result.stdout.strip() or 'неизвестно'))
            except Exception:
                self.status.set('Состояние недоступно')
        self.root.after(150, self.poll)


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    if '--smoke-test' in sys.argv:
        root.after(800, root.destroy)
    root.mainloop()
