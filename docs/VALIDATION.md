# Release and install automation — 2026-10-16

Linux 3.8.1-linux.4 adds distribution dependency installation and a privileged update action. CI publishes missing release versions only after both platform jobs succeed, from their exact uploaded artifacts; existing stable releases remain immutable and Linux uses latest=false.

Initial implementation c74e24c passed [push CI](https://github.com/Morkovkaya/Zaper/actions/runs/38874020190) and [PR CI](https://github.com/Morkovkaya/Zaper/actions/runs/38874063189): Windows installer/self/integration checks, 62 packaged Linux tests, six publisher tests, 216 configurations on each architecture, native X11 and Wayland/HiDPI/tray, isolated real packet lifecycle and tuning rollback, legacy upgrades, staged install/uninstall, injected installation failure rollback and complete root updater fixture. The root updater fixture replaces GitHub network responses with the actual packaged bytes; real digest, safe extraction, dependency preflight and installation run in the disposable runner. Service state in the installer fault fixture uses a fake systemctl; packet lifecycle tests independently use the real engine.

The follow-up adds an injected service-start failure and checks restoration of the old running service. Arch dependency package names were resolved read-only against the host package database. Dependency selection for Fedora/openSUSE is covered by command-plan tests; a real install on those distributions has not been exercised. First installation remains stopped; upgrades preserve service state, settings and user lists. Rollback covers reported install/verify/service-start failures, not power-loss recovery. No application installation, system packages, network/desktop proxy or boot changes were made on the portable Arch host.

---

# Нативные Wayland и X11 — Linux 3.8.1-linux.3 (16 октября 2026)

GTK 3 заменяет Tk; приложение работает нативно в Wayland без XWayland и сохраняет X11. StatusNotifierItem/DBusMenu реализованы через Gio, без pystray/Pillow/AppIndicator; X11 также поддерживает встроенный Gtk.StatusIcon. В Wayland нет X11 API-пути. Окно скрывается после подтверждения хоста/регистрации, возвращается при потере хоста; поддерживается activation token от панели. Автозапуск панели учитывает отдельный start_in_tray.

[Успешная полная сборка реализации](https://github.com/Morkovkaya/Zaper/actions/runs/38868552527), `ec41685582ce8706f11ef3abd1fbb6ab5071ec18`:

- 56 backend-тестов без пропусков, 216 x86_64 и 216 ARM64/QEMU конфигураций плюс UDP-фейки.
- GUI smoke под X11/Xvfb и GdkWaylandDisplay: пять вкладок, все диалоги и native file chooser, параметры сохранения, draft/SHA Hosts, export/import JSON, прогресс, график, отзывчивость и завершение.
- Headless Weston при DISPLAY unset; output scale 1 и 2 проверены реальным get_scale_factor. XWayland не запускается. Дополнительно — Weston с виртуальным input-seat поверх Xvfb, клиент всё равно Wayland и DISPLAY unset.
- Реальный D-Bus протокол StatusNotifierItem/DBusMenu: регистрация, метаданные/иконка/меню, действие «Открыть», скрытие/возврат/выход, исчезновение хоста и потеря watcher. Отдельно реальный X11 embedded tray.
- Настоящие IPv4/IPv6 NFQUEUE-пакеты, автоподбор/rollback/watchdog, proxy backends GNOME/KDE и миграции с 3.6.3-linux.1, 3.8.1-linux.1 и последнего Tk-релиза 3.8.1-linux.2.
- Windows job прошёл; Windows-исходники и релиз не меняются.

Локально дополнительно проверен настоящий KDE Wayland-сеанс Arch/Python 3.14 с DISPLAY удалённым: окно, диалоги, scale 2, регистрация и завершение трея. Cairo для QA установлен только в venv проекта; системные зависимости, compositor/драйверы/сеть/Hosts/proxy не перенастраивались. GTK layout всех пяти вкладок проверен по снимкам реального Wayland-клиента в тестовом compositor. Headless backend Weston без input-seat пишет предупреждения Gdk; проверки с виртуальным seat и настоящим KDE дополняют этот случай.

Финальный релиз берётся из успешного CI main после слияния. Точный коммит/CI и SHA256 приведены в Release. Позднее менялись только плотность GTK-формы, первоначальное чтение статуса и документация.

Зависимости GUI теперь GTK 3 + PyGObject + Cairo, CLI остаётся на стандартной библиотеке. Полный GNOME-сеанс не тестировался; без расширения StatusNotifier окно остаётся видимым. ARM64 — QEMU; физическая ARM-машина, конкретный провайдер, Discord-звонок и игровой матч не подтверждены.

Предыдущие отчёты ниже исторические.

---

# Финальная проверка Linux 3.8.1-linux.2

[Полный успешный CI](https://github.com/Morkovkaya/Zaper/actions/runs/38754541703), исходный коммит `7dc84e4cc3d0ca3449b89e83b17f798c4f043c35`: **56 тестов без пропусков**, Windows и Linux jobs успешны. К перечисленным ниже проверкам добавлены определение пользовательского proxy без изменения его значений, сериализация установщика с операциями обслуживания и обновление с обоих опубликованных Linux-архивов — 3.6.3-linux.1 и 3.8.1-linux.1. Протестированы сохранение настроек/пользовательских списков, отказ установки при занятой блокировке, repair и удаление при umask 077.

Финальный Linux-архив публикуется из успешной сборки main после слияния PR; точный коммит, CI и контрольные суммы приведены в GitHub Release. Этот отчёт и план — документация; после указанной реализации менялась только документация и завершающий перевод строки.

---

# Linux 3.8.1-linux.2 — завершение переноса

Перенесены оставшиеся функции Windows 3.8.1: автоподбор девяти стратегий с повторной проверкой финалистов, отменой и восстановлением; общий ограничитель отправки через локальный прокси; расширенная диагностика HTTPS/HTTP3/STUN/FACEIT/A2S; выбор UDP-фейков и серверных исключений; проверка/скачивание Linux-обновления с SHA256. Сохранение в GUI применяет настройки транзакционно и сохраняет прежнее состояние службы.

[Успешный полный CI реализации](https://github.com/Morkovkaya/Zaper/actions/runs/38753731505) (`eda0bfe23d719f6e6141b5170aba0e7a8a95453c`):

- **55 тестов**, без пропусков; по 216 конфигураций настоящего x86_64/ARM64 движка, дополнительно все встроенные UDP-файлы и серверные исключения.
- Настоящие IPv4/IPv6-пакеты через NFQUEUE, GUI/пять вкладок/X11-трей, установка/удаление и обновление старого 3.6.3-архива при umask 077.
- Автоподбор с настоящим nfqws2: девять стратегий, финалисты, отмена и сохранение исходного running/stopped. Результаты сети в этой проверке детерминированы локальным fixture, а переключения движка настоящие.
- Принудительное убийство процесса подбора: независимый watchdog вернул точные байты настроек и прежнее состояние службы (systemctl заменён изолированным fixture).
- Настоящие параллельные TCP-передачи: общий upload 1 Мбит/с, неограниченный download, half-close и завершение клиентов. Локальные HTTP/STUN/A2S fixtures, отмена subprocess, неверные контрольные суммы.
- Реальные GNOME GSettings/dconf и KDE KConfig в отдельном D-Bus-сеансе: start/stop/SIGKILL и восстановление значений. Полноценный вход в GNOME/Plasma не моделировался.
- Windows installer/self/integration проверки прошли. C# исходники не изменены; сохраняется ранее проверенная правка Windows repair ZIP в build.ps1.

Локально дополнительно проверены Arch/Python 3.14, GUI и реальный X11-трей в Debian-контейнере, приватный GitHub API (токен не выводился/не сохранялся), watchdog и реальные переключения движка. Основной Arch, его сеть/Hosts/proxy/драйверы/boot-настройки не менялись.

Границы платформ: автоподбор использует systemd; без systemd доступен foreground-движок и ручной выбор стратегии. Desktop proxy применяется GNOME/KDE-приложениями, которые его учитывают; в других окружениях используется ручной локальный адрес. HTTP3 проверяется только при наличии этой возможности у curl, иначе явно отмечается unknown. Windows EXE-исключения заменены Linux UID/IP/доменами, не эквивалентны выбору отдельного EXE среди процессов одного UID. ARM64 — QEMU; вход в матч/Anti-Cheat/Discord-звонок и конкретный провайдер не подтверждены.

Предыдущие отчёты ниже исторические; отметки «не перенесено» относятся к прежним релизам.

---

# Проверки Zaper 3.8.1-linux.1 — 15 октября 2026

Проверенный исходный коммит: `717dd1d546d3aae01a58364ddc57c34badfcb60f`.
[Полный успешный CI](https://github.com/Morkovkaya/Zaper/actions/runs/38750359140).
Релизный архив взят непосредственно из артефакта linux-universal этого запуска.
[Опубликованный prerelease](https://github.com/Morkovkaya/Zaper/releases/tag/v3.8.1-linux.1) скачан повторно; SHA256 совпал: `e448446be3bee1a528fac84e2b43c5a802d8c8bfda83bd2b001fd9ed21ef9854`.

- 32 теста: настройки и история, импорт Windows/Linux JSON, откат повреждённой конфигурации, блокировки, Hosts с конфликтами и резервной копией, HTTPS/IPSet fallback, восстановление runtime и редактирование диагностики.
- Все 216 комбинаций настроек приняты настоящим x86_64 движком; все 216 ARM64 — настоящим ARM64 движком под QEMU.
- GUI под Xvfb: четыре вкладки, профили, исключения, Hosts, график, отзывчивость при фоновых операциях. Настоящий X11-трей: скрытие, возврат окна, закрытие в трей и завершение дочернего процесса; при недоступном трее окно остаётся доступным.
- Настоящие IPv4/IPv6 TCP/UDP-пакеты через NFQUEUE в изолированной сети: запуск/остановка, запрет второго экземпляра, очистка после сбоя, сохранение чужих nftables-таблиц.
- Установка, обновление с опубликованной 3.6.3-linux.1 и восстановление runtime при umask 077: настройки и пользовательские списки сохранены. Удаление сохраняет настройки.
- Windows сборка и проверки установщика, включая convenience integration, прошли. Найдена и исправлена упаковка repair ZIP: пути внутри архива теперь используют `/`. C# исходники основного приложения не менялись. Существующий Windows-релиз не заменён.

Порт добавляет профили/историю, ремонт runtime, обновление IP-списка, Hosts, ZIP диагностики, график, XDG-автозапуск и необязательный трей. Сохраняет старые имена службы/настроек и добавляет команды zaper/zaper-gui.

Границы: предварительный Linux-релиз; auto-tune и proxy upload limiter пока отсутствуют. ARM64 проверен через QEMU, загрузка ОС с systemd не моделировалась. Нет подтверждения обхода DPI конкретного провайдера, Discord/FACEIT/Anti-Cheat. Тесты не меняли сеть, Hosts, драйверы или загрузчик основного Arch. Подробности — linux/README.md.

## Исторические проверки 3.6.3

Ниже сохранён отчёт предыдущего выпуска; его ограничения относятся к 3.6.3.

# Проверки релизов — 14 октября 2026

## Windows 3.6.3

Релиз собран из неизменённого коммита `9561c870d7f54dc2ece89b571f03b72e15eb8725` на Windows Server 2022 через .NET Framework и Inno Setup. [Успешный полный запуск](https://github.com/ivanmorkovka1-ux/zaper2/actions/runs/38551027340).

- 35 self-tests до установки и 35 проверок после установки: `Failures: 0`.
- 12 комбинаций game/IPSet и 9 стратегий принимаются настоящим winws2.
- STUN корректный/некорректный transaction, двусторонний relay, ограничение upload, отмена subprocess.
- GUI, четыре страницы, FACEIT/исключения, управление треем, крестик и полный выход.
- Тестовая служба: create/start/restart/remove, отдельный TCP-порт 1.
- Настоящая установка с `/TESTMODE=1 /DIR=<temporary>` и удаление.
- SHA256 скачанного опубликованного установщика совпал с локальным: `2ef40a96652277ac3cc933b9cd0e48cc0ffd45017355477114ad9f07be0f3a96`.

Ранние запуски выявили проблемы тестового harness: каталог UI-отчётов не создавался, а поиск `FAIL` ошибочно совпадал с `Failures: 0`. Исправления находятся только в CI-сценарии. Также наблюдались непостоянная ошибка инициализации Cygwin `0xc0000142` и гонка старого теста перечисления curl-процессов. Harness сохраняет каждый неуспешный отчёт и допускает до трёх попыток только для этих двух случаев; прочие ошибки немедленно проваливают проверку. Финальный запуск, из которого опубликован Windows-релиз, прошёл без повторов. Windows-исходники, сборщик и установщик не менялись.

## Linux 3.6.3-linux.1

- 11 unit/integration-oriented tests, включая реальный `--dry-run` всех **36** комбинаций game/IPSet/strategy для x86_64, пути с пробелами, сохранение настроек, ошибку nftables, запрет удаления чужой таблицы и socket уведомления READY.
- Все **36 ARM64-профилей** приняты настоящим ARM64 nfqws2 под QEMU.
- В отдельном namespace/контейнере: запуск настоящего nfqws2, TCP HTTP и UDP echo, IPv4 и IPv6, запрет второго экземпляра, штатное завершение, принудительное убийство движка и очистка правил.
- Чужая таблица `inet sentinel` сохраняется при запуске/остановке/сбое. Одноимённая чужая таблица запрещает запуск и остаётся на месте.
- Реальные lifecycle-проверки с ограниченным набором capabilities, `no-new-privileges`, read-only rootfs и writable `/run`/`/tmp`.
- Debian 13 и Fedora 43: GUI под Xvfb, runtime, тесты и staging install/uninstall. Ubuntu 24.04 — отдельный GitHub Actions runner. Arch Linux — Python 3.14, engine dry runs и `systemd-analyze verify`.
- Настоящая установка в контейнере при `umask 077`: runtime читается после сброса UID, GUI-пользователь может читать настройки, удаление сохраняет настройки.
- Проверены манифест SHA256, pinned upstream archive и оба статических движка. Соответствующие исходники движка и лицензии включены в архив.

Проверки разработки не включали запуск движка в основной сети пользовательского Arch, изменение его Hosts, sysctl, маршрутов, boot-конфигурации или драйверов.

## Практические границы

Linux — предварительная версия. ARM64 проверен под QEMU, а не на физическом ARM-компьютере. systemd-unit проверен парсером; механизм READY и ограничения прав проверены отдельно, полноценная загрузка ОС с этой службой не моделировалась. Проверки в контейнерах используют ядро хоста, а не отдельные ядра каждого дистрибутива.

Тесты не доказывают успешный обход DPI конкретного провайдера, голос/трансляцию Discord, реальный вход в FACEIT или работу Anti-Cheat. Автоподбор с rollback, proxy upload limiter, обновление Hosts/списков и экспериментальный Windows FACEIT preset пока не перенесены; подробности в [Linux README](../linux/README.md).
