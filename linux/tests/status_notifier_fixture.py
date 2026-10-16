"""Real D-Bus watcher/host for protocol tests, isolated by dbus-run-session."""
import os
from pathlib import Path
import sys
import time
import gi
from gi.repository import Gio, GLib

READY = Path(sys.argv[1])
NAME = 'org.kde.StatusNotifierWatcher'
PATH = '/StatusNotifierWatcher'
INFO = Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
<method name="RegisterStatusNotifierHost"><arg type="s" direction="in"/></method>
<property name="RegisteredStatusNotifierItems" type="as" access="read"/>
<property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
<property name="ProtocolVersion" type="i" access="read"/>
<signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
<signal name="StatusNotifierItemUnregistered"><arg type="s"/></signal>
<signal name="StatusNotifierHostRegistered"/>
<signal name="StatusNotifierHostUnregistered"/>
</interface></node>''')
loop = GLib.MainLoop()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
items = []; host = True; failed = False; menu_item = None; item_peer = None; menu_path = None; sent = False; dropped = False


def fail(message):
    global failed
    failed = True; READY.with_suffix('.error').write_text(str(message)); print('FAIL: StatusNotifier fixture:', message, flush=True); loop.quit()


def value(item):
    return item.unpack() if isinstance(item, GLib.Variant) else item


def find_label(node, expected):
    node = value(node)
    identity, properties, children = node
    if properties.get('label') == expected: return identity
    for child in children:
        found = find_label(child, expected)
        if found is not None: return found
    return None


def inspect_menu(connection, result):
    global menu_item
    try:
        revision, layout = connection.call_finish(result).unpack()
        menu_item = find_label(layout, 'Открыть Zaper')
        assert menu_item is not None, 'DBusMenu has no show action'
        print('PASS: actual StatusNotifierItem registration, icon and DBusMenu layout', flush=True)
    except Exception as exc: fail(exc)


def inspect_item(connection, result):
    global menu_path
    try:
        properties = connection.call_finish(result).unpack()[0]
        assert properties['Id'] == 'zaper' and properties['Title'] == 'Zaper', properties
        assert properties['IconName'].endswith('zaper.png'), properties
        menu_path = properties['Menu']
        assert menu_path.startswith('/'), properties
        bus.call(item_peer, menu_path, 'com.canonical.dbusmenu', 'GetLayout', GLib.Variant('(iias)', (0, -1, [])),
                 None, Gio.DBusCallFlags.NONE, 3000, None, inspect_menu)
    except Exception as exc: fail(exc)


def registered(connection, sender, path, interface, method, parameters, invocation):
    global item_peer
    service = parameters.unpack()[0]
    if method == 'RegisterStatusNotifierItem':
        peer, item_path = (sender, service) if service.startswith('/') else (service, '/StatusNotifierItem')
        items.append(peer + item_path); item_peer = peer
        invocation.return_value(None)
        bus.emit_signal(None, PATH, NAME, 'StatusNotifierItemRegistered', GLib.Variant('(s)', (peer + item_path,)))
        bus.call(peer, item_path, 'org.freedesktop.DBus.Properties', 'GetAll', GLib.Variant('(s)', ('org.kde.StatusNotifierItem',)),
                 None, Gio.DBusCallFlags.NONE, 3000, None, inspect_item)
    else: invocation.return_value(None)


def get_property(connection, sender, path, interface, name):
    return {'RegisteredStatusNotifierItems': GLib.Variant('as', items), 'IsStatusNotifierHostRegistered': GLib.Variant('b', host), 'ProtocolVersion': GLib.Variant('i', 0)}[name]


def delivered(connection, result):
    try:
        connection.call_finish(result)
        Path(os.environ['ZAPER_TRAY_ACTION_FILE'] + '.delivered').touch()
    except GLib.Error as exc: fail(exc)


def tick():
    global sent, dropped, host
    marker = os.environ.get('ZAPER_TRAY_ACTION_FILE')
    if marker and Path(marker).exists() and not sent and menu_item is not None:
        sent = True
        bus.call(item_peer, '/StatusNotifierItem', 'org.kde.StatusNotifierItem', 'ProvideXdgActivationToken', GLib.Variant('(s)', ('fixture-token',)), None, Gio.DBusCallFlags.NONE, 1000, None, None)
        bus.call(item_peer, menu_path, 'com.canonical.dbusmenu', 'Event',
                 GLib.Variant('(isvu)', (menu_item, 'clicked', GLib.Variant('i', 0), 0)),
                 None, Gio.DBusCallFlags.NONE, 3000, None, delivered)
    marker = os.environ.get('ZAPER_TRAY_DROP_FILE')
    if marker and Path(marker).exists() and not dropped:
        dropped = True; host = False
        if os.environ.get('ZAPER_TRAY_DROP_MODE') == 'name': Gio.bus_unown_name(owner)
        else:
            bus.emit_signal(None, PATH, NAME, 'StatusNotifierHostUnregistered', None)
            bus.emit_signal(None, PATH, 'org.freedesktop.DBus.Properties', 'PropertiesChanged',
                            GLib.Variant('(sa{sv}as)', (NAME, {'IsStatusNotifierHostRegistered': GLib.Variant('b', False)}, [])))
    return True


registration = bus.register_object(PATH, INFO.interfaces[0], registered, get_property, None)
owner = Gio.bus_own_name_on_connection(bus, NAME, Gio.BusNameOwnerFlags.NONE,
    lambda *args: READY.touch(), lambda *args: None)
GLib.timeout_add(50, tick)
loop.run()
sys.exit(1 if failed else 0)
