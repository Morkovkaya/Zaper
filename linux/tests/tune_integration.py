"""Real engine transitions in a disposable network namespace; fixture measurements."""
import base64
import dataclasses
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zapret_manager as zm
import zaper_state as state
import zaper_tune as tune
import zaper_network as network
import zaper_maintenance as maintenance
assert os.environ.get('ZAPRET_ISOLATED_TEST')=='1'

if '--worker' in sys.argv:
    # Use real application paths inside disposable runner/container only.
    zm.supervise(zm.load_settings())
    sys.exit(0)

process=None

def active():return process is not None and process.poll() is None

def service(action):
    global process
    if action=='stop':
        if active():process.terminate();process.wait(timeout=8)
        process=None
    elif action=='start':
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+12
        while zm.queue_owner() is None:
            if process.poll() is not None:raise RuntimeError(process.stderr.read().decode())
            if time.monotonic()>deadline:raise RuntimeError('queue readiness timeout')
            time.sleep(.05)
    else:raise ValueError(action)

# Do not write the runner's real settings outside a disposable container, except
# dedicated application directories, which are removed/restored by this fixture.
original=zm.CONFIG.read_bytes() if zm.CONFIG.exists() else None
state.STATE.mkdir(parents=True,exist_ok=True)
saved={p.name:p.read_bytes() for p in state.STATE.glob('tune-*') if p.is_file()}
try:
    zm.atomic_save(zm.Settings(excluded_domains=['retain.example']))
    before=zm.CONFIG.read_bytes()
    def measure(rounds,cancel):
        assert zm.queue_owner() is not None
        settings=zm.load_settings()
        return network.summary([dict(network.sample('fixture core',True),success=True,seconds=.1 if settings.strategy=='split' else .5)])
    with patch.object(zm,'service_available',return_value=True),patch.object(zm,'service',side_effect=service),patch.object(maintenance,'service_active',side_effect=active):
        result=tune.tune(measure=measure,spawn_watch=False,settle=0)
        assert result['strategy']=='split' and not active()
        assert zm.CONFIG.exists() and not tune.journal().exists()
        tune.recover(force=True)
        assert zm.CONFIG.read_bytes()==before
        service('start')
        event=threading.Event()
        def cancelled(*args):event.set();network.checkpoint(event)
        try:tune.tune(event=event,measure=cancelled,spawn_watch=False,settle=0)
        except network.Cancelled:pass
        else:raise AssertionError('cancel did not raise')
        assert active() and zm.CONFIG.read_bytes()==before
        service('stop')
    print('PASS: real nfqws2 nine strategies, finalist recheck, rollback and prior running/stopped state',flush=True)
finally:
    service('stop')
    if original is None:zm.CONFIG.unlink(missing_ok=True)
    else:state.atomic_bytes(zm.CONFIG,original)
    for path in state.STATE.glob('tune-*'):
        if path.is_file():path.unlink()
    for name,data in saved.items():state.atomic_bytes(state.STATE/name,data)
