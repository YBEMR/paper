"""Mock process/ledger/watchdog checks. No real scientific backend enters."""
import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from h02_pair_preflight.common import ContractError,sha
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet,CORE
from h02_pair_b0.bundle import build_bundle,runtime_sources,verify_runtime_freeze
from h02_pair_b0.controller import CallLedger,supervise,run_four_slots,claim_authorization_once
from h02_pair_b0.io_contract import policy_files,load_json,require_research_authorization,consume_worker_launch,atomic_json
from h02_pair_b0.budget import RootBudgetExpired

PROCESS_REPORTS=[]
class ProcessController(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.packet=planner_packet(paired_response_input_view('base__R1'),'R')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='h02_B0_mock_'); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.policy,self.gate=policy_files()
    def test_runtime_freeze_and_source_only_bundle(self):
        m=verify_runtime_freeze(); self.assertIn('research/chapter3_experiments/h02_pair_b0/controller.py',m['source_files_sha256'])
        info=build_bundle(self.root/'bundle')
        self.assertFalse(list((self.root/'bundle').rglob('config_v01.json')))
        self.assertFalse(list((self.root/'bundle').rglob('paired_inputs_audit.json')))
        self.assertTrue(Path(info['worker']).exists())
    def test_bundle_reuse_denied(self):
        build_bundle(self.root/'bundle')
        with self.assertRaises(ContractError): build_bundle(self.root/'bundle')
    def test_R_actual_worker_in_MOCK_mode_denies_H_and_core_config(self):
        import time
        out=self.root/'R'; out.mkdir(); bundle=out/'code'; info=build_bundle(bundle)
        sealed=self.root/'controller_private'; sealed.mkdir(); sentinel=sealed/'truth_H.json'; sentinel.write_text('NOT_H_DATA_DENY_SENTINEL',encoding='utf-8')
        job={'kind':'planner','root_origin':time.monotonic(),'limit_s':120,'packet':self.packet,'probe_denied_paths':[str(sentinel),str(CORE/'config_v01.json')]}
        result=supervise(job,info,bundle,out,self.policy,mode='mock')
        self.assertEqual(result['returncode'],0,(out/'stderr.log').read_text(encoding='utf-8'))
        receipt=load_json(out/'worker_return.json'); payload=receipt['payload']; PROCESS_REPORTS.append({'process':result,'mock_worker':payload})
        self.assertEqual(len(payload['denied_paths']),2); self.assertFalse(payload['real_backend_entered']); self.assertEqual(payload['research_calls'],0)
    def test_actual_worker_REAL_mode_denied_before_core_entry(self):
        import time
        out=self.root/'R'; out.mkdir(); bundle=out/'code'; info=build_bundle(bundle)
        job={'kind':'planner','root_origin':time.monotonic(),'limit_s':120,'packet':self.packet}
        result=supervise(job,info,bundle,out,self.policy,mode='real')
        self.assertEqual(result['returncode'],3)
        self.assertIn('B0_RESEARCH_EXECUTION_NOT_AUTHORIZED',(out/'stderr.log').read_text(encoding='utf-8'))
        self.assertFalse((out/'method').exists()); self.assertFalse((out/'worker_return.json').exists())
        PROCESS_REPORTS.append({'real_mode_gate_probe':result,'scientific_backend_entered':False})
    def test_controller_execute_gate_before_process_or_directory(self):
        with patch('h02_pair_b0.controller.supervise') as launch:
            with self.assertRaisesRegex(ContractError,'NOT_AUTHORIZED'): run_four_slots(self.root/'forbidden')
            launch.assert_not_called(); self.assertFalse((self.root/'forbidden').exists())
    def test_no_launch_after_job_serialization_crosses_deadline(self):
        out=self.root/'out'; out.mkdir(); fake=Mock()
        job={'root_origin':0.0,'limit_s':120}
        with self.assertRaises(RootBudgetExpired): supervise(job,{'worker':'unused'},self.root,out,self.policy,clock=lambda:120.0,popen=fake)
        fake.assert_not_called()
    def test_atomic_audit_consumption_never_reused(self):
        ledger=CallLedger(self.root/'ledger',kind='MOCK_ONLY'); ledger.claim('audit_1',{'token_sha256':'literal','budget_s':60})
        with self.assertRaises(FileExistsError): ledger.claim('audit_1',{'token_sha256':'literal','budget_s':60})
        ledger.stop('MOCK_FAILURE')
        again=CallLedger(self.root/'ledger',kind='MOCK_ONLY')
        with self.assertRaises(ContractError): again.claim('slot_2',{})
    def test_bad_claim_path_denied(self):
        ledger=CallLedger(self.root/'ledger',kind='MOCK_ONLY')
        with self.assertRaises(ContractError): ledger.claim('../escape',{})
    def test_watchdog_grace_kills_without_new_budget(self):
        out=self.root/'out'; out.mkdir(); clock=Mock(side_effect=[100.0,100.0,120.0,120.0,125.0,125.0,125.1,125.2])
        process=Mock(); process.poll.return_value=None; process.returncode=-9
        launch=Mock(return_value=process)
        result=supervise({'root_origin':100.0,'limit_s':20},{'worker':'unused'},self.root,out,self.policy,clock=clock,popen=launch,sleep=Mock())
        process.kill.assert_called_once(); self.assertTrue(result['watchdog_killed'])
        self.assertEqual([t['phase'] for t in result['watchdog_transitions']],['RUN','ARCHIVE_ONLY','TERMINATE'])
    def test_authorization_global_claim_survives_changed_destination(self):
        gate={'authorization_id':'MOCK-unique','authority_store':str(self.root/'fixed_store'),'allowed_run_directory':str(self.root/'run1')}
        claim_authorization_once(gate,self.root/'run1')
        gate['allowed_run_directory']=str(self.root/'run2')
        with self.assertRaises(FileExistsError): claim_authorization_once(gate,self.root/'run2')
    def test_authorization_rejects_unapproved_destination(self):
        gate={'authorization_id':'MOCK-unique','authority_store':str(self.root/'fixed_store'),'allowed_run_directory':str(self.root/'run1')}
        with self.assertRaises(ContractError): claim_authorization_once(gate,self.root/'run2')
    def authorized_mock_metadata(self):
        p=copy.deepcopy(self.policy);p['execution_enabled']=True
        g={'research_authorized':True,'four_slot_authorized':True,'approval_reference':'MOCK_NOT_A_USER_APPROVAL','authorization_id':'MOCK_ONLY','allowed_run_directory':str(self.root/'run'),'authority_store':str(self.root/'authority')}
        return p,g
    def test_only_authorization_flag_can_change_not_scientific_policy(self):
        p,g=self.authorized_mock_metadata()
        self.assertTrue(require_research_authorization(g,p))
        self.assertFalse(self.gate['research_authorized']) # on-disk grant remains CLOSED
    def test_new_gate_cannot_authorize_changed_slots(self):
        p,g=self.authorized_mock_metadata();p['slots'].reverse()
        with self.assertRaisesRegex(ContractError,'SCOPE_DRIFT'):require_research_authorization(g,p)
    def test_new_gate_cannot_authorize_extra_budget(self):
        p,g=self.authorized_mock_metadata();p['maximum_plan_calls']=5
        with self.assertRaisesRegex(ContractError,'SCOPE_DRIFT'):require_research_authorization(g,p)
    def worker_claim_fixture(self):
        p,g=self.authorized_mock_metadata();run=Path(g['allowed_run_directory']);run.mkdir()
        claim_authorization_once(g,run)
        claim=CallLedger(run/'ledger',kind='MOCK_ONLY').claim('slot_2',{'slot':p['slots'][1],'root_origin':1000.0,'budget_s':120})
        job={'kind':'planner','ordinal':2,'root_origin':1000.0,'limit_s':120,'packet':self.packet,'launch_claim_sha256':sha(claim)}
        return p,g,job,run/'slot_2'/'planner_public'
    def test_internal_worker_also_consumes_once(self):
        p,g,j,out=self.worker_claim_fixture();consume_worker_launch(j,g,p,out)
        with self.assertRaises(FileExistsError):consume_worker_launch(j,g,p,out)
    def test_worker_cannot_bypass_controller_whole_run_claim(self):
        p,g=self.authorized_mock_metadata();j={'kind':'planner','ordinal':2}
        with self.assertRaises(FileNotFoundError):consume_worker_launch(j,g,p,self.root/'elsewhere')
    def test_worker_cannot_reuse_launch_for_different_job(self):
        p,g,j,out=self.worker_claim_fixture();j['root_origin']=1001
        with self.assertRaises(ContractError):consume_worker_launch(j,g,p,out)
    def test_worker_cannot_export_to_another_directory(self):
        p,g,j,out=self.worker_claim_fixture()
        with self.assertRaises(ContractError):consume_worker_launch(j,g,p,self.root/'elsewhere')
    def test_fixed_slots_and_budgets_remain_disabled(self):
        self.assertEqual([(s['problem_id'],s['view']) for s in self.policy['slots']],[('base__R1','H'),('base__R1','R'),('base__R2','R'),('base__R2','H')])
        self.assertEqual(self.policy['research_budget_s'],720); self.assertFalse(self.policy['execution_enabled']); self.assertFalse(self.gate['research_authorized'])
