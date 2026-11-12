"""Read-only old-archive and synthetic-worker fixtures; never runs a scientific entry."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
SCIENCE=HERE.parent
RESULTS=SCIENCE/'results'
spec=importlib.util.spec_from_file_location('K173_pure_audit',HERE/'audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
ATTEMPTS=[]
def guard(event,args):
    if event=='import' and str(args[0]).split('.')[0] in {'numpy','scipy','thermal','milp','matlab','schedules','inputs','linked_method','neighborhood_method'}:
        ATTEMPTS.append(str(args[0]));raise RuntimeError('Scientific import forbidden')
    if event in ('subprocess.Popen','os.system','socket.connect'):
        ATTEMPTS.append(event);raise RuntimeError('Scientific/process entry forbidden')
sys.addaudithook(guard)

def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')

class AuditFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal=audit.read(RESULTS/'linked_ablation_preparation01/preparation02/proposal.json')
        cls.original=RESULTS/'p0_execution01/calls/base__R1/anchor_linked4'
        cls.raw=audit.read(cls.original/'result.json')
        cls.instance=audit.read(cls.original/'input_instance.json');cls.config=audit.read(cls.original/'input_config.json')
        cls.closed=audit.read(cls.original/'matlab/closed.json')
        cls.post=audit.read(cls.original/'postcheck.json')
        cls.original_hashes={str(p):audit.sha(p) for p in [cls.original/'result.json',cls.original/'postcheck.json',cls.original/'input_instance.json',cls.original/'input_config.json']}
    def setUp(self):
        fixture_parent=(RESULTS/'linked_ablation_execution01/review/fixture_tmp').resolve()
        fixture_parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='K173_audit_fixture_',dir=fixture_parent)
        base=Path(self.temp.name).resolve()
        assert base.is_relative_to(fixture_parent) and base.name.startswith('K173_audit_fixture_')
        self.base=base;self.folder=base/'calls/base__R1__C';self.folder.mkdir(parents=True)
        self.slot=deepcopy(next(s for s in self.proposal['slots'] if s['case_id']=='base__R1' and s['variant']=='C'))
        self.decl=deepcopy(self.proposal)
        self.decl['scientific_source_sha256']=deepcopy(self.proposal['source_sha256'])
        self.r=deepcopy(self.raw)
        write(base/'declaration.json',self.decl)
        write(self.folder/'input_instance.json',self.instance);write(self.folder/'input_config.json',self.config)
        write(self.folder/'method/matlab/closed.json',self.closed)
        self.wi={'slot_id':self.slot['slot_id'],'case_id':'base__R1','variant':'C',
            'input_verified':True,'source_verified':True,'environment_verified':True,'fresh_input_calls':1,
            'declaration_sha256':audit.sha(base/'declaration.json'),
            'recipe_sha256':audit.canonical(self.decl['cases'][0]['recipes']['C']),
            'budget_identity':self.r['condition']['budget_identity'],
            'worker_root_start_s':float(self.r['condition']['budget_identity']['start']),
            'worker_root_deadline_s':float(self.r['condition']['budget_identity']['start'])+300,
            'limit_s':300,'not_scientific':False}
        self.refresh()
    def tearDown(self):self.temp.cleanup()
    def refresh(self):
        write(self.folder/'result.json',self.r);write(self.folder/'wrapper_raw_result.json',self.r)
        write(self.folder/'worker_identity.json',self.wi)
        write(self.folder/'worker_return.json',{'passed':True,'scientific_call_started':True,'not_scientific':False,
            'slot_id':self.slot['slot_id'],'case_id':self.slot['case_id'],'variant':self.slot['variant'],
            'declaration_sha256':self.wi['declaration_sha256'],'identity_sha256':audit.sha(self.folder/'worker_identity.json'),
            'result_sha256':audit.sha(self.folder/'result.json'),'wrapper_raw_result_sha256':audit.sha(self.folder/'wrapper_raw_result.json')})
    def run_audit(self):return audit.audit_slot(self.folder,self.slot,self.decl)
    def test_archived_complete_C_can_be_classified(self):
        r=self.run_audit();self.assertTrue(r['passed'],r);self.assertTrue(r['eligible_for_post']);self.assertEqual(r['usable_U_J'],self.raw['safe_upper_bound_J'])
    def test_A_schema_with_only_cap_label_normalized(self):
        self.r=audit.read(RESULTS/'linked_quality_pair01/old_n1/result.json')
        self.r['scene_slice_s']=150 # metadata fixture only, no new search or candidate
        self.slot=deepcopy(next(s for s in self.proposal['slots'] if s['case_id']=='base__R1' and s['variant']=='A'))
        self.wi.update(variant='A',slot_id=self.slot['slot_id'],recipe_sha256=audit.canonical(self.decl['cases'][0]['recipes']['A']),
            budget_identity=self.r['condition']['budget_identity'],worker_root_start_s=float(self.r['condition']['budget_identity']['start']),
            worker_root_deadline_s=float(self.r['condition']['budget_identity']['start'])+300)
        self.refresh();r=self.run_audit();self.assertTrue(r['passed'],r)
    def test_fake_worker_not_scientific_is_rejected(self):
        self.wi['not_scientific']=True;self.refresh();self.assertFalse(self.run_audit()['can_continue'])
    def test_wrong_slot_identity_rejected(self):
        self.wi['case_id']='base__R3';self.refresh();self.assertFalse(self.run_audit()['eligible_for_post'])
    def test_incomplete_scene_is_not_SAFE_U(self):
        a=self.r['aggregation'];a['scenes']['AB_offset_0ms']['result']['complete']=False
        self.refresh();r=self.run_audit();self.assertFalse(r['eligible_for_post']);self.assertIsNone(r['usable_U_J'])
    def test_late_aggregate_never_admitted(self):
        a=self.r['aggregation'];a['completed_at_elapsed_s']=300.001;a['receipt_sha256']=audit.receipt_hash(a)
        self.refresh();r=self.run_audit();self.assertIsNone(r['usable_U_J']);self.assertFalse(r['can_continue'])
    def test_normal_deadline_preserves_already_complete_U(self):
        self.r.update(reason='wall_time_limit',budget_exhausted=True,search_failure_latched=True)
        self.r['timing']['method_elapsed_s']=300.02;self.refresh();r=self.run_audit()
        self.assertTrue(r['can_continue'],r);self.assertEqual(r['classification'],'NORMAL_TIME_LIMIT');self.assertEqual(r['usable_U_J'],self.raw['safe_upper_bound_J'])
    def test_numerical_conflict_at_cutoff_is_not_cleared(self):
        self.r.update(reason='wall_time_limit',budget_exhausted=True);self.r['timing']['method_elapsed_s']=300.02
        last=list(self.r['phases'][-1]['scenes'].values())[-1]['solver_result']['rounds'][-1]
        last['numerical_consistency']={'state':'NUMERICAL_ADMISSION_STATUS_CONFLICT'}
        self.refresh();r=self.run_audit();self.assertFalse(r['can_continue']);self.assertEqual(r['classification'],'NUMERICAL_ANOMALY_OBSERVED');self.assertEqual(r['usable_U_J'],self.raw['safe_upper_bound_J'])
    def test_condition_closed_anchor_tamper_rejected(self):
        self.r['phases'][1]['condition']['warm_candidate_sha256']='wrong';self.refresh();self.assertFalse(self.run_audit()['eligible_for_post'])
    def test_missing_cleanup_blocks_post_but_retains_U(self):
        (self.folder/'method/matlab/closed.json').unlink();r=self.run_audit();self.assertFalse(r['eligible_for_post']);self.assertEqual(r['usable_U_J'],self.raw['safe_upper_bound_J'])
    def make_post_fixture(self):
        a=self.run_audit();self.assertTrue(a['eligible_for_post'],a);write(self.folder/'audit.json',a)
        identity={'slot_id':self.slot['slot_id'],'raw_result_sha256':audit.sha(self.folder/'wrapper_raw_result.json'),
            'input_sha256':audit.canonical(self.instance),'candidate_sha256':audit.canonical(self.r['safe_candidate']),
            'accuracy_sha256':audit.canonical(self.config['accuracy_targets']),'declaration_source_sha256':self.decl['source_sha256']}
        write(self.folder/'postcheck.claim.json',identity);write(self.folder/'postcheck.json',self.post)
        p={**identity,'passed':True,'new_U':False,'no_search_or_repair':True,'post_seconds':60,
            'evaluation_calls':1,'not_scientific':False,'evaluation_elapsed_s':1,
            'postcheck_sha256':audit.sha(self.folder/'postcheck.json'),'method_audit_sha256':audit.sha(self.folder/'audit.json')}
        write(self.folder/'post_return.json',p);return a,p
    def test_existing_post_fixture_only_no_new_evaluation(self):
        a,p=self.make_post_fixture();self.assertTrue(audit.audit_post(self.folder,self.slot,self.decl,a)['passed'])
    def test_post_new_U_or_late_false_flags_rejected(self):
        a,p=self.make_post_fixture();p['new_U']=True;p['evaluation_elapsed_s']=61;write(self.folder/'post_return.json',p)
        self.assertFalse(audit.audit_post(self.folder,self.slot,self.decl,a)['passed'])
    def test_post_unsafe_peak_is_rejected(self):
        a,p=self.make_post_fixture();q=deepcopy(self.post);sid=next(iter(q['scenes']));node=next(iter(q['scenes'][sid]['peaks_degC']))
        q['scenes'][sid]['peaks_degC'][node]=['81','82'];write(self.folder/'postcheck.json',q)
        p['postcheck_sha256']=audit.sha(self.folder/'postcheck.json');write(self.folder/'post_return.json',p)
        self.assertFalse(audit.audit_post(self.folder,self.slot,self.decl,a)['passed'])

def main(output):
    output=Path(output)
    if output.exists():raise FileExistsError('append only precheck')
    before={str(p):audit.sha(p) for p in (HERE/'audit.py',HERE/'post_worker.py',HERE/'analyze.py',HERE/'test_audit.py')}
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AuditFixtures)
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    after={p:audit.sha(p) for p in before}
    originals=AuditFixtures.original_hashes
    unchanged=all(audit.sha(p)==v for p,v in originals.items())
    report={'protocol':'K173-stored-audit-post-identity-pure-precheck-v1','tests_run':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful() and unchanged and before==after and not ATTEMPTS,
        'source_before_sha256':before,'source_after_sha256':after,'original_archive_sha256':originals,
        'original_archives_unchanged':unchanged,'forbidden_attempts':ATTEMPTS,
        'fixture_scope':'Temporary archive copies and synthetic worker/post metadata only; A cap normalized in fixture only. No live method, heat or post execution. No new scientific candidate or U.',
        'new_models':0,'solver_calls':0,'thermal_or_post_calls':0,'new_research_calls':0}
    output.mkdir(parents=True);write(output/'checks.json',report)
    (output/'unittest.txt').write_text(log.getvalue(),'utf-8')
    print(json.dumps({'passed':report['passed'],'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},ensure_ascii=False))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
