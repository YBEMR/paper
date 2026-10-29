"""Post semantic rejection across worker/exit/supervisor/batch, mocks only."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from . import common, runner, worker, test_executor as te
from .test_worker_tickets import post_bindings


class ExitProc(te.FakeProc):
    def __init__(self,pid,code): super().__init__(pid);self.code=code
    def poll(self): return self.code


class NegativePostRuntime(te.FakeRuntime):
    def __init__(self,ctx,outcome):
        super().__init__(ctx,{'whole_milp':'safe'});self.outcome=outcome
    def launch(self,args,stdout,stderr):
        ticket=common.read(args[args.index('--ticket')+1])
        if ticket['mode']=='method': return super().launch(args,stdout,stderr)
        self.calls.append((ticket['job_id'],'post'));pid=100+len(self.calls)
        common.save(Path(ticket['ticket_claim_path']),{'simulation_only':True,'pid':pid})
        value=common.verify_input(self.ctx)
        ev=deepcopy(te.fake_safe(value['instance'])['evaluation'])
        ev.update(state=self.outcome,rankable_energy=False,weighted_energy_J=None,
                  safe_upper_bound_J=None,violations=[],simulation_only=True)
        if self.outcome=='THERMAL_VIOLATION':
            ev['violations']=[{'scene_id':'C1','node':'CPU1','time_s':'1/10',
                'temperature_degC':['81','81'],'limit_degC':'80','formed_at_elapsed_s':1}]
        else:
            ev['reason']='REQUEST_DEADLINE_EXCEEDED'
        with patch.object(worker.time,'monotonic',side_effect=self.clock):
            result=worker.run_post(self.ctx,ticket,Path(args[args.index('--output')+1]),
                bindings=post_bindings(value,ev,self.clock,returned_at=2))
        self.last_post=result
        return ExitProc(pid,2)


def post_envelope(state):
    return {'post_state':state,'errors':[],'within_absolute_deadline':True,
        'evaluation':{'state':state},'timely_violations_preserved':
            [{'simulation_only':True}] if state=='THERMAL_VIOLATION' else []}


class PostStatusTests(unittest.TestCase):
    def full_negative(self,state,expected):
        ctx,out=te.case();rt=NegativePostRuntime(ctx,state)
        result=runner.run_batch(ctx,out,runtime=rt,claims_root=out.parent/('claims_post_'+state))
        self.assertEqual(result['state'],'STOPPED',result)
        self.assertEqual(rt.calls,[('whole_milp','method'),('whole_milp','post')])
        self.assertEqual(result['posts'][0]['process']['returncode'],2)
        self.assertEqual(result['posts'][0]['execution_status'],expected)
        self.assertEqual(result['stop_reason'],{'phase':'post','job_id':'whole_milp',
                                               'execution_status':expected,'post_state':state})
        self.assertEqual(result['not_run'],['heft','sa101'])
        self.assertEqual(rt.last_post['post_state'],state)
        self.assertFalse(rt.last_post['errors'])
        self.assertTrue(result['methods'][0]['worker']['safe_witness_preserved'])
        if state=='THERMAL_VIOLATION':self.assertTrue(rt.last_post['timely_violations_preserved'])

    def test_thermal_violation_exit2_remains_semantic_at_batch_level(self):
        self.full_negative('THERMAL_VIOLATION','POST_THERMAL_VIOLATION_STOP')

    def test_invalid_schedule_exit2_remains_semantic_at_batch_level(self):
        self.full_negative('INVALID_SCHEDULE','POST_INVALID_SCHEDULE_STOP')

    def test_worker_main_exit2_contract_is_preserved(self):
        ctx,out=te.case();job=ctx['plan']['jobs'][0]
        ticket={'ticket_claim_path':str(out/'mock_started.json'),'slot_id':'whole_milp__post','mode':'post'}
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
            with self.subTest(state=state),patch('sys.argv',['worker','--plan','x','--plan-sha256','x',
                    '--authorization','x','--ticket','x','--token','x','--output',str(out/'post')]),\
                 patch.object(common,'load_context',return_value=ctx),\
                 patch.object(worker,'validate_ticket',return_value=(ticket,job)),\
                 patch.object(worker,'_save'),patch.object(worker,'wait_monitor_ready'),\
                 patch.object(common,'verify_sources'),patch.object(worker,'run_post',return_value={'post_state':state}):
                self.assertEqual(worker.main(),2)

    def test_real_errors_and_unknown_cleanup_still_dominate(self):
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
            for kind in ('worker_error','process_error','cleanup_unknown','cleanup_failed'):
                with self.subTest(state=state,kind=kind):
                    ev=post_envelope(state);proc={'returncode':2,'wall_limit':False};clean=True
                    if kind=='worker_error':ev['errors']=['numeric failure']
                    if kind=='process_error':proc['error']='transport failure'
                    if kind=='cleanup_unknown':clean=None
                    if kind=='cleanup_failed':clean=False
                    expected='TECHNICAL_FAILURE' if kind.endswith('error') else 'CLEANUP_UNVERIFIED'
                    self.assertEqual(runner.classify_post(ev,proc,clean),expected)

    def test_unexpected_exit_or_missing_semantic_evidence_is_technical(self):
        for state in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
            for code in (0,1,-9,None):
                with self.subTest(state=state,code=code):
                    self.assertEqual(runner.classify_post(post_envelope(state),
                        {'returncode':code,'wall_limit':False},True),'TECHNICAL_FAILURE')
            ev=post_envelope(state)
            if state=='THERMAL_VIOLATION':ev['timely_violations_preserved']=[]
            else:ev['within_absolute_deadline']=False
            self.assertEqual(runner.classify_post(ev,{'returncode':2,'wall_limit':False},True),'TECHNICAL_FAILURE')

    def test_deadline_preserves_timely_violation_and_not_late_SAFE(self):
        proc={'returncode':-9,'wall_limit':True}
        self.assertEqual(runner.classify_post(post_envelope('THERMAL_VIOLATION'),proc,True),'POST_THERMAL_VIOLATION_STOP')
        ev=post_envelope('THERMAL_VIOLATION');ev['timely_violations_preserved']=[]
        self.assertEqual(runner.classify_post(ev,proc,True),'POST_TIME_LIMIT_UNRESOLVED')
        self.assertEqual(runner.classify_post(post_envelope('SAFE'),proc,True),'POST_TIME_LIMIT_UNRESOLVED')
        self.assertEqual(runner.classify_post({'errors':['NO_COMPLETE_WORKER_RECEIPT']},proc,True),'POST_TIME_LIMIT_UNRESOLVED')
        ev=post_envelope('THERMAL_VIOLATION');ev['errors']=['real failure']
        self.assertEqual(runner.classify_post(ev,proc,True),'TECHNICAL_FAILURE')

    def test_normal_SAFE_UNRESOLVED_and_ERROR_keep_existing_meanings(self):
        for state in ('SAFE','UNRESOLVED'):
            self.assertEqual(runner.classify_post(post_envelope(state),{'returncode':0,'wall_limit':False},True),'NORMAL_COMPLETION')
        self.assertEqual(runner.classify_post(post_envelope('ERROR'),{'returncode':2,'wall_limit':False},True),'TECHNICAL_FAILURE')
