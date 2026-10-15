"""Transactional strategy selection, durable rollback and process-death recovery."""
import base64
import dataclasses
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zaper_state as state
import zaper_network as network


def identity(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return None if fields[0]=='Z' else fields[19]
    except (OSError, IndexError): return None


def journal(): return state.STATE / 'tune-pending.json'
def results_path(): return state.STATE / 'tune-results.json'


def write(path, value):
    state.atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode())


def winner(rows):
    valid = [x for x in rows if x.get('measurement') and x['measurement']['valid']]
    def ratio(x):
        m=x['measurement']; return m['good']/len(m['samples']) if m['samples'] else 0
    best = min(valid, key=lambda x: (-ratio(x), x['measurement']['p90'], x['measurement']['median']), default=None)
    current = next((x for x in valid if x['id']=='current'), None)
    if best and current and best is not current:
        p90=current['measurement']['p90']
        if ratio(best)<=ratio(current) and best['measurement']['p90']>=p90-max(.05,p90*.15): return current
    return best


def original_config():
    zm=state.backend()
    return base64.b64encode(zm.CONFIG.read_bytes()).decode() if zm.CONFIG.exists() else None


def restore_bytes(data):
    zm=state.backend()
    if data['config'] is None: zm.CONFIG.unlink(missing_ok=True)
    else: state.atomic_bytes(zm.CONFIG, base64.b64decode(data['config'], validate=True))


def restore_owned(data):
    zm=state.backend()
    # Stop candidate before restoring. Journal remains intact if any recovery step fails.
    zm.service('stop')
    restore_bytes(data)
    if data['running']: zm.service('start')


def recover(force=False, engine_start=False):
    if not journal().exists() and not force: return {'recovered': False}
    with state.operation(allow_pending=True):
        source = state.STATE/'tune-last-backup.json' if force else journal()
        if not source.exists(): raise RuntimeError('Резервная копия автоподбора отсутствует')
        data=json.loads(source.read_text())
        if identity(data['pid'])==data['birth'] and not force: raise RuntimeError('Автоподбор ещё работает')
        state.snapshot('auto-tune-recovery')
        if engine_start:
            # Called inside the starting service: never recursively call systemctl on itself.
            restore_bytes(data)
        else: restore_owned(data)
        journal().unlink(missing_ok=True)
        return {'recovered': True, 'running': data['running']}


def recover_before_engine():
    if journal().exists():
        data=json.loads(journal().read_text())
        if identity(data['pid']) != data['birth']:
            result=recover(engine_start=True)
            return result['running']
    return True


def watch(pid, birth):
    while identity(pid)==birth: time.sleep(.2)
    if journal().exists():
        data=json.loads(journal().read_text())
        if data['pid']==pid and data['birth']==birth:
            recover()


class Cancellation:
    def __init__(self, event): self.event=event
    def is_set(self): return self.event.is_set() or (state.STATE/'tune-cancel').exists()
    def wait(self, timeout): return self.event.wait(timeout)


def cancel():
    if not journal().exists(): return {'cancel_requested': False}
    state.atomic_bytes(state.STATE/'tune-cancel', b'cancel\n')
    return {'cancel_requested': True, 'note':'Дождитесь отката настроек и службы'}


def tune(event=None, progress=None, measure=None, spawn_watch=True, settle=1):
    import zaper_maintenance as maintenance
    zm=state.backend(); measure=measure or network.measure
    event=event or threading.Event(); cancellation=Cancellation(event)
    progress=progress or (lambda percent,message: None)
    if journal().exists(): recover()
    with state.operation():
        if zm.queue_owner() and not maintenance.service_active():
            raise RuntimeError('Остановите foreground-движок перед автоподбором')
        if not zm.service_available():raise RuntimeError('Автоподбор требует запущенный systemd; сохранённые настройки не изменены')
        settings=zm.load_settings(); zm.validate_engine(settings)
        state.snapshot('before-auto-tune')
        data=dict(config=original_config(), running=maintenance.service_active(), pid=os.getpid(), birth=identity(os.getpid()))
        (state.STATE/'tune-cancel').unlink(missing_ok=True)
        write(journal(), data)
        write(state.STATE/'tune-last-backup.json',data)
        if spawn_watch:
            subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve()),'--watch',str(os.getpid()),data['birth']],
                             start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        rows=[]
        try:
            def apply(strategy):
                network.checkpoint(cancellation)
                candidate=dataclasses.replace(settings, strategy=settings.strategy if strategy=='current' else strategy)
                zm.validate_engine(candidate)
                zm.service('stop')
                zm.atomic_save(candidate)
                zm.service('start')
                if cancellation.wait(settle): network.checkpoint(cancellation)
                network.checkpoint(cancellation)
            for i,strategy in enumerate(zm.STRATEGIES):
                network.checkpoint(cancellation)
                progress(i*85//len(zm.STRATEGIES),'Стратегия '+str(i+1)+'/9: '+strategy)
                row=dict(id=strategy,measurement=None,error='')
                try:
                    apply(strategy); row['measurement']=measure(2,cancellation)
                except network.Cancelled: raise
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc: row['error']=str(exc)
                rows.append(row); write(results_path(),rows)
            best=winner(rows)
            if best is None: raise RuntimeError('Ни одна стратегия не прошла обязательные проверки')
            progress(90,'Повторная проверка финалистов')
            finalists=[x for x in rows if x['id']=='current' or x is best]
            for row in finalists:
                apply(row['id']); row['measurement']=measure(3,cancellation)
            write(results_path(),rows)
            best=winner(finalists)
            if best is None: raise RuntimeError('Повторная проверка не пройдена')
            apply(best['id']); network.checkpoint(cancellation)
            if not data['running']: zm.service('stop')
            journal().unlink()
            progress(100,'Выбрана стратегия: '+best['id'])
            return dict(strategy=settings.strategy if best['id']=='current' else best['id'], results=rows, previous_running=data['running'])
        except BaseException:
            restore_owned(data)
            journal().unlink(missing_ok=True)
            raise
        finally:
            (state.STATE/'tune-cancel').unlink(missing_ok=True)


if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    if len(sys.argv)==4 and sys.argv[1]=='--watch': watch(int(sys.argv[2]),sys.argv[3])
