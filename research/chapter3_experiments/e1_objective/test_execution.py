"""Actual isolated mock workers and fixed identity/budget regressions."""
from copy import deepcopy
from pathlib import Path
import tempfile,time,unittest,uuid
from unittest.mock import patch
from .execution_io import REPO,sha,file_sha,runtime_paths,SLOTS,BUDGETS,save,read_json,validate_gate,verify_job,DEFAULT_GATE
from .mock_fixtures import make_fixture
from .ledger import Ledger,LedgerError
from .controller import run_phase,run_batch,recover_post,recover_plan


def mock_materials(base,source_sha='a'*40):
    f=make_fixture(h_activity_power_W='4');packet=dict(instance=f['instance'],config=dict(accuracy_targets=f['accuracy']),objective='OMIT_TEMP')
    manifest=dict(source_sha=source_sha,mode='MOCK_PROCESS',slots=SLOTS,budgets=BUDGETS,
      files={rel:file_sha(REPO/rel) for rel in runtime_paths('MOCK_PROCESS')},inputs={},
      mock_input=dict(input_sha256=sha(packet['instance']),config_sha256=sha(packet['config']),accuracy_sha256=sha(f['accuracy']),
                      objective=packet['objective'],packet_sha256={packet['objective']:sha(packet)}))
    run=base/'run';gate=dict(kind='MOCK_PROCESS',authorized=False,mock_only=True,authorization_id='mock-'+uuid.uuid4().hex,
      source_sha=manifest['source_sha'],scope_sha256=sha(manifest),budgets=BUDGETS,
      authority_store=str((base/'authority').resolve()),allowed_run_directory=str(run.resolve()))
    validate_gate(gate,manifest,'MOCK_PROCESS',run)
    ledger=Ledger(gate['authority_store'],gate,run,kind='MOCK_PROCESS');ledger.claim_batch(dict(manifest_sha256=sha(manifest)))
    return packet,manifest,gate,run,ledger


def plan_case(base,behavior='normal',prior=0,grace=5,probe=None):
    p,m,g,r,l=mock_materials(base);start=time.monotonic()
    out=run_phase(l,g,m,r,1,'PLAN',slot_origin=start,batch_origin=start,packet_loader=lambda:deepcopy(p),
                  mock_behavior=behavior,mock_prior_elapsed_s=prior,grace_s=grace,forbidden_probe_path=probe)
    return p,m,g,r,l,start,out


