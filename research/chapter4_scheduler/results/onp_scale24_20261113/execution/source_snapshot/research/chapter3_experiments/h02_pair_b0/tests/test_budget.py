"""Pure mock deadline regression. Never instantiate a real thermal budget."""
import unittest
from h02_pair_b0.budget import (RootClock, BudgetContractError, RootBudgetExpired,
    anchored_budget_class, watchdog_decision, timely_receipt)


class FakeClock:
    def __init__(self, now=1000.0): self.now=now
    def __call__(self): return self.now


class FakeBaseExpired(RuntimeError): pass


class FakeBase:
    def __init__(self, seconds=60, *, clock):
        self.clock=clock; self.seconds=seconds; self.start=clock()
        self.deadline=self.start+seconds
    def check(self):
        if self.clock() >= self.deadline: raise FakeBaseExpired('fake limit')
    def summary(self, stopped_s=None):
        elapsed=self.elapsed if stopped_s is None else stopped_s
        return dict(limit_s=self.seconds, method_elapsed_s=elapsed,
                    clock_origin='old local start')


class BudgetTests(unittest.TestCase):
    def test_controller_root_includes_before_spawn_cost(self):
        clock=FakeClock(); root=RootClock(120,clock=clock)
        clock.now+=31
        cls=anchored_budget_class(FakeBase,root,clock)
        budget=cls(seconds=120)
        self.assertEqual(budget.elapsed,31)
        self.assertEqual(budget.remaining,89)
        self.assertEqual(budget.deadline,1120)
        self.assertIn('worker startup',budget.summary()['clock_origin'])
        self.assertIn('projection',budget.summary()['clock_origin'])

    def test_exact_120_cutoff(self):
        clock=FakeClock(); root=RootClock(120,clock=clock)
        cls=anchored_budget_class(FakeBase,root,clock); budget=cls(seconds=120)
        clock.now=1119.999; budget.check()
        clock.now=1120
        with self.assertRaises(FakeBaseExpired): budget.check()
        with self.assertRaises(RootBudgetExpired): root.check()

    def test_independent_60_second_audit_root(self):
        clock=FakeClock(2000); root=RootClock(60,clock=clock)
        clock.now+=9
        budget=anchored_budget_class(FakeBase,root,clock)(seconds=60)
        self.assertEqual(budget.remaining,51)
        clock.now=2060
        with self.assertRaises(FakeBaseExpired): budget.check()

    def test_numeric_worker_origin_is_anchored(self):
        clock=FakeClock(1050)
        budget=anchored_budget_class(FakeBase,1000,clock)(seconds=120)
        self.assertEqual(budget.elapsed,50)
        self.assertEqual(budget.deadline,1120)

    def test_remaining_seconds_cannot_replace_full_declared_limit(self):
        clock=FakeClock(); root=RootClock(120,clock=clock); clock.now+=40
        cls=anchored_budget_class(FakeBase,root,clock)
        with self.assertRaisesRegex(BudgetContractError,'remaining seconds'):
            cls(seconds=80)
        self.assertEqual(cls(seconds=120).remaining,80)

    def test_repeated_constructor_cannot_reset_root(self):
        clock=FakeClock(); root=RootClock(120,clock=clock)
        budget=anchored_budget_class(FakeBase,root,clock)(seconds=120)
        clock.now+=20
        with self.assertRaisesRegex(BudgetContractError,'reinitialized'):
            budget.__init__(seconds=120)
        self.assertEqual(budget.elapsed,20)

    def test_changed_metadata_is_detected(self):
        for field,value in [('start',1001),('deadline',1200),('seconds',119),('clock',lambda:1000)]:
            with self.subTest(field=field):
                clock=FakeClock(); root=RootClock(120,clock=clock)
                budget=anchored_budget_class(FakeBase,root,clock)(seconds=120)
                setattr(budget,field,value)
                with self.assertRaisesRegex(BudgetContractError,'drift/reset'): budget.check()

    def test_worker_cannot_change_clock(self):
        clock=FakeClock(); root=RootClock(120,clock=clock)
        with self.assertRaises(BudgetContractError):
            anchored_budget_class(FakeBase,root,FakeClock())
        cls=anchored_budget_class(FakeBase,root,clock)
        with self.assertRaises(BudgetContractError): cls(seconds=120,clock=FakeClock())

    def test_watchdog_grace_is_archive_only(self):
        self.assertEqual(watchdog_decision(1119.999,1000,120),'RUN')
        self.assertEqual(watchdog_decision(1120,1000,120),'ARCHIVE_ONLY')
        self.assertEqual(watchdog_decision(1124.999,1000,120),'ARCHIVE_ONLY')
        self.assertEqual(watchdog_decision(1125,1000,120),'TERMINATE')
        self.assertFalse(timely_receipt(120,120,returned_at_elapsed_s=124))
        self.assertFalse(timely_receipt(122,120,returned_at_elapsed_s=124))

    def test_zero_grace_terminates_at_cutoff(self):
        self.assertEqual(watchdog_decision(1060,1000,60,grace=0),'TERMINATE')

    def test_late_return_preserves_already_formed_evidence(self):
        self.assertTrue(timely_receipt(119.9,120,returned_at_elapsed_s=124))
        self.assertTrue(timely_receipt(59.9,60,returned_at_elapsed_s=61))
        self.assertTrue(timely_receipt(0,60,returned_at_elapsed_s=0))

    def test_strict_receipt_boundary_and_invalid_clock_types(self):
        for value in [120,120.1,-1,float('nan'),float('inf'),True,False,None,'119']:
            with self.subTest(value=str(value)):
                self.assertFalse(timely_receipt(value,120))
        for value in [float('nan'),float('inf'),True,-1,30]:
            with self.subTest(returned=str(value)):
                self.assertFalse(timely_receipt(59.9,60,returned_at_elapsed_s=value))

    def test_root_rejects_invalid_limit_origin_and_clock(self):
        for value in [0,-1,float('nan'),float('inf'),True,'120']:
            with self.subTest(value=str(value)),self.assertRaises(BudgetContractError):
                RootClock(value,clock=FakeClock())
        with self.assertRaises(BudgetContractError): RootClock(120,clock=None)
        with self.assertRaises(BudgetContractError): RootClock(120,clock=FakeClock(),origin=True)

    def test_invalid_watchdog_fields_are_errors(self):
        for args in [(1000,1001,120,5),(1000,1000,120,-1),
                     (float('nan'),1000,120,5),(1000,True,120,5),
                     (1000,1000,False,5),(1000,1000,120,float('inf'))]:
            with self.subTest(args=str(args)),self.assertRaises(BudgetContractError):
                watchdog_decision(*args)

    def test_base_failing_to_stop_still_fails_closed(self):
        class NoCheckBase(FakeBase):
            def check(self): pass
        clock=FakeClock(); root=RootClock(60,clock=clock)
        budget=anchored_budget_class(NoCheckBase,root,clock)(seconds=60)
        clock.now=1060
        with self.assertRaises(RootBudgetExpired): budget.check()

    def test_clock_backwards_is_contract_error(self):
        clock=FakeClock(); root=RootClock(120,clock=clock)
        budget=anchored_budget_class(FakeBase,root,clock)(seconds=120)
        clock.now=999
        with self.assertRaises(BudgetContractError): root.check()
        with self.assertRaises(BudgetContractError): budget.check()

    def test_expired_worker_does_not_gain_startup_time(self):
        clock=FakeClock(); root=RootClock(120,clock=clock); clock.now=1122
        budget=anchored_budget_class(FakeBase,root,clock)(seconds=120)
        self.assertEqual(budget.remaining,0)
        with self.assertRaises(FakeBaseExpired): budget.check()

    def test_root_public_properties_not_resettable(self):
        root=RootClock(120,clock=FakeClock())
        for attr in ['origin','start','seconds','deadline','limit_s']:
            with self.subTest(attr=attr),self.assertRaises(AttributeError): setattr(root,attr,0)


if __name__=='__main__': unittest.main()
