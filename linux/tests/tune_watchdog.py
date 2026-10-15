"""SIGKILL the actual tuner; its separately launched watchdog must restore bytes."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zapret_manager as zm
import zaper_tune as tune
import zaper_state as state
assert os.environ.get('ZAPRET_ISOLATED_TEST')=='1'

if '--worker' in sys.argv:
    import zaper_network as network
    def measure(*args):
        print('CANDIDATE',flush=True)
        time.sleep(60)
        return network.summary([])
    tune.tune(measure=measure,settle=0)
    sys.exit(0)

original=zm.CONFIG.read_bytes() if zm.CONFIG.exists() else None
state.STATE.mkdir(parents=True,exist_ok=True)
saved={p.name:p.read_bytes() for p in state.STATE.glob('tune-*') if p.is_file()}
process=None
try:
    # Fake only systemctl for this test process tree; never operate the runner's services.
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        script=root/'systemctl'
        script.write_text('#!/usr/bin/python3\nimport sys\nfrom pathlib import Path\np=Path('+repr(str(root/'running'))+')\na=sys.argv[1]\nif a=="is-active":sys.exit(0 if p.exists() else 3)\nif a=="start":p.touch()\nif a=="stop":p.unlink(missing_ok=True)\n')
        script.chmod(0o755)
        # Disposable environment only; root's backend requires systemd's availability marker.
        marker=Path('/run/systemd/system');created=not marker.exists();marker.mkdir(parents=True,exist_ok=True)
        try:
            for running in (False,True):
                if running:(root/'running').touch()
                else:(root/'running').unlink(missing_ok=True)
                zm.atomic_save(zm.Settings(strategy='host-seq',excluded_domains=['retain.example']))
                before=zm.CONFIG.read_bytes()
                env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ['PATH'])
                process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                # The child reaches measurement only after journal, watchdog and candidate writes.
                deadline=time.monotonic()+20
                import select
                while True:
                    if process.poll() is not None:raise RuntimeError(process.stderr.read())
                    if time.monotonic()>deadline:raise RuntimeError('tuner readiness timeout')
                    ready,_,_=select.select([process.stdout],[],[],.1)
                    if ready and 'CANDIDATE' in process.stdout.readline():break
                process.kill();process.wait(timeout=3)
                deadline=time.monotonic()+8
                while tune.journal().exists() and time.monotonic()<deadline:time.sleep(.1)
                assert not tune.journal().exists(),'watchdog did not clear pending journal'
                assert zm.CONFIG.read_bytes()==before,'watchdog did not restore original config'
                assert (root/'running').exists()==running,'watchdog did not restore prior running state'
                process.stdout.close();process.stderr.close();process=None
        finally:
            if created:marker.rmdir()
    print('PASS: SIGKILL tuner watchdog restores exact settings and running/stopped state',flush=True)
finally:
    if process is not None:
        if process.poll() is None:process.kill();process.wait()
        process.stdout.close();process.stderr.close()
    if original is None:zm.CONFIG.unlink(missing_ok=True)
    else:state.atomic_bytes(zm.CONFIG,original)
    for path in state.STATE.glob('tune-*'):
        if path.is_file():path.unlink()
    for name,data in saved.items():state.atomic_bytes(state.STATE/name,data)
