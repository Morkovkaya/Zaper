# Zaper для Linux — 3.8.1-linux.2

Нативный Linux-порт обновлён вслед за Windows Zaper 3.8.1. Один архив **Zaper-3.8.1-linux.2-universal.tar.gz** для x86_64 и ARM64/aarch64. Python CLI/Tk, официальный статический nfqws2 1.0.5.2, nftables. Функции Windows 3.8.1 перенесены с Linux-эквивалентами системной интеграции.

## Новое относительно Linux 3.6.3

- Название **Zaper**, тот же значок Z, пять вкладок и отдельное окно «Настройки запуска и трея».
- История настроек с откатом, готовые профили «Обычный» / «Игры + Discord», импорт/экспорт JSON. Windows-профили конвертируются; Windows EXE-исключения пропускаются с отчётом. Linux-исключения доменов/IP/UID сохраняются.
- Все девять стратегий и UDP-профиль `alt12-exp`: 216 комбинаций game/IPSet/strategy/preset на каждой архитектуре. Имя FACEIT не означает подтверждённую совместимость с Anti-Cheat или вход в матч.
- «Проверить и исправить runtime» использует проверенную встроенную копию. Пользовательские `*-user.txt`, настройки и обновлённый IP-список сохраняются.
- IP-обновление: параллельные HTTPS-маршруты напрямую и через proxy из окружения с отменой проигравшего, резервный GitHub API, проверка содержимого и откат файла/службы при ошибке применения. Runtime-манифест не изменяется: обновлённый список находится отдельно в `/etc/zapret2-manager/ipset-all.txt`.
- Редактор Hosts: предпросмотр предложенных записей, сохранение только по кнопке, копия исходника и проверка сторонних изменений. Повторное сохранение и несохранённые правки поддерживаются.
- ZIP диагностики с маскированием секретов и домашних путей; журнал доступен в пределах прав пользователя. График ICMP-задержки и трафика выбирает сетевой интерфейс по текущему маршруту.
- Необязательный трей: запуск скрытым, восстановление окна, включение/выключение и выход. При отсутствии поддерживаемого трея окно остаётся видимым. Все операции выполняются вне Tk-потока.

## Требования

Linux с NFQUEUE/nftables, util-linux (flock), Python **3.10+**. Tk — для GUI; curl — для HTTPS-проверок и загрузок IP/Hosts/обновлений; getent и ping — для DNS/ICMP. Для QUIC-проверки нужна сборка curl с HTTP3 (проверка отсутствующей возможности явно отмечается как непроверенная). Для административных кнопок нужны polkit/pkexec и агент авторизации рабочего окружения. systemd необязателен: без него доступен foreground-запуск. CLI использует только стандартную библиотеку Python.

Примеры зависимостей:

```sh
# Arch
sudo pacman -S python tk nftables curl polkit iproute2 iputils
# Debian / Ubuntu
sudo apt install python3 python3-tk nftables curl policykit-1 iproute2 iputils-ping
# Fedora
sudo dnf install python3 python3-tkinter nftables curl polkit iproute iputils
```

