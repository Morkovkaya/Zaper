"""Per-user upload relay and ownership-aware GNOME/KDE proxy recovery."""
import argparse
import asyncio
from contextlib import contextmanager
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zaper_state import atomic_bytes
from zaper_tune import identity


CHILDREN={}

def remember(process):
    for pid,child in list(CHILDREN.items()):
        if child.poll() is not None: CHILDREN.pop(pid,None)
    CHILDREN[process.pid]=process
    return process


def home():
    path=Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state')))/'zaper/proxy'
    path.mkdir(parents=True,exist_ok=True,mode=0o700); path.chmod(0o700)
    return path


def document(name):
    path=home()/name
    return json.loads(path.read_text()) if path.exists() else None


def write(name, value): atomic_bytes(home()/name, (json.dumps(value,indent=2)+'\n').encode(),0o600)


@contextmanager
def lock():
    with (home()/'lock').open('a') as stream:
        try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Ограничитель уже работает') from None
        yield


def command(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=5)
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'Не удалось изменить desktop proxy')
    return result.stdout.strip()


class Gnome:
    name='gnome'
    keys=(('org.gnome.system.proxy','mode'),
          ('org.gnome.system.proxy.http','host'),('org.gnome.system.proxy.http','port'),
          ('org.gnome.system.proxy.https','host'),('org.gnome.system.proxy.https','port'))
    def read(self): return [command(['gsettings','get',schema,key]) for schema,key in self.keys]
    def target(self, port): return ["'manual'","'127.0.0.1'",str(port),"'127.0.0.1'",str(port)]
    def put(self,index,value): command(['gsettings','set',*self.keys[index],value])
    def original_is_happ(self, values, upstream):
        return values[0]=="'manual'" and values[1].strip("'") in ('localhost','127.0.0.1') and values[2]==str(upstream)


class Kde:
    name='kde'
    keys=('ProxyType','httpProxy','httpsProxy')
    def __init__(self):
        self.reader=shutil.which('kreadconfig6') or shutil.which('kreadconfig5')
        self.writer=shutil.which('kwriteconfig6') or shutil.which('kwriteconfig5')
        if not self.reader or not self.writer: raise RuntimeError('Нужны kreadconfig/kwriteconfig из KDE')
    def read(self): return [command([self.reader,'--file','kioslaverc','--group','Proxy Settings','--key',k,'--default','']) for k in self.keys]
    def target(self,port): return ['1',f'http://127.0.0.1 {port}',f'http://127.0.0.1 {port}']
    def put(self,index,value):
        command([self.writer,'--file','kioslaverc','--group','Proxy Settings','--key',self.keys[index],value])
        # KIO observes config notifications on D-Bus; unsupported tools must fail before activation.
    def notify(self):
        bus=shutil.which('dbus-send')
        if not bus: raise RuntimeError('Нужен dbus-send для уведомления KDE')
        command([bus,'--session','--type=signal','/KIO/Scheduler','org.kde.KIO.Scheduler.reparseSlaveConfiguration','string:'])
    def original_is_happ(self,values,upstream):
        return values[0]=='1' and values[1] in (f'http://127.0.0.1 {upstream}',f'http://127.0.0.1:{upstream}',f'http://localhost {upstream}')


def adapter(name):
    if name=='gnome': return Gnome()
    if name=='kde': return Kde()
    if name=='manual': return None
    raise ValueError('Выберите manual, gnome или kde')


def autostart():
    return Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'autostart/zaper-proxy-recovery.desktop'


def recovery_entry():
    # Fixed installed entrypoint, never a profile-supplied executable.
    return b'[Desktop Entry]\nType=Application\nName=Zaper proxy recovery\nExec=/usr/local/bin/zaper proxy-recover\nTerminal=false\nNoDisplay=true\n'


