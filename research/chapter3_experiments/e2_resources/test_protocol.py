"""Protocol and real-process MOCK tests only; no real HEFT/thermal call."""
from copy import deepcopy
from pathlib import Path
import tempfile,time,unittest,uuid
from unittest.mock import patch
from .protocol import PROTOCOL_ID,SLOTS
from .input_contract import prepare_inputs
from e1_objective.execution_io import (REPO,DEFAULT_GATE,BUDGETS,protocol_slots,
    validate_gate,verify_job,sha,file_sha,runtime_paths,save,read_json)
from e1_objective.controller import run_phase,run_batch
from e1_objective.ledger import Ledger,LedgerError
from e1_objective.mock_fixtures import make_fixture


def materials(base,*,mode='REAL_RESEARCH',protocol=PROTOCOL_ID,source_sha='a'*40):
    m=dict(protocol_id=protocol,source_sha=source_sha,mode=mode,
           slots=[list(s) for s in SLOTS],budgets=deepcopy(BUDGETS),inputs={},files={})
    run=base/'run'
    g=dict(kind=mode,authorized=mode=='REAL_RESEARCH',four_slot_authorized=True,
           approval_reference='TEST_ONLY_NOT_A_REAL_AUTHORIZATION',mock_only=mode=='MOCK_PROCESS',
           authorization_id='test-'+uuid.uuid4().hex,source_sha=source_sha,
           budgets=deepcopy(BUDGETS),authority_store=str((base/'authority').resolve()),
           allowed_run_directory=str(run.resolve()))
    g['scope_sha256']=sha(m)
    return m,g,run


def mock_materials(base,source_sha='a'*40):
    m,g,r=materials(base,mode='MOCK_PROCESS',source_sha=source_sha)
    f=make_fixture(h_activity_power_W='4')
    p=dict(config=dict(accuracy_targets=f['accuracy']),instance=f['instance'],objective='FULL')
    m['mock_input']=dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config']),
        accuracy_sha256=sha(f['accuracy']),objective='FULL',packet_sha256={'FULL':sha(p)})
    m['files']={rel:file_sha(REPO/rel) for rel in runtime_paths('MOCK_PROCESS')}
    g['scope_sha256']=sha(m);validate_gate(g,m,'MOCK_PROCESS',r)
    l=Ledger(g['authority_store'],g,r,kind='MOCK_PROCESS')
    l.claim_batch(dict(manifest_sha256=sha(m)))
    return p,m,g,r,l


