"""Pure frozen-scope and factory checks; no scientific execution."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from research.chapter3_experiments import natural_delivery_entry as e

class EntryChecks(unittest.TestCase):
    def setUp(self):
        names=('ENTRY','WORKER_MODULE','PREPARATION','JOBS','SCOPE','METHOD_SECONDS','METHOD_WATCHDOG_SECONDS',
               'NATIVE_RESPONSE_VALIDATOR','validate_plan','freeze','native_session_factory','run_whole')
        self.saved={k:getattr(e.base,k) for k in names};e.configure()
    def tearDown(self):
        for k,v in self.saved.items():setattr(e.base,k,v)
    def test_scope_and_policy_required(self):
        p=deepcopy(e.base.read(e.PREVIOUS))
        p.update(budget_extension_only=False,delivery_policy=e.POLICY)
        for name in (e.ENTRY,e.ADAPTER):p['source_sha256'][name]='fixture'
        e.validate_plan(p)
        self.assertEqual(e.base.METHOD_SECONDS,600)
        self.assertEqual(e.base.SCOPE['method_calls'],1)
        self.assertEqual(e.base.SCOPE['post_seconds_each'],60)
        bad=deepcopy(p);bad['delivery_policy']['reserve_deduction_s']=20
        with self.assertRaises(ValueError):e.validate_plan(bad)
    def test_native_cap_and_options_identity(self):
        req=dict(remaining_s=500,solver_max_time_s_declared=470,solver_max_time_s=470,cut_max_iterations=10)
        response=dict(solver_max_time_s_declared=470,solver_max_time_s_allocated=470,
            solver_max_time_s_used=469,solver_max_time_s_scope='native_MaxTime_only_not_response_or_evidence_deadline',
            cut_max_iterations_declared=10,cut_max_iterations_actual_effective=10,options={'Display':'off','MaxTime':469})
        self.assertTrue(e.validate_response(req,response,{'Display':'off'})['passed'])
        with self.assertRaises(ValueError):e.prior.validate_response_600(req,response,{'Display':'off'})
        missing=dict(req);missing.pop('solver_max_time_s')
        with self.assertRaises(ValueError):e.validate_response(missing,response,{'Display':'off'})
        over=dict(response,solver_max_time_s_used=471,options={'Display':'off','MaxTime':471})
        with self.assertRaises(ValueError):e.validate_response(req,over,{'Display':'off'})
        for key,value in [('solver_max_time_s_allocated',471),('solver_max_time_s_used',468),('cut_max_iterations_actual_effective',9)]:
            bad=deepcopy(response);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):e.validate_response(req,bad,{'Display':'off'})
        with self.assertRaises(ValueError):e.validate_response(req,dict(response,options={'Display':'iter','MaxTime':469}),{'Display':'off'})
    def test_factory_wraps_reserve_inside_equality(self):
        from research.chapter3_experiments import native_delivery_reserve as reserve
        from research.chapter3_experiments.numeric_case_diagnostic import equality_session
        calls=[];session=SimpleNamespace(close=lambda:calls.append('close'))
        with patch.object(e.prior.repaired,'_native_factory_original',return_value=lambda:session), \
             patch.object(reserve,'attach',side_effect=lambda s:calls.append('reserve') or s), \
             patch.object(equality_session,'attach',side_effect=lambda s:calls.append('equality') or s):
            self.assertIs(e.native_session_factory({})(),session)
        self.assertEqual(calls,['reserve','equality'])
    def test_factory_closes_on_attach_failure(self):
        from research.chapter3_experiments import native_delivery_reserve as reserve
        calls=[];session=SimpleNamespace(close=lambda:calls.append('close'))
        with patch.object(e.prior.repaired,'_native_factory_original',return_value=lambda:session), \
             patch.object(reserve,'attach',side_effect=ValueError('fixture')):
            with self.assertRaises(ValueError):e.native_session_factory({})()
        self.assertEqual(calls,['close'])

if __name__=='__main__':unittest.main()
