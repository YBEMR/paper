"""Eight-arm dispatch contract, without starting any research backend."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import run,method as filtered
from ..blocking import method as frozen,core
from ..i1.initializer import run_heft_i1
from ..i1.admission import ADMISSION_S
from ..tests.test_method import FakeClock
from timing import MethodBudget


class EntryTests(unittest.TestCase):
    def test_exact_roots_arms_order_and_budgets(self):
        cases=[{'case_id':r+'__n24','root_id':r} for r in ('U03','U04')]
        s=run.slots(cases)
        self.assertEqual(len(s),8)
        for root in ('U03','U04'):
            self.assertEqual({x['arm'] for x in s if x['root_id']==root},{'ON','ON_P','OFF','OFF_P'})
        self.assertEqual(run.BUDGETS['method_s'],300);self.assertEqual(ADMISSION_S,180)
        self.assertEqual(run.BUDGETS['I1_new_work_admission_s'],180)
        self.assertEqual(run.BUDGETS['post_s'],60)
        with self.assertRaises(ValueError):run.slots(cases+[cases[0]])

    def test_all_four_share_exact_initializer_budget_evaluator(self):
        root=(run.REPO/'.runtime').resolve();root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='onp-entry-',dir=root) as tmp:
            for arm in ('ON','ON_P','OFF','OFF_P'):
                b=MethodBudget(300,clock=FakeClock());ev=object();seen=[];old=core.reconstruct
                def stub(loader,folder,**kw):
                    Path(folder).mkdir();seen.append(kw);return {'stub':True}
                with patch.object(frozen,'execute_reconstruction',side_effect=stub) as oldfn, \
                     patch.object(filtered,'execute_reconstruction',side_effect=stub) as newfn:
                    run.dispatch(arm,None,Path(tmp)/arm,b,frozen.Bindings(None,ev,'REAL_CORE'))
                self.assertEqual(oldfn.call_count,0 if arm.endswith('_P') else 1)
                self.assertEqual(newfn.call_count,1 if arm.endswith('_P') else 0)
                kw=seen[0];self.assertIs(kw['bindings'].initializer,run_heft_i1)
                self.assertIs(kw['bindings'].evaluator,ev);self.assertIs(kw['budget'],b)
                self.assertEqual(kw['seconds'],300);self.assertEqual(kw['bindings'].kind,'REAL_I1')
                self.assertEqual(kw['allow_blocking_edges'],arm.startswith('ON'))
                self.assertIs(core.reconstruct,old)

    def test_no_other_method_and_exception_restores_observer(self):
        with self.assertRaises(ValueError):run.dispatch('SA',None,None,None,None)
        old=core.reconstruct
        with patch.object(frozen,'execute_reconstruction',side_effect=RuntimeError('mock only')):
            with self.assertRaises(RuntimeError):
                run.dispatch('ON',None,None,MethodBudget(300),frozen.Bindings(None,None,'REAL_CORE'))
        self.assertIs(core.reconstruct,old)
