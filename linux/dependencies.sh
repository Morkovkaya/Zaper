#!/bin/sh
# Generic distribution packages only; never update the whole system or select drivers.
set -eu
. /etc/os-release
case "$ID ${ID_LIKE:-}" in
 *arch*|*manjaro*) set -- pacman -S --needed --noconfirm python python-gobject python-cairo gtk3 nftables curl polkit iproute2 iputils util-linux systemd ;;
 *debian*|*ubuntu*|*linuxmint*) set -- apt-get install -y python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 nftables curl pkexec iproute2 iputils-ping util-linux systemd ;;
 *fedora*|*rhel*) set -- dnf install -y python3 python3-gobject python3-cairo gtk3 nftables curl polkit iproute iputils util-linux systemd ;;
 *opensuse*|*suse*) set -- zypper --non-interactive install python3 python3-gobject python3-gobject-cairo typelib-1_0-Gtk-3_0 nftables curl polkit iproute2 iputils util-linux systemd ;;
 *) echo "Unsupported distribution: $ID. Install the dependencies listed in README.md, then run install.sh install." >&2; exit 1 ;;
esac
# Print mode is for diagnostics and tests; it never changes packages.
if [ "${ZAPER_PRINT_DEPENDENCIES:-}" = 1 ]; then printf '%s\n' "$@"; exit; fi
[ "$(id -u)" = 0 ] || { echo 'Dependency installation requires root' >&2; exit 1; }
# If everything is present, updates do not contact the package manager again.
if command -v nft >/dev/null && command -v curl >/dev/null && command -v pkexec >/dev/null && command -v ip >/dev/null && command -v ping >/dev/null && command -v flock >/dev/null && command -v systemctl >/dev/null && /usr/bin/python3 -I -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_foreign("cairo"); from gi.repository import Gtk' 2>/dev/null; then
    exit
fi
case "$1" in apt-get) apt-get update ;; esac
"$@"