class ExecutionTests(unittest.TestCase):
    def test_actual_mock_plan_post_and_no_science(self):
        with tempfile.TemporaryDirectory(prefix='e1_mock_') as tmp:
            p,m,g,r,l,start,out=plan_case(Path(tmp));self.assertEqual(out['result']['state'],'SAFE',out)
            self.assertFalse(out['result']['stop_required'])
            ret=read_json(Path(out['output'])/'worker_return.json')
            self.assertEqual(ret['guard']['science_modules_loaded'],[]);self.assertFalse(ret['guard']['real_backend_entered'])
            self.assertEqual(out['job']['root_origin'],ret['result']['timing']['root_origin'])
            self.assertGreater(ret['result']['timing']['method_elapsed_s'],out['process']['startup_elapsed_s'])
            post=run_phase(l,g,m,r,1,'POST',slot_origin=start,batch_origin=start,packet=out['packet'],planning_result=out['result'])
            self.assertEqual(post['result']['state'],'POST_SAFE',post)
            self.assertEqual(post['result']['candidate_sha256'],out['result']['selected_candidate_sha256'])
            self.assertEqual(read_json(Path(out['output'])/'accepted_result.json')['formal_research_calls'],0)
            with self.assertRaises(LedgerError):l.claim_plan(1,time.monotonic(),out['job']['claim']['job_context'])

    def test_worker_denies_science_file_and_descendants(self):
        with tempfile.TemporaryDirectory(prefix='e1_probe_') as tmp:
            base=Path(tmp);probe=base/'outside.txt';probe.write_text('test-only')
            *_,out=plan_case(base,'probe',probe=probe)
            self.assertEqual(out['result']['state'],'SAFE',out)
            ret=read_json(Path(out['output'])/'worker_return.json')
            self.assertTrue({'thermal','e1_objective.search','outside-file','child-process'}<=set(ret['guard']['denied']))
            self.assertEqual(ret['guard']['science_modules_loaded'],[])

    def test_crash_keeps_safe_and_stops(self):
        with tempfile.TemporaryDirectory(prefix='e1_crash_') as tmp:
            p,m,g,r,l,start,out=plan_case(Path(tmp),'crash_after_checkpoint')
            self.assertEqual(out['process']['classification'],'NONZERO_EXIT_FAULT',out)
            self.assertEqual(out['result']['state'],'SAFE',out);self.assertTrue(out['result']['stop_required'])
            self.assertEqual(out['result']['recovery'],'PREEXISTING_CHECKPOINT_ONLY')
            self.assertTrue(out['result']['final_request_unresolved']);self.assertTrue((l.root/'stop.json').exists())

    def test_watchdog_reaps_hang_preserves_selection(self):
        with tempfile.TemporaryDirectory(prefix='e1_hang_') as tmp:
            # MOCK only: leave 3 seconds to form the checkpoint before hanging.
            # The inherited 300 second root and .2 second archive grace stay fixed.
            *_,out=plan_case(Path(tmp),'hang_after_checkpoint',297,.2)
            self.assertEqual(out['process']['classification'],'WATCHDOG_KILLED',out)
            self.assertTrue(out['process']['reaped']);self.assertTrue(out['process']['killed'])
            self.assertEqual(out['result']['state'],'SAFE',out);self.assertLess(out['result']['selected_at_s'],300)
            self.assertFalse(out['result']['stop_required']);self.assertTrue(out['result']['final_request_unresolved'])

    def test_late_archive_preserves_old_selection(self):
        with tempfile.TemporaryDirectory(prefix='e1_late_') as tmp:
            # MOCK only: receipt formation must precede the late-archive phase.
            *_,out=plan_case(Path(tmp),'late_archive',297,.3)
            self.assertEqual(out['result']['state'],'SAFE',out);self.assertFalse(out['result']['stop_required'])
            self.assertGreaterEqual(out['process']['receipt_observed_elapsed_s'],300)
            self.assertLess(out['result']['selected_at_s'],300)

    def test_import_delay_is_charged(self):
        with tempfile.TemporaryDirectory(prefix='e1_import_') as tmp:
            *_,out=plan_case(Path(tmp),'import_delay',299.85,.3)
            self.assertEqual(out['result']['state'],'UNRESOLVED',out);self.assertFalse(out['result']['stop_required'],out)
            self.assertGreaterEqual(out['process']['method_elapsed_s'],300)

    def test_bad_receipt_identity_stops(self):
        with tempfile.TemporaryDirectory(prefix='e1_bad_') as tmp:
            *_,out=plan_case(Path(tmp),'bad_identity')
            self.assertTrue(out['result']['stop_required']);self.assertEqual(out['result']['state'],'UNRESOLVED')
            self.assertFalse((Path(out['output'])/'real_backend_entry.json').exists())

    def test_real_gate_closed_before_claim_or_process(self):
        with tempfile.TemporaryDirectory(prefix='e1_closed_') as tmp:
            base=Path(tmp);p,m,g,r,l=mock_materials(base);m['mode']='REAL_RESEARCH';manifest=base/'manifest.json';save(manifest,m)
            target=base/'forbidden_run'
            with patch('e1_objective.controller.supervise',side_effect=AssertionError('must not launch')),self.assertRaisesRegex(ValueError,'NOT_AUTHORIZED'):
                run_batch(manifest,DEFAULT_GATE,target)
            self.assertFalse(target.exists())

    def test_job_root_slot_input_and_mode_identity(self):
        with tempfile.TemporaryDirectory(prefix='e1_identity_') as tmp:
            p,m,g,r,l,start,out=plan_case(Path(tmp));job=out['job']
            for field,value in [('root_origin',job['root_origin']+1),('limit_s',120),('ordinal',2)]:
                changed=deepcopy(job);changed[field]=value
                with self.subTest(field=field),self.assertRaises(ValueError):verify_job(changed,g,m,Path(out['output']))
            changed=deepcopy(job);changed['packet']['instance']['window_ms']='399'
            with self.assertRaises(ValueError):verify_job(changed,g,m,Path(out['output']))
            changed=deepcopy(job);changed['mode']='REAL_RESEARCH'
            with self.assertRaises(ValueError):verify_job(changed,g,m,Path(out['output']))

    def test_post_safe_requires_raw_and_valid_formation_time(self):
        with tempfile.TemporaryDirectory(prefix='e1_post_contract_') as tmp:
            base=Path(tmp);f=make_fixture(h_activity_power_W='4');p=dict(instance=f['instance'],config=dict(accuracy_targets=f['accuracy']),objective='FULL')
            job=dict(mode='MOCK_PROCESS',scope_sha256='scope',packet=p,root_origin=0,slot_deadline=420,batch_deadline=1800,
                     planning_result=dict(safe_candidate=f['candidate'],evaluation=f['receipt']))
            process=dict(classification='NATURAL_EXIT',method_elapsed_s=2)
            returned=dict(job_sha256=sha(job),kind='MOCK_PROCESS',manifest_sha256='scope',packet_sha256=sha(p),
                          returned_at_s=2,result=dict(state='POST_SAFE',evaluation=f['receipt'],stop_required=False))
            save(base/'worker_return.json',returned)
            with self.assertRaisesRegex(ValueError,'WITHOUT_RAW'):recover_post(job,base,process)
            raw=deepcopy(f['receipt']);raw['completed_at_elapsed_s']=3
            save(base/'post_receipt.json',dict(job_sha256=sha(job),receipt=raw))
            with self.assertRaisesRegex(ValueError,'FUTURE_FORMATION'):recover_post(job,base,process)
            raw['completed_at_elapsed_s']=1
            save(base/'post_receipt.json',dict(job_sha256=sha(job),receipt=raw))
            self.assertEqual(recover_post(job,base,process)['state'],'POST_SAFE')
            # An earlier total deadline dominates the nominal 60 second root.
            job['slot_deadline']=.5
            returned.update(job_sha256=sha(job));save(base/'worker_return.json',returned)
            save(base/'post_receipt.json',dict(job_sha256=sha(job),receipt=raw))
            self.assertEqual(recover_post(job,base,process)['state'],'UNRESOLVED')

    def test_early_total_deadline_is_normal_without_candidate(self):
        from .exports import verify_export
        fixture=make_fixture();result=dict(method='e1-adapted-heft',seed=None,state='UNRESOLVED',
            safe_candidate=None,evaluation=None,safe_upper_bound_J=None,planning_score_J=None,
            reason='METHOD_BUDGET_EXHAUSTED',stop_required=False,
            timing=dict(limit_s=300,method_elapsed_s=2))
        checked=verify_export(fixture['instance'],dict(accuracy_targets=fixture['accuracy']),result,300,evidence_seconds=1)
        self.assertEqual(checked['state'],'NO_SELECTED_SAFE_INPUT_UNFINISHED')
        with self.assertRaises(ValueError):verify_export(fixture['instance'],dict(accuracy_targets=fixture['accuracy']),result)

    def test_post_not_started_root_expiry_consumed_as_normal(self):
        with tempfile.TemporaryDirectory(prefix='e1_post_no_launch_') as tmp:
            p,m,g,r,l,start,out=plan_case(Path(tmp))
            post=run_phase(l,g,m,r,1,'POST',slot_origin=start,batch_origin=start,packet=out['packet'],
                           planning_result=out['result'],mock_prior_elapsed_s=60)
            self.assertEqual(post['result']['state'],'UNRESOLVED');self.assertFalse(post['result']['stop_required'])
            self.assertFalse((l.root/'01_post_launch.json').exists())
            self.assertTrue((l.root/'01_post_finish.json').exists())
            self.assertFalse((l.root/'stop.json').exists())

    def test_post_total_limit_stops_without_fake_launch_or_technical_fault(self):
        with tempfile.TemporaryDirectory(prefix='e1_post_total_limit_') as tmp:
            p,m,g,r,l,start,out=plan_case(Path(tmp))
            post=run_phase(l,g,m,r,1,'POST',slot_origin=time.monotonic()-421,batch_origin=start,
                           packet=out['packet'],planning_result=out['result'])
            self.assertEqual(post['result']['reason'],'DECLARED_TOTAL_BUDGET_EXHAUSTED')
            self.assertTrue(post['result']['stop_required']);self.assertFalse(post['result']['technical_failure'])
            self.assertFalse((l.root/'01_post_launch.json').exists());self.assertTrue((l.root/'stop.json').exists())

    def test_source_drift_consumed_without_spawn(self):
        with tempfile.TemporaryDirectory(prefix='e1_drift_') as tmp:
            p,m,g,r,l=mock_materials(Path(tmp));m['files'][next(iter(m['files']))]='0'*64
            g['scope_sha256']=sha(m);g['authorization_id']='other-'+uuid.uuid4().hex
            l=Ledger(g['authority_store'],g,r,kind='MOCK_PROCESS');l.claim_batch(dict(test='drift'));start=time.monotonic()
            with patch('e1_objective.controller.supervise',side_effect=AssertionError('must not spawn')):
                out=run_phase(l,g,m,r,1,'PLAN',slot_origin=start,batch_origin=start,packet_loader=lambda:deepcopy(p))
            self.assertTrue(out['result']['stop_required']);self.assertTrue((l.root/'01_plan_claim.json').exists())
            self.assertFalse((l.root/'01_plan_launch.json').exists())

if __name__=='__main__':unittest.main()
