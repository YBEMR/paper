"""Private fake-service worker lifecycle; importing science is forbidden."""
import argparse
from contextlib import contextmanager,redirect_stdout
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
REPO=SCIENCE.parents[1]
sys.path.insert(0,str(SCIENCE))
from linked_release_execution import worker as w
from linked_release_execution import registry as r

GUARD={'scientific_import':0,'scientific_code_entry':0,'real_process_launch':0}
ALLOWED={str(p.resolve()).replace('\\','/') for p in (Path(__file__),HERE/'worker.py',HERE/'registry.py')}


class GuardViolation(BaseException):pass


def audit(event,args):
    if event=='import' and args[0].split('.')[-1] in {'numpy','scipy','thermal','milp','inputs',
        'timing','matlab_bridge','run_p0','neighborhood_method','linked_method','linked_release_method','linked_release_policy','initial_schedule'}:
        GUARD['scientific_import']+=1;raise GuardViolation('real science import: '+args[0])
    if event=='subprocess.Popen' or event=='os.system' or event.startswith('os.spawn'):
        GUARD['real_process_launch']+=1;raise GuardViolation('real process: '+event)


def profile(frame,event,arg):
    if event=='call':
        filename=frame.f_code.co_filename.replace('\\','/')
        if '/research/chapter3_experiments/' in filename and '/results/' not in filename and filename not in ALLOWED:
            GUARD['scientific_code_entry']+=1;raise GuardViolation('real scientific default alias: '+filename)


class Clock:
    def __init__(self):self.time=0.0
    def __call__(self):return self.time
    def step(self,n):self.time+=n


class FakeBudget:
    made=[]
    def __init__(self,seconds,*,clock):
        self.clock=clock;self.seconds=seconds;self.start=clock();self.deadline=self.start+seconds
        self.records=[];self._scene_adapter_budget_identity={'FAKE_ROOT_ONLY':len(self.made)+1}
        self.made.append(self)
    @property
    def elapsed(self):return self.clock()-self.start
    @property
    def remaining(self):return max(0,self.deadline-self.clock())
    def check(self):
        if self.clock()>=self.deadline:raise TimeoutError('FAKE_ROOT_EXHAUSTED')
    @contextmanager
    def phase(self,name):
        self.check();self.records.append(name)
        yield


