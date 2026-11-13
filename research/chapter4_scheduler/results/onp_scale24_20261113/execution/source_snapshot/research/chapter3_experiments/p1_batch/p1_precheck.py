"""Pure P1 adapter/lifecycle checks plus inherited contracts, with physical guards."""
from contextlib import ExitStack,redirect_stdout,redirect_stderr
import io
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest.mock import patch
import p1_controller as r


def run(out):
    out=Path(out).resolve();out.relative_to(r.REPO);out.mkdir(parents=True,exist_ok=False)
    before=r.sources();log=io.StringIO();error=None;result=None
    prior_files=[r.ROOT/'results/p0_resume01'/name for name in ('archive_inventory.json','ledger.json','process_terminal.json','analysis01/facts.json')]
    prior_before={str(p.relative_to(r.REPO)):r.sha(p) for p in prior_files}
    guards={k:0 for k in ('whole','linked','heuristic','matlab','milp','linprog','model','heat','candidate_heat','scene_heat','subprocess')}
    def forbidden(key):
        def fail(*a,**kw):guards[key]+=1;raise AssertionError('Forbidden P1 precheck '+key)
        return fail
    try:
        import formal_milp,linked_method,heuristic_runner,matlab_bridge,milp,thermal,scene_adapter,scipy.optimize
        with ExitStack() as stack:
            stack.enter_context(patch('platform.platform',return_value='TEST_ONLY_ENV_METADATA'))
            original=tempfile.TemporaryDirectory
            fixture=r.REPO/'.runtime/k158';fixture.mkdir(exist_ok=True)
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
                    'test_p1','test_resume','test_p0','test_four_method_comparison','test_four_whole_status',
                    'test_execution_status','test_completion_metrics'))
                result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    except BaseException:error=traceback.format_exc();log.write(error)
    after=r.sources();prior_after={str(p.relative_to(r.REPO)):r.sha(p) for p in prior_files}
    g={'protocol':r.PROTOCOL,'passed':bool(result and result.wasSuccessful() and not result.skipped and error is None
        and before==after and prior_before==prior_after and not any(guards.values())),
       'tests_run':result.testsRun if result else 0,'errors':len(result.errors) if result else 1,
       'failures':len(result.failures) if result else 0,'skipped':len(result.skipped) if result else 0,
       'error':error,'source_sha256':after,'source_unchanged':before==after,'blocked_calls':guards,
       'P0_critical_unchanged':prior_before==prior_after,'P0_critical_sha256':prior_after,
       'research_calls':0,'native_calls':0,'thermal_evaluations':0,'physical_models':0}
    (out/'unittest.txt').write_text(log.getvalue(),encoding='utf-8');r.write_new(out/'checks.json',g)
    print({k:g[k] for k in ('passed','tests_run','errors','failures','skipped','source_unchanged','blocked_calls','error')})
    return g['passed']

if __name__=='__main__':
    import sys
    raise SystemExit(0 if run(sys.argv[1]) else 1)
