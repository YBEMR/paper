"""K129: one frozen old-N1/fixed-unit-all-OPP-start quality pair.

Independent fresh invocations, 300 s each, identical scene slices/settings.
Claims are irreversible: consumed research invocations cannot be rerun here.
"""
import argparse
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
PROTOCOL='K129-old-N1-vs-fixed-unit-all-opp-start-v1'
SHARED={'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'}
SECONDS=300

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def save(p,value):
    p=Path(p); pending=p.with_suffix(p.suffix+'.pending')
    with pending.open('x',encoding='utf-8') as s:
        json.dump(value,s,ensure_ascii=False,indent=2,allow_nan=False,default=str); s.write('\n')
    pending.replace(p)
def local(p):
    p=Path(p).resolve(); p.relative_to(REPO); return p
def sources():
    paths=list(HERE.glob('*.py'))+[HERE/'config_v01.json',HERE/'solve_model.m',HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(paths)}
def jobs():
    return [{'id':'old_n1','method':'n1'},{'id':'all_opp_start','method':'fixed_unit_opp_start'}]
def fresh_input(budget=None):
    from inputs import load_config,build_instance
    from control_policy import with_auto_low_idle
    raw=load_config()
    return with_auto_low_idle(raw),with_auto_low_idle(build_instance(raw,'base__R1',budget=budget))

def prepare(out,checks):
    from scene_adapter import canonical_hash
    from run_neighborhood_diagnostic import opened_stages
    out=local(out); gate=read(checks); src=sources()
    if (gate.get('passed') is not True or gate.get('source_sha256')!=src
        or any(v.get('errors',0) or v.get('failures',0) for v in gate['modules'].values())):
        raise ValueError('Passing matching targeted precheck required')
    config,instance=fresh_input()
    if instance['window_ms']!='400' or instance['start_grid_ms']!='5':
        raise ValueError('Original input domain changed')
    out.mkdir(parents=True,exist_ok=False); (out/'claims').mkdir()
    save(out/'input_config.json',config); save(out/'input_instance.json',instance)
    for name,digest in src.items():
        target=out/'source_snapshot'/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,target)
        if sha(target)!=digest: raise ValueError('Source changed while freezing')
    shutil.copyfile(checks,out/'checks.json')
    declaration={'protocol':PROTOCOL,'jobs':jobs(),'method_call_limit':2,'per_method_budget_s':SECONDS,
        'shared_deployment':SHARED,'old_opened_by_scene':opened_stages(instance),
        'new_opened_by_scene':{s['id']:[i['id'] for i in s['stage_instances']] for s in instance['scenarios']},
        'source_sha256':src,'input_sha256':canonical_hash(instance),'config_sha256':canonical_hash(config),
        'checks_sha256':sha(out/'checks.json'),'scene_slice_s':60,'CutMaxIterations':10,
        'builder_options':{'fix_late_options':True,'aggregate_opp_locks':True,
            'relax_auxiliary_integrality':True,'strengthen_energy_lower_bounds':True,
            'prefilter_deadlines':True,'cumulative_precedence':False},
        'changed_factor':'all Stage OPP/start opened, including shared Stage instances; all seed units remain fixed',
        'initialisation':'same fresh at-most-three-template constructor; no historical candidate or cache',
        'primary_success':'new complete SAFE energy upper strictly below old complete SAFE energy lower',
        'secondary_reference':'K127 HEFT saved U only after execution; no contemporary HEFT call or initialization',
        'signed_HEFT_gap':'(U_method-U_HEFT)/U_HEFT; do not truncate negative values',
        'retry_allowed':False,'extend_budget_allowed':False,'new_temperature_conditions':0,
        'scenario_entry':'original independent 50 C entrances; maximum 80 C; no scenario switching',
        'authorization':'user supports fixed-unit revision and same-budget safe-energy criterion, then says continue',
        'declared_at_utc':now()}
    save(out/'declaration.json',declaration)
    save(out/'ledger.json',{'protocol':PROTOCOL,'state':'DECLARED','consumed':0,
        'method_budget_s_reserved':0,'calls':[],'declared_at_utc':now()})
    save(out/'environment.json',{'python':sys.version,'platform':platform.platform()})
    print(json.dumps({'prepared':True,'source_files':len(src),'calls':2,'per_method_s':SECONDS}),flush=True)

def admission(out):
    from scene_adapter import canonical_hash
    d=read(out/'declaration.json')
    if (d['protocol']!=PROTOCOL or d['jobs']!=jobs() or d['per_method_budget_s']!=SECONDS
        or d['method_call_limit']!=2 or d['shared_deployment']!=SHARED
        or d['scene_slice_s']!=60 or d['CutMaxIterations']!=10
        or d['builder_options']!={'fix_late_options':True,'aggregate_opp_locks':True,
            'relax_auxiliary_integrality':True,'strengthen_energy_lower_bounds':True,
            'prefilter_deadlines':True,'cumulative_precedence':False}
        or d['source_sha256']!=sources() or sha(out/'checks.json')!=d['checks_sha256']):
        raise ValueError('Frozen source or rules changed')
    for name,h in d['source_sha256'].items():
        if sha(out/'source_snapshot'/name)!=h: raise ValueError('Snapshot mismatch '+name)
    if (canonical_hash(read(out/'input_instance.json'))!=d['input_sha256']
        or canonical_hash(read(out/'input_config.json'))!=d['config_sha256']):
        raise ValueError('Frozen input changed')
    return d