class WorkerTests(unittest.TestCase):
    def setUp(self):
        scratch=(REPO/'.runtime').resolve();scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='k176_worker_fake_',dir=scratch)
        Path(self.temp.name).resolve().relative_to(scratch);self.addCleanup(self.temp.cleanup)
        self.repo=Path(self.temp.name);self.batch=self.repo/'FAKE_batch';self.batch.mkdir()
        self.claims=self.batch/'claims';self.claims.mkdir();(self.batch/'calls').mkdir()
        self.path=self.batch/'declaration.json';self.global_claim=self.repo/'FAKE_global.json'
        self.clock=Clock();self.imports=[];self.dispatches=[];self.fresh=[]
        self.raw={'MOCK_ONLY':'raw'};self.config={'MOCK_ONLY':'config'};self.instance={'MOCK_ONLY':'instance'}
        self.model_file=self.repo/'source_fixture.txt';self.model_file.write_text('fixture-source','utf-8')
        self.matlab_file=self.repo/'FAKE_matlab_not_executable.txt';self.matlab_file.write_text('not executable','utf-8')
        proposal=json.loads((SCIENCE/'results/linked_release_integration01/next_proposal.json').read_text('utf-8-sig'))
        self.cases=[{'common':deepcopy(proposal['common']),'recipes':deepcopy(proposal['recipes'])}]
        for case in self.cases:
            case['common']['config_sha256']=w._canonical(self.config)
            case['common']['input_sha256']=w._canonical(self.instance)
        self.declaration={'protocol':r.PROTOCOL,'budgets':{'method_s':300},'slots':[{**deepcopy(x),'slot_id':x['case_id']+'__'+x['variant']} for x in proposal['slots']],
            'cases':self.cases,'source_sha256':{'source_fixture.txt':w._sha(self.model_file)},
            'frozen_dependency_sha256':{},'protected_archive_sha256':{},
            'environment':{'python_executable':str(Path(sys.executable).resolve()),'python_version':'FAKE_PYTHON',
                'platform':'FAKE_PLATFORM','matlab_executable':str(self.matlab_file),
                'matlab_executable_sha256':w._sha(self.matlab_file)}}
        r.write_new(self.path,self.declaration)
        r.write_new(self.global_claim,{'protocol':r.PROTOCOL,'declaration_sha256':w._sha(self.path),
            'no_retry':True,'call_limit':2,'method_seconds_limit':600,'post_calls_limit':2,
            'post_seconds_limit':120,'calendar_deadline_monotonic':1200,
            'started_utc':datetime.now(timezone.utc).isoformat(),
            'calendar_deadline_utc':(datetime.now(timezone.utc)+timedelta(seconds=1200)).isoformat()})
        self.registry=SimpleNamespace(REPO=self.repo,GLOBAL_CLAIM=self.global_claim,PROTOCOL=r.PROTOCOL,
            load_declaration=lambda path:deepcopy(self.declaration),
            slot_spec=lambda d,s:next(x for x in d['slots'] if x['slot_id']==s),
            case_spec=lambda d,c:next(x for x in d['cases'] if x['common']['case_id']==c))
    def environment(self):
        return {'python_executable':str(Path(sys.executable).resolve()),'python_version':'FAKE_PYTHON','platform':'FAKE_PLATFORM'}
    def importer(self,name):
        self.assertTrue(FakeBudget.made)
        root=FakeBudget.made[-1]
        self.imports.append({'name':name,'root':root,'elapsed':root.elapsed})
        self.clock.step(1)
        if name in ('linked_method','linked_release_method'):
            return SimpleNamespace(execute_linked_conditional_release=self.entry,execute_linked_fixed_unit_opp_start=self.entry)
        if name=='matlab_bridge':
            def forbidden_native(*a,**kw):raise AssertionError('no fake fixture may start native session')
            return SimpleNamespace(DEFAULT_MATLAB=str(self.matlab_file),MatlabSession=forbidden_native)
        if name=='p0_batch.run_p0':return SimpleNamespace(fresh_input=self.fresh_input)
        raise AssertionError('unexpected importer name: '+name)
    def fresh_input(self,case,budget):
        self.fresh.append((case,budget));self.clock.step(1)
        return deepcopy(self.raw),deepcopy(self.config),deepcopy(self.instance)
    def entry(self,loader,folder,**kwargs):
        root=FakeBudget.made[-1];self.assertIs(kwargs['budget'],root);self.assertIs(kwargs['clock'],root.clock)
        self.assertEqual(kwargs['session_factory'].keywords,{'cut_max_iterations':10})
        config,instance=loader(root)
        self.assertEqual((config,instance),(self.config,self.instance))
        folder.mkdir(exist_ok=False)
        self.dispatches.append({'kwargs':kwargs,'folder':folder,'root':root})
        self.clock.step(1)
        return {'not_scientific':True,'state':'UNRESOLVED','reason':'FAKE_ONLY_NO_SCIENCE',
            'timing':{'limit_s':300},'condition':{'budget_identity':deepcopy(root._scene_adapter_budget_identity)}}
    def invoke(self,variant='C',**service_changes):
        slot=next(s for s in self.declaration['slots'] if s['case_id']=='base__R3' and s['variant']==variant)
        out=self.batch/'calls'/slot['slot_id'];out.mkdir(exist_ok=True)
        claim=self.claims/(slot['slot_id']+'.json')
        if not claim.exists():r.write_new(claim,{**slot,'protocol':r.PROTOCOL,
            'declaration_sha256':w._sha(self.path),'state':'CONSUMED_BEFORE_LAUNCH','no_retry':True,
            'slot_deadline_monotonic':self.clock()+480})
        services={'budget_class':FakeBudget,'clock':self.clock,'registry':self.registry,
            'environment':self.environment,'import_module':self.importer}
        services.update(service_changes)
        with redirect_stdout(io.StringIO()):code=w.run_worker(self.path,slot['slot_id'],out,_services=services)
        return code,out

    def test_C_release_parameters_root_before_import_and_fresh_unpack(self):
        for variant in ('C','conditional_release'):
            with self.subTest(variant=variant):
                code,out=self.invoke(variant);self.assertEqual(code,0)
                dispatch=self.dispatches[-1];kwargs=dispatch['kwargs'];root=dispatch['root']
                self.assertEqual(kwargs['scene_slice_s'],60)
                self.assertIn('linked_opened_by_scene',kwargs)
                if variant=='C':self.assertIs(kwargs['preeliminate_closed_anchors'],True)
                else:self.assertNotIn('preeliminate_closed_anchors',kwargs)
                recipe=self.cases[0]['recipes'][variant]
                self.assertEqual({k:v for k,v in kwargs.items() if k in recipe['kwargs']},recipe['kwargs'])
                self.assertEqual(root.seconds,300);self.assertEqual(root.deadline-root.start,300)
                arm_import=next(x for x in self.imports if x['root'] is root)
                self.assertEqual(arm_import['name'],'linked_method' if variant=='C' else 'linked_release_method')
                self.assertIs(self.fresh[-1][1],root)
                raw=r.read(out/'wrapper_raw_result.json');self.assertEqual(raw,r.read(out/'result.json'))
                identity=r.read(out/'worker_identity.json');receipt=r.read(out/'worker_return.json')
                self.assertTrue(identity['not_scientific']);self.assertFalse(identity['scientific_admission_eligible'])
                self.assertTrue(receipt['not_scientific']);self.assertEqual(identity['fresh_input_calls'],1)
                self.assertTrue(identity['input_verified']);self.assertTrue(identity['source_verified'])
                self.assertEqual(identity['budget_identity'],root._scene_adapter_budget_identity)
                self.assertEqual(receipt['exit_zero_scope'],'files saved and reviewable only; not scientific SAFE or native cleanup approval')
    def test_duplicate_started_slot_rejected_and_old_evidence_unchanged(self):
        code,out=self.invoke();self.assertEqual(code,0)
        before={p.name:w._sha(p) for p in out.iterdir() if p.is_file()}
        code,_=self.invoke();self.assertNotEqual(code,0)
        self.assertEqual(before,{p.name:w._sha(p) for p in out.iterdir() if p.is_file()})
        self.assertEqual(len(self.dispatches),1)
    def test_wrong_input_blocks_returned_scientific_result(self):
        def wrong(case,budget):self.fresh.append((case,budget));return self.raw,self.config,{'WRONG_INPUT':True}
        self.fresh_input=wrong
        code,out=self.invoke();self.assertNotEqual(code,0)
        self.assertFalse((out/'wrapper_raw_result.json').exists());self.assertFalse(r.read(out/'worker_identity.json')['input_verified'])
    def test_wrong_environment_blocks_arm_import_and_dispatch(self):
        code,out=self.invoke(environment=lambda:{**self.environment(),'python_version':'DIFFERENT'})
        self.assertNotEqual(code,0);self.assertFalse(self.imports);self.assertFalse(self.dispatches)
        self.assertFalse(r.read(out/'worker_identity.json')['environment_verified'])
    def test_source_drift_before_entry_blocks_arm_import(self):
        self.model_file.write_text('drifted-fixture-only','utf-8')
        code,out=self.invoke();self.assertNotEqual(code,0)
        self.assertFalse(self.imports);self.assertFalse(self.dispatches)
        self.assertFalse(r.read(out/'worker_identity.json')['source_verified'])
    def test_wrong_batch_counts_and_reservations_block_dispatch(self):
        for field,value in (('call_limit',3),('method_seconds_limit',601),
                            ('post_calls_limit',3),('post_seconds_limit',121)):
            with self.subTest(field=field):
                claim=r.read(self.global_claim);original=deepcopy(claim)
                claim[field]=value
                self.global_claim.write_text(json.dumps(claim),'utf-8')
                # Isolated fake slot paths preserve every refusal record.
                slot=self.declaration['slots'][0]
                out=self.batch/'calls'/slot['slot_id']
                if out.exists():
                    out.rename(out.with_name(out.name+'_'+field))
                code,_=self.invoke('C');self.assertNotEqual(code,0)
                self.assertFalse(self.imports);self.assertFalse(self.dispatches)
                self.global_claim.write_text(json.dumps(original),'utf-8')
    def test_full_300_root_must_fit_remaining_batch_calendar(self):
        claim=r.read(self.global_claim);claim['calendar_deadline_monotonic']=299
        self.global_claim.write_text(json.dumps(claim),'utf-8')
        code,out=self.invoke();self.assertNotEqual(code,0)
        self.assertFalse(self.imports);self.assertFalse(self.dispatches)
        self.assertFalse(r.read(out/'worker_identity.json')['scientific_call_started'])
    def test_duplicate_input_loader_is_rejected_on_same_root(self):
        def double_loader(loader,folder,**kwargs):
            root=kwargs['budget'];loader(root);loader(root)
            raise AssertionError('second input load must not complete')
        self.entry=double_loader
        code,out=self.invoke();self.assertNotEqual(code,0)
        self.assertEqual(len(self.fresh),1)
        self.assertEqual(r.read(out/'worker_identity.json')['fresh_input_calls'],1)
        self.assertFalse((out/'result.json').exists())
    def test_arm_import_time_is_billed_before_original_dispatch(self):
        code,out=self.invoke('conditional_release');self.assertEqual(code,0)
        identity=r.read(out/'worker_identity.json')
        self.assertEqual([x['name'] for x in self.imports],
            ['linked_release_method','matlab_bridge','p0_batch.run_p0'])
        self.assertEqual(identity['worker_root_deadline_s']-identity['worker_root_start_s'],300)
        self.assertGreaterEqual(identity['method_dispatch_started_s']-identity['worker_root_start_s'],3)
        self.assertIn('worker_selected_arm_imports',FakeBudget.made[-1].records)
    def test_archive_failure_preserves_already_returned_fake_result(self):
        original=w._write_new
        def fail_identity(path,value):
            if Path(path).name=='worker_identity.json':raise OSError('FAKE_IDENTITY_ARCHIVE_FAILURE')
            return original(path,value)
        with patch.object(w,'_write_new',side_effect=fail_identity):code,out=self.invoke()
        self.assertEqual(code,3)
        self.assertEqual(r.read(out/'result.json'),r.read(out/'wrapper_raw_result.json'))
        self.assertTrue(r.read(out/'result.json')['not_scientific'])
        self.assertFalse((out/'worker_return.json').exists())


def main(output):
    if output.exists():raise FileExistsError('append-only fake checks')
    output.mkdir(parents=True)
    paths=[Path(__file__),HERE/'worker.py',HERE/'registry.py']
    before={p.relative_to(REPO).as_posix():r.sha(p) for p in paths}
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(WorkerTests))
    finally:sys.setprofile(None)
    after={name:r.sha(REPO/name) for name in before}
    report={'protocol':r.PROTOCOL,'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'source_sha256':before,'source_after_sha256':after,'source_unchanged':before==after,
        'guard':GUARD,'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0,
        'scope':'private _services fake worker lifecycle; every output not_scientific and real admission ineligible',
        'passed':result.wasSuccessful() and before==after and not any(GUARD.values())}
    r.write_new(output/'checks.json',report);(output/'unittest.txt').write_text(stream.getvalue(),'utf-8')
    print(json.dumps({'FAKE_ONLY_NOT_RESEARCH':True,**{k:report[k] for k in ('passed','tests_run','failures','errors','guard')}},ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(parser.parse_args().out))
