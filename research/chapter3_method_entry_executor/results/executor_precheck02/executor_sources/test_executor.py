"""Manual mocks only. No subprocess, real planner, model, or integration."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from . import common, worker, runner
from .test_monitor import good_host

FROZEN = None
CASE_NO = 0


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def sleep(self, seconds): self.value += seconds


class Budget:
    seconds = 300
    def check(self): pass
    @contextmanager
    def phase(self, name): yield


def fake_safe(instance):
    candidate = {'scenes': {s['id']: [{'stage_id': t['id'], 'unit': instance['stage_modes'][t['shared_stage_id']][0]['unit_id'],
        'opp': 'H', 'start_ms': '0'} for t in s['stage_instances']] for s in instance['scenarios']}}
    # An evidence-contract oracle, not a feasible schedule or real SAFE proof.
    ev = {'state': 'SAFE', 'rankable_energy': True, 'completed_at_elapsed_s': 30,
          'safe_upper_bound_J': '1', 'weighted_energy_J': ['1', '1'],
          'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED'},
          'evidence_identity': {'input_sha256': common.canonical(instance), 'candidate_sha256': common.canonical(candidate)},
          'scenes': {s['id']: {'state': 'SAFE', 'complete': True, 'covered_until_s': '23/100', 'energy_J': ['1', '1']}
                     for s in instance['scenarios']}, 'simulation_only': True}
    return {'state': 'SAFE', 'safe_candidate': candidate, 'evaluation': ev,
            'safe_upper_bound_J': '1', 'simulation_only': True}


def case():
    global CASE_NO
    CASE_NO += 1
    out = FROZEN/'manual_mock_artifacts'/f'case{CASE_NO:03d}'
    ctx = {'plan': common.read(FROZEN/'plan.json'), 'plan_dir': FROZEN,
           'common_path': FROZEN/'common_input.json', 'plan_sha256': common.sha(FROZEN/'plan.json'),
           'authorization_path': FROZEN/'authorization_template.json',
           'authorized': True, 'simulation_only': True}
    return ctx, out


def bindings(ctx, mode='unresolved', seen=None):
    def lifecycle(loader, out, **kwargs):
        config, instance = loader(Budget())
        if seen is not None: seen.append(kwargs)
        Path(out).mkdir(parents=True)
        common.save(Path(out)/'input_config.json', config)
        common.save(Path(out)/'input_instance.json', instance)
        raw = fake_safe(instance) if mode in ('safe', 'safe_timeout', 'cleanup_failure', 'numeric') else {
            'state': 'UNRESOLVED', 'reason': 'NO_SAFE_INITIAL_WITNESS',
            'initialisation': {'state': 'UNRESOLVED', 'reason': 'NO_SAFE_INITIAL_WITNESS'}, 'simulation_only': True}
        raw.update(timing={'method_elapsed_s': 40}, stop_stage='candidate_search',
                   first_legal_candidate_at_s=15, first_safe_at_s=30 if 'evaluation' in raw else None,
                   integer_solver_entered=False, matlab_worker_ready=False)
        if mode == 'construction_timeout': raw.update(reason='wall_time_limit', budget_exhausted=True, model_complete=False, stop_stage='model_construction')
        if mode == 'memory': raw.update(reason='RESOURCE_LIMIT', stop_stage='model_construction', model_complete=False)
        if mode == 'safe_timeout': raw.update(reason='wall_time_limit', budget_exhausted=True)
        if mode == 'numeric': raw['reason'] = 'NUMERICAL_ADMISSION_STATUS_CONFLICT'
        if mode == 'cleanup_failure': raw.update(matlab_worker_ready=True, cleanup_error='mock leftover MATLAB')
        common.save(Path(out)/'result.json', raw)
        return raw
    return {'whole': lifecycle, 'heuristic': lifecycle, 'builder': lambda *a, **k: None,
            'session': lambda *a, **k: None, 'lower': lambda *a, **k: {'lower_bound_J': '0'}}


class FakeMonitor:
    def __init__(self, pid, *, clock): self.pid=pid; self.clock=clock
    def sample(self, force=False): return {'simulation_only': True}
    def summary(self): return {'simulation_only': True, 'sampled_peak_same_time_rss_sum_bytes': 123}
    def cleanup_verified(self): return True
    def terminate_owned(self, force=False): return {'simulation_only': True}
    def register_identities(self, items, source=''): pass


class FakeProc:
    def __init__(self, pid): self.pid=pid
    def poll(self): return 0
    def kill(self): pass


class FakeRuntime:
    def __init__(self, ctx, modes=None, *, host=None):
        self.ctx=ctx; self.modes=modes or {}; self.clock=Clock(); self.sleep=self.clock.sleep
        self.calls=[]; self.host=good_host() if host is None else host
    def probe(self, root): return deepcopy(self.host)
    monitor = FakeMonitor
    def launch(self, args, stdout, stderr):
        ticket = common.read(args[args.index('--ticket')+1]); mode=ticket['mode']; mid=ticket['job_id']
        out=Path(args[args.index('--output')+1]); self.calls.append((mid, mode))
        pid=100+len(self.calls)
        common.save(Path(ticket['ticket_claim_path']), {'simulation_only': True, 'pid': pid})
        job=next(j for j in self.ctx['plan']['jobs'] if j['id']==mid)
        if mode=='method': worker.run_method(self.ctx, job, out, bindings=bindings(self.ctx, self.modes.get(mid, 'unresolved')))
        else:
            out.mkdir(parents=True)
            common.save(out/'post_result.json', {'job_id':mid,'input_sha256':self.ctx['plan']['common_input_sha256'],
                'plan_sha256':self.ctx['plan_sha256'],'source_manifest_sha256':common.canonical(self.ctx['plan']['source_sha256']),
                'post_state':'SAFE','errors':[],'simulation_only':True})
        return FakeProc(pid)


class ExecutorTests(unittest.TestCase):
    def test_real_false_approval_blocks_before_process(self):
        with self.assertRaisesRegex(ValueError, 'APPROVAL'):
            common.load_context(FROZEN, common.sha(FROZEN/'plan.json'), FROZEN/'authorization_template.json')

    def test_three_fresh_mock_workers_one_common_input(self):
        ctx,out=case(); rt=FakeRuntime(ctx)
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_three')
        self.assertEqual(r['state'],'COMPLETE',r)
        self.assertEqual(rt.calls,[(m,'method') for m in common.METHODS])
        self.assertEqual(len({x['process']['pid'] for x in r['methods']}),3)
        self.assertEqual(r['method_lifecycle_entered'],3)

    def test_final_SAFE_has_one_independent_mock_post(self):
        ctx,out=case(); rt=FakeRuntime(ctx,{'whole_milp':'safe'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_post')
        self.assertEqual(r['state'],'COMPLETE',r)
        self.assertEqual(len(r['posts']),1)
        self.assertTrue(r['methods'][0]['worker']['safe_witness_preserved'])

    def test_construction_timeout_preserves_phase_and_continues(self):
        ctx,out=case(); rt=FakeRuntime(ctx,{'whole_milp':'construction_timeout'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_timeout')
        self.assertEqual(r['state'],'COMPLETE',r)
        self.assertEqual(r['methods'][0]['execution_status'],'NORMAL_TIME_LIMIT')
        self.assertEqual(r['methods'][0]['worker']['stop_stage'],'model_construction')

    def test_memory_failure_stops_remaining_methods(self):
        ctx,out=case(); rt=FakeRuntime(ctx,{'whole_milp':'memory'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_memory')
        self.assertEqual(r['state'],'STOPPED'); self.assertEqual(len(rt.calls),1)
        self.assertEqual(r['not_run'],['heft','sa101'])

    def test_cleanup_failure_retains_SAFE_but_stops(self):
        ctx,out=case(); rt=FakeRuntime(ctx,{'whole_milp':'cleanup_failure'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_cleanup')
        self.assertEqual(r['state'],'STOPPED'); self.assertEqual(len(rt.calls),1)
        self.assertTrue(r['methods'][0]['worker']['safe_witness_preserved'])

    def test_numeric_conflict_with_SAFE_is_not_success(self):
        ctx,out=case(); rt=FakeRuntime(ctx,{'whole_milp':'numeric'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_numeric')
        self.assertEqual(r['state'],'STOPPED')
        self.assertTrue(r['methods'][0]['worker']['numerical_anomaly'])

    def test_SAFE_before_deadline_is_preserved(self):
        ctx,out=case(); job=ctx['plan']['jobs'][1]
        r=worker.run_method(ctx,job,out,bindings=bindings(ctx,'safe_timeout'))
        self.assertEqual(r['execution_status'],'NORMAL_TIME_LIMIT')
        self.assertTrue(r['safe_witness_preserved']); self.assertEqual(r['safe_upper_bound_J'],'1')

    def test_late_or_wrong_identity_SAFE_rejected(self):
        ctx,_=case(); instance=common.verify_input(ctx)['instance']
        for kind in ('late','identity','partial'):
            raw=fake_safe(instance)
            if kind=='late': raw['evaluation']['completed_at_elapsed_s']=300
            if kind=='identity': raw['evaluation']['evidence_identity']['input_sha256']='wrong'
            if kind=='partial': next(iter(raw['evaluation']['scenes'].values()))['complete']=False
            self.assertFalse(common.inspect_safe_receipt(instance,raw)['preserved'],kind)

    def test_host_memory_gate_has_zero_launch(self):
        ctx,out=case(); host=good_host();host['physical_available_bytes']=1
        rt=FakeRuntime(ctx,host=host)
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_host')
        self.assertEqual(r['state'],'STOPPED');self.assertEqual(rt.calls,[])
        self.assertFalse(r['claims_consumed'])

    def test_second_batch_same_claim_cannot_resume(self):
        ctx,out=case();claims=out.parent/'claims_repeat'
        a=runner.run_batch(ctx,out,runtime=FakeRuntime(ctx),claims_root=claims)
        self.assertEqual(a['state'],'COMPLETE')
        ctx,b=case();rt=FakeRuntime(ctx)
        r=runner.run_batch(ctx,b,runtime=rt,claims_root=claims)
        self.assertEqual(r['state'],'STOPPED');self.assertEqual(rt.calls,[])
        self.assertFalse(r['claim_created_here']);self.assertTrue(r['claim_already_exists'])

    def test_archived_SAFE_checkpoint_survives_missing_envelope(self):
        ctx,out=case();instance=common.verify_input(ctx)['instance'];raw=fake_safe(instance)
        common.save(out/'method/initial_receipt_checkpoint.json',{'initialisation':{'witness':{
            'candidate':raw['safe_candidate'],'evaluation':raw['evaluation']}}})
        r=common.recover_archived_safe(instance,out)
        self.assertTrue(r['preserved']);self.assertEqual(r['archive_source'],'initial_checkpoint')

    def test_first_legal_is_not_first_candidate(self):
        ctx,_=case();instance=common.verify_input(ctx)['instance'];job=ctx['plan']['jobs'][0]
        raw={'diagnostic':{'first_candidate_received_s':5,'first_legal_candidate_s':7},
             'initialisation':{'attempts':[]},'timing':{'method_elapsed_s':10}}
        e=worker.normalize_result(raw,job,instance,input_sha256=common.INPUT_SHA,plan_sha256=ctx['plan_sha256'])
        self.assertEqual(e['first_legal_candidate_s'],7)

    def test_stage_initialization_failed_is_not_infeasible(self):
        ctx,out=case(); e=worker.run_method(ctx,ctx['plan']['jobs'][0],out,bindings=bindings(ctx))
        self.assertEqual(e['initialisation_reason'],'NO_SAFE_INITIAL_WITNESS')
        self.assertFalse(e['safe_witness_preserved'])
        self.assertFalse(e['independently_proven_optimal'])

    def test_monitor_handshake_wrong_pid_and_deadline(self):
        ctx,out=case(); clock=Clock()
        ticket={'ticket_claim_path':str(out/'start.json'),'worker_token':'token',
                'absolute_deadline_monotonic_s':1}
        common.save(out/'monitor_ready.json',{'worker_token':'token','plan_sha256':ctx['plan_sha256'],'pid':10})
        self.assertTrue(worker.wait_monitor_ready(ctx,ticket,clock=clock,sleep=clock.sleep,pid=10))
        with self.assertRaises(ValueError): worker.wait_monitor_ready(ctx,ticket,clock=clock,sleep=clock.sleep,pid=11)
        clock.value=1
        with self.assertRaises(TimeoutError): worker.wait_monitor_ready(ctx,ticket,clock=clock,sleep=clock.sleep,pid=10)

    def test_missing_worker_envelope_keeps_earlier_checkpoint(self):
        ctx,out=case()
        class LostEnvelope(FakeRuntime):
            def launch(self,args,stdout,stderr):
                ticket=common.read(args[args.index('--ticket')+1]); w=Path(args[args.index('--output')+1])
                raw=fake_safe(common.verify_input(self.ctx)['instance'])
                common.save(w/'method/initial_receipt_checkpoint.json',{'initialisation':{'witness':{
                    'candidate':raw['safe_candidate'],'evaluation':raw['evaluation']}}})
                self.calls.append((ticket['job_id'],ticket['mode']))
                return FakeProc(201)
        rt=LostEnvelope(ctx)
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_lost')
        self.assertEqual(r['state'],'STOPPED');self.assertEqual(len(rt.calls),1)
        self.assertTrue(r['methods'][0]['worker']['safe_witness_preserved'])

    def test_process_wall_cap_stops_without_retry_and_retains_SAFE(self):
        ctx,out=case()
        class HungProc(FakeProc):
            done=False
            def poll(self): return 0 if self.done else None
        class Hung(FakeRuntime):
            def launch(self,args,stdout,stderr):
                super().launch(args,stdout,stderr)
                self.proc=HungProc(301);return self.proc
            def monitor(self,pid,clock):
                parent=self
                class M(FakeMonitor):
                    def terminate_owned(self,force=False): parent.proc.done=True;return {'simulation_only':True}
                return M(pid,clock=clock)
        rt=Hung(ctx,{'whole_milp':'safe'})
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_hung')
        self.assertEqual(r['state'],'STOPPED');self.assertEqual(len(rt.calls),1)
        self.assertEqual(r['methods'][0]['execution_status'],'PROCESS_WALL_LIMIT_STOP')
        self.assertTrue(r['methods'][0]['worker']['safe_witness_preserved'])

    def test_method_input_archive_drift_stops(self):
        ctx,out=case()
        class Drift(FakeRuntime):
            def launch(self,args,stdout,stderr):
                proc=super().launch(args,stdout,stderr)
                w=Path(args[args.index('--output')+1])/'method/input_instance.json'
                data=common.read(w);data['window_ms']='235'
                # Deliberate test corruption, never a production repair.
                w.write_text(__import__('json').dumps(data),encoding='utf8')
                return proc
        rt=Drift(ctx)
        r=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/'claims_drift')
        self.assertEqual(r['state'],'STOPPED');self.assertEqual(len(rt.calls),1)
        self.assertIn('ARCHIVE_MISMATCH',str(r['methods'][0]['worker']['errors']))

    def test_whole_and_SA_binding_parameters(self):
        ctx,out=case();seen=[]
        worker.run_method(ctx,ctx['plan']['jobs'][0],out,bindings=bindings(ctx,seen=seen))
        self.assertEqual(seen[0]['seconds'],300)
        self.assertEqual(seen[0]['feedback_kind'],'conditional')
        self.assertEqual(seen[0]['model_builder'].keywords,{'prefilter_deadlines':True,'cumulative_precedence':False})
        self.assertEqual(seen[0]['session_factory'].keywords,{'cut_max_iterations':10})
        ctx,out=case();seen=[]
        worker.run_method(ctx,ctx['plan']['jobs'][2],out,bindings=bindings(ctx,seen=seen))
        self.assertEqual((seen[0]['method'],seen[0]['seed'],seen[0]['allow_auto_low']),('sa',101,True))
