"""Pure mock lifecycle/export regressions. No research schedule or thermal call."""
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import patch
from fractions import Fraction as F
from h02_pair_preflight.common import sha, ContractError
from h02_pair_b0.budget import RootClock, RootBudgetExpired, anchored_budget_class
from schedules import validate_schedule
from .mock_fixtures import make_fixture
from .scoring import score_candidate
from .runner import execute, ObjectiveRecorder
from .exports import verify_export
from .boundary import (Bindings, planner_chain, post_chain, MockConsumption,
                       supervision_state, validate_pair)


class Clock:
    def __init__(self, value=10): self.value = value
    def __call__(self): return self.value


class MockBudget:
    def __init__(self, seconds=300, *, clock):
        self.clock, self.start, self.seconds = clock, clock(), seconds
        self.deadline = self.start + seconds
    @property
    def elapsed(self): return self.clock() - self.start
    def check(self):
        if self.elapsed >= self.seconds: raise RootBudgetExpired('mock_deadline')
    @contextmanager
    def phase(self, name):
        self.check()
        yield
    def summary(self, stopped_s=None): return dict(limit_s=self.seconds, method_elapsed_s=self.elapsed)


def setup(*, objective='OMIT_TEMP', clock=None):
    clock = clock or Clock()
    root = RootClock(300, clock=clock, origin=0)
    budget = anchored_budget_class(MockBudget, root, clock)(seconds=300, clock=clock)
    a = make_fixture(opp='L', temperature_energy_J='1/10', h_activity_power_W='4')
    b = make_fixture(opp='H', temperature_energy_J='1/100', h_activity_power_W='4')
    config = dict(accuracy_targets=a['accuracy'])
    packet = dict(config=config, instance=a['instance'], objective=objective)
    values = {sha(f['candidate']): f['receipt'] for f in (a,b)}
    def evaluator(i,c,accuracy,budget): return deepcopy(values[sha(c)])
    return clock, root, budget, packet, a, b, evaluator


def sequence_search(candidates, after=None):
    def search(i,c,budget,assess,**kwargs):
        for j,candidate in enumerate(candidates): assess(deepcopy(candidate), 'mock:'+str(j))
        if after: after()
        return dict(status='MOCK_SEARCH_COMPLETED')
    return search