class ProtocolTests(unittest.TestCase):
    def test_legacy_and_explicit_e1_recipe_preserved(self):
        legacy=[['base__R1','FULL'],['base__R1','OMIT_TEMP'],['base__R3','OMIT_TEMP'],['base__R3','FULL']]
        self.assertEqual(protocol_slots({}),legacy)
        self.assertEqual(protocol_slots({'protocol_id':'E1_OBJECTIVE_V1'}),legacy)

    def test_e2_fixed_recipe_and_fresh_views(self):
        view=protocol_slots({'protocol_id':PROTOCOL_ID});view[0][0]='tampered'
        self.assertEqual(protocol_slots({'protocol_id':PROTOCOL_ID}),[list(s) for s in SLOTS])
        self.assertTrue(all(s[1]=='FULL' for s in SLOTS))

    def test_explicit_unknown_protocol_never_falls_back(self):
        for value in ('UNKNOWN',None,False,{},[]):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'UNKNOWN_EXECUTION_PROTOCOL'):
                protocol_slots({'protocol_id':value})

    def test_exact_e2_gate_validates(self):
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t));self.assertEqual(validate_gate(g,m,'REAL_RESEARCH',r),g)

    def test_unknown_protocol_gate_rejected_even_with_e1_slots(self):
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t),protocol='unknown');m['slots']=protocol_slots({});g['scope_sha256']=sha(m)
            with self.assertRaisesRegex(ValueError,'UNKNOWN_EXECUTION_PROTOCOL'):validate_gate(g,m,'REAL_RESEARCH',r)

    def test_e1_e2_mixed_slots_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            for protocol,slots in ((PROTOCOL_ID,protocol_slots({})),('E1_OBJECTIVE_V1',[list(s) for s in SLOTS])):
                m,g,r=materials(Path(t),protocol=protocol);m['slots']=slots;g['scope_sha256']=sha(m)
                with self.subTest(protocol=protocol),self.assertRaisesRegex(ValueError,'SLOTS_DRIFT'):
                    validate_gate(g,m,'REAL_RESEARCH',r)

    def test_e2_slot_list_tamper_rejected_even_with_rehashed_scope(self):
        with tempfile.TemporaryDirectory() as t:
            for field,value in ((0,'base__R1'),(1,'OMIT_TEMP')):
                m,g,r=materials(Path(t));m['slots'][0][field]=value;g['scope_sha256']=sha(m)
                with self.subTest(field=field),self.assertRaisesRegex(ValueError,'SLOTS_DRIFT'):
                    validate_gate(g,m,'REAL_RESEARCH',r)

    def test_prior_e1_authorization_denied_before_claim_or_process(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);m,g,r=materials(base);e1=deepcopy(m)
            e1['protocol_id']='E1_OBJECTIVE_V1';e1['slots']=protocol_slots(e1);g['scope_sha256']=sha(e1)
            save(base/'manifest.json',m);save(base/'gate.json',g)
            with patch('e1_objective.controller.Ledger',side_effect=AssertionError('claim forbidden')),\
                 patch('e1_objective.controller.supervise',side_effect=AssertionError('process forbidden')),\
                 self.assertRaisesRegex(ValueError,'SOURCE_OR_SCOPE_DRIFT'):
                run_batch(base/'manifest.json',base/'gate.json',r)
            self.assertFalse(r.exists());self.assertFalse((base/'authority').exists())

    def test_e2_closed_gate_denied_before_claim_or_process(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);m,g,r=materials(base);save(base/'manifest.json',m)
            with patch('e1_objective.controller.Ledger',side_effect=AssertionError('claim forbidden')),\
                 patch('e1_objective.controller.supervise',side_effect=AssertionError('process forbidden')),\
                 self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):
                run_batch(base/'manifest.json',DEFAULT_GATE,r)
            self.assertFalse(r.exists())

    def test_all_four_real_job_packet_identities_static_only(self):
        packets=prepare_inputs()
        with tempfile.TemporaryDirectory() as t:
            m,g,r=materials(Path(t))
            m['inputs']={pid:dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config'])) for pid,p in packets.items()}
            g['scope_sha256']=sha(m)
            for ordinal,(pid,objective) in enumerate(SLOTS,1):
                p=packets[pid];ctx=dict(input_sha256=sha(p['instance']),config_sha256=sha(p['config']),
                    accuracy_sha256=sha(p['config']['accuracy_targets']),objective=objective,packet_sha256=sha(p))
                claim=dict(phase='PLAN',ordinal=ordinal,root_origin=1,limit_s=300,source_sha=m['source_sha'],
                           kind='REAL_RESEARCH',run_dir=str(r),job_context=ctx)
                job=dict(mode='REAL_RESEARCH',run_dir=str(r),scope_sha256=sha(m),phase='PLAN',ordinal=ordinal,
                         root_origin=1,limit_s=300,claim=claim,packet=p)
                output=r/('slot_'+str(ordinal))/'plan'
                with self.subTest(slot=ordinal):self.assertTrue(verify_job(job,g,m,output))
                wrong=deepcopy(job);wrong['packet']=deepcopy(packets[SLOTS[ordinal%4][0]])
                with self.subTest(wrong_slot=ordinal),self.assertRaisesRegex(ValueError,'REAL_SLOT_IDENTITY'):
                    verify_job(wrong,g,m,output)

    def test_mock_e2_full_plan_post_and_once_only(self):
        with tempfile.TemporaryDirectory(prefix='e2_mock_') as t:
            p,m,g,r,l=mock_materials(Path(t));start=time.monotonic()
            plan=run_phase(l,g,m,r,1,'PLAN',slot_origin=start,batch_origin=start,packet_loader=lambda:deepcopy(p))
            self.assertEqual(plan['result']['state'],'SAFE',plan);self.assertEqual(plan['result']['objective'],'FULL')
            post=run_phase(l,g,m,r,1,'POST',slot_origin=start,batch_origin=start,packet=p,planning_result=plan['result'])
            self.assertEqual(post['result']['state'],'POST_SAFE',post)
            self.assertEqual(post['result']['candidate_sha256'],plan['result']['selected_candidate_sha256'])
            for out in (plan,post):
                ret=read_json(Path(out['output'])/'worker_return.json')
                self.assertEqual(ret['guard']['science_modules_loaded'],[])
                self.assertFalse(ret['guard']['real_backend_entered'])
                self.assertEqual(read_json(Path(out['output'])/'accepted_result.json')['formal_research_calls'],0)
            with self.assertRaises(LedgerError):l.claim_post(1,time.monotonic(),post['job']['selected_token'])

if __name__=='__main__':unittest.main()
