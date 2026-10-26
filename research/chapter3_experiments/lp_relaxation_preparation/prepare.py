"""K190 zero-call preparation. Deliberately has no execute/worker action."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np
import scipy
import scipy.optimize

import lp_checks as lp
import test_lp_checks

HERE = Path(__file__).resolve().parent
REPO = lp.REPO
OUT = REPO/'research/chapter3_experiments/results/k190_lp_preparation01'
OLD = REPO/'research/chapter3_experiments/results/whole_long_budget01'
FIXED = REPO/'research/chapter3_experiments/results/fixed_integer_native03'
MATLAB = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(name,value):
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')


def main():
    started=time.monotonic()
    if OUT.exists(): raise FileExistsError('Do not overwrite preparation evidence')
    OUT.mkdir(parents=True)
    (OUT/'.gitattributes').write_bytes(b'* -text\n')
    guards={k:0 for k in ('Popen','scipy.optimize.linprog','scipy.optimize.milp')}
    def forbid(name):
        def fail(*args,**kwargs):
            guards[name]+=1
            raise AssertionError('Forbidden scientific/native entry: '+name)
        return fail
    with ExitStack() as stack:
        stack.enter_context(patch('subprocess.Popen',side_effect=forbid('Popen')))
        for name in ('linprog','milp'):
            stack.enter_context(patch.object(scipy.optimize,name,side_effect=forbid('scipy.optimize.'+name)))
        log=io.StringIO()
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(test_lp_checks))
        with (OUT/'pure_tests.txt').open('x',encoding='utf-8',newline='\n') as f:f.write(log.getvalue())
        if not result.wasSuccessful(): raise AssertionError('Pure fixture failure')
        original,source=lp.numeric.load_original_mat(OLD/'method/matlab/request_000001.mat')
        expected=read(FIXED/'declaration.json')['source_files']
        source_key=(OLD/'method/matlab/request_000001.mat').relative_to(REPO).as_posix()
        assert source['sha256']==expected[source_key]['sha256']
        original_sources={name:dict(sha256=sha(REPO/name),expected=info['sha256']) for name,info in expected.items()}
        assert all(info['sha256']==info['expected'] for info in original_sources.values())
        payload=lp.make_relaxation(original)
        identity=lp.assert_identity(original,payload)
        x0=lp.check_vector(original,payload,original['x0'],require_objective=False)
        prior=read(FIXED/'method_return.json')
        assert prior['state']=='FIXED_CONFIGURATION_NUMERICALLY_ADMITTED'
        fixed_vector=lp.check_vector(original,payload,prior['result']['x'],prior['result']['fval'])
        assert x0['accepted'] and fixed_vector['accepted']
        fixed_payload,_=lp.numeric.load_original_mat(FIXED/'matlab/request_000001.mat')
        try:lp.assert_identity(original,{key:fixed_payload[key] for key in lp.LP_KEYS})
        except ValueError:reject_fixed=True
        else:reject_fixed=False
        assert reject_fixed
        rows,columns=original['A'].shape
        max_iterations=max(30000,10*(rows+original['Aeq'].shape[0]+columns))
        options=dict(Algorithm='dual-simplex',Preprocess='none',ConstraintTolerance=1e-9,
            OptimalityTolerance=1e-7,MaxIterations=max_iterations,Display='off',
            MaxTime='positive remainder of the one 300-second root at native entry')
        expected_env=read(OLD/'pure_checks.json')['environment']
        environment=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__)
        assert all(environment[key]==expected_env[key] for key in environment)
        local_specs=[
            ('toolbox/optim/optim/linprog.m',{'92-105':'x0 is explicitly rejected','315-333':'dual-simplex receives tolerances, preprocessing and time'},
             ['X0NotAccepted','options.Preprocess','options.MaxTime']),
            ('toolbox/optim/+optim/+options/Linprog.m',{'272-282':'LinprogDualSimplex algorithm class','550-558':'option metadata and hidden Preprocess enum'},
             ['LinprogDualSimplex',"{'basic','none'}",'propInfo.MaxTime','propInfo.MaxIterations']),
            ('toolbox/optim/+optim/+options/Intlinprog.m',{'630-638':'separate IntlinprogBranchAndCut class'},['IntlinprogBranchAndCut']),
            ('toolbox/matlab/optimfun/+optim/+options/+meta/Factory.m',{'67-68':'integer iteration range','157-166':'tolerance types','174-185':'iteration/time types'},
             ['maxTimeType','maxIterType','constraintToleranceType','optimalityToleranceType']),
            ('toolbox/matlab/optimfun/+optim/+options/+meta/IntegerType.m',{'62-65':'nonnegative integer scalar validation'},['floor']),
            ('toolbox/matlab/optimfun/+optim/+options/+meta/ToleranceType.m',{'61-62':'tolerance scalar validation'},['isreal']),
            ('toolbox/matlab/optimfun/+optim/+options/+meta/EnumType.m',{'49-58':'enum value validation'},['strcmpi'])]
        local_sources=[]
        for name,anchors,tokens in local_specs:
            path=MATLAB/name; content=path.read_text(encoding='utf-8-sig')
            assert all(token in content for token in tokens),name
            local_sources.append(dict(path=path.as_posix(),sha256=sha(path),anchors=anchors,checked_tokens=tokens))
        backend=MATLAB/'toolbox/optim/+optim/+algorithm/LinprogDualSimplex.p'
        local_sources.append(dict(path=backend.as_posix(),sha256=sha(backend),readable=False,
            scope='hash only; no claim to inspect protected implementation'))
        old_options=read(OLD/'method/matlab/request_000001.response.json')['options']
        assert old_options['ConstraintTolerance']==options['ConstraintTolerance']
        assert old_options['LPOptimalityTolerance']==options['OptimalityTolerance']
        assert old_options['LPPreprocess']==options['Preprocess']
        assert old_options['RootLPAlgorithm']=='dual-simplex'
        saved=dict(utc=datetime.now(timezone.utc).isoformat(),passed=True,test_count=result.testsRun,
            original_payload=source,original_sources=original_sources,
            seven_argument_identity=identity,original_x0_LP_numeric_witness=x0,
            K189_vector_LP_numeric_witness=fixed_vector,K189_fixed_bounds_explicitly_rejected=reject_fixed,
            integer_conditions_removed=source['integer_columns'],
            inequalities=rows,equalities=original['Aeq'].shape[0],columns=columns,nnz=original['A'].nnz,
            original_integer_columns_bounds_all_zero_one=bool(np.all(original['lb'][original['intcon']]==0)&np.all(original['ub'][original['intcon']]==1)),
            finite_lower_bounds=int(np.count_nonzero(np.isfinite(original['lb']))),
            finite_upper_bounds=int(np.count_nonzero(np.isfinite(original['ub']))),
            options=options,environment=environment,
            option_validation='static installed-source/validator audit only; native dynamic readback not run',
            local_interface_sources=local_sources,guard_calls=guards,
            original_files_still_match=all(sha(REPO/name)==info['sha256'] for name,info in expected.items()),
            native_starts=0,research_calls=0,thermal_integrations=0,new_safe_or_U=False,
            time_seconds=time.monotonic()-started)
        assert not any(guards.values())
        assert saved['original_files_still_match']
        save('precheck.json',saved)
        source_bindings={p.relative_to(REPO).as_posix():sha(p) for p in
            (FIXED/'method_return.json',FIXED/'transport_identity.json',FIXED/'independent_review.json',lp.FIXED_CORE)}
        proposal=dict(protocol='K190-original-array-independent-continuous-LP-v1',subject_commit='f80d1828113d35f8aa04c8799a65150ef1b3959b',
            authorized=False,execution_enabled=False,execution_entry_implemented=False,
            problem='base__R1 original K187 archived numerical payload',
            change='remove original 1681 integrality requirements only; retain every original bound',
            solver='MATLAB R2023b linprog, standalone dual-simplex; not intlinprog internal root LP',
            original_environment=expected_env,original_native_environment=read(OLD/'method/matlab/ready.json'),
            signature='[x,fval,exitflag,output,lambda]=linprog(c,A,b,Aeq,beq,lb,ub,options)',
            x0='reference only; not passed because the installed independent LP API rejects x0',
            options=options,source_files=original_sources,reference_bindings=source_bindings,
            local_interface_sources=local_sources,
            proposed_budget=dict(requests_max=1,method_seconds=300,calendar_seconds=480,
                thermal_post_calls=0,thermal_integrations=0,cleanup_seconds_max=40,worker_watchdog_seconds=420,
                root_origin='before scientific imports and archived payload read',
                includes=['hash/input checks','array copy and identity','MATLAB startup','native option construction/readback',
                    'transport','one linprog call','original row/bound and objective acceptance'],
                extra_wall_only_for_stop_archive=True,no_retry=True,no_auto_followup=True),
            required_before_run=['explicit user authorization of this proposal and budget',
                'one-shot standalone LP transport implementation and pure lifecycle tests',
                'immutable execution declaration/source snapshot and input bindings',
                'host/resource/process gate; verify R2023b version/path and read back every selected option before call'],
            required_outputs=['original and transported array identity','selected/actual options',
                'root and native timing','full raw x/fval/exitflag/output/lambda/warnings',
                'original row/bound residuals; original integer distance diagnostic only','owned process cleanup'],
            interpretation=dict(LP_is_relaxation='exact real-array feasible-domain containment; numerical statuses are not certificates',
                primal_value='a feasible primal objective alone is not an MILP lower bound',
                exit1='solver-reported LP optimum only after original-row/bound admission',
                exit_minus2='numerical status conflict/unresolved versus archived tolerance witnesses; no physical infeasibility conclusion',
                exit_minus3='unbounded status requires diagnosis; not a physical conclusion',
                timeout='unresolved; no admitted vector is not infeasibility',
                late='archive only, no in-budget numerical admission',
                new_SAFE=False,new_U=False,certified_lower_bound=False,free_MILP_repaired=False),
            pause_scopes=['3600-second whole MILP rerun','K168','deadline remaining 24','integer release','augmentation','small-domain solver comparison'])
        save('protocol_proposal.json',proposal)
        for p in sorted(HERE.iterdir()):
            if p.suffix in ('.py','.md'):
                dst=OUT/'source_snapshot'/p.name;dst.parent.mkdir(exist_ok=True);shutil.copyfile(p,dst)
        save('source_snapshot_hashes.json',{p.name:sha(p) for p in sorted(HERE.iterdir()) if p.suffix in ('.py','.md')})
        print(dict(passed=True,tests=result.testsRun,columns=columns,rows=rows,
            original_bounds=True,reference_witnesses=2,requests=0,thermal_integrations=0))


if __name__=='__main__':main()
