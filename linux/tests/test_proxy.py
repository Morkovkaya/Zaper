import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zaper_proxy as proxy


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_aggregate_upload_rate_and_half_close_response(self):
        count=0
        async def upstream(reader,writer):
            nonlocal count
            while True:
                chunk=await reader.read(32768)
                if not chunk:break
                count+=len(chunk)
            writer.write(b'received:'+str(count).encode());await writer.drain();writer.close()
        server=await asyncio.start_server(upstream,'127.0.0.1',0)
        relay=await proxy.Relay(server.sockets[0].getsockname()[1],1,unused_port()).start()
        started=time.monotonic()
        async def send():
            reader,writer=await asyncio.open_connection('127.0.0.1',relay.port)
            writer.write(b'x'*125000);await writer.drain();writer.write_eof()
            response=await asyncio.wait_for(reader.read(),6);writer.close();await writer.wait_closed()
            self.assertTrue(response.startswith(b'received:'))
        try:
            await asyncio.gather(send(),send())
            elapsed=time.monotonic()-started
            self.assertEqual(count,250000);self.assertGreater(elapsed,1.65);self.assertLess(elapsed,5.5)
        finally: await relay.close();server.close();await server.wait_closed()
        self.assertFalse(relay.tasks)

    async def test_download_is_not_upload_throttled_and_pending_clients_close(self):
        async def upstream(reader,writer):
            writer.write(b'x'*500000);await writer.drain();writer.close()
        server=await asyncio.start_server(upstream,'127.0.0.1',0)
        relay=await proxy.Relay(server.sockets[0].getsockname()[1],1,unused_port()).start()
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',relay.port)
            started=time.monotonic();self.assertEqual(len(await asyncio.wait_for(reader.readexactly(500000),3)),500000)
            self.assertLess(time.monotonic()-started,2)
            await relay.close();writer.close()
        finally: await relay.close();server.close();await server.wait_closed()


class ProxyStateTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ,{'XDG_STATE_HOME':str(self.root/'state'),'XDG_CONFIG_HOME':str(self.root/'config')}))

    def test_adapter_rollback_and_preserving_new_external_proxy(self):
        class Desktop:
            keys=('mode','host','port');values=['manual','127.0.0.1','10819']
            def read(self):return list(self.values)
            def put(self,i,value):self.values[i]=value
        desktop=Desktop()
        data=dict(desktop='gnome',before=['manual','127.0.0.1','10809'],after=['manual','127.0.0.1','10819'])
        with patch.object(proxy,'adapter',return_value=desktop):
            proxy.write('pending.json',data);proxy.recover()
            self.assertEqual(desktop.values[-1],'10809')
            desktop.values=['manual','new.proxy.example','8080']
            proxy.write('pending.json',data);result=proxy.recover()
            self.assertEqual(desktop.values,['manual','new.proxy.example','8080']);self.assertTrue(result['external_changes_preserved'])

    def test_duplicate_lock_and_validation(self):
        with proxy.lock():
            with self.assertRaisesRegex(RuntimeError,'уже'): proxy.recover()
        for rate in (0,1001,True):
            with self.assertRaises(ValueError): proxy.Relay(rate=rate)
        with self.assertRaises(ValueError):proxy.Relay(port=10809)

    def test_real_daemon_start_stop_collision_and_sigkill_watchdog(self):
        if os.geteuid()==0:self.skipTest('daemon CLI is intentionally per-user; run as ordinary user')
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen();server.settimeout(.2)
        stop=threading.Event()
        def accept():
            while not stop.is_set():
                try: client,_=server.accept();client.close()
                except socket.timeout:pass
                except OSError:break
        thread=threading.Thread(target=accept);thread.start()
        upstream=server.getsockname()[1];port=unused_port()
        try:
            result=proxy.start(1,port,upstream,'manual');self.assertTrue(result['active'])
            self.assertTrue(proxy.autostart().exists())
            with self.assertRaises(RuntimeError):proxy.start(1,port,upstream)
            live=proxy.document('live.json');os.kill(live['pid'],signal.SIGKILL)
            deadline=time.monotonic()+5
            while (proxy.home()/'pending.json').exists() and time.monotonic()<deadline:time.sleep(.05)
            self.assertFalse((proxy.home()/'pending.json').exists());self.assertFalse(proxy.autostart().exists())
            proxy.start(1,port,upstream);proxy.stop();self.assertFalse(proxy.status()['active'])
            with socket.socket() as collision:
                collision.bind(('127.0.0.1',port));collision.listen()
                with self.assertRaises(RuntimeError):proxy.start(1,port,upstream)
            self.assertFalse((proxy.home()/'pending.json').exists())
        finally:
            try:proxy.stop()
            finally:stop.set();server.close();thread.join()

    def test_gnome_partial_startup_failure_rolls_back(self):
        desktop=proxy.Gnome();before=["'manual'","'127.0.0.1'",'10809',"'127.0.0.1'",'10809']
        values=list(before);values[2]='10819'
        with patch.object(desktop,'read',side_effect=lambda:list(values)),patch.object(desktop,'put',side_effect=lambda i,v:values.__setitem__(i,v)),patch.object(proxy,'adapter',return_value=desktop):
            proxy.write('pending.json',dict(desktop='gnome',before=before,after=desktop.target(10819)))
            proxy.recover();self.assertEqual(values,before)
