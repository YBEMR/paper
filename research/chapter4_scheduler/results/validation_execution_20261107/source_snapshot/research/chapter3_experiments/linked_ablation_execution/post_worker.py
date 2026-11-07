"""One independent original-candidate postcheck; CLI is dispatched only by K173 batch."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
if str(SCIENCE) not in sys.path:sys.path.insert(0,str(SCIENCE))
from linked_ablation_execution import registry
from linked_ablation_execution.audit import audit_slot, canonical, interval, read, sha

def post_identity(folder,slot,declaration):
    result=read(folder/'result.json');instance=read(folder/'input_instance.json');config=read(folder/'input_config.json')
    return {'slot_id':slot['slot_id'],'raw_result_sha256':sha(folder/'wrapper_raw_result.json'),
        'input_sha256':canonical(instance),'candidate_sha256':canonical(result['safe_candidate']),
        'accuracy_sha256':canonical(config['accuracy_targets']),'declaration_source_sha256':declaration['source_sha256']}

def run_post(declaration_path,slot_id,out):
    started=time.monotonic();out=Path(out).resolve();declaration_path=Path(declaration_path).resolve()
    declaration=registry.load_declaration(declaration_path);slot=registry.slot_spec(declaration,slot_id)
    if out!=(declaration_path.parent/'calls'/slot_id).resolve():raise ValueError('Unexpected post folder')
    if slot['post_seconds_max']!=60 or declaration['budgets']['post_s']!=60:raise ValueError('Post budget drift')
    if any((out/name).exists() for name in ('postcheck.claim.json','postcheck.json','post_return.json')):
        raise FileExistsError('Post was already claimed; no retry')
    audit=read(out/'audit.json');current=audit_slot(out,slot,declaration)
    if audit.get('eligible_for_post') is not True or current.get('eligible_for_post') is not True or current.get('usable_U_J')!=audit.get('usable_U_J'):
        raise ValueError('Normal method/source/identity/isolation gate is not satisfied')
    result=read(out/'result.json');instance=read(out/'input_instance.json');config=read(out/'input_config.json')
    identity=post_identity(out,slot,declaration)
    identity.update(declaration_sha256=sha(declaration_path),method_audit_sha256=sha(out/'audit.json'),
        post_seconds=60,new_U=False,no_search_or_repair=True,post_started_monotonic=started,
        post_deadline_monotonic=started+60,claimed_at_utc=registry.now(),no_retry=True)
    registry.write_new(out/'postcheck.claim.json',identity)
    record={**identity,'protocol':'K173-independent-post-return-v1','passed':False,
        'not_scientific':False,'evaluation_calls':0,'evaluation_elapsed_s':None,
        'postcheck_sha256':None,'errors':[]}
    code=2
    try:
        # These original scientific imports happen only in this actual child.
        # The post budget starts before declaration/source/identity preparation.
        from schedules import validate_schedule
        from thermal import Budget,evaluate_candidate
        budget=Budget(seconds=60);budget.start=started;budget.check()
        legality=validate_schedule(instance,result['safe_candidate'])
        budget.check()
        record['evaluation_calls']=1
        fresh=evaluate_candidate(instance,result['safe_candidate'],config['accuracy_targets'],budget)
        elapsed=budget.elapsed
        fresh['post_provenance']=identity
        registry.write_new(out/'postcheck.json',fresh)
        old_interval=interval(result['weighted_energy_J'])
        new_interval=interval(fresh['weighted_energy_J']) if fresh.get('weighted_energy_J') else None
        tests={'original_legality':legality.get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED',
            'full_SAFE':fresh.get('state')=='SAFE' and fresh.get('rankable_energy') is True,
            'in_post_budget':0<=elapsed<=60,
            'energy_reproduced':new_interval is not None and max(old_interval[0],new_interval[0])<=min(old_interval[1],new_interval[1]),
            'original_method_U_unchanged':read(out/'result.json')['safe_upper_bound_J']==audit['usable_U_J'],
            'source_still_frozen':all(sha(registry.REPO/name)==value for name,value in declaration['source_sha256'].items())}
        record.update(passed=all(tests.values()),checks=tests,evaluation_elapsed_s=elapsed,
            postcheck_sha256=sha(out/'postcheck.json'),original_U_J=audit['usable_U_J'])
        code=0 if record['passed'] else 2
    except BaseException as e:
        record['errors'].append({'type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc()})
        record['evaluation_elapsed_s']=time.monotonic()-started
    record['post_returned_monotonic']=time.monotonic()
    record['return_wall_s']=record['post_returned_monotonic']-started
    record['result_after_sha256']=sha(out/'result.json')
    registry.write_new(out/'post_return.json',record)
    print(json.dumps({'slot_id':slot_id,'post_passed':record['passed'],'evaluation_calls':record['evaluation_calls'],
        'evaluation_elapsed_s':record['evaluation_elapsed_s'],'new_U':False},ensure_ascii=False),flush=True)
    return code

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--declaration',type=Path,required=True)
    parser.add_argument('--slot-id',required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();raise SystemExit(run_post(args.declaration,args.slot_id,args.out))
