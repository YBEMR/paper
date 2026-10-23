"""K176 pure fake two-slot and owned-process lifecycle checks; no science."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
REPO=SCIENCE.parents[1]
sys.path.insert(0,str(SCIENCE))
from linked_release_execution import batch as b,supervise as s,registry as r

GUARD={'scientific_import':0,'scientific_code_entry':0,'real_process_launch':0}
ALLOWED={str(p.resolve()).replace('\\','/') for p in (Path(__file__),HERE/'batch.py',HERE/'supervise.py',HERE/'registry.py')}


class GuardViolation(BaseException):pass


def audit(event,args):
    if event=='import' and args[0].split('.')[-1] in {
        'milp','thermal','inputs','schedules','matlab_bridge','worker','post_worker',
        'neighborhood_method','linked_method','initial_schedule','initial_point'}:
        GUARD['scientific_import']+=1;raise GuardViolation('science import forbidden: '+args[0])
    if event=='subprocess.Popen' or event=='os.system' or event.startswith('os.spawn'):
        GUARD['real_process_launch']+=1;raise GuardViolation('real process forbidden: '+event)


def profile(frame,event,arg):
    if event=='call':
        filename=frame.f_code.co_filename.replace('\\','/')
        if '/research/chapter3_experiments/' in filename and '/results/' not in filename and filename not in ALLOWED:
            GUARD['scientific_code_entry']+=1;raise GuardViolation('science/default alias forbidden: '+filename)


class FakeClock:
    def __init__(self):self.value=0.0;self.base=datetime(2026,10,23,tzinfo=timezone.utc)
    def __call__(self):return self.value
    def utc(self):return self.base+timedelta(seconds=self.value)
    def step(self,seconds):self.value+=seconds


def workspace_temp(test):
    scratch=(REPO/'.runtime').resolve();scratch.mkdir(exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='k176_fake_',dir=scratch)
    # Verify the exact recursive-cleanup target stays in this test workspace.
    Path(temporary.name).resolve().relative_to(scratch)
    test.addCleanup(temporary.cleanup)
    return temporary


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=workspace_temp(self)
        self.parent=Path(self.temp.name);self.out=self.parent/'FAKE_linked_release_execution01';self.out.mkdir()
        self.global_claim=self.parent/'FAKE_global_claim.json'
        self.clock=FakeClock();self.methods=[];self.posts=[];self.audits=[]
        self.patches=[patch.object(b,'OUT',self.out),patch.object(b,'GLOBAL_CLAIM',self.global_claim)]
        for item in self.patches:item.start();self.addCleanup(item.stop)
        # Preserve actual K175 slot metadata (run_once/state), rather than a
        # thin invented slot hiding the declaration-to-claim normalization.
        proposal={'slots':[dict(slot,run_once=True,state='AUTHORIZED_UNSTARTED') for slot in b.expected_slots()]}
        self.declaration={'slots':deepcopy(proposal['slots']),'MOCK_ONLY':True}
        for slot in self.declaration['slots']:slot['state']='AUTHORIZED_UNSTARTED'
        self.path=self.out/'declaration.json';b.write_new(self.path,self.declaration)
        b.write_new(self.out/'ledger.json',b.initial_ledger())
    def loader(self,path):return deepcopy(self.declaration)
    def executor(self,slot,folder,path,**limits):
        self.methods.append(slot['slot_id']);self.clock.step(5)
        self.assertEqual(slot['method_seconds'],300)
        self.assertEqual(limits['calendar_deadline_utc'],(self.clock.base+timedelta(seconds=1200)).isoformat())
        for name in ('result.json','wrapper_raw_result.json','input_config.json','input_instance.json'):
            b.write_new(folder/name,{'MOCK_ONLY':True,'slot_id':slot['slot_id'],'kind':name})
        return {'returncode':0,'process_closed':True,'watchdog_stop':None,'MOCK_ONLY':True}
    def auditor(self,folder,slot,declaration):
        self.audits.append(slot['slot_id'])
        return {'passed':True,'can_continue':True,'eligible_for_post':True,
                'classification':'NORMAL_COMPLETION','MOCK_ONLY':True}
    def post(self,slot,folder,path,**limits):
        self.posts.append(slot['slot_id']);self.clock.step(1)
        return {'returncode':0,'process_closed':True,'watchdog_stop':None,'MOCK_ONLY':True}
    def post_auditor(self,*args):return {'passed':True,'new_U':False,'MOCK_ONLY':True}
    def run_fake(self,**kwargs):
        entries={'executor':self.executor,'auditor':self.auditor,'post':self.post,
            'post_auditor':self.post_auditor,'declaration_loader':self.loader,
            'clock':self.clock,'utc_clock':self.clock.utc}
        entries.update(kwargs)
        return b.run(self.path,**entries)


class BatchLifecycleTests(Fixture):
    def test_complete_two_fixed_order_and_unique_posts(self):
        out=self.run_fake();self.assertEqual(out['state'],'COMPLETED')
        expected=[x['slot_id'] for x in b.expected_slots()]
        self.assertEqual(self.methods,expected);self.assertEqual(self.posts,expected)
        self.assertEqual((out['consumed'],out['reserved_method_budget_s'],out['post_consumed'],out['reserved_post_budget_s']),(2,600,2,120))
        self.assertEqual(b.read(self.out/'ledger.json')['state'],'COMPLETED')
        for slot in expected:
            self.assertTrue((self.out/'claims'/(slot+'.json')).is_file())
            self.assertTrue((self.out/'claims'/(slot+'__post.json')).is_file())
            self.assertTrue((self.out/'calls'/slot/'audit.json').is_file())
    def test_no_restart_after_complete(self):
        self.run_fake()
        with self.assertRaises(FileExistsError):self.run_fake()
        self.assertEqual(len(self.methods),2)
    def test_exception_consumes_one_and_stops_without_post(self):
        def broken(*args,**kwargs):self.methods.append('CRASH');raise RuntimeError('FAKE_INTERFACE_FAILURE')
        out=self.run_fake(executor=broken)
        self.assertEqual(out['state'],'BLOCKED');self.assertEqual((out['consumed'],out['reserved_method_budget_s']),(1,300))
        self.assertEqual((len(self.methods),len(self.posts),len(self.audits)),(1,0,0))
    def test_normal_no_safe_can_continue_with_no_post(self):
        def no_safe(*args):return {'passed':True,'can_continue':True,'eligible_for_post':False,'classification':'NORMAL_NO_INTEGER_CANDIDATE'}
        out=self.run_fake(auditor=no_safe)
        self.assertEqual(out['state'],'COMPLETED');self.assertEqual((len(self.methods),len(self.posts)),(2,0))
        self.assertEqual(out['post_consumed'],0)
    def test_normal_deadline_can_continue_but_numerical_or_coverage_failure_stops(self):
        count=0
        def deadline(*args):
            nonlocal count
            count+=1
            return {'passed':count==1,'can_continue':count==1,'eligible_for_post':count==1,
                'classification':'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST' if count==1 else 'NUMERICAL_UNRESOLVED'}
        out=self.run_fake(auditor=deadline)
        self.assertEqual(out['state'],'BLOCKED');self.assertEqual((len(self.methods),len(self.posts)),(2,1))
    def test_passed_without_explicit_post_eligibility_cannot_bypass_gate(self):
        out=self.run_fake(auditor=lambda *a:{'passed':True,'can_continue':True,'classification':'COVERAGE_UNRESOLVED'})
        self.assertEqual(out['consumed'],1);self.assertFalse(self.posts)
    def test_post_exception_consumed_once_no_retry(self):
        def crash(*args,**kwargs):self.posts.append('CRASH');raise RuntimeError('FAKE_POST_FAILURE')
        out=self.run_fake(post=crash)
        self.assertEqual((out['state'],out['consumed'],out['post_consumed']),('BLOCKED',1,1))
        self.assertEqual(len(self.methods),1);self.assertEqual(len(self.posts),1)
        with self.assertRaises(FileExistsError):self.run_fake()
    def test_post_cannot_modify_method_U_even_if_post_auditor_says_pass(self):
        def mutate(slot,folder,path,**kwargs):
            self.posts.append(slot['slot_id']);b.save(folder/'result.json',{'FAKE_REPLACED_U':'bad'})
            return {'returncode':0,'process_closed':True,'watchdog_stop':None}
        out=self.run_fake(post=mutate)
        self.assertEqual(out['state'],'BLOCKED');self.assertEqual(out['consumed'],1)
        audit=b.read(self.out/'calls'/'base__R3__C'/'post_audit.json')
        self.assertEqual(audit['reason'],'POST_CHANGED_METHOD_EVIDENCE')
    def test_source_drift_after_method_blocks_audit_post_and_new_slot(self):
        calls=0
        def loader(path):
            nonlocal calls
            calls+=1
            if calls>=3:raise ValueError('FAKE_SOURCE_DRIFT')
            return deepcopy(self.declaration)
        out=self.run_fake(declaration_loader=loader)
        self.assertEqual(out['state'],'BLOCKED');self.assertEqual((len(self.methods),len(self.posts)),(1,0))
    def test_calendar_crossed_during_gate_before_claim_consumes_zero(self):
        calls=0
        def loader(path):
            nonlocal calls
            calls+=1
            if calls==2:self.clock.step(1200)
            return deepcopy(self.declaration)
        out=self.run_fake(declaration_loader=loader)
        self.assertEqual(out['consumed'],0);self.assertEqual(out['reserved_method_budget_s'],0)
        self.assertEqual(len(self.methods),0);self.assertTrue(self.global_claim.is_file())
    def test_claim_is_authoritative_if_ledger_write_fails(self):
        original=b.save
        def fail(path,value):
            if Path(path).name=='ledger.json' and value.get('active') is not None:
                raise OSError('FAKE_LEDGER_REPLACE_FAILURE')
            return original(path,value)
        with patch.object(b,'save',side_effect=fail):out=self.run_fake()
        self.assertEqual(out['state'],'STOPPED_EXCEPTION');self.assertEqual(out['consumed'],1)
        self.assertEqual(out['reserved_method_budget_s'],300);self.assertFalse(self.methods)
    def test_prior_output_path_is_rejected_before_slot_consumption(self):
        (self.out/'calls').mkdir();(self.out/'calls'/'base__R3__C').mkdir()
        with self.assertRaises(FileExistsError):self.run_fake()
        self.assertFalse(self.global_claim.exists());self.assertFalse(self.methods)
    def test_nonzero_or_watchdog_process_receipt_cannot_reach_audit(self):
        def timeout(slot,folder,path,**kwargs):
            self.methods.append(slot['slot_id'])
            return {'returncode':0,'process_closed':True,'watchdog_stop':'METHOD_RETURN_LIMIT'}
        out=self.run_fake(executor=timeout)
        self.assertEqual(out['state'],'BLOCKED');self.assertEqual(out['consumed'],1)
        self.assertFalse(self.audits);self.assertFalse(self.posts)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp=workspace_temp(self)
        self.folder=Path(self.temp.name);self.clock=FakeClock()
        self.end=(self.clock.base+timedelta(seconds=1200)).isoformat()
    def test_fake_owned_process_natural_and_watchdog_cleanup(self):
        launches=[];kills=[];clock=self.clock
        class FakeProcess:
            pid=17301
            def __init__(self,finish):self.finish=finish;self.code=None
            def poll(self):
                if self.code is None and clock()>=self.finish:self.code=0
                return self.code
            def wait(self,timeout):
                clock.step(timeout)
                if self.poll() is None:raise subprocess.TimeoutExpired('FAKE',timeout)
                return self.code
        def popen(command,**kwargs):launches.append(kwargs);return FakeProcess(finish=2)
        with patch.object(subprocess,'CREATE_NO_WINDOW',0x08000000,create=True):
            out=s.run_child(['FAKE_ONLY'],self.folder,'method',watchdog_s=420,
                slot_deadline_monotonic=480,calendar_deadline_utc=self.end,clock=clock,utc_clock=clock.utc,
                popen_factory=popen,tree_killer=lambda proc:kills.append(proc.pid))
        self.assertEqual(out['returncode'],0);self.assertTrue(out['process_closed']);self.assertIsNone(out['watchdog_stop'])
        self.assertEqual(launches[0]['creationflags'],0x08000000);self.assertFalse(kills)
        other=self.folder/'second';other.mkdir();clock.value=0
        def long(*args,**kwargs):return FakeProcess(finish=1000)
        def kill(proc):kills.append(proc.pid);proc.code=-9;return {'owned_root_pid':proc.pid,'attempted':True}
        out=s.run_child(['FAKE_ONLY'],other,'method',watchdog_s=420,
            slot_deadline_monotonic=480,calendar_deadline_utc=self.end,clock=clock,utc_clock=clock.utc,
            popen_factory=long,tree_killer=kill)
        self.assertEqual(out['watchdog_stop'],'METHOD_RETURN_LIMIT');self.assertEqual(kills,[17301]);self.assertTrue(out['process_closed'])
    def test_expired_calendar_or_slot_never_launches_new_child(self):
        def forbidden(*args,**kwargs):raise AssertionError('no fake child may launch after cutoff')
        for deadline,utc_stop,expected in [(0,self.end,'SLOT_RETURN_LIMIT'),(480,self.clock.base.isoformat(),'CALENDAR_LIMIT')]:
            out=s.run_child(['FAKE_ONLY'],self.folder,'method',watchdog_s=420,
                slot_deadline_monotonic=deadline,calendar_deadline_utc=utc_stop,clock=self.clock,utc_clock=self.clock.utc,
                popen_factory=forbidden,tree_killer=forbidden)
            self.assertFalse(out['launched']);self.assertEqual(out['watchdog_stop'],expected)


def main(output):
    if output.exists():raise FileExistsError('prechecks are append-only')
    output.mkdir(parents=True)
    sources={p.relative_to(REPO).as_posix():r.sha(p) for p in (Path(__file__),HERE/'batch.py',HERE/'supervise.py',HERE/'registry.py')}
    prior=SCIENCE/'results/linked_ablation_preparation01/preparation02/proposal.json';prior_hash=r.sha(prior)
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        stream=io.StringIO()
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (BatchLifecycleTests,SupervisorTests)])
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    finally:sys.setprofile(None)
    after={name:r.sha(REPO/name) for name in sources}
    report={'protocol':b.PROTOCOL,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'source_sha256':sources,'source_after_sha256':after,'source_unchanged':sources==after,
        'original_preparation_unchanged':r.sha(prior)==prior_hash,'guard':GUARD,
        'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0,
        'scope':'FAKE two-slot executors/auditors/post and FAKE Popen only; no research process or source freeze/real claim',
        'passed':result.wasSuccessful() and sources==after and r.sha(prior)==prior_hash and not any(GUARD.values())}
    r.write_new(output/'checks.json',report);(output/'unittest.txt').write_text(stream.getvalue(),encoding='utf-8')
    print(json.dumps({'FAKE_ONLY_NOT_RESEARCH':True,**{k:report[k] for k in ('passed','tests_run','failures','errors','guard')}},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(parser.parse_args().out))
