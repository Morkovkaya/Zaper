#!/bin/sh
# DESTDIR stages files only; it never invokes host systemctl.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=${1:-install}
stage=${DESTDIR:-}
app="$stage/opt/zapret2-manager"
cli="$stage/usr/local/bin/zapret2-manager"
gui="$stage/usr/local/bin/zapret2-manager-gui"
unit="$stage/etc/systemd/system/zapret2-manager.service"
if [ -z "$stage" ] && [ "$(id -u)" -ne 0 ]; then
    echo 'Use sudo ./install.sh install (or uninstall)' >&2
    exit 1
fi
# Internal file installation is invoked by the lock-holding transaction wrapper.
case "$mode" in install|uninstall) ;; *) echo 'Usage: install.sh install [--with-deps] | uninstall' >&2; exit 2 ;; esac
option=${2:-}
case "$option" in ''|--with-deps|--files-only) ;; *) echo 'Unknown installer option' >&2; exit 2 ;; esac
if [ -n "$stage" ] && [ "$option" = --with-deps ]; then
    echo 'DESTDIR cannot install host dependencies' >&2; exit 2
fi
if [ "$option" = --with-deps ]; then
    [ "$mode" = install ] || exit 2
    /bin/sh "$source_dir/dependencies.sh"
fi
if [ -z "$stage" ] && [ "$option" != --files-only ]; then
    exec /usr/bin/python3 -I "$source_dir/zaper_install.py" "$source_dir" "$mode"
fi
case "$mode" in
 install)
    test -f "$source_dir/runtime/sha256.json" || { echo 'Download a complete release archive first' >&2; exit 1; }
    /usr/bin/python3 -I "$source_dir/zapret_manager.py" verify >/dev/null
    if [ -e "$app" ] && [ ! -f "$app/.zapret2-manager-install" ]; then
        echo "$app is occupied; refusing to overwrite" >&2
        exit 1
    fi
    test ! -L "$app" || { echo 'Install path must not be a symlink' >&2; exit 1; }
    if [ -z "$stage" ] && [ -d /run/systemd/system ]; then
        if systemctl cat zapret2-manager.service >/dev/null 2>&1; then
            systemctl stop zapret2-manager.service
        fi
    fi
    mkdir -p "$app" "$(dirname "$cli")" "$(dirname "$unit")" "$stage/usr/share/applications"
    mkdir -p "$stage/etc/zapret2-manager" "$stage/var/lib/zapret2-manager"
    chmod 755 "$stage/etc/zapret2-manager" "$stage/var/lib/zapret2-manager"
    cp "$source_dir"/install.sh "$source_dir"/dependencies.sh "$app/"
    cp "$source_dir"/*.py "$source_dir"/runtime-repair.* "$source_dir"/zaper.png "$source_dir/LICENSE" "$source_dir/THIRD_PARTY_NOTICES.md" "$app/"
    cp "$source_dir"/zapret2-*-source.tar.gz "$app/"
    task_user_lists=$(mktemp -d)
    trap 'rm -rf "$task_user_lists"' EXIT HUP INT TERM
    for task_user_file in "$app"/runtime/lists/*-user.txt; do
        if [ -f "$task_user_file" ]; then cp "$task_user_file" "$task_user_lists/"; fi
    done
    rm -rf "$app/runtime"
    cp -R "$source_dir/runtime" "$app/runtime"
    for task_user_file in "$task_user_lists"/*; do
        if [ -f "$task_user_file" ]; then cp "$task_user_file" "$app/runtime/lists/"; fi
    done
    printf '%s\n' 'Zapret2 Manager installed by install.sh' > "$app/.zapret2-manager-install"
    find "$app" -type d -exec chmod 755 {} +
    find "$app" -type f -exec chmod 644 {} +
    chmod 755 "$app/runtime/bin/x86_64/nfqws2" "$app/runtime/bin/arm64/nfqws2"
    if [ -z "$stage" ]; then chown -R root:root "$app"; fi
    /usr/bin/python3 -I "$app/zapret_manager.py" check >/dev/null
    cat > "$cli" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -I /opt/zapret2-manager/zapret_manager.py "$@"
EOF
    cat > "$gui" <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -I /opt/zapret2-manager/zapret_gui.py "$@"
EOF
    chmod 755 "$cli" "$gui"
    ln -sf zapret2-manager "$stage/usr/local/bin/zaper"
    ln -sf zapret2-manager-gui "$stage/usr/local/bin/zaper-gui"
    mkdir -p "$stage/usr/share/icons/hicolor/32x32/apps"
    chmod 755 "$stage/usr/share/icons" "$stage/usr/share/icons/hicolor" "$stage/usr/share/icons/hicolor/32x32" "$stage/usr/share/icons/hicolor/32x32/apps"
    cp "$source_dir/zaper.png" "$stage/usr/share/icons/hicolor/32x32/apps/zaper.png"
    chmod 644 "$stage/usr/share/icons/hicolor/32x32/apps/zaper.png"
    cp "$source_dir/zapret2-manager.service" "$unit"
    cat > "$stage/usr/share/applications/zapret2-manager.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Zaper
Comment=Native Linux network manager
Exec=/usr/local/bin/zapret2-manager-gui
Icon=zaper
Terminal=false
Categories=Network;
EOF
    chmod 644 "$unit" "$stage/usr/share/applications/zapret2-manager.desktop"
    if [ -z "$stage" ] && [ -d /run/systemd/system ]; then systemctl daemon-reload; fi
    echo 'Installed. GUI: zapret2-manager-gui; CLI: zapret2-manager. A running service is restored after upgrade; initial start: sudo zaper start.'
    ;;
 uninstall)
    test -f "$app/.zapret2-manager-install" || { echo 'No owned installation found' >&2; exit 1; }
    if [ -z "$stage" ] && [ -d /run/systemd/system ]; then
        systemctl disable --now zapret2-manager.service
    fi
    rm -rf "$app"
    rm -f "$cli" "$gui" "$stage/usr/local/bin/zaper" "$stage/usr/local/bin/zaper-gui" "$stage/usr/share/icons/hicolor/32x32/apps/zaper.png" "$unit" "$stage/usr/share/applications/zapret2-manager.desktop"
    if [ -z "$stage" ] && [ -d /run/systemd/system ]; then systemctl daemon-reload; fi
    echo 'Uninstalled. /etc/zapret2-manager settings preserved.'
    ;;
 *) echo 'Usage: install.sh install|uninstall' >&2; exit 2 ;;
esac
