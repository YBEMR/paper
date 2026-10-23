"""K156 continuation and file-lock fixtures plus unchanged K154 regressions."""
from contextlib import ExitStack,redirect_stdout,redirect_stderr
import io
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch
import resume as r


def run(out):
    out=Path(out).resolve();out.relative_to(r.REPO);out.mkdir(parents=True,exist_ok=False)
    before=r.sources();old=r.prior_inventory();log=io.StringIO();error=None;result=None
    guards={key:0 for key in ('whole','linked','heuristic','matlab','milp','linprog','model','heat','candidate_heat','scene_heat','subprocess')}
    def forbidden(key):
        def fail(*a,**kw):guards[key]+=1;raise AssertionError('Forbidden continuation precheck '+key)
        return fail
    try:
        import formal_milp,linked_method,heuristic_runner,matlab_bridge,milp,thermal,scene_adapter,scipy.optimize
        with ExitStack() as stack:
            stack.enter_context(patch('platform.platform',return_value='TEST_ONLY_ENV_METADATA'))
            original=tempfile.TemporaryDirectory
            fixture=r.REPO/'.runtime/k156';fixture.mkdir(exist_ok=True)
            def temp(*a,**kw):kw.setdefault('dir',fixture);return original(*a,**kw)
            stack.enter_context(patch('tempfile.TemporaryDirectory',side_effect=temp))
            for obj,name,key in ((formal_milp,'execute_formal_milp','whole'),
                (linked_method,'execute_linked_fixed_unit_opp_start','linked'),
                (heuristic_runner,'execute_heuristic','heuristic'),(matlab_bridge.MatlabSession,'__init__','matlab'),
                (scipy.optimize,'milp','milp'),(scipy.optimize,'linprog','linprog'),(milp,'build_model','model'),
                (thermal,'evaluate_candidate','candidate_heat'),(thermal,'evaluate_piecewise','heat'),
                (scene_adapter,'evaluate_piecewise','scene_heat')):
                stack.enter_context(patch.object(obj,name,side_effect=forbidden(key)))
            stack.enter_context(patch('subprocess.Popen',side_effect=forbidden('subprocess')))
            with redirect_stdout(log),redirect_stderr(log):
                suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in (
                    'test_resume','test_p0','test_four_method_comparison','test_four_whole_status',
                    'test_execution_status','test_completion_metrics'))
                result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    except BaseException:error=traceback.format_exc();log.write(error)
    after=r.sources();old_after=r.prior_inventory()
    g={'protocol':r.PROTOCOL,'passed':bool(result and result.wasSuccessful() and not result.skipped
        and error is None and before==after and old==old_after and not any(guards.values())),
        'tests_run':result.testsRun if result else 0,'errors':len(result.errors) if result else 1,
        'failures':len(result.failures) if result else 0,'skipped':len(result.skipped) if result else 0,
        'error':error,'source_sha256':after,'source_unchanged':before==after,
        'prior_artifacts_unchanged':old==old_after,'prior_artifact_count':len(old),
        'blocked_calls':guards,'research_calls':0,'native_calls':0,'thermal_evaluations':0,'physical_models':0}
    r.write_new(out/'checks.json',g);(out/'unittest.txt').write_text(log.getvalue(),encoding='utf-8')
    print({k:g[k] for k in ('passed','tests_run','errors','failures','error')})
    return g['passed']


if __name__=='__main__':
    import sys
    raise SystemExit(0 if run(sys.argv[1]) else 1)