def recover_owned():
    data=document('pending.json')
    if not data: return {'restored':False}
    desktop=adapter(data['desktop'])
    preserved=[]
    if desktop:
        current=desktop.read()
        # If any setting has a newer value, keep the user's whole desktop proxy.
        if any(now not in (before,ours) for before,ours,now in zip(data['before'],data['after'],current)):
            preserved=list(desktop.keys)
            current=[]
        # A partially applied startup is also rolled back.
        for i,(before,ours,now) in enumerate(zip(data['before'],data['after'],current)):
            if now==ours: desktop.put(i,before)
            elif now!=before: preserved.append(desktop.keys[i])
        if hasattr(desktop,'notify'): desktop.notify()
    path=autostart()
    if path.exists() and path.read_bytes()==recovery_entry():
        previous=data.get('autostart_before')
        if previous is None: path.unlink()
        else:
            import base64
            atomic_bytes(path,base64.b64decode(previous),0o600)
    (home()/'pending.json').unlink(missing_ok=True)
    return {'restored':True,'external_changes_preserved':preserved}


def recover():
    with lock(): return recover_owned()


class Relay:
    def __init__(self, upstream_port=10809, rate=17, port=10819):
        if type(rate) is not int or not 1<=rate<=1000: raise ValueError('Лимит должен быть от 1 до 1000 Мбит/с')
        if not all(type(p) is int and 1<=p<=65535 for p in (port,upstream_port)) or port==upstream_port:
            raise ValueError('Нужны разные порты от 1 до 65535')
        self.upstream_port,self.rate,self.port=upstream_port,rate,port
        self.bytes_per_second=rate*1_000_000/8
        self.next=0.; self.pacing=asyncio.Lock(); self.server=None; self.tasks=set(); self.writers=set()

    async def start(self):
        self.server=await asyncio.start_server(self.forward,'127.0.0.1',self.port)
        return self

    async def pace(self,count):
        async with self.pacing:
            now=asyncio.get_running_loop().time()
            self.next=max(self.next,now-16384/self.bytes_per_second)
            delay=max(0,self.next-now); self.next+=count/self.bytes_per_second
        if delay: await asyncio.sleep(delay)

    async def copy(self,reader,writer,upload):
        while True:
            chunk=await reader.read(8192)
            if not chunk:
                if writer.can_write_eof(): writer.write_eof(); await writer.drain()
                return
            if upload: await self.pace(len(chunk))
            writer.write(chunk); await writer.drain()

    async def forward(self,reader,writer):
        task=asyncio.current_task(); self.tasks.add(task); self.writers.add(writer)
        remote=None
        try:
            incoming,remote=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',self.upstream_port),5)
            self.writers.add(remote)
            copies=[asyncio.create_task(self.copy(reader,remote,True)),asyncio.create_task(self.copy(incoming,writer,False))]
            try:
                # Half-close permits request EOF followed by a complete response.
                done,pending=await asyncio.wait(copies,return_when=asyncio.FIRST_COMPLETED)
                for item in done: item.result()
                if pending: await asyncio.wait_for(asyncio.gather(*pending),30)
            finally:
                for item in copies: item.cancel()
                await asyncio.gather(*copies,return_exceptions=True)
        except (OSError,ConnectionError,asyncio.TimeoutError): pass
        finally:
            for item in (writer,remote):
                if item:
                    item.close(); self.writers.discard(item)
            self.tasks.discard(task)

    async def close(self):
        if self.server: self.server.close()
        for writer in list(self.writers): writer.close()
        tasks=list(self.tasks)
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        if self.server: await self.server.wait_closed()


def status():
    live=document('live.json') or {}
    active=bool(live) and identity(live['pid'])==live['birth']
    return dict(active=active,**{k:v for k,v in live.items() if k not in ('pid','birth')},pending=bool(document('pending.json')))


def watch(pid,birth):
    while identity(pid)==birth: time.sleep(.2)
    live=document('pending.json')
    if live and (live['pid'],live['birth'])==(pid,birth):
        with lock():
            recover_owned(); (home()/'live.json').unlink(missing_ok=True)


