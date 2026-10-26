"""One-time K191 pure preflight; blocked native/optimization entry points."""
from contextlib import ExitStack
import io
import re
import sys
import unittest
from unittest.mock import patch

import run_once as run


def main():
    d=run.admission()
    if (run.OUT/'launch.claim.json').exists():raise RuntimeError('Preflight must precede execution')
    # Windows platform inventory can spawn `ver`; perform this read before
    # the stricter test guard. No native scientific tool is started here.
    environment=run.common.check_python_environment(d['original_environment'])
    guards={k:0 for k in ('Popen','milp','linprog')}
    def forbid(name):
        def fail(*args,**kwargs):guards[name]+=1;raise AssertionError('FORBIDDEN '+name)
        return fail
    with ExitStack() as stack:
        import scipy.optimize
        stack.enter_context(patch('subprocess.Popen',side_effect=forbid('Popen')))
        for name in ('milp','linprog'):
            stack.enter_context(patch.object(scipy.optimize,name,side_effect=forbid(name)))
        import test_run_once
        output=io.StringIO()
        tests=unittest.TextTestRunner(stream=output,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_run_once))
        with (run.OUT/'pure_tests.txt').open('x',encoding='utf-8',newline='\n') as f:f.write(output.getvalue())
        if not tests.wasSuccessful():raise AssertionError('Pure lifecycle tests failed')
        lp=run.bind_lp()
        original,source=lp.numeric.load_original_mat(run.OLD/'method/matlab/request_000001.mat')
        payload=lp.make_relaxation(original);identity=lp.assert_identity(original,payload)
        reference=lp.check_vector(original,payload,original['x0'],require_objective=False)
        if not reference['accepted']:raise ValueError('Original numerical witness drift')
        bridge=run.common.bind_bridge()
        assert run.common.REPO==run.REPO
        assert run.common.FROZEN==run.OLD/'source_snapshot/research/chapter3_experiments'
        assert run.sha(bridge.__file__)==d['original_sources'][
            'research/chapter3_experiments/results/whole_long_budget01/source_snapshot/research/chapter3_experiments/matlab_bridge.py']['sha256']
        script=(run.HERE/'solve_lp_once.m').read_text('utf-8-sig')
        assert len(re.findall(r'^\s*\[x,fval,exitflag,output,lambda\]=linprog\(',script,re.M))==1
        assert 'p.c,p.A,p.b,p.Aeq,p.beq,p.lb,p.ub,opts' in script
        assert 'intlinprog(' not in script and 'evaluate_piecewise(' not in script
        assert not any(guards.values())
        assert not any(name in sys.modules for name in ('thermal','milp','method_runner','initial_schedule'))
        run.admission()
        run.write_new(run.OUT/'pure_checks.json',dict(passed=True,utc=run.common.now(),test_count=tests.testsRun,
            declaration_sha256=run.sha(run.OUT/'declaration.json'),environment=environment,
            archived_source=source,LP_identity=identity,original_numeric_witness=reference,
            generic_controller_runtime_paths_verified=True,matlab_script_single_call_static_check=True,
            guards=guards,native_starts=0,research_calls=0,thermal_integrations=0,
            native_options_dynamic_readback='not run; must pass in the sole future MATLAB process'))
        print({'passed':True,'tests':tests.testsRun,'original_payload':True,'native_starts':0,'heat':0})


if __name__=='__main__':main()
