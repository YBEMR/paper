"""Pure budget wiring checks; no model construction or scientific calls."""
from copy import deepcopy
import sys
from types import ModuleType
import unittest
from unittest.mock import patch
from research.chapter3_experiments import natural_full_600_entry as e

class BudgetChecks(unittest.TestCase):
    def setUp(self):
        names=('ENTRY','WORKER_MODULE','PREPARATION','JOBS','SCOPE','METHOD_SECONDS',
               'METHOD_WATCHDOG_SECONDS','validate_plan','freeze','native_session_factory','run_whole')
        self.saved={k:getattr(e.base,k) for k in names}
        e.configure()
    def tearDown(self):
        for k,v in self.saved.items():setattr(e.base,k,v)
    def test_scope_and_unchanged_problem(self):
        p=deepcopy(e.base.read(e.PREVIOUS))
        p.update(jobs=e.base.JOBS,scope=e.SCOPE,method_process_watchdog_seconds=705,budget_extension_only=True)
        p['source_sha256'][e.ENTRY]='fixture'
        e.validate_plan(p)
        self.assertEqual(e.base.METHOD_SECONDS,600)
        self.assertEqual(len(e.base.JOBS),1)
        self.assertEqual(e.SCOPE['post_seconds_each'],60)
        for key,value in [('scope',dict(e.SCOPE,method_seconds_each=601)),('jobs',[]),('cut_max_iterations',9)]:
            bad=deepcopy(p);bad[key]=value
            with self.assertRaises(ValueError):e.validate_plan(bad)
    def test_audit_uses_600_and_restores(self):
        fake=ModuleType('audit_whole');fake.SECONDS=300
        def recorded():
            self.assertEqual(fake.SECONDS,600)
            return 'saved-only'
        with patch.dict(sys.modules,{'audit_whole':fake}),patch.object(e,'_run_whole_original',recorded):
            self.assertEqual(e.run_whole(),'saved-only')
            self.assertEqual(fake.SECONDS,300)
    def test_parent_clock_has_real_600_deadline(self):
        e.base.sys.path.insert(0,str(e.base.EXP))
        from timing import MethodBudget
        clock=e.base.ParentOriginClock(100,clock=lambda:550)
        b=MethodBudget(e.base.METHOD_SECONDS,clock=clock)
        self.assertEqual(b.deadline,700)
        b.check()
        self.assertEqual(b.elapsed,450)

if __name__=='__main__':unittest.main()
