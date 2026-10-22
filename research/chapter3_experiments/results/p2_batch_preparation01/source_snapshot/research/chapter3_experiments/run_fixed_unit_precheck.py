"""K129 bounded small-domain checks; native optimizers are forbidden."""
import argparse
from contextlib import ExitStack,redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch
from uuid import uuid4

import scipy.optimize
import matlab_bridge
import milp

HERE=Path(__file__).resolve().parent; REPO=HERE.parents[1]
MODULES=('test_fixed_unit_neighborhood','test_fixed_unit_method','test_neighborhood_condition',
         'test_neighborhood_milp','test_neighborhood_adapter','test_neighborhood_method',
         'test_neighborhood_archive_failure','test_bridge_cleanup_archive',
         'test_bridge_softcap','test_bridge_cut_iterations')
REFERENCE='3859cbe55ffdbacc638727fa84af2a970082b0a2'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def sources():
    paths=list(HERE.glob('*.py'))+[HERE/'config_v01.json',HERE/'solve_model.m',HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}
def save(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',encoding='utf-8')

def default_identity(out):
    """Old default/old N1 arrays on a tiny structural fixture, no physics."""
    import numpy as np
    from copy import deepcopy
    from control_policy import with_auto_low_idle
    from inputs import load_config
    from thermal import Budget
    from test_neighborhood_milp import fixture,condition_for
    raw=subprocess.check_output(['git','show',REFERENCE+':research/chapter3_experiments/milp.py'],cwd=REPO)
    temp=REPO/'.runtime'/('fixed_unit_reference_'+uuid4().hex)
    temp.mkdir(parents=True); path=temp/'reference_milp.py'; path.write_bytes(raw)
    spec=importlib.util.spec_from_file_location('_k129_reference_milp',path)
    previous=importlib.util.module_from_spec(spec); sys.modules[spec.name]=previous; spec.loader.exec_module(previous)
    case,mapping,seed,opened=fixture('npu'); config=with_auto_low_idle(load_config())
    budget=Budget(seconds=120); condition=condition_for(case,mapping,seed,opened,budget)
    records=[]
    for name,c in [('default',None),('old_N1',condition)]:
        flags=dict(include_physics=False,fixed_shared_deployment=mapping,
            fixed_scene_id=case['scenarios'][0]['id'],neighborhood_condition=c,
            prefilter_deadlines=True,relax_auxiliary_integrality=True)
        old=previous.build_model(deepcopy(case),config,budget=budget,**flags)
        new=milp.build_model(deepcopy(case),config,budget=budget,**flags)
        left,right=old.as_solver_dict(),new.as_solver_dict(); digests={}
        for key in ['c','A','b','Aeq','beq','lb','ub','intcon']:
            a,b=left[key],right[key]
            if hasattr(a,'tocsc'):
                a,b=a.tocsc(),b.tocsc()
                assert a.shape==b.shape and (a!=b).nnz==0,(name,key)
                data=a.data.tobytes()+a.indices.tobytes()+a.indptr.tobytes()
            else:
                assert np.array_equal(a,b),(name,key)
                data=np.asarray(a).tobytes()
            digests[key]=hashlib.sha256(data).hexdigest()
        assert old.options==new.options and old.summary()==new.summary(),name
        assert old.rows==new.rows,name
        records.append({'scope':name,'arrays_equal':True,'options_summary_rows_equal':True,
                        'array_sha256':digests,'reference_commit':REFERENCE})
    save(out/'default_identity.json',records)
    return records

def run(out):
    out=out.resolve(); out.relative_to(REPO); out.mkdir(parents=True,exist_ok=False)
    before=sources()
    for name,h in before.items():
        target=out/'source_snapshot'/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    captured=io.StringIO(); results={}; error=None; identity=None; start=time.monotonic()
    root=REPO/'.runtime/fixed_unit_precheck'; root.mkdir(parents=True,exist_ok=True)
    class Folder:
        def __init__(self,*a,**kw):
            requested=kw.get('dir',a[2] if len(a)>2 else None)
            parent=Path(requested).resolve() if requested is not None else root
            parent.relative_to(REPO); parent.mkdir(parents=True,exist_ok=True)
            path=parent/('case_'+uuid4().hex); path.mkdir(); self.name=str(path)
        def __enter__(self): return self.name
        def __exit__(self,*a): return False
        def cleanup(self): pass
    def forbidden(*a,**kw): raise AssertionError('No native optimizer or MATLAB in this small-domain precheck')
    try:
        with ExitStack() as stack,redirect_stdout(captured),redirect_stderr(captured):
            stack.enter_context(patch.object(tempfile,'TemporaryDirectory',Folder))
            for owner,name in [(scipy.optimize,'milp'),(scipy.optimize,'linprog')]:
                stack.enter_context(patch.object(owner,name,side_effect=forbidden))
            for name in MODULES:
                # Cleanup/startup fault tests exercise the constructor with
                # fake Popen. For every other module, forbid construction.
                owner,attribute=((subprocess,'Popen') if name.startswith('test_bridge_')
                    else (matlab_bridge.MatlabSession,'__init__'))
                with patch.object(owner,attribute,side_effect=forbidden):
                    suite=unittest.defaultTestLoader.loadTestsFromName(name)
                    result=unittest.TextTestRunner(stream=captured,verbosity=2).run(suite)
                results[name]={'passed':result.wasSuccessful(),'count':result.testsRun,
                    'errors':len(result.errors),'failures':len(result.failures)}
            if all(r['passed'] for r in results.values()): identity=default_identity(out)
    except BaseException:
        error=traceback.format_exc(); captured.write(error)
    (out/'unittest.txt').write_bytes(captured.getvalue().encode('utf-8'))
    after=sources(); details={}
    for name in MODULES:
        module=sys.modules.get(name)
        details[name]=getattr(module,'RECORDS',getattr(module,'PHYSICAL_RECORDS',{}))
    save(out/'fixture_records.json',details)
    report={'protocol':'K129-fixed-unit-all-opp-start-targeted-precheck-v1',
        'passed':bool(results and all(r['passed'] for r in results.values()) and identity and before==after and error is None),
        'modules':results,'count':sum(r['count'] for r in results.values()),'source_sha256':after,
        'source_unchanged':before==after,'old_default_and_N1_identity':identity,
        'native_or_research_calls':0,'original_scale_models':0,'error':error,
        'elapsed_s':time.monotonic()-start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'environment':{'python':sys.version,'platform':platform.platform()},
        'scope':'small correctness only; echo/fake native transport is not optimization or energy improvement evidence'}
    save(out/'checks.json',report)
    print(json.dumps({k:report[k] for k in ['passed','count','error','elapsed_s']},ensure_ascii=False),flush=True)
    return report['passed']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    raise SystemExit(0 if run(p.parse_args().out) else 1)
