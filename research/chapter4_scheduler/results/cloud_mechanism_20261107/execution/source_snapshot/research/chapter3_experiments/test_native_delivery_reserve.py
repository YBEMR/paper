"""Fake clocks/backends only: no solver, construction or thermal evaluation."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from research.chapter3_experiments import native_delivery_reserve as reserve


class Clock:
    def __init__(self, now=100):self.now = now
    def __call__(self):return self.now


class Budget:
    def __init__(self, clock):
        self.clock, self.seconds, self.start, self.deadline = clock, 600, 0, 600
    def check(self):
        if self.clock() >= self.deadline:raise TimeoutError('root exhausted')


class FakeSession:
    def __init__(self, folder):
        self.clock = Clock()
        self.budget = Budget(self.clock)
        self.deadline = 600
        self.workdir = Path(folder)
        self.counter = 0
        self.calls = []
        self.event_consumer = object()
        self.returned = {'status':'SOLVED','budget_valid':True,'x':[1.0]}
    def solve(self, model, remaining_s=None, budget=None, x0=None, solver_max_time_s=None):
        self.counter += 1
        self.calls.append(dict(model=model,remaining_s=remaining_s,budget=budget,x0=x0,
                               solver_max_time_s=solver_max_time_s))
        return self.returned


class DeliveryReserveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='reserve_fake_', dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.s = FakeSession(self.temp.name)
    def receipt(self):
        return json.loads((self.s.workdir/'request_000001.delivery_reserve.json').read_text(encoding='utf-8'))
    def test_original_root_callback_inputs_and_return_identity(self):
        callback=self.s.event_consumer;budget=self.s.budget;model=object();x0=object()
        self.assertIs(reserve.attach(self.s),self.s)
        got=self.s.solve(model,remaining_s=500,budget=budget,x0=x0)
        call=self.s.calls[0]
        self.assertIs(got,self.s.returned)
        self.assertIs(self.s.event_consumer,callback)
        self.assertIs(call['model'],model);self.assertIs(call['x0'],x0)
        self.assertIs(call['budget'],budget)
        self.assertEqual(call['remaining_s'],500)
        self.assertEqual(call['solver_max_time_s'],470)
        self.assertEqual((budget.start,budget.deadline,self.s.deadline),(0,600,600))
        self.assertEqual(self.receipt()['effective_response_deadline'],600)
    def test_cap_is_computed_at_call_after_conversion_time(self):
        reserve.attach(self.s)
        self.s.clock.now=125
        self.s.solve({},remaining_s=475,budget=self.s.budget)
        self.assertEqual(self.s.calls[0]['solver_max_time_s'],445)
        self.assertEqual(self.receipt()['allocation_at_monotonic'],125)
    def test_stricter_request_and_session_deadlines_are_respected(self):
        reserve.attach(self.s)
        self.s.deadline=450
        self.s.solve({},remaining_s=200,budget=self.s.budget)
        self.assertEqual(self.s.calls[0]['solver_max_time_s'],170)
        self.assertEqual(self.s.calls[0]['remaining_s'],200)
        self.assertEqual(self.receipt()['effective_response_deadline'],300)
    def test_no_request_or_counter_consumption_when_reserve_unavailable(self):
        for now in (570,580):
            with self.subTest(now=now),tempfile.TemporaryDirectory(dir=self.temp.name) as folder:
                s=FakeSession(folder);s.clock.now=now;reserve.attach(s)
                with self.assertRaises(reserve.DeliveryReserveUnavailable):
                    s.solve({},remaining_s=600-now,budget=s.budget)
                self.assertEqual(s.counter,0);self.assertEqual(s.calls,[])
                self.assertEqual(len(list(s.workdir.glob('*'))),1)
                data=json.loads(next(s.workdir.glob('*')).read_text(encoding='utf-8'))
                self.assertFalse(data['native_backend_called'])
                self.assertFalse(data['native_request_number_consumed'])
    def test_reject_external_cap_and_wrong_budget(self):
        reserve.attach(self.s)
        with self.assertRaises(ValueError):self.s.solve({},solver_max_time_s=10)
        self.s.budget.seconds=300
        with self.assertRaises(ValueError):self.s.solve({})
        self.assertEqual(self.s.counter,0)
    def test_exhausted_root_never_calls_backend(self):
        reserve.attach(self.s);self.s.clock.now=600
        with self.assertRaises(TimeoutError):self.s.solve({})
        self.assertEqual(self.s.calls,[])
    def test_late_backend_receipt_is_not_promoted(self):
        self.s.returned={'status':'BUDGET_EXHAUSTED','budget_valid':False,'x':[]}
        reserve.attach(self.s)
        self.assertIs(self.s.solve({}),self.s.returned)
    def test_install_order_and_double_attach_guard(self):
        self.s._exact_equalities_attached=True
        with self.assertRaises(ValueError):reserve.attach(self.s)
        del self.s._exact_equalities_attached
        reserve.attach(self.s)
        with self.assertRaises(ValueError):reserve.attach(self.s)


if __name__=='__main__':unittest.main()
