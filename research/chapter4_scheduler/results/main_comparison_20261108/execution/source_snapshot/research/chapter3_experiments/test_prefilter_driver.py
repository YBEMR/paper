"""One-use K108 controller checks with mock workers; no solver or research run."""
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_prefilter_diagnostic as d
from inputs import load_config
from run_milp_precheck import fixtures


class DriverTests(unittest.TestCase):
    def temporary(self):
        root=d.REPO/'.runtime'/'prefilter_correctness';root.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def small_manifest(self):
        jobs=[{'problem_id':'fixture_'+str(i//2),'variant':v,'prefilter_deadlines':v=='prefilter',
            'method':'milp','seed':None,'seconds':300,'call_id':f'fixture_{i//2}__{v}'}
            for i,v in enumerate(['current','prefilter']*3)]
        return {'jobs':jobs,'calls':6,'input_sha256':{j['problem_id']:'fixture' for j in jobs}}

    def records(self,root):
        m=self.small_manifest();s={'fixture':'hash'};fp=d.canonical_hash(m)
        gate={'passed':True,'count':1,'checks':[{'passed':True}],
              'source_sha256':s,'manifest_sha256':fp}
        g=root/'gate.json';a=root/'approval.json';r=root/'review.json'
        d.save(g,gate);d.save(a,{'approved':True,'manifest_sha256':fp,'source_sha256':s,
                              'user_confirmation_text':'TEST ONLY'})
        d.save(r,{'passed':True,'source_sha256':s,'manifest_sha256':fp,
                  'precheck_record_sha256':d.digest(g)})
        return m,s,g,a,r

    def test_manifest_exact_six_jobs_same_input_per_pair(self):
        m=d.manifest();self.assertEqual(m['calls'],6);self.assertEqual(m['maximum_method_seconds'],1800)
        self.assertEqual([j['problem_id'] for j in m['jobs']],
            [p for p in ['base__R1','initial_78__R1','response_R__R1'] for _ in range(2)])
        self.assertEqual([j['variant'] for j in m['jobs']],['current','prefilter']*3)
        self.assertTrue(all(j['seconds']==300 for j in m['jobs']))
        self.assertEqual(len({j['call_id'] for j in m['jobs']}),6)
        self.assertEqual(set(m['input_sha256']),set(j['problem_id'] for j in m['jobs']))

    def test_rules_rejects_physical_config_drift(self):
        with patch.object(d,'digest',return_value='wrong'):
            self.assertRaises(ValueError,d.rules)

    def test_gate_requires_current_precheck_approval_and_independent_review(self):
        with self.temporary() as folder:
            root=Path(folder);m,s,g,a,r=self.records(root)
            with patch.object(d,'manifest',return_value=m),patch.object(d,'signature',return_value=s):
                self.assertEqual(d.validate_gate(g,a,r),m)
                original=json.loads(r.read_text());bad=deepcopy(original);bad['precheck_record_sha256']='wrong'
                d.save(r,bad);self.assertRaises(ValueError,d.validate_gate,g,a,r);d.save(r,original)
                original=json.loads(g.read_text());bad=deepcopy(original);bad['source_sha256']={'new':'source'}
                d.save(g,bad);self.assertRaises(ValueError,d.validate_gate,g,a,r);d.save(g,original)
                bad=json.loads(a.read_text());bad['approved']=False;d.save(a,bad)
                self.assertRaises(ValueError,d.validate_gate,g,a,r)

    def test_claim_cannot_be_reused_in_another_output(self):
        with self.temporary() as folder:
            root=Path(folder);m,_,_,a,_=self.records(root)
            d.claim(a,m,root/'first');self.assertRaises(FileExistsError,d.claim,a,m,root/'second')

    def run_mock(self,root,*,error=False,timeout=False,source_change=False):
        m,s,g,a,r=self.records(root);spawned=[]
        class Process:
            returncode=0
            pid=987654321
            def __init__(self,args,**kwargs):
                spawned.append(args);self.waits=0;self.returncode=1 if error else 0
                target=Path(args[args.index('--out')+1]);target.mkdir()
                if not error:
                    d.save(target/'result.json',{'state':'UNRESOLVED','reason':'NO_INTEGER_CANDIDATE'})
                    d.save(target/'input_instance.json',{})
            def wait(self,timeout):
                self.waits+=1
                if timeout and self.waits==1 and timeout_case:
                    raise subprocess.TimeoutExpired('fixture',timeout)
                return self.returncode
            def kill(self):self.returncode=-9
        timeout_case=timeout
        with ExitStack() as stack:
            stack.enter_context(patch.object(d,'validate_gate',return_value=m))
            stack.enter_context(patch.object(d,'source_paths',return_value={}))
            if source_change:
                stack.enter_context(patch.object(d,'signature',side_effect=[s,{'changed':'source'},s]))
            else:stack.enter_context(patch.object(d,'signature',return_value=s))
            stack.enter_context(patch.object(d,'technical_check',return_value={'passed':True,'errors':[]}))
            stack.enter_context(patch.object(d.subprocess,'Popen',side_effect=Process))
            killer=stack.enter_context(patch.object(d.subprocess,'run'))
            d.run(g,a,r,root/'run')
        return spawned,json.loads((root/'run/calls.json').read_text()),killer

    def test_worker_error_stops_remaining_calls_without_retry(self):
        with self.temporary() as folder:
            spawned,calls,_=self.run_mock(Path(folder),error=True)
            self.assertEqual(len(spawned),1);self.assertEqual(len(calls),1)
            self.assertFalse(calls[0]['technical_check']['passed'])
            self.assertTrue((Path(folder)/'run/stop.json').is_file())

    def test_no_safe_or_improvement_is_not_a_reason_to_retry_or_expand(self):
        with self.temporary() as folder:
            spawned,calls,_=self.run_mock(Path(folder))
            self.assertEqual(len(spawned),6);self.assertEqual(len(calls),6)
            self.assertTrue(all(c['technical_check']['passed'] for c in calls))
            self.assertFalse((Path(folder)/'run/stop.json').exists())

    def test_cleanup_watchdog_terminates_only_current_pid_then_stops(self):
        with self.temporary() as folder:
            spawned,calls,killer=self.run_mock(Path(folder),timeout=True)
            self.assertEqual(len(spawned),1);self.assertEqual(len(calls),1)
            self.assertTrue(calls[0]['cleanup_watchdog']);self.assertFalse(calls[0]['technical_check']['passed'])
            if d.sys.platform=='win32':
                self.assertEqual(killer.call_args.args[0],['taskkill','/PID','987654321','/T','/F'])

    def test_source_change_stops_before_any_worker(self):
        with self.temporary() as folder:
            spawned,calls,_=self.run_mock(Path(folder),source_change=True)
            self.assertEqual(spawned,[]);self.assertEqual(calls,[])

    def test_technical_check_keeps_unresolved_distinct_and_requires_variant(self):
        i,starts=deepcopy(fixtures(load_config())['one_stage_energy'])
        j={'problem_id':i['id'],'variant':'prefilter','prefilter_deadlines':True,
           'method':'milp','seed':None,'seconds':300,'call_id':i['id']+'__prefilter'}
        sha=d.canonical_hash(i)
        r={'state':'UNRESOLVED','reason':'NO_INTEGER_CANDIDATE','safe_upper_bound_J':None,
           'timing':{'limit_s':300},'source_signature_unchanged':True,
           'candidate_and_cache_shared_between_calls':False,'prefilter_deadlines':True,
           'preprocessing_variant':'prefilter','input_sha256':sha,
           'call_id':j['call_id'],'problem_id':i['id'],'method':'milp','seed':None}
        self.assertTrue(d.technical_check(r,i,j,sha)['passed'])
        bad=deepcopy(r);bad['prefilter_deadlines']=False
        self.assertFalse(d.technical_check(bad,i,j,sha)['passed'])
        self.assertFalse(d.technical_check(r,i,j,'different-input')['passed'])
        bad=deepcopy(r);bad.update(model_complete=True,model_summary={'formulation':{}})
        self.assertFalse(d.technical_check(bad,i,j,sha)['passed'])
        for reason in ('SOLVER_INTERFACE_ERROR','INITIALISED_SOLVER_INTERFACE_ERROR',
                       'NUMERICAL_CANDIDATE_ANOMALY'):
            bad=deepcopy(r);bad['reason']=reason
            self.assertFalse(d.technical_check(bad,i,j,sha)['passed'])

    def test_worker_reloads_and_builds_its_own_bound_inside_supplied_budget(self):
        i,_=deepcopy(fixtures(load_config())['one_stage_energy']);events=[]
        j={'problem_id':i['id'],'variant':'current','prefilter_deadlines':False,
           'method':'milp','seed':None,'seconds':300,'call_id':i['id']+'__current'}
        m={'jobs':[j],'input_sha256':{i['id']:d.canonical_hash(i)}};s={'fixture':'hash'}
        class Budget:
            elapsed=1
            def check(self):events.append('budget-check')
        def execute(loader,out,**kwargs):
            events.append(('method',kwargs));c,inst=loader(Budget());Path(out).mkdir()
            d.save(Path(out)/'input_instance.json',inst)
            return {'state':'UNRESOLVED','safe_candidate':None}
        with self.temporary() as folder:
            root=Path(folder);declaration=root/'declaration.json'
            d.save(declaration,{'manifest':m,'source_sha256':s})
            with patch.object(d,'signature',return_value=s), \
                 patch.object(d,'load_config',return_value=load_config()), \
                 patch.object(d,'build_instance',side_effect=lambda c,name,budget:events.append('fresh-input') or deepcopy(i)), \
                 patch.object(d,'independent_lower_bound',side_effect=lambda inst:events.append('fresh-L0') or {'lower_bound_J':'1'}), \
                 patch('prefilter_method.execute_prefilter_method',side_effect=execute):
                d.worker(j,root/'call',declaration)
            self.assertEqual(events[0][1],{'seconds':300,'variant':'current'})
            self.assertEqual(events[1:3],['fresh-input','fresh-L0'])
            r=json.loads((root/'call/result.json').read_text())
            self.assertEqual(r['certified_lower_bound_J'],'1');self.assertEqual(r['independent_lower_bound']['formed_at_s'],1)
            self.assertTrue(r['source_signature_unchanged'])


if __name__=='__main__':unittest.main()
