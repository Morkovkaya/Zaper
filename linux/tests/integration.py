"""Run only in an isolated network namespace/container with CAP_NET_ADMIN."""
import json
import os
from pathlib import Path
import signal
import socket
import threading
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zapret_manager as manager


def nft(*args):
    return manager.checked(['nft', *args])


def wait_for(predicate, process, label):
    deadline = time.monotonic() + 15
    while not predicate():
        if process.poll() is not None:
            raise RuntimeError(f'{label}: supervisor exited {process.returncode}')
        if time.monotonic() > deadline:
            raise RuntimeError('Timeout: ' + label)
        time.sleep(.1)


def has_table():
    return subprocess.run(['nft', 'list', 'table', 'inet', manager.TABLE], capture_output=True).returncode == 0


def test_lifecycle(crash):
    log = tempfile.TemporaryFile(mode='w+')
    process = subprocess.Popen([sys.executable, str(manager.HOME / 'zapret_manager.py'), 'run'], stdout=log, stderr=log)
    try:
        wait_for(has_table, process, 'table readiness')
        # An independent nft table survives start/stop/crash.
        assert 'sentinel' in nft('list', 'table', 'inet', 'sentinel')
        # IPv4 and IPv6 traffic actually reaches and leaves NFQUEUE.
        for address in ('127.0.0.1', '::1'):
            subprocess.run(['ping', '-c', '1', '-W', '2', address], check=True, capture_output=True)
        # UDP on both IP families passes through the real NFQUEUE engine.
        for family, address in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
            with socket.socket(family, socket.SOCK_DGRAM) as server, socket.socket(family, socket.SOCK_DGRAM) as client:
                server.bind((address, 0))
                server.settimeout(3)
                client.settimeout(3)
                def echo():
                    payload, peer = server.recvfrom(1024)
                    server.sendto(payload, peer)
                thread = threading.Thread(target=echo)
                thread.start()
                client.sendto(b'Linux NFQUEUE echo', server.getsockname())
                assert client.recv(1024) == b'Linux NFQUEUE echo'
                thread.join(timeout=4)
                assert not thread.is_alive()
        # Local HTTP on intercepted TCP port 80 validates both directions.
        server = subprocess.Popen([sys.executable, '-m', 'http.server', '80', '--bind', '127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(.2)
            manager.checked(['curl', '--noproxy', '*', '--max-time', '5', 'http://127.0.0.1/'])
        finally:
            server.terminate()
            server.wait(timeout=5)
        assert 'packets 0 bytes 0 queue' not in nft('list', 'table', 'inet', manager.TABLE).split('meta l4proto udp')[1].split('}')[0]
        # Duplicate manager must not remove the running manager's table.
        duplicate = subprocess.run([sys.executable, str(manager.HOME / 'zapret_manager.py'), 'run'], capture_output=True, timeout=15)
        assert duplicate.returncode == 1 and has_table()
        if crash:
            os.kill(manager.queue_owner(), signal.SIGKILL)
        else:
            process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
        assert process.returncode == (1 if crash else 0)
        assert not has_table()
        assert manager.queue_owner() is None
        assert 'sentinel' in nft('list', 'table', 'inet', 'sentinel')
        print('PASS: ' + ('engine crash cleanup' if crash else 'start, queue traffic, duplicate lock, graceful stop'))
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.seek(0)
        print(log.read()[-3000:])
        log.close()


if __name__ == '__main__':
    if os.environ.get('ZAPRET_ISOLATED_TEST') != '1':
        raise SystemExit('Set ZAPRET_ISOLATED_TEST=1 only inside a fresh isolated network namespace')
    nft('add', 'table', 'inet', 'sentinel')
    try:
        test_lifecycle(False)
        test_lifecycle(True)
        nft('add', 'table', 'inet', manager.TABLE)
        try:
            refused = subprocess.run([sys.executable, str(manager.HOME / 'zapret_manager.py'), 'run'], capture_output=True, timeout=15)
            assert refused.returncode == 1 and has_table()
            print('PASS: foreign table collision refused without deleting it')
        finally:
            nft('delete', 'table', 'inet', manager.TABLE)
    finally:
        nft('delete', 'table', 'inet', 'sentinel')
