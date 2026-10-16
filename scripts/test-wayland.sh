#!/bin/sh
# Headless compositor, independent socket/session. Does not attach to the user's desktop.
set -eu
bundle=$(realpath "$1")
shift
work=$(mktemp -d /tmp/zaper-wayland.XXXXXX)
chmod 700 "$work"
cleanup() {
    if [ -n "${watcher_pid:-}" ]; then kill "$watcher_pid" 2>/dev/null || true; wait "$watcher_pid" 2>/dev/null || true; fi
    if [ -n "${compositor_pid:-}" ]; then kill "$compositor_pid" 2>/dev/null || true; wait "$compositor_pid" 2>/dev/null || true; fi
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM
export XDG_RUNTIME_DIR="$work"
export XDG_CONFIG_HOME="$work/config"
export XDG_STATE_HOME="$work/state"
export WAYLAND_DISPLAY=zaper-test-wayland
export GDK_BACKEND=wayland
export XDG_SESSION_TYPE=wayland
task_test_parent_display=${DISPLAY:-}
unset DISPLAY
# No --xwayland option is passed: XWayland is never started. The optional
# nested X11 backend supplies virtual input devices only to the compositor.
# The tested GTK client always runs with DISPLAY unset.
case "${ZAPER_WESTON_BACKEND:-headless}" in
 headless)
    weston --backend=headless-backend.so --socket="$WAYLAND_DISPLAY" --idle-time=0 --width=2560 --height=2048 --scale="${ZAPER_TEST_SCALE:-1}" --use-pixman --no-config > "$work/weston.log" 2>&1 &
    ;;
 x11)
    env DISPLAY="$task_test_parent_display" weston --backend=x11-backend.so --socket="$WAYLAND_DISPLAY" --idle-time=0 --width=2560 --height=2048 --scale="${ZAPER_TEST_SCALE:-1}" --use-pixman --no-config > "$work/weston.log" 2>&1 &
    ;;
 *) echo 'Unsupported test compositor backend' >&2; exit 1 ;;
esac
compositor_pid=$!
for attempt in $(seq 1 100); do
    if [ -S "$work/$WAYLAND_DISPLAY" ]; then break; fi
    if ! kill -0 "$compositor_pid" 2>/dev/null; then cat "$work/weston.log"; exit 1; fi
    sleep .05
done
if [ ! -S "$work/$WAYLAND_DISPLAY" ]; then cat "$work/weston.log"; exit 1; fi
if [ "${1:-}" = '--tray' ]; then
    export ZAPER_TRAY_ACTION_FILE="$work/show-action"
    for arg in "$@"; do
        if [ "$arg" = "--watcher-loss" ]; then export ZAPER_TRAY_DROP_MODE=name; fi
    done
    export ZAPER_TRAY_DROP_FILE="$work/drop-host"
    /usr/bin/python3 "$bundle/tests/status_notifier_fixture.py" "$work/watcher-ready" &
    watcher_pid=$!
    for attempt in $(seq 1 100); do
        if [ -f "$work/watcher-ready" ]; then break; fi
        if ! kill -0 "$watcher_pid" 2>/dev/null; then echo 'StatusNotifier fixture failed' >&2; exit 1; fi
        sleep .05
    done
    test -f "$work/watcher-ready"
fi
/usr/bin/python3 "$bundle/tests/gui_smoke.py" --wayland "$@"
