"""E4b two-count identity/control regressions, never real research."""
from copy import deepcopy
from pathlib import Path
import tempfile,time,unittest,uuid
from unittest.mock import patch
from .protocol import PROTOCOL_ID,SLOTS,BUDGETS,SUPERVISION
from .input_contract import prepare_inputs
from e1_objective.execution_io import (REPO,DEFAULT_GATE,protocol_slots,protocol_limits,sha,file_sha,
                                      runtime_paths,validate_gate,save,read_json,verify_job)
from e1_objective.ledger import Ledger,LedgerError
from e1_objective.controller import run_phase,run_batch,_fresh_packet
from e1_objective.mock_fixtures import make_fixture


def materials(base,mode='MOCK_PROCESS',source_sha='a'*40):
    m=dict(protocol_id=PROTOCOL_ID,source_sha=source_sha,mode=mode,slots=[list(s) for s in SLOTS],
           budgets=dict(BUDGETS),supervision=dict(SUPERVISION),files={},inputs={})
    run=base/'run';g=dict(protocol_id=PROTOCOL_ID,kind=mode,authorized=mode=='REAL_RESEARCH',
        four_slot_authorized=False,stage_authorized=True,mock_only=mode=='MOCK_PROCESS',
        approval_reference='TEST_ONLY_NOT_REAL_AUTHORIZATION',authorization_id='mock-e4-req-'+uuid.uuid4().hex,
        source_sha=source_sha,budgets=dict(BUDGETS),authority_store=str((base/'authority').resolve()),
        allowed_run_directory=str(run.resolve()))
    # Legacy flag is kept only by old E1/E2. E4b uses its explicit stage flag.
    g['scope_sha256']=sha(m)
    return m,g,run


def mock_materials(base,source_sha='a'*40):
    m,g,r=materials(base,source_sha=source_sha);f=make_fixture(h_activity_power_W='4')
    p=dict(config=dict(accuracy_targets=f['accuracy']),instance=f['instance'],objective='FULL')
    m['mock_input']=dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config']),
        accuracy_sha256=sha(f['accuracy']),objective='FULL',packet_sha256={'FULL':sha(p)})
    m['files']={rel:file_sha(REPO/rel) for rel in runtime_paths('MOCK_PROCESS')};g['scope_sha256']=sha(m)
    validate_gate(g,m,'MOCK_PROCESS',r)
    l=Ledger(g['authority_store'],g,r,kind='MOCK_PROCESS');l.claim_batch(dict(manifest_sha256=sha(m)))
    return p,m,g,r,l