class RunnerTests(unittest.TestCase):
    def run_case(self, objective, *, transform=None):
        clock,root,budget,p,a,b,evaluator=setup(objective=objective)
        search=sequence_search([a['candidate'],b['candidate']])
        kwargs=dict(search=search,validator=validate_schedule,evaluator=evaluator)
        if transform: transform(clock,kwargs,a,b)
        result=execute(lambda budget:(p['config'],p['instance']),budget,objective,**kwargs)
        return p,a,b,result

    def test_inverse_ranking_export_keeps_objective_selection(self):
        p,a,b,result=self.run_case('OMIT_TEMP')
        self.assertEqual(result['safe_candidate'],a['candidate'])
        self.assertGreater(F(result['safe_upper_bound_J']),F(b['receipt']['safe_upper_bound_J']))
        self.assertEqual(result['evaluation'],a['receipt'])
        self.assertEqual(verify_export(p['instance'],p['config'],result)['state'],'SELECTED_SAFE_IDENTITY_VERIFIED')
        p,a,b,result=self.run_case('FULL')
        self.assertEqual(result['safe_candidate'],b['candidate'])
        verify_export(p['instance'],p['config'],result)

    def test_decimal_receipt_representation_keeps_numeric_identity(self):
        def transform(clock,kwargs,a,b):
            original=kwargs['evaluator']
            def decimal_receipt(*args):
                r=original(*args)
                r['weighted_energy_J']=[format(float(F(v)),'.6f') for v in r['weighted_energy_J']]
                r['safe_upper_bound_J']=r['weighted_energy_J'][1]
                return r
            kwargs['evaluator']=decimal_receipt
        p,a,b,r=self.run_case('FULL',transform=transform)
        self.assertFalse(r['stop_required']); self.assertEqual(r['state'],'SAFE')
        self.assertEqual(r['evaluation']['weighted_energy_J'],['0.780000','0.780000'])
        verify_export(p['instance'],p['config'],r)

    def test_true_best_cannot_be_substituted_into_omit_export(self):
        p,a,b,result=self.run_case('OMIT_TEMP')
        for field,value in [('safe_candidate',b['candidate']),('safe_upper_bound_J',b['receipt']['safe_upper_bound_J']),
                            ('evaluation',b['receipt']),('planning_score_J',['0','0']),('selected_at_s',300)]:
            damaged=deepcopy(result); damaged[field]=value
            with self.subTest(field=field), self.assertRaises(ContractError): verify_export(p['instance'],p['config'],damaged)

    def test_exact_score_tie_keeps_earliest_not_lower_true_u(self):
        clock,root,budget,p,a,b,e=setup()
        second=make_fixture(opp='L',start_ms='5',temperature_energy_J='1/100',h_activity_power_W='4')
        table={sha(x['candidate']):x['receipt'] for x in (a,second)}
        r=execute(lambda b:(p['config'],p['instance']),budget,'OMIT_TEMP',validator=validate_schedule,
            evaluator=lambda i,c,ac,b:deepcopy(table[sha(c)]),search=sequence_search([a['candidate'],second['candidate']]))
        self.assertEqual(r['safe_candidate'],a['candidate']); verify_export(p['instance'],p['config'],r)

    def test_cache_is_local_and_never_mutates_true_receipt(self):
        clock,root,budget,p,a,b,e=setup(); calls=[]
        def evaluator(*args): calls.append(1); return e(*args)
        rec=ObjectiveRecorder(p['instance'],p['config']['accuracy_targets'],budget,'OMIT_TEMP',validator=validate_schedule,evaluator=evaluator)
        view=rec.assess(a['candidate'],'first'); view['planning_score_J']=['0','0']
        self.assertNotEqual(rec.assess(a['candidate'],'duplicate')['planning_score_J'],['0','0'])
        self.assertEqual(len(calls),1); self.assertEqual(rec.cache_hits,1)
        self.assertEqual(rec.best['evaluation'],a['receipt'])
        other=ObjectiveRecorder(p['instance'],p['config']['accuracy_targets'],budget,'FULL',validator=validate_schedule,evaluator=evaluator)
        other.assess(a['candidate'],'other-call'); self.assertEqual(len(calls),2)

    def test_late_evaluator_preserves_old_selected_and_raw_timely_safe(self):
        def transform(clock,kwargs,a,b):
            def evaluator(i,c,ac,budget):
                if c==b['candidate']: clock.value=301
                return deepcopy(a['receipt'] if c==a['candidate'] else b['receipt'])
            kwargs['evaluator']=evaluator
        p,a,b,r=self.run_case('FULL',transform=transform)
        self.assertEqual(r['reason'],'METHOD_BUDGET_EXHAUSTED')
        self.assertEqual(r['safe_candidate'],a['candidate'])
        last=r['archive']['evaluations'][-1]
        self.assertTrue(last['accepted_safe']); self.assertFalse(last['eligible_for_selection'])
        verify_export(p['instance'],p['config'],r)

    def test_scoring_crossing_deadline_cannot_add_selection(self):
        def transform(clock,kwargs,a,b):
            def slow(*args):
                value=score_candidate(*args)
                if args[1]==b['candidate']: clock.value=300
                return value
            kwargs['scorer']=slow
        p,a,b,r=self.run_case('FULL',transform=transform)
        self.assertEqual(r['safe_candidate'],a['candidate']); self.assertFalse(r['archive']['evaluations'][-1]['eligible_for_selection'])
        verify_export(p['instance'],p['config'],r)

    def test_selection_assembly_crossing_deadline_cannot_add_safe(self):
        from . import runner
        clock,root,budget,p,a,b,e=setup()
        original=runner.deepcopy
        def copying(value):
            result=original(value)
            if isinstance(value,dict) and 'true_U_J' in value and 'planning_score_J' in value:
                clock.value=300
            return result
        with patch.object(runner,'deepcopy',side_effect=copying):
            r=execute(lambda b:(p['config'],p['instance']),budget,'FULL',validator=validate_schedule,
                evaluator=e,search=sequence_search([a['candidate']]))
        self.assertEqual(r['state'],'UNRESOLVED'); self.assertEqual(r['reason'],'METHOD_BUDGET_EXHAUSTED')
        self.assertFalse(r['archive']['evaluations'][0]['eligible_for_selection'])
        verify_export(p['instance'],p['config'],r)

    def test_late_physical_completion_is_not_safe_output(self):
        def transform(clock,kwargs,a,b):
            def late(*args):
                clock.value=301; receipt=deepcopy(a['receipt']); receipt['completed_at_elapsed_s']=300
                return receipt
            kwargs['evaluator']=late
        p,a,b,r=self.run_case('FULL',transform=transform)
        self.assertEqual(r['state'],'UNRESOLVED'); self.assertIsNone(r['evaluation'])
        self.assertEqual(r['reason'],'METHOD_BUDGET_EXHAUSTED'); verify_export(p['instance'],p['config'],r)

    def test_budget_expiry_keeps_timely_violation(self):
        clock,root,budget,p,a,b,e=setup()
        def violation(i,c,ac,b):
            clock.value=301
            return dict(state='THERMAL_VIOLATION',problem_id=i['id'],evidence_identity=dict(input_sha256=sha(i),candidate_sha256=sha(c)),
                violations=[dict(scene_id='AB',node='N0',temperature_degC=['81','81'],limit_degC='80',time_s='1/10',formed_at_elapsed_s=299)])
        r=execute(lambda b:(p['config'],p['instance']),budget,'FULL',validator=validate_schedule,evaluator=violation,search=sequence_search([a['candidate']]))
        self.assertEqual(r['reason'],'METHOD_BUDGET_EXHAUSTED'); self.assertEqual(len(r['archive']['violations']),1)

    def test_technical_failure_preserves_old_safe_but_stops_batch(self):
        def transform(clock,kwargs,a,b):
            def evaluator(i,c,ac,budget):
                if c==b['candidate']: raise ValueError('injected_fault')
                return deepcopy(a['receipt'])
            kwargs['evaluator']=evaluator
        p,a,b,r=self.run_case('FULL',transform=transform)
        self.assertTrue(r['stop_required']); self.assertEqual(r['state'],'SAFE')
        self.assertEqual(r['safe_candidate'],a['candidate']); self.assertTrue(verify_export(p['instance'],p['config'],r)['stop_required'])

    def test_mutated_input_or_receipt_identity_stops(self):
        for fault in ('mutation','identity','legality','numerical'):
            def transform(clock,kwargs,a,b):
                def bad(i,c,ac,budget):
                    r=deepcopy(a['receipt'])
                    if fault=='mutation': i['window_ms']='1'
                    if fault=='identity': r['evidence_identity']['candidate_sha256']='wrong'
                    if fault=='legality': r['legality']['node_order']=[]
                    if fault=='numerical': r['reason']='NUMERICAL_ERROR'
                    return r
                kwargs['evaluator']=bad
            with self.subTest(fault=fault):
                p,a,b,r=self.run_case('FULL',transform=transform)
                self.assertTrue(r['stop_required']); self.assertEqual(r['state'],'UNRESOLVED')

    def test_no_safe_and_no_candidate_are_not_failure_or_infeasibility(self):
        clock,root,budget,p,a,b,e=setup()
        def unresolved(i,c,ac,b):
            return dict(state='UNRESOLVED',problem_id=i['id'],evidence_identity=dict(input_sha256=sha(i),candidate_sha256=sha(c)),violations=[],reason='precision_unresolved')
        r=execute(lambda b:(p['config'],p['instance']),budget,'FULL',validator=validate_schedule,evaluator=unresolved,search=sequence_search([a['candidate']]))
        self.assertFalse(r['stop_required']); self.assertEqual(r['state'],'UNRESOLVED'); verify_export(p['instance'],p['config'],r)
        r=execute(lambda b:(p['config'],p['instance']),budget,'FULL',validator=validate_schedule,evaluator=unresolved,search=sequence_search([]))
        self.assertEqual(r['reason'],'DECLARED_SEARCH_COMPLETED'); verify_export(p['instance'],p['config'],r)


