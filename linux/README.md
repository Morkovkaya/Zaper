# Zapret 2 Manager для Linux — 3.6.3-linux.1 (предварительная версия)

Нативное приложение: Python CLI и графический интерфейс Tk, официальный статический **nfqws2 1.0.5.2**, nftables. Один архив для **x86_64 и aarch64/ARM64**. Выбор процессора автоматический; интерфейсы, диски и настройки загрузки не привязаны к компьютеру. Wine не требуется.

## Требования

Linux с NFQUEUE/nftables, Python **3.10+**; Tk для GUI. Для кнопок с правами администратора нужны polkit (`pkexec`) и агент авторизации рабочего окружения. systemd необязателен: без него доступен запуск в терминале. CLI не зависит от сторонних модулей Python. Root нужен только для установки, настроек и управления пакетами.

Примеры зависимостей (приложение само их не устанавливает):

```sh
# Arch
sudo pacman -S python tk nftables polkit
# Debian / Ubuntu
sudo apt install python3 python3-tk nftables policykit-1
# Fedora
sudo dnf install python3 python3-tkinter nftables polkit
```

## Установка и запуск

Распакуйте `Zapret2Manager-3.6.3-linux.1-universal.tar.gz` и перейдите в его папку:

```sh
python3 zapret_manager.py check       # проверка runtime и профиля без изменения сети
sudo ./install.sh install
zapret2-manager-gui
# CLI с systemd:
sudo zapret2-manager start
zapret2-manager status
sudo zapret2-manager stop
# Автозапуск включается отдельно:
sudo zapret2-manager enable
sudo zapret2-manager disable
# Без systemd (остановка Ctrl+C):
sudo zapret2-manager run
```

Установка не запускает движок автоматически и не включает автозапуск. При обновлении установленная служба останавливается; включите её после проверки новой версии. Настройки хранятся в `/etc/zapret2-manager/settings.json`, код и runtime — в `/opt/zapret2-manager`. При удалении настройки сохраняются:

```sh
sudo ./install.sh uninstall
```

Без systemd сначала завершите запущенный foreground-процесс, затем удаляйте приложение.

## Режимы, стратегии, исключения и диагностика

```sh
sudo zapret2-manager configure --game udp --ipset loaded --strategy split
sudo zapret2-manager restart
zapret2-manager show
zapret2-manager diagnose
zapret2-manager probe
sudo zapret2-manager configure --exclude-ip 192.0.2.0/24 --exclude-ip 2001:db8::/32 --exclude-domain example.org
sudo zapret2-manager configure --exclude-uid 1001
sudo zapret2-manager configure --clear-exclusions
journalctl -u zapret2-manager -b
```

Игры: `off`, `tcp`, `udp`, `all`. IPSet: `none` — только базовые профили, `loaded` — поставляемый IP-список, `any` — любой IP. Игровые профили добавляются только при `loaded` или `any`, как в Windows. TLS-стратегии: исходная (`current`), `split`, `disorder`; настройки проверяет настоящий движок до сохранения. После сохранения нужен перезапуск.

Повторяемые `--exclude-*` заменяют список соответствующего типа. Остальные списки сохраняются. Исключения IP/CIDR и доменов применяются ко всем профилям. UID исключает пользователя целиком и помечает его соединения, чтобы обратный трафик тоже проходил мимо движка. GUI содержит редактор этих исключений.

`probe` проверяет прямой HTTPS к YouTube, его API, Discord Gateway и FACEIT, без системного HTTP proxy. Неуспешная проверка возвращает код 1; HTTP 403 не считается успехом. Доступность голоса Discord, трансляции, матча или Anti-Cheat этим не подтверждается.

## Сеть и переносимость

Приложение создаёт только таблицу `inet zapret2_manager`, очередь **200**, fwmark **0x40000000** для пакетов движка и ct mark **0x20000000** для исключений UID. Эти значения должны быть свободны от конфликтов с другими сетевыми утилитами. Проверка занятой очереди и чужой одноимённой таблицы запрещает запуск с конфликтом.

Никаких `flush ruleset`, изменений Hosts, маршрутов, sysctl, названий сетевых карт или драйверов. Правила охватывают IPv4/IPv6 и только локальные соединения, не режим роутера. Обработка TCP ограничена выбранными портами. Первые UDP-пакеты всех портов передаются движку для распознавания STUN/Discord; модификация определяется профилями. Лимит первых 12 пакетов соединения работает, когда conntrack accounting включён системой; без него больше пакетов попадёт в очередь. Приложение не меняет этот глобальный sysctl.

Очередь использует bypass: при отсутствии движка пакеты не блокируются. При остановке, ошибке правил или сбое движка удаляется собственная таблица. После SIGKILL или отключения питания собственные оставшиеся правила очищаются при следующем запуске. Чужие таблицы сохраняются. Существующие VPN, правила drop и аппаратный/flowtable offload могут влиять на результат: приложение не переписывает их.

## Отличия от Windows

Это первый Linux-порт, а не полная копия Windows UI. Вместо WinDivert и SCM используются NFQUEUE и необязательная systemd-служба. Исключения отдельных EXE заменены доменами/IP/UID: автоматически сопоставлять Windows EXE с Linux-процессами нельзя. Пока не перенесены автоподбор с восстановлением стратегии, ограничитель загрузки proxy, автоматическое обновление списков/Hosts и экспериментальный FACEIT UDP preset. FACEIT Anti-Cheat не переносится этим приложением. Доступность конкретных сервисов у конкретного провайдера требует проверки в его сети.

## Сборка и проверки

Из корня репозитория:

```sh
python3 scripts/package-linux.py
python3 -m unittest discover -s dist/Zapret2Manager-3.6.3-linux.1/tests -p test_manager.py -v
xvfb-run -a python3 dist/Zapret2Manager-3.6.3-linux.1/zapret_gui.py --smoke-test
python3 scripts/test-arm64.py dist/Zapret2Manager-3.6.3-linux.1
# Только в отдельном namespace, не в основной сети:
sudo unshare --net sh -c 'ip link set lo up; ZAPRET_ISOLATED_TEST=1 python3 dist/Zapret2Manager-3.6.3-linux.1/tests/integration.py'
```

Упаковка проверяет фиксированный SHA256 всего upstream-архива и обоих движков. Архив содержит лицензии, манифест runtime и соответствующие исходники zapret2 с ссылками на происхождение. GitHub Actions проверяет Windows и Linux независимо и выдаёт архивы только после успешных тестов.