class RequestCountProtocolTests(unittest.TestCase):
    def test_fixed_two_arms_and_720_evidence_seconds(self):
        self.assertEqual(protocol_slots({'protocol_id':PROTOCOL_ID}),[list(s) for s in SLOTS])
        limits=protocol_limits({'protocol_id':PROTOCOL_ID})
        self.assertEqual(limits['budgets'],BUDGETS);self.assertEqual(limits['supervision'],SUPERVISION)
        self.assertEqual(2*300+2*60,720)
        limits['budgets']['plan_calls']=99
        self.assertEqual(protocol_limits({'protocol_id':PROTOCOL_ID})['budgets']['plan_calls'],2)

    def test_e1_e2_legacy_limits_still_four_and_1800(self):
        for pid in ('E1_OBJECTIVE_V1','E2_RESOURCES_V1'):
            limits=protocol_limits({'protocol_id':pid})
            self.assertEqual(limits['budgets']['plan_calls'],4);self.assertEqual(limits['supervision']['batch_wall_s'],1800)

    def test_prior_two_and_three_slot_protocols_remain_unchanged(self):
        for pid,count,wall in [('E3_DEPLOYMENT_V1',2,960),('E4_DEADLINE_V1',3,1380)]:
            with self.subTest(protocol=pid):
                limits=protocol_limits({'protocol_id':pid})
                self.assertEqual(limits['budgets']['plan_calls'],count)
                self.assertEqual(limits['supervision']['batch_wall_s'],wall)

    def test_old_stage_authorizations_cannot_consume_request_batch(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);m,g,r=materials(b,'REAL_RESEARCH');save(b/'manifest.json',m)
            for pid in ('E3_DEPLOYMENT_V1','E4_DEADLINE_V1'):
                old=deepcopy(g);old['protocol_id']=pid;old['budgets']=protocol_limits(old)['budgets'];save(b/'old.json',old)
                with self.subTest(protocol=pid),patch('e1_objective.controller.Ledger',side_effect=AssertionError('no claim')),self.assertRaises(ValueError):
                    run_batch(b/'manifest.json',b/'old.json',r)
            self.assertFalse(r.exists())

    def test_e4_requests_explicit_real_gate_accepts_two_not_four(self):
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t),'REAL_RESEARCH');self.assertEqual(validate_gate(g,m,'REAL_RESEARCH',r),g)
            g['budgets']['plan_calls']=4
            with self.assertRaisesRegex(ValueError,'SLOTS_DRIFT'):validate_gate(g,m,'REAL_RESEARCH',r)

    def test_e4_requests_gate_requires_explicit_protocol_and_stage_approval(self):
        with tempfile.TemporaryDirectory() as t:
            for field in ('protocol_id','stage_authorized'):
                m,g,r=materials(Path(t),'REAL_RESEARCH');del g[field]
                with self.subTest(field=field),self.assertRaises(ValueError):validate_gate(g,m,'REAL_RESEARCH',r)

    def test_wrong_total_or_extra_slot_refused(self):
        with tempfile.TemporaryDirectory() as t:
            for edit in ('wall','slot'):
                m,g,r=materials(Path(t),'REAL_RESEARCH')
                if edit=='wall':m['supervision']['batch_wall_s']=1800
                else:m['slots'].append(['base__R3','FULL'])
                g['scope_sha256']=sha(m)
                with self.subTest(edit=edit),self.assertRaises(ValueError):validate_gate(g,m,'REAL_RESEARCH',r)

    def test_old_budget_auth_or_default_gate_denied_before_claim(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);m,g,r=materials(b,'REAL_RESEARCH');save(b/'manifest.json',m)
            old=deepcopy(g);old['protocol_id']='E2_RESOURCES_V1';old['budgets'].update(plan_calls=4,post_calls=4)
            save(b/'old.json',old)
            for auth in (b/'old.json',DEFAULT_GATE):
                with self.subTest(auth=str(auth)),patch('e1_objective.controller.Ledger',side_effect=AssertionError('no claim')),\
                     self.assertRaises(ValueError):run_batch(b/'manifest.json',auth,r)
            self.assertFalse(r.exists())

    def test_ledger_enforces_third_slot_without_process(self):
        with tempfile.TemporaryDirectory() as t:
            p,m,g,r,l=mock_materials(Path(t))
            ctx=dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config']),
                     accuracy_sha256=sha(p['config']['accuracy_targets']),objective='FULL')
            for n in (0,3,True):
                with self.subTest(slot=n),self.assertRaises(LedgerError):l.claim_plan(n,time.monotonic(),ctx)
                with self.subTest(phase_slot=n),self.assertRaisesRegex(ValueError,'PHASE_SLOT'):
                    run_phase(l,g,m,r,n,'PLAN',slot_origin=time.monotonic(),batch_origin=time.monotonic(),packet_loader=lambda:p)
            self.assertFalse((l.root/'03_plan_claim.json').exists());self.assertFalse(r.exists())

    def test_ledger_unknown_or_e4_requests_four_call_authorization_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t));g['budgets']['plan_calls']=4
            with self.assertRaisesRegex(LedgerError,'BUDGETS'):Ledger(g['authority_store'],g,r,kind='MOCK_PROCESS')
            g['protocol_id']='UNKNOWN'
            with self.assertRaisesRegex(LedgerError,'PROTOCOL'):Ledger(g['authority_store'],g,r,kind='MOCK_PROCESS')

    def test_fresh_parent_view_matches_both_frozen_inputs_static_only(self):
        packets=prepare_inputs()
        for problem,objective in SLOTS:
            with self.subTest(problem=problem):self.assertEqual(_fresh_packet(problem,objective),packets[problem])

    def test_real_job_identities_of_both_views_without_backend(self):
        packets=prepare_inputs()
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t),'REAL_RESEARCH')
            m['inputs']={pid:dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config'])) for pid,p in packets.items()}
            g['scope_sha256']=sha(m)
            for n,(pid,objective) in enumerate(SLOTS,1):
                p=packets[pid];ctx=dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config']),
                    accuracy_sha256=sha(p['config']['accuracy_targets']),objective=objective,packet_sha256=sha(p))
                claim=dict(phase='PLAN',ordinal=n,root_origin=1,limit_s=300,source_sha=m['source_sha'],
                           kind='REAL_RESEARCH',run_dir=str(r),job_context=ctx)
                job=dict(mode='REAL_RESEARCH',run_dir=str(r),scope_sha256=sha(m),phase='PLAN',ordinal=n,
                         root_origin=1,limit_s=300,claim=claim,packet=p)
                with self.subTest(slot=n):self.assertTrue(verify_job(job,g,m,r/('slot_'+str(n))/'plan'))
                wrong=deepcopy(job);wrong['packet']=deepcopy(packets[SLOTS[n%2][0]])
                with self.subTest(wrong_slot=n),self.assertRaisesRegex(ValueError,'REAL_SLOT_IDENTITY'):
                    verify_job(wrong,g,m,r/('slot_'+str(n))/'plan')

    def test_controller_stops_at_two_slots_without_any_worker(self):
        with tempfile.TemporaryDirectory() as t:
            b=Path(t);m,g,r=materials(b,'REAL_RESEARCH');save(b/'m.json',m);save(b/'g.json',g)
            class NoResearchLedger:
                def __init__(self,*args,**kwargs):r.mkdir()
                def claim_batch(self,*args):pass
                def stop(self,*args):pass
            with patch('e1_objective.controller.Ledger',NoResearchLedger),\
                 patch('e1_objective.controller.run_phase',return_value=dict(result=dict(state='UNRESOLVED',stop_required=False))) as phase:
                run_batch(b/'m.json',b/'g.json',r)
            self.assertEqual([x.args[4] for x in phase.call_args_list],[1,2])
            self.assertEqual(read_json(r/'batch_summary.json')['planned_slots'],2)

    def test_mock_two_plan_post_pairs_bind_same_candidate_and_deadline(self):
        with tempfile.TemporaryDirectory(prefix='e4_requests_mock_') as t:
            p,m,g,r,l=mock_materials(Path(t));batch=time.monotonic()
            for n in (1,2):
                start=time.monotonic();plan=run_phase(l,g,m,r,n,'PLAN',slot_origin=start,batch_origin=batch,packet_loader=lambda:deepcopy(p))
                self.assertEqual(plan['result']['state'],'SAFE',plan)
                post=run_phase(l,g,m,r,n,'POST',slot_origin=start,batch_origin=batch,packet=p,planning_result=plan['result'])
                self.assertEqual(post['result']['state'],'POST_SAFE',post)
                self.assertEqual(post['result']['candidate_sha256'],plan['result']['selected_candidate_sha256'])
                self.assertEqual(plan['job']['batch_deadline'],batch+960)
                for x in (plan,post):
                    ret=read_json(Path(x['output'])/'worker_return.json')
                    self.assertFalse(ret['guard']['real_backend_entered']);self.assertEqual(ret['guard']['science_modules_loaded'],[])
                with self.assertRaises(LedgerError):l.claim_post(n,time.monotonic(),post['job']['selected_token'])
            self.assertEqual(len(list(l.root.glob('*_claim.json'))),4)

    def test_parent_input_preparation_cannot_reset_300_root(self):
        with tempfile.TemporaryDirectory() as t:
            p,m,g,r,l=mock_materials(Path(t));start=time.monotonic()
            def delayed():time.sleep(.2);return deepcopy(p)
            out=run_phase(l,g,m,r,1,'PLAN',slot_origin=start,batch_origin=start,packet_loader=delayed,mock_prior_elapsed_s=299.9)
            self.assertEqual(out['result']['state'],'UNRESOLVED');self.assertFalse(out['result']['stop_required'])
            self.assertEqual(out['process']['classification'],'PREPARATION_CUTOFF')
            self.assertFalse((l.root/'01_plan_launch.json').exists())

if __name__=='__main__':unittest.main()
