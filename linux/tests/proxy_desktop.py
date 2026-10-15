"""Run only inside a fresh dbus-run-session with isolated XDG directories."""
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zaper_proxy as proxy
assert os.environ.get('ZAPER_ISOLATED_DESKTOP')=='1'
assert os.environ.get('XDG_CONFIG_HOME','').startswith('/tmp/')
server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(.2)
stop=threading.Event()
def accept():
    while not stop.is_set():
        try:client,_=server.accept();client.close()
        except socket.timeout:pass
        except OSError:break
thread=threading.Thread(target=accept);thread.start()
try:
    for name in ('gnome','kde'):
        desktop=proxy.adapter(name)
        upstream=server.getsockname()[1]
        before=desktop.target(upstream)
        for i,value in enumerate(before):desktop.put(i,value)
        if hasattr(desktop,'notify'):desktop.notify()
        for crash in (False,True):
            proxy.start(1,10819,upstream,name)
            assert desktop.read()==desktop.target(10819),(name,desktop.read())
            if crash:
                live=proxy.document('live.json');os.kill(live['pid'],signal.SIGKILL)
                deadline=time.monotonic()+8
                while proxy.document('pending.json') and time.monotonic()<deadline:time.sleep(.05)
            else:proxy.stop()
            assert not proxy.document('pending.json'),name
            assert desktop.read()==before,(name,desktop.read(),before)
        print('PASS:',name,'real settings backend start/stop and SIGKILL watchdog restoration',flush=True)
finally:
    proxy.stop();stop.set();server.close();thread.join()
