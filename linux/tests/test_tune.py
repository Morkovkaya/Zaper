import base64
from contextlib import ExitStack
import dataclasses
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import zapret_manager as zm
import zaper_state as state
import zaper_tune as tune
import zaper_network as network
import zaper_maintenance as maintenance


def measurement(good=True,p90=.3):
    return network.summary([dict(network.sample('core',True),success=good,seconds=p90)])


class TuneTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        stack=ExitStack();self.addCleanup(stack.close)
        for target,name,value in ((state,'STATE',self.root/'state'),(zm,'CONFIG',self.root/'settings.json')):
            stack.enter_context(patch.object(target,name,value))
        stack.enter_context(patch.object(zm,'validate_engine',return_value='valid'))
        stack.enter_context(patch.object(zm,'queue_owner',return_value=None))
        stack.enter_context(patch.object(zm,'service_available',return_value=True))
        self.running=False;self.actions=[]
        def service(action):
            self.actions.append(action);self.running=action in ('start','restart')
        stack.enter_context(patch.object(zm,'service',side_effect=service))
        stack.enter_context(patch.object(maintenance,'service_active',side_effect=lambda:self.running))
        self.original=zm.Settings(strategy='host-seq',excluded_domains=['keep.example'])
        zm.atomic_save(self.original);self.raw=zm.CONFIG.read_bytes()

    def execute(self,**kwargs): return tune.tune(spawn_watch=False,settle=0,**kwargs)

    def test_winner_hysteresis_success_fraction_and_latency(self):
        def row(name,p90,good=True): return dict(id=name,measurement=measurement(good,p90))
        current=row('current',.3)
        self.assertIs(tune.winner([current,row('split',.27)]),current)
        self.assertEqual(tune.winner([current,row('split',.20)])['id'],'split')
        self.assertIsNone(tune.winner([row('split',.2,False)]))

    def test_all_candidates_finalists_and_original_baseline_stopped_state(self):
        seen=[]
        def measure(rounds,cancel):
            strategy=zm.load_settings().strategy;seen.append((rounds,strategy));return measurement(True,.1 if strategy=='split' else .4)
        result=self.execute(measure=measure)
        self.assertEqual(result['strategy'],'split');self.assertFalse(self.running)
        self.assertEqual(zm.load_settings().strategy,'split');self.assertEqual(seen[0],(2,'host-seq'))
        self.assertEqual(len(seen),11);self.assertFalse(tune.journal().exists())
        tune.recover(force=True)
        self.assertEqual(zm.CONFIG.read_bytes(),self.raw);self.assertFalse(self.running)

    def test_failed_and_cancelled_tune_restore_exact_bytes_and_running_state(self):
        self.running=True
        with self.assertRaisesRegex(RuntimeError,'Ни одна'): self.execute(measure=lambda *a:measurement(False))
        self.assertEqual(zm.CONFIG.read_bytes(),self.raw);self.assertTrue(self.running)
        cancel=threading.Event()
        def measure(*args): cancel.set();network.checkpoint(cancel)
        with self.assertRaises(network.Cancelled): self.execute(event=cancel,measure=measure)
        self.assertEqual(zm.CONFIG.read_bytes(),self.raw);self.assertTrue(self.running)
        self.assertFalse(tune.journal().exists())

    def test_finalist_failure_rolls_back(self):
        with self.assertRaisesRegex(RuntimeError,'Повторная'):
            self.execute(measure=lambda rounds,*a:measurement(rounds==2))
        self.assertEqual(zm.CONFIG.read_bytes(),self.raw)

    def test_crash_recovery_journal_and_concurrent_lock(self):
        state.STATE.mkdir()
        tune.write(tune.journal(),dict(config=base64.b64encode(self.raw).decode(),running=True,pid=99999999,birth='none'))
        zm.atomic_save(zm.Settings(game='all'))
        self.assertTrue(tune.recover()['recovered']);self.assertEqual(zm.CONFIG.read_bytes(),self.raw);self.assertTrue(self.running)
        with state.operation():
            with self.assertRaisesRegex(RuntimeError,'операции'): self.execute(measure=lambda *a:measurement())
        self.assertEqual(zm.CONFIG.read_bytes(),self.raw)

    def test_recovery_failure_keeps_journal_and_no_false_success(self):
        with patch.object(zm,'service',side_effect=RuntimeError('systemctl failed')):
            with self.assertRaisesRegex(RuntimeError,'systemctl'): self.execute(measure=lambda *a:measurement())
        self.assertTrue(tune.journal().exists())

    def test_pending_journal_blocks_other_mutations_until_recovery(self):
        state.STATE.mkdir()
        tune.write(tune.journal(),dict(config=base64.b64encode(self.raw).decode(),running=False,pid=99999999,birth='none'))
        with self.assertRaisesRegex(RuntimeError,'Незавершённый'):state.save_settings(zm.Settings(game='udp'))
        tune.recover();self.assertEqual(zm.CONFIG.read_bytes(),self.raw)