def execute(job,out,d):
    from scene_adapter import canonical_hash
    from matlab_bridge import MatlabSession
    def loader(budget):
        config,instance=fresh_input(budget)
        if canonical_hash(instance)!=d['input_sha256'] or canonical_hash(config)!=d['config_sha256']:
            raise ValueError('Billed fresh input differs')
        return config,instance
    options=dict(shared_deployment=dict(SHARED),seconds=SECONDS,scene_slice_s=60,
        builder_options={'cumulative_precedence':False},
        session_factory=partial(MatlabSession,cut_max_iterations=10))
    if job['method']=='n1':
        from neighborhood_method import execute_n1_neighborhood
        return execute_n1_neighborhood(loader,out/job['id'],
            opened_by_scene=d['old_opened_by_scene'],**options)
    from fixed_unit_method import execute_fixed_unit_opp_start
    return execute_fixed_unit_opp_start(loader,out/job['id'],**options)

def run(out):
    from run_neighborhood_diagnostic import technical_issues
    from matlab_bridge import cleanup_is_complete
    out=local(out); d=admission(out); ledger=read(out/'ledger.json')
    for job in jobs():
        previous=next((c for c in ledger['calls'] if c['id']==job['id']),None)
        if previous:
            if previous['state']=='COMPLETED': continue
            raise FileExistsError('Consumed unsettled/failed call cannot restart: '+job['id'])
        if ledger['consumed']>=2: raise ValueError('Two-call cap consumed')
        admission(out)
        claim=out/'claims'/(job['id']+'.json')
        with claim.open('x',encoding='utf-8') as s:
            json.dump({**job,'seconds':SECONDS,'claimed_at_utc':now(),'no_retry':True},s,indent=2)
        row={**job,'state':'RUNNING','started_at_utc':now(),'seconds':SECONDS}
        ledger['calls'].append(row); ledger['consumed']+=1; ledger['method_budget_s_reserved']+=SECONDS
        ledger['state']='RUNNING'; save(out/'ledger.json',ledger)
        print('START '+job['id']+' independent 300 s; no retry',flush=True)
        started=time.monotonic(); result=None; error=None
        try: result=execute(job,out,d)
        except BaseException: error=traceback.format_exc()
        elapsed=time.monotonic()-started
        try: admission(out); unchanged=True
        except Exception as exc: unchanged=False; error=(error or '')+'\n'+repr(exc)
        issues=technical_issues(result)
        if isinstance(result,dict) and result.get('condition') is not None:
            actual=result['condition']['opened_by_scene']
            expected=d['old_opened_by_scene'] if job['method']=='n1' else d['new_opened_by_scene']
            if {k:sorted(v) for k,v in actual.items()}!={k:sorted(v) for k,v in expected.items()}:
                issues.append({'scope':'search_domain','reason':'OPENED_DOMAIN_MISMATCH'})
        closed=out/job['id']/'matlab/closed.json'
        cleanup=read(closed) if closed.is_file() else None
        if (isinstance(result,dict) and result.get('matlab_worker_ready') and not cleanup):
            issues.append({'scope':'cleanup','reason':'MISSING_CLOSED_RECEIPT'})
        if cleanup and not cleanup_is_complete(cleanup):
            issues.append({'scope':'cleanup','reason':'WORKER_CLEANUP_ANOMALY'})
        failed=bool(error or issues or not unchanged)
        row.update(state='TECHNICAL_BLOCK' if failed else 'COMPLETED',error=error,
            technical_issues=issues,source_unchanged=unchanged,cleanup=cleanup,
            wrapper_wall_s=elapsed,completed_at_utc=now(),method_state=(result or {}).get('state'),
            reason=(result or {}).get('reason'),safe_upper_bound_J=(result or {}).get('safe_upper_bound_J'),
            timing=(result or {}).get('timing'))
        save(out/'claims'/(job['id']+'_result.json'),row); save(out/'ledger.json',ledger)
        print(json.dumps({k:row.get(k) for k in ['id','state','method_state','reason','safe_upper_bound_J','wrapper_wall_s']}),flush=True)
        if failed:
            ledger['state']='BLOCKED'; save(out/'ledger.json',ledger); return False
    ledger['state']='COMPLETED'; save(out/'ledger.json',ledger); return True

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); a=p.add_mutually_exclusive_group(required=True)
    a.add_argument('--prepare',action='store_true'); a.add_argument('--run',action='store_true')
    p.add_argument('--out',type=Path,required=True); p.add_argument('--checks',type=Path); args=p.parse_args()
    if args.prepare:
        if args.checks is None: p.error('--checks required')
        prepare(args.out,args.checks)
    else: raise SystemExit(0 if run(args.out) else 1)