Трей требует **pystray**, Pillow и поддерживаемую панель X11 либо AppIndicator/StatusNotifierWatcher. Пример для Debian/Ubuntu: `sudo apt install python3-pystray`. Для GNOME может потребоваться расширение рабочего окружения. Наличие pystray само по себе не гарантирует поддержку трея; при невозможности проверить доступность приложение оставляет окно открытым. [Документация pystray о Linux backends](https://pystray.readthedocs.io/en/latest/usage.html#supported-backends).

## Установка и обновление

После распаковки перейдите в папку архива:

```sh
python3 zapret_manager.py check
sudo ./install.sh install
zaper-gui
# CLI с systemd:
sudo zaper start
zaper status
sudo zaper stop
# Без systemd:
sudo zaper run                 # остановка Ctrl+C
```

Для обновления предыдущей Linux-версии достаточно нового `install.sh install`. Каталог `/opt/zapret2-manager`, служба `zapret2-manager.service`, настройки `/etc/zapret2-manager` и старые команды `zapret2-manager` / `zapret2-manager-gui` сохранены. Добавлены короткие имена `zaper` / `zaper-gui`. Обновление останавливает существующую systemd-службу; после проверки включите её явно. Foreground-процесс нужно завершить перед обновлением.

Установка не запускает перехват и не включает автозапуск автоматически. Настройки панели находятся у текущего пользователя в `$XDG_CONFIG_HOME/zaper/preferences.json` (обычно `~/.config/zaper`). Автозапуск панели — отдельный XDG `.desktop` файл; автозапуск службы — отдельно через systemd. Изменение запуска службы не перезапускает её.

```sh
sudo zaper enable
sudo zaper disable
sudo ./install.sh uninstall
```

Удаление сохраняет системные настройки/историю и пользовательские настройки панели. Выключите ограничитель (`zaper proxy-stop`) перед обновлением/удалением. Отключите автозапуск панели в её настройках перед удалением; установщик от root не удаляет файлы других пользователей.

## CLI

```sh
sudo zaper configure --game udp --ipset loaded --strategy host-seq --game-udp-preset alt12-exp
sudo zaper restart
sudo zaper configure --exclude-domain example.org --exclude-ip 192.0.2.0/24 --exclude-uid 1001
sudo zaper configure --clear-exclusions
zaper profile-export --name 'Мой профиль' > profile.json
sudo zaper profile-import < profile.json
sudo zaper preset normal       # либо gaming
zaper history
sudo zaper restore НОМЕР_ИЗ_ИСТОРИИ
sudo zaper repair
sudo zaper update-ips
zaper probe
zaper monitor --target 1.1.1.1
zaper diagnose
journalctl -u zapret2-manager -b
```

CLI сохраняет/импортирует/откатывает настройки без перезапуска по умолчанию; флаг `--apply` применяет их с перезапуском только активной службы и возвращает прежние настройки при ошибке. GUI использует этот флаг. Выключенная служба остаётся выключенной. История включает исключения; каждый откат сначала сохраняет текущую конфигурацию, включая повреждённый JSON. Изменения защищены межпроцессной блокировкой.

`hosts-read`, `hosts-preview`, `hosts-save` и `diagnostics-export` — JSON-команды для GUI. Hosts-save получает текст и SHA256 исходного файла через stdin. Они никогда не принимают произвольный системный путь. ZIP возвращается в base64, а GUI записывает выбранный файл с правами обычного пользователя. История/диагностика могут содержать пользовательские домены и IP; перед передачей просмотрите архив.

IPSet: `none` — только базовые профили, `loaded` — поставляемый/обновлённый список, `any` — любой IP. Игровые профили добавляются при `loaded` или `any`. Неизвестный игровой UDP фильтруется по IP, без доменных include-фильтров. Повторяемые `--exclude-*` заменяют соответствующий список; остальные сохраняются.

## Автоподбор и диагностика

```sh
sudo zaper autotune            # все 9 стратегий, затем повторная проверка финалистов
sudo zaper tune-cancel         # из второго терминала; дождитесь отката
zaper tune-results
sudo zaper tune-recover        # вернуть состояние перед последним подбором
zaper measure                 # HTTPS-содержимое, HTTP/3 при поддержке curl, UDP STUN
zaper faceit --server 'connect 192.0.2.10:27015'
sudo zaper faceit-exclude --server 192.0.2.10:27015 --apply
sudo zaper faceit-exclude --server 192.0.2.10:27015 --remove --apply
zaper fake-list
sudo zaper configure --discord-fake ACTIVE_DISCORD_UDP.bin --game-fake ACTIVE_GAME_UDP.bin --auto-check yes --apply
```

Подбор требует работающий systemd для временного переключения стратегий. Сохраняет точные исходные настройки, историю и состояние службы, не меняет её автозапуск. Выбор учитывает обязательные HTTPS-проверки, долю успешных проб, P90/медиану и запас 15%/50 мс против случайных колебаний. Текущая стратегия — фактическая исходная конфигурация. Ошибка/отмена возвращает прежнее состояние. Независимый watchdog восстанавливает после гибели процесса; журнал восстанавливается перед следующим запуском движка после выключения питания. Незавершённый журнал запрещает другие изменения до восстановления.

STUN проверяет transaction ID/cookie/размер; CS2 A2S поддерживает challenge на том же UDP-сокете. HTTP 401/403/404/429 означает HTTPS-ответ, а не доказанный доступ в аккаунт или матч. Регионы FACEIT проверяются по ICMP. Выбранные серверы исключаются только из UDP-профилей. Поле сервера не меняет стратегию без явного нажатия исключения.

## Ограничитель прокси

```sh
# Обычным пользователем, без sudo. Сначала запустите Happ/другой локальный HTTP/SOCKS proxy.
zaper proxy-start --rate 17 --upstream 10809 --desktop manual
zaper proxy-status
zaper proxy-stop
# Если системный HTTP proxy GNOME/KDE уже указывает на 127.0.0.1:10809:
zaper proxy-start --rate 17 --desktop gnome     # либо kde
zaper proxy-recover                          # аварийное восстановление при остановленном реле
```

Лимит **1–1000 Мбит/с**, общий на все соединения, применяется к отправке; получение ответа не ограничивается. Реле слушает только `127.0.0.1:10819`, передаёт протокол без разбора и работает с HTTP CONNECT/SOCKS, если исходный порт поддерживает этот протокол. В ручном режиме укажите адрес реле в приложении; уже запущенные программы и приложения, игнорирующие desktop proxy, сами не переключаются. Это ограничитель прокси-трафика, а не всего интерфейса/VPN-туннеля.

GNOME использует GSettings/dconf (`gsettings` из glib, schemas и dconf), KDE — kreadconfig/kwriteconfig 5 или 6 и D-Bus KIO (`dbus-send`). [GNOME proxy configuration](https://wiki.gnome.org/DevGnomeOrg%282f%29Gnome3PortingGuide%282f%29ProxyConfiguration.html), [KDE proxy](https://docs.kde.org/stable_kf6/en/kio-extras/kcontrol6/proxy/proxy.pdf). Режим выбирается явно; окружения Xfce/Sway/Hyprland и прочие используют ручной адрес. До переключения записывается снимок; штатная остановка, watchdog после SIGKILL и отдельный XDG-вход восстановления возвращают прежние значения. Если пользователь выбрал другой proxy, он сохраняется. Журнал и логи — `$XDG_STATE_HOME/zaper/proxy` (обычно `~/.local/state/zaper/proxy`), права 0700/0600. Закрытие панели не выключает отдельно запущенное реле.

## Обновление приложения

Вкладка «Обслуживание» → «Релизы / обновление приложения» проверяет Linux-релизы и скачивает архив с проверкой размера/SHA256 из GitHub API. Для приватного репозитория введите токен Contents:read; он существует только в окне/запросе и не передаётся в командной строке. Через CLI JSON `{"token":"..."}` подаётся на stdin команд `app-updates` / `app-download --directory КАТАЛОГ`; в публичном репозитории токен не нужен. Страница Releases и установка вручную также доступны. При ошибке или неверной сумме прежний файл остаётся целым.

## Переносимость и границы

Никаких имён сетевых карт, аппаратных драйверов, дисков или boot-настроек. Менеджер создаёт только свою `inet zapret2_manager`, очередь **200**, fwmark **0x40000000** и ct mark **0x20000000** для исключений UID. Эти значения не должны конфликтовать с другими утилитами. Чужие таблицы сохраняются; занятая очередь или чужая одноимённая таблица запрещают запуск.

Работа с локальными IPv4/IPv6 соединениями, не режим роутера. Первые UDP-пакеты всех портов передаются движку для распознавания STUN/Discord, модификация определяется профилем. Лимит первых 12 пакетов зависит от включённого системой conntrack accounting; приложение не меняет этот sysctl. Existing VPN/drop/flowtable offload могут влиять на результат.

Queue bypass сохраняет передачу при отсутствии движка. При штатной остановке/ошибке/сбое собственная таблица удаляется; после SIGKILL или отключения питания оставшаяся собственная таблица очищается при следующем старте.

Автоподбор с rollback, proxy upload limiter и проверка/скачивание обновлений перенесены. Установка скачанного архива выполняется штатным `install.sh install`; токены GitHub не сохраняются. EXE-иконки и Windows Task Scheduler/SCM заменены Linux-подходами: IP/домены/UID, XDG и необязательная systemd-служба. Пробы не подтверждают голос/трансляцию Discord, реальный FACEIT-матч, Anti-Cheat или работу у конкретного провайдера.

## Сборка и проверки

Для упаковки — Python 3.12+, для установленного приложения — Python 3.10+:

```sh
python3 scripts/package-linux.py
python3 -m unittest discover -s dist/Zaper-3.8.1-linux.2/tests -p 'test_*.py' -v
xvfb-run -a python3 dist/Zaper-3.8.1-linux.2/tests/gui_smoke.py
python3 scripts/test-arm64.py dist/Zaper-3.8.1-linux.2
sudo unshare --net sh -c 'ip link set lo up; ZAPRET_ISOLATED_TEST=1 python3 dist/Zaper-3.8.1-linux.2/tests/integration.py'
```

Тест установки/обновления выполняйте только в одноразовом контейнере/VM. GitHub Actions проверяет предыдущий архив Linux, strict umask, реальные пакеты и трей. ARM64 проверяется под QEMU; отдельная ARM-машина и полноценная загрузка systemd не моделируются. Контейнеры используют ядро хоста. Архив содержит лицензии, исходники движка, контрольные суммы и копию восстановления.
