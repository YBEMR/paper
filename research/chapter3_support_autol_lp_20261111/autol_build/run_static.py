"""Frozen auto-L full R1 static construction only: no candidate or solver."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(p,d):
    with p.open('x',encoding='utf-8') as f:
        json.dump(d,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
def verify(plan):
    for name,h in plan['frozen_source_sha256'].items():
        if sha(HERE/'frozen'/name)!=h: raise ValueError('FROZEN_SOURCE_DRIFT '+name)
    for name,h in plan['frozen_input_sha256'].items():
        if sha(HERE/name)!=h: raise ValueError('FROZEN_INPUT_DRIFT '+name)
    if sha(Path(__file__))!=plan['runner_sha256']:raise ValueError('RUNNER_DRIFT')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=['off','on'],required=True);parser.add_argument('--plan-sha256',required=True)
    a=parser.parse_args();p=HERE/'plan.json'
    if sha(p)!=a.plan_sha256:raise ValueError('PLAN_DRIFT')
    plan=read(p);verify(plan)
    out=HERE/'execution'/a.variant;out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(HERE/'frozen/research/chapter3_experiments'))
    import numpy as np
    import scipy
    import scipy.optimize as opt
    import thermal
    import milp
    from build_observer import BuildObserver
    from timing import MethodBudget
    banned=[]
    def forbidden(*args,**kwargs):
        banned.append('FORBIDDEN_SOLVER_OR_EVALUATOR_ATTEMPT')
        raise RuntimeError(banned[-1])
    # All static construction dependencies are loaded before installing guards.
    opt.linprog=forbidden;opt.milp=forbidden
    thermal.evaluate_candidate=forbidden;milp.evaluate_candidate=forbidden
    import subprocess,os
    subprocess.Popen=forbidden;subprocess.run=forbidden;os.system=forbidden
    budget=MethodBudget(plan['seconds_each']);started=datetime.now(timezone.utc).isoformat()
    observer=BuildObserver(budget,out/'build_progress.jsonl')
    result={};model=matrix=None;failure=None;stage='input_read';t=time.monotonic()
    save(out/'started.json',dict(started_utc=started,argv=sys.argv,cwd=str(REPO),plan_sha256=a.plan_sha256,scope='STATIC_ONLY_NO_INITIALIZATION_NO_THERMAL_EVALUATION_NO_SOLVER'))
    try:
        with budget.phase(stage):
            instance=read(HERE/'input_instance.json');config=read(HERE/'input_config.json')
        assert {s['id']:len(s['stage_instances']) for s in instance['scenarios']}=={'AB_offset_0ms':6,'AC_offset_0ms':6}
        assert instance['execution_rules']['idle_policy']=='auto_low_immediate_v1'
        stage='model_construction'
        with budget.phase(stage):
            model=milp.build_model(instance,config,budget=budget,progress=observer,propagate_support=a.variant=='on',**plan['baseline_flags'])
            observer.finish('MODEL_CONSTRUCTED')
        budget.check();result['model_completed_at_s']=budget.elapsed
        stage='matrix_export'
        with budget.phase(stage):matrix=model.as_solver_dict()
        budget.check();result['matrix_completed_at_s']=budget.elapsed
        stage='complete'
    except BaseException as e:
        failure=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc())
    stopped=budget.elapsed;archive_start=time.monotonic()
    if observer.finished_at is None:observer.finish('CONSTRUCTION_INTERRUPTED')
    result['construction']=observer.snapshot()
    retained=model if model is not None else observer.model
    if retained is not None:
        result['model_summary']=retained.summary()
        result['joint_state_blocks']={sid:sum(map(len,s['states'])) for sid,s in retained.scenes.items()}
        result['event_intervals']={sid:len(s['events'])-1 for sid,s in retained.scenes.items()}
        result['row_family_counts']=dict(Counter(r['tag'].split('/')[0] for r in retained.rows))
        result['row_nonzeros_counter']=retained.row_nonzeros
        save(out/'options.json',retained.options)
        save(out/'variable_names.json',retained.names)
        if 'option_support' in getattr(retained,'preprocessing',{}):save(out/'deletion_proof.json',retained.preprocessing['option_support'])
    if matrix is not None:
        result['matrix_shape']=list(matrix['A'].shape);result['matrix_nnz']=int(matrix['A'].nnz)
        with (out/'exported_model.npz').open('xb') as f:
            np.savez_compressed(f,A_data=matrix['A'].data,A_indices=matrix['A'].indices,A_indptr=matrix['A'].indptr,A_shape=matrix['A'].shape,b=matrix['b'],c=matrix['c'],lb=matrix['lb'],ub=matrix['ub'],intcon=matrix['intcon'])
    verify(plan)
    result.update(variant=a.variant,started_utc=started,ended_utc=datetime.now(timezone.utc).isoformat(),method_static_elapsed_s=stopped,archive_wall_s=time.monotonic()-archive_start,failure=failure,stop_stage=stage,model_complete=model is not None,matrix_complete=matrix is not None,budget=budget.summary(stopped),new_solver_calls=0,new_initialization_calls=0,new_candidate_thermal_evaluations=0,forbidden_call_attempts=banned,environment=dict(python=sys.version,platform=platform.platform(),numpy=np.__version__,scipy=scipy.__version__),source_import_path=str(HERE/'frozen/research/chapter3_experiments'))
    save(out/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ['variant','model_complete','matrix_complete','matrix_shape','matrix_nnz','joint_state_blocks','event_intervals','method_static_elapsed_s','failure']},default=str),flush=True)
    if failure:raise SystemExit(1)

if __name__=='__main__':main()
