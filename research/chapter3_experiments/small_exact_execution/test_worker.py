"""Pure K194 worker lifecycle fixtures. Every receipt/evaluator is synthetic."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_once as r


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=HERE)
        self.out=Path(self.temp.name)/'fixture'
        r.prepare(self.out,fixture_only=True)
        self.sha=r.digest(self.out/'declaration.json')
        self.tick=[100.0]

    def tearDown(self):
        self.temp.cleanup()

    def worker(self,evaluator,admitter):
        with redirect_stdout(StringIO()), patch('subprocess.Popen',side_effect=AssertionError('Native launch forbidden')):
            return r.worker(self.out,self.sha,100.0,evaluator=evaluator,admitter=admitter,clock=lambda:self.tick[0])

    def test_full_mock_batch_has_1550_unique_calls_never_formal_reference(self):
        seen=[]
        def evaluate(view,candidate,**kwargs):
            seen.append(r.canonical(candidate));return {'fixture_only':True}
        def admit(*args): return {'state':'SAFE','energy_J':['1','1'],'technical_stop':False}
        terminal=self.worker(evaluate,admit)
        self.assertEqual(terminal['state'],'COMPLETED')
        self.assertEqual(terminal['calls_started'],1550)
        self.assertEqual(len(set(seen)),1550)
        self.assertFalse(terminal['formal_reference_accepted'])
        self.assertTrue(terminal['fixture_only'])
        self.assertEqual(len(list((self.out/'receipts').glob('*.admission.json'))),1550)

    def test_normal_timeout_continues_then_technical_stops(self):
        calls=[]
        def evaluate(*args,**kwargs): calls.append(1);return {}
        def admit(*args):
            return {'state':'UNRESOLVED','energy_J':None,'technical_stop':False,'reason':'wall_time_limit'} if len(calls)==1 else {'state':'TECHNICAL_UNRESOLVED','energy_J':None,'technical_stop':True,'reason':'fixture_fault'}
        terminal=self.worker(evaluate,admit)
        self.assertEqual(terminal['calls_started'],2)
        self.assertEqual(terminal['counts']['UNRESOLVED'],1)
        self.assertEqual(terminal['counts']['NOT_STARTED'],1548)

    def test_timely_violation_survives_following_technical_fault(self):
        terminal=self.worker(lambda *a,**k:{},lambda *a:{'state':'VIOLATION','energy_J':None,'technical_stop':True,'reason':'later_fault'})
        self.assertEqual(terminal['calls_started'],1)
        self.assertEqual(terminal['counts']['VIOLATION'],1)
        self.assertFalse(terminal['formal_reference_accepted'])

    def test_raw_saved_before_admission_and_duplicate_claim_denied(self):
        def fail(*args):
            files=list((self.out/'receipts').glob('*.json'))
            self.assertEqual(len(files),1)
            self.assertEqual(json.loads(files[0].read_bytes())['raw_receipt'],{'timely_evidence':'fixture'})
            raise ValueError('admission fixture failure')
        terminal=self.worker(lambda *a,**k:{'timely_evidence':'fixture'},fail)
        self.assertEqual(terminal['calls_started'],1)
        self.assertEqual(terminal['counts']['TECHNICAL_UNRESOLVED'],1)
        with self.assertRaises(FileExistsError): self.worker(lambda *a,**k:{},fail)

    def test_shared_root_deadline_stops_without_reset_or_refill(self):
        def evaluate(*args,**kwargs):
            self.assertEqual(kwargs['budget'].start,100)
            self.assertEqual(kwargs['budget'].deadline,110)
            self.tick[0]=2501.0
            return {}
        terminal=self.worker(evaluate,lambda *a:{'state':'UNRESOLVED','energy_J':None,'technical_stop':False})
        self.assertEqual(terminal['calls_started'],1)
        self.assertEqual(terminal['reason'],'ROOT_TIME_LIMIT')
        self.assertEqual(terminal['counts']['NOT_STARTED'],1549)
        self.assertFalse(terminal['reference_formed_before_root_deadline'])

    def test_source_fault_keeps_previous_violation_and_coverage(self):
        original=r.verify_sources
        seen=[]
        def verify(declaration):
            seen.append(1)
            if len(seen)>1: raise ValueError('SOURCE_DRIFT fixture')
            return original(declaration)
        with patch.object(r,'verify_sources',side_effect=verify):
            terminal=self.worker(lambda *a,**k:{},lambda *a:{'state':'VIOLATION','energy_J':None,'technical_stop':True})
        self.assertEqual(terminal['state'],'TECHNICAL_STOP')
        self.assertEqual(terminal['counts']['VIOLATION'],1)
        self.assertTrue((self.out/'coverage_records.json').exists())

    def test_fixture_declaration_cannot_launch_real_worker(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Must not launch')):
            with self.assertRaisesRegex(ValueError,'fixture'):
                r.launch(self.out,self.sha)
        self.assertFalse((self.out/'launch.claim.json').exists())

    def test_supervisor_simulation_passes_one_shared_root_without_real_launch(self):
        declaration=json.loads((self.out/'declaration.json').read_bytes())
        declaration['fixture_only']=False
        (self.out/'declaration.json').write_text(json.dumps(declaration),encoding='utf-8')
        identity=r.digest(self.out/'declaration.json')
        seen=[]
        class FakeProcess:
            pid=99999999
            returncode=0
            def poll(self): return 0
            def wait(self,timeout): return 0
        def popen(args,**kwargs):
            seen.append(args)
            self.assertEqual(args[3],'worker')
            self.assertEqual(args[6],identity)
            self.assertEqual(args[7],'--root-start')
            return FakeProcess()
        with patch.object(r,'memory_probe',return_value={'passed':True,'fixture_only':True}), \
             patch.object(r.subprocess,'Popen',side_effect=popen),redirect_stdout(StringIO()):
            terminal=r.launch(self.out,identity)
        self.assertEqual(len(seen),1)
        self.assertEqual(terminal['state'],'WORKER_EXITED')
        self.assertFalse((self.out/'method.claim.json').exists())

    def test_payload_drift_stops_before_any_evaluation(self):
        with (self.out/'input_instance.json').open('a') as stream: stream.write(' ')
        terminal=self.worker(lambda *a,**k:self.fail('No evaluator call allowed'),lambda *a:None)
        self.assertEqual(terminal['calls_started'],0)
        self.assertEqual(terminal['state'],'TECHNICAL_STOP')


if __name__=='__main__': unittest.main(verbosity=2)
