"""P2 initial78 original-H-only input and receipt adapter; unchanged scientific methods."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[1]
sys.path[:0]=[str(ROOT/'p0_batch'),str(ROOT)]
import run_p0 as p0
from run_four_method_comparison import read,sha,canonical
PROBLEMS=tuple('initial_78__R'+str(i) for i in range(1,6))
NORMAL=p0.NORMAL
SECONDS=300
METHODS=p0.METHODS

def jobs(problem_id):
    if problem_id not in PROBLEMS:raise ValueError('P2 permits only initial_78 R1..R5')
    blocks=[[deepcopy(j)] for j in METHODS]+[[{'id':'sa'+str(seed),'method':'sa','seed':seed} for seed in range(101,106)]]
    k=PROBLEMS.index(problem_id)%4
    return [j for block in blocks[k:]+blocks[:k] for j in block]

def slots():
    return [dict(job,problem_id=pid,slot_id=pid+'__'+job['id'],seconds=300,ordinal=i*8+n+1)
            for i,pid in enumerate(PROBLEMS) for n,job in enumerate(jobs(pid))]

def fresh_input(problem_id,budget=None):
    if problem_id not in PROBLEMS:raise ValueError('P2 rejects old and undeclared condition IDs')
    from inputs import build_instance,load_config
    from control_policy import with_auto_low_idle,resolve_idle_policy
    from run_neighborhood_diagnostic import opened_stages
    from run_four_method_comparison import masks
    raw=load_config();instance=build_instance(raw,problem_id,budget=budget)
    config,instance=with_auto_low_idle(raw),with_auto_low_idle(instance)
    if (instance['id']!=problem_id or instance['response_variant']!='H'
        or F(instance['window_ms'])!=400 or F(instance['start_grid_ms'])!=5
        or resolve_idle_policy(instance)!='auto_low_immediate_v1'
        or any(any(F(t)!=78 for t in s['entry']['temperature_degC'])
               or any(F(t)!=80 for t in s['maximum_temperature_degC']) for s in instance['scenarios'])):
        raise ValueError('P2 response/time/thermal/control contract changed')
    opened_stages(instance);masks(instance,4)
    return raw,config,instance

def input_declaration(problem_id):
    from run_four_method_comparison import scene_spec,masks
    from run_neighborhood_diagnostic import opened_stages
    raw,config,instance=fresh_input(problem_id)
    ids=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(canonical,(raw,config,instance))))
    return {'problem_id':problem_id,**ids,'input_identities':ids,'scene_spec':scene_spec(instance),
        'first_opened_by_scene':opened_stages(instance),
        'linked_opened_by_job':{'anchor_linked4':masks(instance,4)}},(raw,config,instance)

def result_records(job,result,declaration,folder,**kw):
    if job not in jobs(declaration['problem_id']):
        raise ValueError('Unbound method identity')
    if job['method']=='milp':
        from audit_whole import result_records as audit
        return audit(result,declaration,folder,**kw)
    if job['method']=='linked_fixed_unit_opp_start':
        import audit_cutoff as adapter
        from execution_status import classify_execution
        record=adapter.correct_records(job,result,declaration,folder,**kw)
        if record.get('cutoff_audit',{}).get('applied'):
            _,python,_,_=adapter._last_mapping(result,folder)
            cancel=Path(folder)/'matlab'/f"request_{python['request_number']:06d}.cancel"
            valid=cancel.is_file() and cancel.read_text(encoding='ascii').strip()=='budget'
            record['cutoff_audit']['cancel_file_verified']=valid
            if not valid:
                record['context']['hard_errors'].append('MISSING_MATCHING_ROOT_CANCEL_FILE')
                record['execution']=classify_execution(result,record['context'])
        return record
    from audit_heuristic import result_records as audit
    return audit(result,declaration,**kw)
