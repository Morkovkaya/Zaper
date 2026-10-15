"""Local network fixtures only: no dependence on provider connectivity."""
import http.server
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zaper_network as net


class NetworkTests(unittest.TestCase):
    def test_semantic_http_validation_and_errors(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def do_GET(self):
                value={'/gateway':b'{"url":"wss://gateway.discord.gg"}', '/bad':b'{"url":"https://wrong"}', '/youtube':b'ytInitialData', '/jpeg':b'\xff\xd8'+b'x'*1200}.get(self.path,b'')
                self.send_response(204 if self.path=='/empty' else 200);self.end_headers();self.wfile.write(value)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            for kind in ('gateway','youtube','jpeg','empty'):
                self.assertTrue(net.http(kind,base+'/'+kind,kind)['success'],kind)
            self.assertFalse(net.http('bad',base+'/bad','gateway')['success'])
            self.assertFalse(net.http('bad',base+'/bad','jpeg')['success'])
        finally: server.shutdown();server.server_close();thread.join()

    def test_cancel_interrupts_and_reaps_subprocess(self):
        cancel=threading.Event(); timer=threading.Timer(.12,cancel.set);timer.start()
        started=time.monotonic()
        try:
            with self.assertRaises(net.Cancelled): net.run([sys.executable,'-c','import time;time.sleep(30)'],cancel)
        finally: timer.join()
        self.assertLess(time.monotonic()-started,2)

    def test_stun_transaction_and_length_validation(self):
        request=b'\x00\x01\x00\x00\x21\x12\xa4\x42'+b'012345678901'
        response=b'\x01\x01'+request[2:]
        self.assertTrue(net.valid_stun(response,request))
        for bad in (b'',response[:-1],response[:-1]+b'x',b'\x01\x01\x00\x04'+response[4:]):
            self.assertFalse(net.valid_stun(bad,request))
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1',0))
            def reply():
                data,peer=server.recvfrom(1000);server.sendto(b'\x01\x01'+data[2:],peer)
            thread=threading.Thread(target=reply);thread.start()
            self.assertTrue(net.stun('127.0.0.1',server.getsockname()[1])['success']);thread.join()

    def test_a2s_challenge_reuses_socket_and_rejects_bad_server(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1',0));server.settimeout(3)
            errors=[]
            def reply():
                try:
                    data,peer=server.recvfrom(1000);server.sendto(b'\xff'*4+b'Aabcd',peer)
                    follow,again=server.recvfrom(1000)
                    if peer!=again or not follow.endswith(b'abcd'): errors.append('challenge/port mismatch')
                    server.sendto(b'\xff'*4+b'I\x11',again)
                except Exception as e: errors.append(str(e))
            thread=threading.Thread(target=reply);thread.start()
            self.assertIn('A2S_INFO',net.a2s('127.0.0.1:'+str(server.getsockname()[1])));thread.join()
            self.assertFalse(errors,errors)
        for value in ('localhost:1','1.2.3.4:0','1.2.3.4:65536','bad'):
            with self.assertRaises(ValueError): net.parse_server(value)

    def test_missing_http3_is_explicit_unknown_and_not_a_fake_pass(self):
        good=dict(net.sample('core',True),success=True)
        with patch.object(net,'http',return_value=good),patch.object(net,'stun',return_value=net.sample('udp')),patch.object(net,'run',return_value=(0,'curl without quic','')):
            result=net.measure(1)
        self.assertTrue(result['valid']);self.assertTrue(any(x['unknown'] and 'HTTP/3' in x['error'] for x in result['samples']))
