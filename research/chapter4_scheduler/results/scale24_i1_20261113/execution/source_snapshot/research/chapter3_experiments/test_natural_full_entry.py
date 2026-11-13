"""Pure adapter-boundary tests; no numerical model, native process or heat call."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.chapter3_experiments import natural_full_entry as e


class AdapterChecks(unittest.TestCase):
    def test_scope_is_one_whole_one_heft_one_sa(self):
        self.assertEqual([j['id'] for j in e.JOBS],['whole_milp','heft','sa101'])
        self.assertEqual(e.SCOPE['method_calls'],3)
        self.assertEqual(e.SCOPE['method_seconds_total'],900)
        self.assertEqual(e.SCOPE['post_seconds_total_at_most'],180)
        self.assertEqual(e.SCOPE['batch_calendar_seconds'],1440)
        self.assertEqual(e.SCOPE['retries'],0)

    def test_bootstrap_only_first_read_then_real_monotonic(self):
        now=[125.]
        clock=e.ParentOriginClock(100.,lambda:now[0])
        self.assertEqual(clock(),100.)
        self.assertEqual(clock(),125.)
        now[0]=129.
        self.assertEqual(clock(),129.)
        with self.assertRaises(ValueError):e.ParentOriginClock(130.,lambda:now[0])

    def test_original_budget_includes_parent_preparation(self):
        # Importing the original numerical definitions does not evaluate them.
        with patch.object(sys,'path',[str(e.EXP),*sys.path]):
            from timing import MethodBudget
            from thermal import Exhausted
            now=[125.]
            b=MethodBudget(300,clock=e.ParentOriginClock(100.,lambda:now[0]))
            self.assertEqual((b.start,b.deadline,b.elapsed),(100.,400.,25.))
            now[0]=399.999;b.check()
            now[0]=400.
            with self.assertRaises(Exhausted):b.check()
            expired=MethodBudget(300,clock=e.ParentOriginClock(0.,lambda:400.))
            with self.assertRaises(Exhausted):expired.check()

    def model_fixture(self):
        times=[F(0),F(1,200),F(2,5)]
        estimate={'deadline_legal_options':2,'predicted_total_variables':5,'predicted_total_rows':3,
                  'stage_binary_variables':2,'unique_state_duration_coefficient_keys':4,'nonzeros_upper_bound':8,
                  'scenes':[{'id':'s','events':3,'event_times_s_sha256':hashlib.sha256(
                      json.dumps(list(map(str,times)),separators=(',',':')).encode()).hexdigest()}]}
        model=SimpleNamespace(instance={},options=[{},{}],names=list('abcde'),
                    rows=[{'coef':{0:1}},{'coef':{1:2}},{'coef':{3:1}}],integer=[0,1],option_vars=[0,1],
                    lb=[0,0,0,0,0],ub=[1,1,5,5,5],coefficients=SimpleNamespace(calls=4),
                    scenes={'s':{'events':times}})
        return model,estimate

    def test_full_domain_model_admission_counts_without_physics(self):
        model,estimate=self.model_fixture()
        self.assertEqual(e.admit_model(model,estimate)['actual_nonzeros'],3)

    def test_old_restricted_domain_or_wrong_scale_rejected(self):
        for mutation in ('explicit','options','events','integrality','coefficient','bounds','rows'):
            with self.subTest(mutation=mutation):
                m,s=self.model_fixture()
                if mutation=='explicit':m.instance['start_domain']={'kind':'explicit_grid_subset'}
                elif mutation=='options':m.options.append({})
                elif mutation=='events':m.scenes['s']['events'][1]=F(1,100)
                elif mutation=='integrality':m.integer=[0]
                elif mutation=='coefficient':m.coefficients.calls=5
                elif mutation=='bounds':m.lb[0]=1
                elif mutation=='rows':m.rows.append({'coef':{}})
                with self.assertRaises(ValueError):e.admit_model(m,s)

    def test_full_builder_flags_do_not_fix_choice_domains(self):
        f=e.BUILDER_FLAGS
        for name in ('fixed_deployment','fixed_shared_deployment','fixed_scene_id','neighborhood_condition'):
            self.assertIsNone(f[name])
        self.assertFalse(f['preeliminate_closed_anchors'])
        self.assertTrue(f['prefilter_deadlines'])
        self.assertTrue(f['include_physics'])

    def test_new_plan_and_separate_user_binding(self):
        # Fake paths/data only; no real freeze, claim, subprocess or source import.
        old=e.read(e.RESULTS/'small_whole_preparation01/plan.json')
        plan={'schema':'natural-full-three-manual-v1','execution_authorized':False,
              'jobs':deepcopy(e.JOBS),'scope':deepcopy(e.SCOPE),'input_file':e.INPUT,'config_file':e.CONFIG,
              'method_process_watchdog_seconds':405,'historical_candidate_or_cache_input':False,
              'reference_read_by_search':False,'science_source_count':197,
              'source_sha256':{e.ENTRY:'fake'},'builder_flags':deepcopy(e.BUILDER_FLAGS),
              'feedback_kind':'conditional','cut_max_iterations':10}
        e.validate_plan(plan)
        for key,value in [('execution_authorized',True),('jobs',[e.JOBS[0]]),('cut_max_iterations',9)]:
            bad=deepcopy(plan);bad[key]=value
            with self.assertRaises(ValueError):e.validate_plan(bad)
        self.assertEqual(old['method_seconds'],300)

    def test_declaration_uses_new_scene_identity(self):
        inst={'id':'new','window_ms':'400','platform':{'node_order':['CPU1']},
              'scenarios':[{'id':'s','weight':'1','maximum_temperature_degC':['80']}]}
        d=e.declaration(inst,{'x':1})
        self.assertEqual(d['problem_id'],'new')
        self.assertEqual(d['scene_spec']['s']['window_s'],'2/5')
        self.assertEqual(d['scene_spec']['s']['limits'],{'CPU1':'80'})


if __name__=='__main__':unittest.main()
