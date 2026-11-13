"""K161: once-only P2 original-H initial78 forty-call campaign; no prior restart."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
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
sys.path[:0]=[str(HERE),str(ROOT/'p2_batch'),str(ROOT/'p0_resume'),str(ROOT/'p0_batch'),str(ROOT)]
import p2_entry as p
import safe_io
from run_four_method_comparison import read,sha,now,canonical
PROTOCOL='K161-P2-initial78-originalH-authorized-40x300-once-v1'
OUT=ROOT/'results/p2_execution01'
GLOBAL_CLAIM=ROOT/'results/p2_execution_claim01.json'
BASE=ROOT/'results/p2_batch_preparation01/declaration.json'
COUNT=40
WALL=19200
POST_SECONDS=60
AUTHORIZATION='用户明确确认：P2 initial_78原H响应 R1—R5共40次，各300秒，方法上限12000秒、总日历19200秒；预检通过并冻结后执行，不补跑、不延时，模型、既定参数及热安全标准不变。'

def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False,default=str);stream.write('\n')

def slots():return p.slots()

def sources():
    base=read(BASE)['source_sha256']
    if len(base)!=218 or any(sha(REPO/name)!=h for name,h in base.items()):
        raise ValueError('Original 218 scientific/execution sources changed')
    return {**base,**{q.relative_to(REPO).as_posix():sha(q) for q in sorted(list(HERE.glob('*.py'))+[HERE/'protocol.md',HERE/'lineage.json'])}}

def verify_checks(path):
    g=read(path)
    if (g.get('protocol')!=PROTOCOL or g.get('passed') is not True or g.get('source_sha256')!=sources()
        or g.get('source_unchanged') is not True or g.get('P0_critical_unchanged') is not True
        or not g.get('tests_run') or g.get('error') is not None
        or any(g.get(k)!=0 for k in ('errors','failures','skipped','research_calls','native_calls','thermal_evaluations','physical_models'))
        or not g.get('blocked_calls') or any(g['blocked_calls'].values())):
        raise ValueError('Successful source-matched pure P2 precheck required')

def freeze(checks):
    import prepare_p2
    prepare_p2.admission(BASE.parent)
    verify_checks(checks)
    if OUT.exists() or GLOBAL_CLAIM.exists():raise FileExistsError('P2 already declared or consumed')
    frozen=sources();OUT.mkdir();(OUT/'claims').mkdir();(OUT/'calls').mkdir();(OUT/'inputs').mkdir()
    inputs={}
    for pid in p.PROBLEMS:
        d,triple=p.input_declaration(pid)
        if d!=read(BASE)['inputs'][pid]:raise ValueError('P2 prepared input identity changed')
        inputs[pid]=d
        folder=OUT/'inputs'/pid;folder.mkdir()
        for name,value in zip(('raw_config.json','config.json','instance.json'),triple):write_new(folder/name,value)
    for name,h in frozen.items():
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,target)
        if sha(target)!=h:raise ValueError('Source snapshot race')
    shutil.copyfile(checks,OUT/'precheck.json');shutil.copyfile(HERE/'protocol.md',OUT/'protocol.md')
    d={'protocol':PROTOCOL,'authorization':AUTHORIZATION,'authorized':True,'frozen_at_utc':now(),
       'source_sha256':frozen,'inputs':inputs,'slots':slots(),'call_limit':40,'seconds_each':300,
       'total_reserved_method_seconds':12000,'calendar_stop_s':19200,
       'method_return_watchdog_s':420,'slot_watchdog_s':480,'post_seconds':60,
       'precheck_sha256':sha(OUT/'precheck.json'),'protocol_sha256':sha(OUT/'protocol.md'),
       'retry_methods':False,'historical_initialization':False,'change_condition':'P0_original_H_initial_temperature_50_to_78_only',
       'P0_manifest_sha256':sha(ROOT/'results/p0_resume01/archive_inventory.json'),
       'P1_manifest_sha256':sha(ROOT/'results/p1_execution01/archive_inventory.json'),
       'P2_preparation_sha256':sha(BASE)}
    write_new(OUT/'declaration.json',d);safe_io.save(OUT/'ledger.json',initial_ledger())
    publish_status(initial_ledger(),phase='DECLARED');admission()
    return {'frozen':True,'calls':40,'source_files':len(frozen),'research_calls':0}

def admission():
    d=read(OUT/'declaration.json')
    expected={'protocol':PROTOCOL,'authorization':AUTHORIZATION,'authorized':True,'call_limit':40,
        'seconds_each':300,'total_reserved_method_seconds':12000,'calendar_stop_s':19200,
        'method_return_watchdog_s':420,'slot_watchdog_s':480,'post_seconds':60,
        'retry_methods':False,'historical_initialization':False,'change_condition':'P0_original_H_initial_temperature_50_to_78_only'}
    if any(d.get(k)!=v for k,v in expected.items()) or d.get('slots')!=slots() or d.get('source_sha256')!=sources():
        raise ValueError('P2 frozen scope/source/budget drift')
    verify_checks(OUT/'precheck.json')
    if (d['P2_preparation_sha256']!=sha(BASE)
        or d['P1_manifest_sha256']!=sha(ROOT/'results/p1_execution01/archive_inventory.json')
        or d['precheck_sha256']!=sha(OUT/'precheck.json') or d['protocol_sha256']!=sha(OUT/'protocol.md')
        or sha(OUT/'protocol.md')!=sha(HERE/'protocol.md')
        or d['P0_manifest_sha256']!=sha(ROOT/'results/p0_resume01/archive_inventory.json')):raise ValueError('Gate/protocol/P0 manifest drift')
    for name,h in d['source_sha256'].items():
        if sha(OUT/'source_snapshot'/name)!=h:raise ValueError('P2 snapshot changed')
    for pid,definition in d['inputs'].items():
        folder=OUT/'inputs'/pid
        triple=[read(folder/name) for name in ('raw_config.json','config.json','instance.json')]
        if dict(zip(('raw_config_sha256','config_sha256','input_sha256'),map(canonical,triple)))!=definition['input_identities']:
            raise ValueError('P2 frozen input snapshot drift')
    return d

def deadline_utc():
    launcher=read(OUT/'launcher_claim.json')
    end=datetime.fromisoformat(launcher['calendar_deadline_utc'])
    if (launcher['protocol']!=PROTOCOL or launcher['declaration_sha256']!=sha(OUT/'declaration.json')
        or launcher['script_sha256']!=sha(HERE/'p2_supervise.py')
        or end!=datetime.fromisoformat(launcher['started_utc'])+timedelta(seconds=WALL)):
        raise ValueError('P2 launcher calendar identity changed')
    return end
def remaining_calendar():return (deadline_utc()-datetime.now(timezone.utc)).total_seconds()

def initial_ledger():
    return {'protocol':PROTOCOL,'state':'DECLARED','prior_consumed':0,'consumed_new':0,
        'consumed_total':0,'reserved_total_method_s':0,'calls':[],'active':None}

def publish_status(ledger,*,phase):
    safe_io.save(OUT/'status.json',{'protocol':PROTOCOL,'state':ledger['state'],'phase':phase,
        'consumed_new':ledger['consumed_new'],'consumed_total':ledger['consumed_total'],
        'completed_new':sum(row.get('state')=='COMPLETED' for row in ledger['calls']),
        'active':ledger.get('active'),'updated_utc':now()})

def claim(ledger,slot,clock=time.monotonic):
    n=ledger['consumed_new']
    if (ledger['state'] not in ('DECLARED','RUNNING') or ledger.get('active') is not None
        or n>=40 or slot!=slots()[n] or ledger['consumed_total']!=n or ledger['reserved_total_method_s']!=n*300
        or [r['slot_id'] for r in ledger['calls']]!=[s['slot_id'] for s in slots()[:n]]):
        raise ValueError('P2 once-only slot prefix/order/budget mismatch')
    write_new(OUT/'claims'/(slot['slot_id']+'.json'),dict(slot,no_retry=True,claimed_utc=now()))
    stamp=clock();row=dict(slot,state='RUNNING',slot_start_monotonic=stamp,started_utc=now())
    ledger['calls'].append(row)
    ledger.update(state='RUNNING',consumed_new=n+1,consumed_total=n+1,reserved_total_method_s=(n+1)*300,
        active={'slot_id':slot['slot_id'],'phase':'METHOD','slot_start_monotonic':stamp,'phase_start_monotonic':stamp})
    safe_io.save(OUT/'ledger.json',ledger);publish_status(ledger,phase='METHOD');return row

def write_terminal(ledger,state,error=None):
    n=sum((OUT/'claims'/(s['slot_id']+'.json')).is_file() for s in slots())
    value={'protocol':PROTOCOL,'state':state,'ended_utc':now(),'consumed_new':n,'consumed_total':n,
        'reserved_total_method_s':n*300,'unstarted_remaining':40-n,
        'last_in_memory_slot':(ledger.get('active') or {}).get('slot_id'),
        'error':error,'research_calls_retried':False,'P0_claims_modified':False}
    write_new(OUT/'worker_terminal.json',value);return value

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
    if ledger!=initial_ledger() or GLOBAL_CLAIM.exists() or list((OUT/'claims').iterdir()):
        raise FileExistsError('Continuation consumed/stopped; no restart')
    write_new(GLOBAL_CLAIM,{'protocol':PROTOCOL,'declaration_sha256':sha(OUT/'declaration.json'),
        'started_monotonic':clock(),'started_utc':now(),'prior_consumed':0,'remaining':40,'no_retry':True})
    try:
        started=clock();t=clock()
        if entries is None:
            from run_minimal_comparison import common_entry_points
            entries=common_entry_points()
        write_new(OUT/'imports.json',{'wall_s':clock()-t,'scope':'imports only; no warm model/cache/witness'})
        if executor is None:
            from p2_dispatch import execute
            executor=execute
        auditor=auditor or p.result_records
        post=post or postcheck
        prep=d
        for slot in d['slots']:
            if remaining_calendar()<=0:
                ledger['state']='STOPPED_P2_CALENDAR_LIMIT';safe_io.save(OUT/'ledger.json',ledger)
                write_terminal(ledger,ledger['state']);return False
            admission();row=claim(ledger,slot,clock)
            job=next(j for j in p.jobs(slot['problem_id']) if j['id']==slot['id'])
            parent=OUT/'calls'/slot['problem_id'];parent.mkdir(exist_ok=True)
            folder=parent/job['id']
            if folder.exists():raise FileExistsError('Research output directory already exists')
            result=None;identity={'input_verified':None};errors=[];t=clock()
            try:result,identity=executor(job,parent,deepcopy(prep['inputs'][slot['problem_id']]),entries)
            except BaseException:errors.append(traceback.format_exc())
            row['method_return_inclusive_wall_s']=clock()-t
            folder.mkdir(parents=True,exist_ok=True)
            source_valid=True
            try:admission()
            except Exception:source_valid=False;errors.append(traceback.format_exc())
            if isinstance(result,dict):write_new(folder/'wrapper_raw_result.json',result)
            try:records=auditor(job,result,prep['inputs'][slot['problem_id']],folder,
                input_valid=identity['input_verified'],source_valid=source_valid,errors=errors)
            except Exception:
                errors.append(traceback.format_exc())
                records={'execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},'usable_U_J':None}
            row.update(records=records,errors=errors)
            # Immutable evidence before any replaceable progress/ledger update.
            write_new(OUT/'claims'/(slot['slot_id']+'_method_return.json'),row)
            safe_io.save(OUT/'ledger.json',ledger)
            okay=records['execution']['execution_status'] in p.NORMAL and source_valid and not errors
            if okay:
                ledger['active'].update(phase='POST',phase_start_monotonic=clock())
                publish_status(ledger,phase='POST')
                t=clock()
                try:row['postcheck']=post(slot,result,records,folder)
                except BaseException:row['postcheck']={'passed':False,'error':traceback.format_exc()}
                row['postcheck_wall_s']=clock()-t;okay=row['postcheck'].get('passed') is True
            row.update(state='COMPLETED' if okay else 'BLOCKED',completed_utc=now(),
                slot_wall_s=clock()-row['slot_start_monotonic'])
            write_new(OUT/'claims'/(slot['slot_id']+'_result.json'),row)
            write_new(OUT/'claims'/(slot['slot_id']+'_artifact_sha256.json'),
                {f.relative_to(folder).as_posix():sha(f) for f in sorted(folder.rglob('*')) if f.is_file()})
            ledger.update(state='RUNNING' if okay else 'BLOCKED',active=None)
            safe_io.save(OUT/'ledger.json',ledger);publish_status(ledger,phase='BETWEEN_CALLS')
            print(json.dumps({'event':'SLOT_COMPLETE','ordinal':slot['ordinal'],'slot':slot['slot_id'],
                'status':records['execution']['execution_status'],'U_J':records.get('usable_U_J'),
                'post_passed':(row.get('postcheck') or {}).get('passed'),'continue':okay}),flush=True)
            if not okay:write_terminal(ledger,'BLOCKED');return False
        ledger.update(state='COMPLETED',active=None,process_wall_s=clock()-started)
        safe_io.save(OUT/'ledger.json',ledger);publish_status(ledger,phase='COMPLETED')
        write_terminal(ledger,'COMPLETED');return True
    except BaseException:
        write_terminal(ledger,'STOPPED_EXCEPTION',traceback.format_exc())
        return False

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('freeze','run','inspect'))
    parser.add_argument('--checks',type=Path);args=parser.parse_args()
    if args.mode=='freeze':
        if args.checks is None:parser.error('--checks required')
        print(freeze(args.checks))
    elif args.mode=='inspect':print({'admitted':bool(admission()),'state':read(OUT/'ledger.json')['state']})
    else:raise SystemExit(0 if run() else 1)