async def serve(rate,port,upstream,desktop_name):
    with lock():
        recover_owned()
        relay=Relay(upstream,rate,port)
        desktop=adapter(desktop_name)
        before=desktop.read() if desktop else []
        if desktop and not desktop.original_is_happ(before,upstream):
            raise RuntimeError('Сначала включите системный HTTP proxy 127.0.0.1:'+str(upstream)+' или выберите ручной режим')
        if isinstance(desktop,Kde) and not shutil.which('dbus-send'): raise RuntimeError('Нужен dbus-send для KDE')
        # Listen and verify upstream before touching desktop settings.
        await relay.start()
        try:
            _,connection=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',upstream),3)
            connection.close(); await connection.wait_closed()
            pid=os.getpid();birth=identity(pid)
            data=dict(pid=pid,birth=birth,desktop=desktop_name,before=before,after=desktop.target(port) if desktop else [],autostart_before=None)
            import base64
            path=autostart()
            if path.exists(): data['autostart_before']=base64.b64encode(path.read_bytes()).decode()
            write('pending.json',data)
            atomic_bytes(path,recovery_entry(),0o600)
            pid=os.getpid();birth=identity(pid)
            # Watchdog starts before settings are changed, even if a later write fails.
            remember(subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'watch',str(pid),birth],
                             start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True))
            if desktop:
                for i,value in enumerate(data['after']): desktop.put(i,value)
                if hasattr(desktop,'notify'): desktop.notify()
            stop=asyncio.Event(); loop=asyncio.get_running_loop()
            for sig in (signal.SIGTERM,signal.SIGINT): loop.add_signal_handler(sig,stop.set)
            write('live.json',dict(pid=pid,birth=birth,rate_mbps=rate,port=port,upstream_port=upstream,desktop=desktop_name))
            await stop.wait()
        finally:
            await relay.close()
            recover_owned()
            (home()/'live.json').unlink(missing_ok=True)


def start(rate=17,port=10819,upstream=10809,desktop='manual'):
    # GUI and desktop settings belong to the logged-in user, never root/pkexec.
    if os.geteuid()==0: raise RuntimeError('Запустите ограничитель обычным пользователем без sudo')
    Relay(upstream,rate,port); adapter(desktop)
    if status()['active']: raise RuntimeError('Ограничитель уже работает')
    log=home()/'relay.log'
    with log.open('w') as stream:
        process=remember(subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'serve',str(rate),str(port),str(upstream),desktop],
                                 stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True,close_fds=True))
    deadline=time.monotonic()+8
    try:
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError(log.read_text()[-4000:])
            live=document('live.json')
            if live and live['pid']==process.pid and status()['active']: return status()
            time.sleep(.05)
        raise RuntimeError('Ограничитель не запустился за 8 секунд')
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        raise


def stop():
    live=document('live.json')
    if live and identity(live['pid'])==live['birth']:
        os.kill(live['pid'],signal.SIGTERM)
        deadline=time.monotonic()+8
        while identity(live['pid'])==live['birth'] and time.monotonic()<deadline: time.sleep(.05)
        if identity(live['pid'])==live['birth']: raise RuntimeError('Ограничитель ещё завершает соединения')
    for pid,child in list(CHILDREN.items()):
        if child.poll() is not None: CHILDREN.pop(pid,None)
    return recover()




def detected_proxy():
    """Read the user's proxy without changing it; environment takes precedence."""
    for key in ('https_proxy','HTTPS_PROXY','http_proxy','HTTP_PROXY','ALL_PROXY','all_proxy'):
        value=os.environ.get(key,'').strip()
        if value:return value
    desktop=os.environ.get('XDG_CURRENT_DESKTOP','').lower()
    try:
        if 'gnome' in desktop:
            values=Gnome().read()
            if values[0]=="'manual'":
                host=values[3].strip("'") or values[1].strip("'");port=values[4] if values[3].strip("'") else values[2]
                if host and port.isdigit() and 1<=int(port)<=65535:return 'http://'+host+':'+port
        elif 'kde' in desktop or 'plasma' in desktop:
            values=Kde().read()
            if values[0]=='1':
                value=values[2] or values[1]
                return value.replace(' ',':') if ' ' in value else value
    except (OSError,RuntimeError,subprocess.SubprocessError):pass
    return None


if __name__=='__main__':
    try:
        if sys.argv[1]=='serve': asyncio.run(serve(int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),sys.argv[5]))
        elif sys.argv[1]=='watch': watch(int(sys.argv[2]),sys.argv[3])
    except Exception as exc:
        print('Ошибка: '+str(exc),file=sys.stderr); sys.exit(1)
