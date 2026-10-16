# Native Wayland implementation plan

> Execute inline in the feature branch; preserve backend behavior and verify before release.

**Goal:** Run the full Zaper desktop natively on Wayland without XWayland, retaining X11 compatibility and existing CLI/settings.
**Architecture:** Replace Tk with GTK 3/PyGObject. Keep background command workers and JSON CLI; all widgets and tray callbacks stay on GTK's main loop. Use StatusNotifierItem/DBusMenu for Wayland and embedded Gtk.StatusIcon only as an X11 fallback. Restore window visibility if the tray host disappears.
**Spec:** User request to make Zaper work on Wayland; all existing Linux 3.8.1-linux.2 frontend operations remain available.
**Tech Stack:** Python 3.10+, GTK 3/PyGObject, headless Weston, Xvfb, D-Bus.

## Constraints

- Never change the developer host's display server, drivers, compositor configuration, network, Hosts or proxy.
- Backend remains standard-library only; GTK is a GUI dependency. Preserve installed CLI/service/settings paths and all profiles.
- Require a real tray host before hiding a window; when absent/lost, leave/show the window. No X11-only APIs in native Wayland mode.
- Validate native GdkWaylandDisplay with DISPLAY removed, not only a Wayland environment variable on an X11 window.

### Task 1: GTK frontend
Files: linux/zapret_gui.py, tests/gui_smoke.py.
- [ ] Preserve five tabs, settings/fakes/exclusions, profiles/history, tuning/proxy, diagnostics/chart, maintenance/Hosts/updater and launch preferences.
- [ ] Use native GTK file dialogs and transient dialogs, responsive workers, progress and safe busy/close behavior. Clear token widgets on close.
- [ ] Exercise every dialog/page and callback under X11 and native Wayland; ensure no UI exceptions or lost controls after closing dialogs.

### Task 2: Tray
Files: linux/zaper_tray.py, tests/status_notifier_fixture.py, tests/gui_smoke.py.
- [ ] Use a native Gio D-Bus StatusNotifierItem with a verified StatusNotifierWatcher/host; optional embedded Gtk.StatusIcon on X11 only.
- [ ] Check startup/hide/show/close/exit, unavailable host, host disappearance and action delivery through the real D-Bus interface.
- [ ] Preserve per-user panel autostart/start-in-tray preferences and error notifications.

### Task 3: Native Wayland verification and delivery
Files: scripts/test-wayland.sh, workflow, README, version, validation.
- [ ] Test with headless Weston, GDK_BACKEND=wayland and DISPLAY unset; test scale factors 1 and 2, native dialogs and tray protocol.
- [ ] Run all backend/packet/ARM64/migration and Windows regression checks; inspect GTK layout screenshots under X11.
- [ ] Publish Linux 3.8.1-linux.3 from verified main CI, merge PR after checks, compare downloaded release with the CI artifact and retain proof in outputs.