class BoundaryTests(unittest.TestCase):
    def test_mock_chain_root_includes_preparation(self):
        clock,root,budget,p,a,b,e=setup()
        bindings=Bindings(sequence_search([a['candidate']]),validate_schedule,e,MockBudget,RootBudgetExpired)
        out=planner_chain(p,root,bindings)
        self.assertEqual(out['result']['timing']['root_origin'],0)
        self.assertEqual(out['result']['timing']['method_elapsed_s'],10)
        self.assertFalse(out['usable_as_research_evidence'])

    def test_input_phase_expiry_remains_normal_unresolved(self):
        clock,root,budget,p,a,b,e=setup()
        bindings=Bindings(sequence_search([]),validate_schedule,e,MockBudget,RootBudgetExpired)
        from . import boundary
        real_deepcopy=boundary.deepcopy
        def copying(value):
            result=real_deepcopy(value)
            if isinstance(value,dict) and set(value)=={'accuracy_targets'}:
                clock.value=300
                raise RootBudgetExpired('mock_input_deadline')
            return result
        with patch.object(boundary,'deepcopy',side_effect=copying):
            out=planner_chain(p,root,bindings)
        self.assertEqual(out['result']['reason'],'METHOD_BUDGET_EXHAUSTED')
        self.assertFalse(out['result']['stop_required'])

    def test_real_kind_rejected_before_any_callable(self):
        clock,root,budget,p,a,b,e=setup(); calls=[]
        def forbidden(*args,**kwargs): calls.append(1); raise AssertionError('real forbidden')
        bindings=Bindings(forbidden,forbidden,forbidden,MockBudget,RootBudgetExpired,kind='REAL_CORE')
        with self.assertRaisesRegex(ContractError,'NOT_AUTHORIZED'): planner_chain(p,root,bindings)
        with self.assertRaisesRegex(ContractError,'NOT_AUTHORIZED'): post_chain(p,{},root,bindings)
        self.assertEqual(calls,[])

    def test_whitelist_and_same_true_input(self):
        clock,root,budget,left,a,b,e=setup(objective='FULL'); right=deepcopy(left); right['objective']='OMIT_TEMP'
        self.assertEqual(validate_pair(left,right)['differing_fields'],['objective'])
        for change in ('input','accuracy','extra'):
            r=deepcopy(right)
            if change=='input': r['instance']['window_ms']='399'
            if change=='accuracy': r['config']['accuracy_targets']['temperature_enclosure_width_K']='1'
            if change=='extra': r['historical_best']=a['candidate']
            with self.subTest(change=change),self.assertRaises(ContractError): validate_pair(left,r)

    def test_once_claim_stop_and_limits(self):
        ledger=MockConsumption()
        with self.assertRaises(ContractError): ledger.claim_post(1,'hash')
        ledger.claim_plan(1); ledger.claim_post(1,'hash')
        with self.assertRaises(ContractError): ledger.claim_plan(1)
        with self.assertRaises(ContractError): ledger.claim_post(1,'other')
        ledger.observe({'state':'SAFE','stop_required':True})
        with self.assertRaises(ContractError): ledger.claim_plan(2)
        with self.assertRaises(ContractError): MockConsumption().claim_plan(5)

    def test_watchdog_does_not_extend_evidence(self):
        self.assertEqual(supervision_state(299,0,300,299,299),'RUN')
        self.assertEqual(supervision_state(300,0,300,300,300),'ARCHIVE_ONLY')
        self.assertEqual(supervision_state(305,0,300,305,305),'TERMINATE')
        self.assertEqual(supervision_state(10,0,300,420,420),'TERMINATE')
        self.assertEqual(supervision_state(10,0,300,10,1800),'TERMINATE')

    def test_root_cannot_be_reset(self):
        clock,root,budget,*_=setup()
        budget.start=5
        with self.assertRaises(ValueError): budget.check()
        cls=anchored_budget_class(MockBudget,root,clock)
        with self.assertRaises(ValueError): cls(seconds=290,clock=clock)

    def test_post_only_same_candidate_and_no_search(self):
        clock,root,budget,p,a,b,e=setup(); root=RootClock(60,clock=clock,origin=0)
        def no_search(*args,**kwargs): raise AssertionError('post search forbidden')
        bindings=Bindings(no_search,validate_schedule,e,MockBudget,RootBudgetExpired)
        token=dict(input_sha256=sha(p['instance']),candidate=deepcopy(a['candidate']),candidate_sha256=sha(a['candidate']))
        out=post_chain(p,token,root,bindings)
        self.assertEqual(out['state'],'MOCK_SAFE_RECEIPT_CHECKED'); self.assertEqual(out['new_real_SAFE'],0)
        token['candidate']=b['candidate']
        self.assertTrue(post_chain(p,token,root,bindings)['stop_required'])


if __name__=='__main__': unittest.main()
