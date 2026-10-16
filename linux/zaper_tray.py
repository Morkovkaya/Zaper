"""Native StatusNotifierItem/DBusMenu; embedded Gtk.StatusIcon on X11 only."""
from pathlib import Path
import time
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib

WATCHER = 'org.kde.StatusNotifierWatcher'
WATCHER_PATH = '/StatusNotifierWatcher'
ITEM = 'org.kde.StatusNotifierItem'
ITEM_PATH = '/StatusNotifierItem'
MENU = 'com.canonical.dbusmenu'
MENU_PATH = '/MenuBar'
ITEM_INFO = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.kde.StatusNotifierItem">
<method name="ProvideXdgActivationToken"><arg type="s" direction="in"/></method>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
<property name="IconName" type="s" access="read"/><property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="IconThemePath" type="s" access="read"/><property name="Menu" type="o" access="read"/>
<property name="AttentionIconName" type="s" access="read"/><property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionMovieName" type="s" access="read"/><property name="OverlayIconName" type="s" access="read"/>
<property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<signal name="NewStatus"><arg type="s"/></signal><signal name="NewIcon"/><signal name="NewToolTip"/>
</interface></node>''')
MENU_INFO = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>''')
ACTIONS = (('Открыть Zaper', 'show'), ('Включить', 'start'), ('Выключить', 'stop'), ('Выход из панели', 'quit'))


