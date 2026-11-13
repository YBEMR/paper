"""K155: single-use, authorized 40-slot P0 execution; unchanged K154 dispatch."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[1]
sys.path[:0]=[str(ROOT/'p0_batch'),str(ROOT)]
import run_p0 as p
from run_four_method_comparison import read,save,sha,now,canonical

PROTOCOL='K155-P0-authorized-40x300-once-v1'
OUT=ROOT/'results/p0_execution01'
GLOBAL_CLAIM=ROOT/'results/p0_execution_claim01.json'
PREP=p.PREP
SECONDS=300
TOTAL=12000
WALL=19200
SLOT_WALL=480
METHOD_RETURN_WALL=420
POST_SECONDS=60
AUTHORIZATION='用户确认：R1—R5共40次、每次300秒；先冻结实际批量启动流程并通过必要预检，再执行；模型、参数和热安全标准不变，不补跑、不延长预算。'


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False,default=str)
        stream.write('\n')


def sources():
    return {**p.sources(),**{path.relative_to(REPO).as_posix():sha(path)
        for path in sorted(list(HERE.glob('*.py'))+[HERE/'protocol.md'])}}


def verify_gate(path):
    g=read(path)
    if (g.get('protocol')!=PROTOCOL or g.get('passed') is not True
        or g.get('source_sha256')!=sources() or not g.get('tests_run')
        or any(g.get(k)!=0 for k in ('errors','failures','skipped','research_calls','native_calls','thermal_evaluations','physical_models'))
        or g.get('source_unchanged') is not True
        or g.get('error') is not None or not g.get('blocked_calls') or any(g['blocked_calls'].values())):
        raise ValueError('Matching successful pure K155 precheck required')


def freeze(checks):
    verify_gate(checks);p.admission(PREP)
    if OUT.exists() or GLOBAL_CLAIM.exists():raise FileExistsError('Frozen P0 batch already exists')
    OUT.mkdir();(OUT/'claims').mkdir();(OUT/'calls').mkdir()
    frozen=sources()
    # K154 already holds an exact snapshot of inherited 191 files. Avoid another
    # redundant copy; archive only the new execution files and bind both layers.
    for path,h in frozen.items():
        if path in p.sources():continue
        target=OUT/'execution_source_snapshot'/path
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/path,target)
        if sha(target)!=h:raise ValueError('Freeze race')
    shutil.copyfile(HERE/'protocol.md',OUT/'protocol.md')
    shutil.copyfile(checks,OUT/'precheck.json')
    d={'protocol':PROTOCOL,'authorization':AUTHORIZATION,'authorized':True,
       'authorization_origin':'direct human message in this chat; not external agent approval',
       'frozen_at_utc':now(),'slots':p.slots(),'method_call_limit':40,'seconds_each':SECONDS,
       'total_reserved_method_seconds':TOTAL,'calendar_stop_s':WALL,
       'method_return_watchdog_s':METHOD_RETURN_WALL,'slot_watchdog_s':SLOT_WALL,
       'post_budget_seconds':POST_SECONDS,'source_sha256':frozen,
       'preparation_declaration_sha256':sha(PREP/'declaration.json'),
       'preparation_review_sha256':sha(PREP/'preparation_review.json'),
       'precheck_sha256':sha(OUT/'precheck.json'),'protocol_sha256':sha(OUT/'protocol.md'),
       'retry_allowed':False,'extend_budget_allowed':False,'historical_initialization':False,
       'result_policy':'keep prior in-budget safe evidence; no late U, proof or cache inheritance'}
    write_new(OUT/'declaration.json',d)
    save(OUT/'ledger.json',{'protocol':PROTOCOL,'state':'DECLARED','consumed':0,
        'reserved_method_budget_s':0,'calls':[],'active':None})
    admission();return {'frozen':True,'slots':40,'authorized':True,'research_calls':0}


def admission():
    d=read(OUT/'declaration.json')
    if (d.get('protocol')!=PROTOCOL or d.get('authorization')!=AUTHORIZATION
        or d.get('authorized') is not True or d.get('slots')!=p.slots()
        or d.get('method_call_limit')!=40 or d.get('seconds_each')!=300
        or d.get('total_reserved_method_seconds')!=12000 or d.get('calendar_stop_s')!=WALL
        or d.get('method_return_watchdog_s')!=420 or d.get('slot_watchdog_s')!=480
        or d.get('post_budget_seconds')!=60 or d.get('source_sha256')!=sources()
        or d.get('retry_allowed') is not False or d.get('extend_budget_allowed') is not False
        or d.get('historical_initialization') is not False
        or d.get('preparation_declaration_sha256')!=sha(PREP/'declaration.json')
        or d.get('preparation_review_sha256')!=sha(PREP/'preparation_review.json')
        or d.get('precheck_sha256')!=sha(OUT/'precheck.json')
        or d.get('protocol_sha256')!=sha(OUT/'protocol.md')
        or sha(OUT/'protocol.md')!=sha(HERE/'protocol.md')):
        raise ValueError('Frozen batch scope/source/input/protocol drift')
    verify_gate(OUT/'precheck.json');p.admission(PREP)
    inherited=p.sources()
    for path,h in d['source_sha256'].items():
        target=(PREP/'source_snapshot' if path in inherited else OUT/'execution_source_snapshot')/path
        if sha(target)!=h:raise ValueError('Frozen source snapshot changed')
    return d


def claim_slot(ledger,slot,clock=time.monotonic):
    count=ledger['consumed']
    if (ledger['state'] not in ('DECLARED','RUNNING') or ledger.get('active') is not None
        or count>=40 or slot!=p.slots()[count] or ledger['reserved_method_budget_s']!=count*300
        or [r['slot_id'] for r in ledger['calls']]!=[r['slot_id'] for r in p.slots()[:count]]):
        raise ValueError('Slot repeat/order/count/active/STOP mismatch')
    # Exclusive disk claim precedes invocation. A crash consumes this slot;
    # there is no resume/retry command that can erase or bypass this record.
    write_new(OUT/'claims'/(slot['slot_id']+'.json'),dict(slot,claimed_at_utc=now(),no_retry=True))
    stamp=clock()
    row=dict(slot,state='RUNNING',started_utc=now(),slot_start_monotonic=stamp)
    ledger['calls'].append(row)
    ledger.update(state='RUNNING',consumed=count+1,reserved_method_budget_s=(count+1)*300,
        active={'slot_id':slot['slot_id'],'phase':'METHOD','slot_start_monotonic':stamp,
                'phase_start_monotonic':stamp})
    save(OUT/'ledger.json',ledger)
    return row


def postcheck(slot,result,records,folder):
    if records.get('usable_U_J') is None:
        return {'state':'NOT_APPLICABLE_NO_USABLE_U','passed':True,'new_U':False}
    from thermal import Budget,evaluate_candidate
    from schedules import validate_schedule
    raw,config,instance=p.fresh_input(slot['problem_id'])
    candidate=result['safe_candidate']
    receipt=result['aggregation'] if slot['method']=='linked_fixed_unit_opp_start' else result['evaluation']
    provenance={'raw_result_sha256':sha(folder/'wrapper_raw_result.json'),
        'input_sha256':canonical(instance),'candidate_sha256':canonical(candidate),
        'accuracy_sha256':canonical(config['accuracy_targets']),'source_sha256':sources(),
        'post_seconds':60,'new_U':False,'no_search_or_repair':True}
    claim=folder/'postcheck.claim.json';target=folder/'postcheck.json'
    write_new(claim,{'provenance':provenance,'claimed_at_utc':now(),'no_retry':True})
    legality=validate_schedule(instance,candidate)
    fresh=evaluate_candidate(instance,candidate,config['accuracy_targets'],Budget(seconds=POST_SECONDS))
    fresh['post_provenance']=provenance
    write_new(target,fresh)
    old=tuple(map(F,receipt['weighted_energy_J']))
    new=tuple(map(F,fresh['weighted_energy_J'])) if fresh.get('weighted_energy_J') else (F(-1),F(-1))
    tests={'legality':legality.get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED',
        'complete_safe':fresh.get('state')=='SAFE' and fresh.get('rankable_energy') is True,
        'all_scenes':set(fresh.get('scenes',{}))==set(candidate['scenes']),
        'full_window':all(s.get('complete') is True and F(s['covered_until_s'])==F(instance['window_ms'])/1000
                          for s in fresh.get('scenes',{}).values()),
        'energy_overlap':max(old[0],new[0])<=min(old[1],new[1]),
        'raw_unchanged':sha(folder/'wrapper_raw_result.json')==provenance['raw_result_sha256']}
    return {'state':'PASSED' if all(tests.values()) else 'UNRESOLVED_OR_FAILED',
        'passed':all(tests.values()),'checks':tests,'new_U':False,'elapsed_s':fresh.get('elapsed_s')}


def run(*,clock=time.monotonic,entries=None,executor=None,auditor=None,post=None):
    d=admission();ledger=read(OUT/'ledger.json')
    if ledger!={'protocol':PROTOCOL,'state':'DECLARED','consumed':0,'reserved_method_budget_s':0,'calls':[],'active':None}:
        raise FileExistsError('Batch already started/stopped; no restart')
    if GLOBAL_CLAIM.exists() or list((OUT/'claims').iterdir()):raise FileExistsError('Batch single-use claim exists')
    start=clock()
    write_new(GLOBAL_CLAIM,{'protocol':PROTOCOL,'declaration_sha256':sha(OUT/'declaration.json'),
        'started_monotonic':start,'no_retry':True,'claimed_at_utc':now()})
    # Imported once, never precompute a candidate, model, L0 or thermal result.
    t=clock()
    if entries is None:
        from run_minimal_comparison import common_entry_points
        entries=common_entry_points()
    save(OUT/'imports.json',{'wall_s':clock()-t,'scope':'imports only; MATLAB startup remains billed'})
    if executor is None:
        from dispatch import execute
        executor=execute
    auditor=auditor or p.result_records;post=post or postcheck
    prep=read(PREP/'declaration.json')
    for slot in d['slots']:
        if clock()-start>=WALL:
            ledger.update(state='BLOCKED_CALENDAR_LIMIT',active=None);save(OUT/'ledger.json',ledger);return False
        admission()
        row=claim_slot(ledger,slot,clock)
        pid=slot['problem_id'];job=next(j for j in p.jobs(pid) if j['id']==slot['id'])
        parent=OUT/'calls'/pid;parent.mkdir(exist_ok=True)
        # Existing entries demand a never-created per-call directory and own
        # its exclusive creation. Creating it here would invalidate every call.
        folder=parent/job['id']
        if folder.exists():raise FileExistsError('Call directory already exists')
        result=None;identity={'input_verified':None};errors=[]
        t=clock()
        try:result,identity=executor(job,parent,deepcopy(prep['inputs'][pid]),entries)
        except BaseException:errors.append(traceback.format_exc())
        method_wall=clock()-t
        folder.mkdir(parents=True,exist_ok=True)
        source_valid=True
        try:admission()
        except Exception:source_valid=False;errors.append(traceback.format_exc())
        if isinstance(result,dict):write_new(folder/'wrapper_raw_result.json',result)
        try:
            records=auditor(job,result,prep['inputs'][pid],folder,
                input_valid=identity.get('input_verified'),source_valid=source_valid,errors=errors)
        except Exception:
            errors.append(traceback.format_exc())
            records={'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},'usable_U_J':None}
        row.update(method_return_inclusive_wall_s=method_wall,errors=errors,records=records)
        # Persist formed evidence BEFORE any post check; a post failure cannot
        # erase an earlier budget-valid U, but prevents continuation/ranking.
        save(OUT/'ledger.json',ledger)
        okay=records['execution']['execution_status'] in p.NORMAL and not errors and source_valid
        if okay:
            ledger['active']['phase']='POST'
            ledger['active']['phase_start_monotonic']=clock();save(OUT/'ledger.json',ledger)
            t=clock()
            try:row['postcheck']=post(slot,result,records,folder)
            except BaseException:
                row['postcheck']={'passed':False,'error':traceback.format_exc(),'new_U':False}
            row['postcheck_wall_s']=clock()-t
            okay=row['postcheck'].get('passed') is True
        row.update(state='COMPLETED' if okay else 'BLOCKED',completed_utc=now(),
                   slot_wall_s=clock()-row['slot_start_monotonic'])
        write_new(OUT/'claims'/(slot['slot_id']+'_result.json'),row)
        manifest={f.relative_to(folder).as_posix():sha(f) for f in sorted(folder.rglob('*'))
                  if f.is_file() and f.suffix!='.mat'}
        write_new(OUT/'claims'/(slot['slot_id']+'_artifact_sha256.json'),manifest)
        ledger.update(state='RUNNING' if okay else 'BLOCKED',active=None)
        save(OUT/'ledger.json',ledger)
        print(json.dumps({'event':'SLOT_COMPLETE','slot':slot['slot_id'],'ordinal':slot['ordinal'],
            'status':records['execution']['execution_status'],'U_J':records.get('usable_U_J'),
            'post_passed':(row.get('postcheck') or {}).get('passed'),'continue':okay}),flush=True)
        if not okay:return False
    ledger.update(state='COMPLETED',active=None,total_process_wall_s=clock()-start)
    save(OUT/'ledger.json',ledger);return True


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','run','inspect'))
    parser.add_argument('--checks',type=Path)
    args=parser.parse_args()
    if args.mode=='freeze':
        if args.checks is None:parser.error('freeze requires --checks')
        print(freeze(args.checks))
    elif args.mode=='inspect':print({'admitted':bool(admission()),'ledger':read(OUT/'ledger.json')['state']})
    else:raise SystemExit(0 if run() else 1)
