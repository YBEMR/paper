"""Run pure P0 tests with optimization, subprocess and heat entries blocked."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch

import run_p0 as p


def run(out):
    out=Path(out).resolve();out.relative_to(p.REPO)
    out.mkdir(parents=True,exist_ok=False)
    before=p.sources();log=io.StringIO();error=None;result=None
    guards={key:0 for key in ('whole_entry','linked_entry','heuristic_entry','matlab',
        'milp','linprog','subprocess','model','scene_heat','heat','candidate_heat')}
    def blocked(key):
        def fail(*args,**kwargs):
            guards[key]+=1
            raise AssertionError('Forbidden P0 precheck operation: '+key)
        return fail
    try:
        import formal_milp,linked_method,heuristic_runner,matlab_bridge,milp,scene_adapter,thermal
        import scipy.optimize
        with ExitStack() as stack:
            # Windows platform.platform() can spawn cmd merely to discover the
            # OS release. Mock this metadata lookup; retain the no-subprocess gate.
            stack.enter_context(patch('platform.platform',return_value='TEST_ONLY_OS_METADATA'))
            for obj,name,label in (
                (formal_milp,'execute_formal_milp','whole_entry'),
                (linked_method,'execute_linked_fixed_unit_opp_start','linked_entry'),
                (heuristic_runner,'execute_heuristic','heuristic_entry'),
                (matlab_bridge.MatlabSession,'__init__','matlab'),
                (scipy.optimize,'milp','milp'),(scipy.optimize,'linprog','linprog'),
                (milp,'build_model','model'),(scene_adapter,'evaluate_piecewise','scene_heat'),
                (thermal,'evaluate_piecewise','heat'),(thermal,'evaluate_candidate','candidate_heat')):
                stack.enter_context(patch.object(obj,name,side_effect=blocked(label)))
            stack.enter_context(patch('subprocess.Popen',side_effect=blocked('subprocess')))
            fixture=p.REPO/'.runtime/k154_fixtures';fixture.mkdir(parents=True,exist_ok=True)
            original=tempfile.TemporaryDirectory
            def temp(*args,**kw):
                kw.setdefault('dir',fixture)
                return original(*args,**kw)
            stack.enter_context(patch('tempfile.TemporaryDirectory',side_effect=temp))
            with redirect_stdout(log),redirect_stderr(log):
                suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in (
                    'test_p0','test_four_method_comparison','test_four_whole_status',
                    'test_execution_status','test_completion_metrics'))
                result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    except BaseException:
        error=traceback.format_exc();log.write(error)
    after=p.sources()
    value={'protocol':p.PROTOCOL,'passed':bool(result and result.wasSuccessful() and not result.skipped
        and before==after and not any(guards.values()) and error is None),
        'tests_run':result.testsRun if result else 0,'errors':len(result.errors) if result else 1,
        'failures':len(result.failures) if result else 0,'skipped':len(result.skipped) if result else 0,
        'source_sha256':after,'source_unchanged':before==after,'blocked_calls':guards,
        'error':error,'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0,
        'scope':'fresh rational input expansion, mocked method dispatch and saved-record inspection only'}
    p.save(out/'checks.json',value)
    (out/'unittest.txt').write_text(log.getvalue(),encoding='utf-8')
    print({k:value[k] for k in ('passed','tests_run','errors','failures','error')})
    return value['passed']