class Tray:
    def __init__(self, action, image, onready=lambda: None, onerror=lambda error: None):
        self.action, self.onready, self.onerror = action, onready, onerror
        self.image = Path(image).resolve()
        self.ready = self.stopped = self.failed = self.pending = False
        self.activation_token = None
        self.native = False; self.legacy = self.bus = None; self.registrations = []; self.source = None
        self.started = self.last_check = time.monotonic()
        self.menu = Gtk.Menu()
        for index, (title, _) in enumerate(ACTIONS, 1):
            item = Gtk.MenuItem(label=title); item.connect('activate', lambda item, identity=index: self.activate(identity)); self.menu.append(item)
        self.menu.show_all()
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None); self.check_host(initial=True)
        except GLib.Error as exc: self.fallback(str(exc))
        if not self.failed: self.source = GLib.timeout_add(150, self.tick)

    def activate(self, identity):
        if not self.stopped and 1 <= identity <= len(ACTIONS):
            command = ACTIONS[identity - 1][1]
            token, self.activation_token = self.activation_token, None
            self.action({'command': command, 'activation_token': token} if token and command == 'show' else command)

    def check_host(self, initial=False):
        if self.pending or self.stopped: return
        self.pending = True; self.last_check = time.monotonic()
        def reply(connection, result):
            self.pending = False
            if self.stopped: return
            try:
                host = connection.call_finish(result).unpack()[0]
                if isinstance(host, GLib.Variant): host = host.unpack()
                if not host: raise RuntimeError('В окружении нет хоста StatusNotifier')
                if initial: self.register_native()
            except (GLib.Error, ValueError, OSError, RuntimeError) as exc:
                if initial: self.fallback(str(exc))
                else: self.fail(str(exc))
        self.bus.call(WATCHER, WATCHER_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                      GLib.Variant('(ss)', (WATCHER, 'IsStatusNotifierHostRegistered')),
                      GLib.VariantType.new('(v)'), Gio.DBusCallFlags.NONE, 1000, None, reply)

    def register_native(self):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(self.image))
        width, height = pixbuf.get_width(), pixbuf.get_height()
        pixels, channels, stride = pixbuf.get_pixels(), pixbuf.get_n_channels(), pixbuf.get_rowstride()
        argb = bytearray()
        for y in range(height):
            for x in range(width):
                offset = y * stride + x * channels
                argb.extend((pixels[offset + 3] if channels == 4 else 255, pixels[offset], pixels[offset + 1], pixels[offset + 2]))
        self.pixmaps = [(width, height, bytes(argb))]
        self.registrations.append(self.bus.register_object(ITEM_PATH, ITEM_INFO.interfaces[0], self.item_call, self.item_property, None))
        self.registrations.append(self.bus.register_object(MENU_PATH, MENU_INFO.interfaces[0], self.menu_call, self.menu_property, None))
        self.native = True
        def registered(connection, result):
            if self.stopped: return
            try: connection.call_finish(result); self.mark_ready()
            except GLib.Error as exc: self.fail(str(exc))
        self.bus.call(WATCHER, WATCHER_PATH, WATCHER, 'RegisterStatusNotifierItem',
                      GLib.Variant('(s)', (self.bus.get_unique_name(),)), None, Gio.DBusCallFlags.NONE, 1000, None, registered)

    def item_property(self, connection, sender, path, interface, name):
        values = {'Category': ('s', 'ApplicationStatus'), 'Id': ('s', 'zaper'), 'Title': ('s', 'Zaper'),
                  'Status': ('s', 'Passive' if self.stopped else 'Active'), 'WindowId': ('i', 0), 'ItemIsMenu': ('b', False),
                  'IconName': ('s', str(self.image)), 'IconPixmap': ('a(iiay)', self.pixmaps), 'IconThemePath': ('s', str(self.image.parent)),
                  'Menu': ('o', MENU_PATH), 'ToolTip': ('(sa(iiay)ss)', (str(self.image), self.pixmaps, 'Zaper', 'Управление Zaper'))}
        signature, value = values.get(name, ('a(iiay)', []) if name.endswith('Pixmap') else ('s', ''))
        return GLib.Variant(signature, value)

    def item_call(self, connection, sender, path, interface, method, parameters, invocation):
        if method == 'ProvideXdgActivationToken':
            token = parameters.unpack()[0]
            if len(token) <= 4096: self.activation_token = token
        elif method in ('Activate', 'SecondaryActivate', 'ContextMenu'): self.activate(1)
        invocation.return_value(None)

    def menu_property(self, connection, sender, path, interface, name):
        signature, value = {'Version': ('u', 3), 'TextDirection': ('s', 'ltr'), 'Status': ('s', 'normal'), 'IconThemePath': ('as', [str(self.image.parent)])}[name]
        return GLib.Variant(signature, value)

    def properties(self, identity, names=()):
        if identity == 0: values = {'children-display': GLib.Variant('s', 'submenu')}
        elif 1 <= identity <= len(ACTIONS):
            values = {'label': GLib.Variant('s', ACTIONS[identity - 1][0]), 'enabled': GLib.Variant('b', not self.stopped), 'visible': GLib.Variant('b', True)}
        else: raise ValueError('Неизвестный пункт меню')
        return {key: value for key, value in values.items() if not names or key in names}

    def layout(self, identity, depth, names):
        children = [GLib.Variant('(ia{sv}av)', self.layout(index, 0, names)) for index in range(1, len(ACTIONS) + 1)] if identity == 0 and depth != 0 else []
        return identity, self.properties(identity, names), children

    def menu_call(self, connection, sender, path, interface, method, parameters, invocation):
        try:
            args = parameters.unpack()
            if method == 'GetLayout': result = GLib.Variant('(u(ia{sv}av))', (1, self.layout(*args)))
            elif method == 'GetGroupProperties': result = GLib.Variant('(a(ia{sv}))', ([(identity, self.properties(identity, args[1])) for identity in args[0]],))
            elif method == 'GetProperty': result = GLib.Variant('(v)', (self.properties(args[0])[args[1]],))
            elif method in ('Event', 'EventGroup'):
                events = [args] if method == 'Event' else args[0]
                errors = []
                for identity, event, value, timestamp in events:
                    if not 1 <= identity <= len(ACTIONS): errors.append(identity)
                    elif event == 'clicked': self.activate(identity)
                result = GLib.Variant('(ai)', (errors,)) if method == 'EventGroup' else None
            elif method == 'AboutToShow': result = GLib.Variant('(b)', (False,))
            elif method == 'AboutToShowGroup': result = GLib.Variant('(aiai)', ([], []))
            else: raise ValueError('Неизвестный метод меню')
            invocation.return_value(result)
        except (ValueError, TypeError, KeyError) as exc:
            invocation.return_dbus_error('com.canonical.dbusmenu.Error.InvalidArgument', str(exc))

    def mark_ready(self):
        if not self.ready and not self.stopped: self.ready = True; self.onready()

    def fallback(self, error):
        if self.stopped: return
        display = Gdk.Display.get_default()
        if display and 'X11' in display.__gtype__.name:
            self.legacy = Gtk.StatusIcon.new_from_file(str(self.image)); self.legacy.set_title('Zaper'); self.legacy.set_tooltip_text('Zaper')
            self.legacy.connect('activate', lambda *_: self.activate(1)); self.legacy.connect('popup-menu', self.popup); self.legacy.set_visible(True)
        else: self.fail(error)

    def popup(self, icon, button, timestamp): self.menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, timestamp)

    def tick(self):
        if self.stopped: self.source = None; return False
        if self.legacy:
            if self.legacy.is_embedded(): self.mark_ready()
            elif self.ready: self.fail('Панель X11-трея завершилась')
        elif self.native and self.ready and time.monotonic() - self.last_check > 1: self.check_host()
        if not self.ready and time.monotonic() - self.started > 4: self.fail('Трей не подтвердил готовность за 4 секунды')
        return not self.stopped

    def fail(self, error):
        if self.failed or self.stopped: return
        self.failed = True; self.ready = False; self.stop(); self.onerror(str(error))

    def notify(self, text):
        if not self.bus or self.stopped: return
        def reply(connection, result):
            try: connection.call_finish(result)
            except GLib.Error: pass
        self.bus.call('org.freedesktop.Notifications', '/org/freedesktop/Notifications', 'org.freedesktop.Notifications', 'Notify',
                      GLib.Variant('(susssasa{sv}i)', ('Zaper', 0, str(self.image), 'Zaper', str(text)[:300], [], {}, 5000)),
                      None, Gio.DBusCallFlags.NONE, 1000, None, reply)

    def stop(self):
        if self.stopped: return
        self.stopped = True; self.ready = False
        if self.source: GLib.source_remove(self.source); self.source = None
        if self.native:
            self.bus.emit_signal(None, ITEM_PATH, ITEM, 'NewStatus', GLib.Variant('(s)', ('Passive',)))
            for registration in self.registrations: self.bus.unregister_object(registration)
            self.registrations.clear(); self.native = False
        if self.legacy: self.legacy.set_visible(False); self.legacy = None
        self.menu.destroy()
