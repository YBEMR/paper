"""K164: consume only original deadline slots 3..40, with unchanged research entries."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[1]
sys.path[:0]=[str(HERE),str(ROOT/'deadline_execution'),str(ROOT/'deadline_batch'),str(ROOT/'p0_resume'),str(ROOT/'p0_batch'),str(ROOT)]
import deadline_controller as prior
import cancel_adapter
import safe_io
from run_four_method_comparison import read,sha,now,canonical

PROTOCOL='K164-deadline-remaining38-original-calendar-once-v1'
OLD=ROOT/'results/deadline_execution01'
REPAIR=ROOT/'results/deadline_cutoff_repair01'
OUT=ROOT/'results/deadline_resume01'
GLOBAL_CLAIM=ROOT/'results/deadline_resume_claim01.json'
OFFSET=2
COUNT=38
METHOD_SECONDS=300
AUTHORIZATION='原K163四十次授权内的管理记录修正与未消费38次续接；前两次原样保留且不重跑，仍使用最初19200秒绝对截止；没有新增预算、条件、参数、算法或热标准。'
write_new=prior.write_new


def slots():return prior.p.slots()[OFFSET:]


def deadline_utc():
    return prior.deadline_utc()


def remaining_calendar():return (deadline_utc()-datetime.now(timezone.utc)).total_seconds()


def sources():
    return {**prior.sources(),**{p.relative_to(REPO).as_posix():sha(p)
        for p in sorted(list(HERE.glob('*.py'))+[HERE/'protocol.md',HERE/'lineage.json'])}}


def prior_inventory():
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}


def prior_gate():
    prior.admission()
    terminal=read(OLD/'process_terminal.json')
    worker=terminal.get('worker_terminal') or {}
    if (terminal.get('state')!='STOPPED_PROCESS_OR_WORKER_FAILURE'
        or terminal.get('watchdog_stop') is not None or worker.get('consumed_total')!=2
        or worker.get('reserved_total_method_s')!=600):
        raise ValueError('Prior two-call terminal mismatch')
    claims=[v for v in prior.p.slots() if (OLD/'claims'/(v['slot_id']+'.json')).exists()]
    if claims!=prior.p.slots()[:2]:raise ValueError('Prior claims must be exactly original slots 1..2')
    review=read(REPAIR/'repair_review.json');post=read(REPAIR/'post_summary.json')
    if review.get('passed') is not True or post.get('passed') is not True:
        raise ValueError('Strict readonly repair proof and once-only delayed post required')
    if post.get('new_U') is not False or post.get('research_repeated') is not False:
        raise ValueError('Delayed post cannot add a search result')
    original=prior.p.slots()
    row=read(OLD/'claims'/(original[0]['slot_id']+'_result.json'))
    if row.get('state')!='COMPLETED' or (row.get('postcheck') or {}).get('passed') is not True:
        raise ValueError('Original first slot not complete')
    slot=original[1];folder=OLD/'calls'/slot['problem_id']/slot['id']
    old_row=read(OLD/'claims'/(slot['slot_id']+'_result.json'))
    old_records=old_row['records'];old_context=old_records['context']
    raw=read(folder/'wrapper_raw_result.json')
    job=next(j for j in prior.p.jobs(slot['problem_id']) if j['id']==slot['id'])
    data=read(prior.BASE)['inputs'][slot['problem_id']]
    derived=cancel_adapter.result_records(job,raw,data,folder,
        input_valid=old_context.get('input_identity_valid'),
        source_valid=old_context.get('source_identity_valid'),errors=old_row.get('errors'))
    if (derived['execution']['execution_status']!='NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
        or (derived.get('cancel_overwrite_audit') or {}).get('applied') is not True
        or derived['cancel_overwrite_audit']['original_execution']!=old_records['execution']
        or old_context.get('hard_errors')!=['MISSING_MATCHING_ROOT_CANCEL_FILE']
        or derived.get('usable_U_J')!=post.get('original_U_J')
        or post.get('original_raw_sha256')!=sha(folder/'wrapper_raw_result.json')
        or post.get('original_declaration_sha256')!=sha(OLD/'declaration.json')
        or post.get('postcheck_sha256')!=sha(REPAIR/'post01/postcheck.json')
        or post.get('postclaim_sha256')!=sha(REPAIR/'post01/postcheck.claim.json')):
        raise ValueError('Derived cutoff classification or delayed-post provenance mismatch')
    for slot in slots():
        if (OLD/'calls'/slot['problem_id']/slot['id']).exists():
            raise ValueError('A remaining method was already started')
    return True


def verify_checks(path):
    g=read(path)
    if (g.get('protocol')!=PROTOCOL or g.get('passed') is not True
        or g.get('source_sha256')!=sources() or g.get('source_unchanged') is not True
        or not g.get('tests_run') or g.get('error') is not None
        or any(g.get(k)!=0 for k in ('errors','failures','skipped','research_calls','native_calls','thermal_evaluations','physical_models'))
        or not g.get('blocked_calls') or any(g['blocked_calls'].values())):
        raise ValueError('Matching pure continuation precheck required')


def freeze(checks):
    verify_checks(checks);prior_gate()
    if OUT.exists() or GLOBAL_CLAIM.exists():raise FileExistsError('Continuation already declared')
    if remaining_calendar()<=0:raise TimeoutError('Original campaign calendar already expired')
    OUT.mkdir();(OUT/'claims').mkdir();(OUT/'calls').mkdir()
    inherited=prior.sources();current=sources()
    for name,digest in current.items():
        if name in inherited:continue
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,target)
        if sha(target)!=digest:raise ValueError('Source snapshot race')
    shutil.copyfile(checks,OUT/'precheck.json');shutil.copyfile(HERE/'protocol.md',OUT/'protocol.md')
    d={'protocol':PROTOCOL,'authorization':AUTHORIZATION,'frozen_at_utc':now(),
        'source_sha256':current,'prior_artifact_sha256':prior_inventory(),
        'prior_declaration_sha256':sha(OLD/'declaration.json'),
        'slots':slots(),'prior_consumed':2,'prior_reserved_method_s':600,
        'remaining_calls':38,'seconds_each':300,'remaining_reserved_method_s':11400,
        'campaign_call_limit':40,'campaign_reserved_method_s':12000,
        'original_calendar_deadline_utc':deadline_utc().isoformat(),
        'calendar_was_not_reset':True,'method_return_watchdog_s':420,'slot_watchdog_s':480,
        'post_seconds':60,'new_or_reused_initialization':False,
        'precheck_sha256':sha(OUT/'precheck.json'),'protocol_sha256':sha(OUT/'protocol.md'),
        'retry_methods':False,'restore_old_claims':False,'scope':'segmented original-budget continuation; raw first two slots unchanged',
        'repair_review_sha256':sha(REPAIR/'repair_review.json'),
        'delayed_post_sha256':sha(REPAIR/'post_summary.json')}
    write_new(OUT/'declaration.json',d)
    safe_io.save(OUT/'ledger.json',initial_ledger())
    publish_status(initial_ledger(),phase='DECLARED')
    admission();return {'frozen':True,'remaining_calls':38,'prior_calls':2,'calendar_remaining_s':remaining_calendar()}


def initial_ledger():
    return {'protocol':PROTOCOL,'state':'DECLARED','prior_consumed':2,'consumed_new':0,
        'consumed_total':2,'reserved_total_method_s':600,'calls':[],'active':None}


def admission():
    d=read(OUT/'declaration.json')
    if (d.get('protocol')!=PROTOCOL or d.get('authorization')!=AUTHORIZATION
        or d.get('prior_declaration_sha256')!=sha(OLD/'declaration.json')
        or d.get('source_sha256')!=sources() or d.get('slots')!=slots()
        or d.get('prior_consumed')!=2 or d.get('prior_reserved_method_s')!=600
        or d.get('remaining_calls')!=38 or d.get('seconds_each')!=300
        or d.get('remaining_reserved_method_s')!=11400 or d.get('campaign_call_limit')!=40
        or d.get('campaign_reserved_method_s')!=12000
        or d.get('original_calendar_deadline_utc')!=deadline_utc().isoformat()
        or d.get('calendar_was_not_reset') is not True
        or d.get('repair_review_sha256')!=sha(REPAIR/'repair_review.json')
        or d.get('delayed_post_sha256')!=sha(REPAIR/'post_summary.json')
        or d.get('method_return_watchdog_s')!=420 or d.get('slot_watchdog_s')!=480
        or d.get('post_seconds')!=60 or d.get('new_or_reused_initialization') is not False
        or d.get('retry_methods') is not False or d.get('restore_old_claims') is not False
        or d.get('precheck_sha256')!=sha(OUT/'precheck.json')
        or d.get('protocol_sha256')!=sha(OUT/'protocol.md')
        or sha(OUT/'protocol.md')!=sha(HERE/'protocol.md')):raise ValueError('Continuation declaration drift')
    verify_checks(OUT/'precheck.json')
    prior_gate()
    if any(sha(REPO/name)!=h for name,h in d['prior_artifact_sha256'].items()):
        raise ValueError('Prior immutable evidence changed')
    inherited=prior.sources()
    for name,h in d['source_sha256'].items():
        if name not in inherited and sha(OUT/'source_snapshot'/name)!=h:
            raise ValueError('Continuation source snapshot changed')
    return d


def publish_status(ledger,*,phase):
    safe_io.save(OUT/'status.json',{'protocol':PROTOCOL,'state':ledger['state'],'phase':phase,
        'consumed_new':ledger['consumed_new'],'consumed_total':ledger['consumed_total'],
        'completed_new':sum(row.get('state')=='COMPLETED' for row in ledger['calls']),
        'active':ledger.get('active'),'updated_utc':now()})


def claim(ledger,slot,clock=time.monotonic):
    if remaining_calendar()<=0:raise TimeoutError('Original calendar expired before claim')
    count=ledger['consumed_new']
    if (ledger['state'] not in ('DECLARED','RUNNING') or ledger.get('active') is not None
        or count>=38 or slot!=slots()[count] or slot['ordinal']<3
        or ledger['consumed_total']!=2+count or ledger['reserved_total_method_s']!=(2+count)*300
        or [r['slot_id'] for r in ledger['calls']]!=[s['slot_id'] for s in slots()[:count]]):
        raise ValueError('Slot prefix, budget, prior exclusion or active claim mismatch')
    if (OLD/'claims'/(slot['slot_id']+'.json')).exists():raise FileExistsError('Prior claim cannot be replayed')
    write_new(OUT/'claims'/(slot['slot_id']+'.json'),dict(slot,no_retry=True,claimed_utc=now()))
    stamp=clock();row=dict(slot,state='RUNNING',slot_start_monotonic=stamp,started_utc=now())
    ledger['calls'].append(row)
    ledger.update(state='RUNNING',consumed_new=count+1,consumed_total=count+3,
        reserved_total_method_s=(count+3)*300,
        active={'slot_id':slot['slot_id'],'phase':'METHOD','slot_start_monotonic':stamp,
                'phase_start_monotonic':stamp})
    safe_io.save(OUT/'ledger.json',ledger);publish_status(ledger,phase='METHOD')
    return row


def write_terminal(ledger,state,error=None):
    # An independent exclusive file; never replace a possibly locked ledger.
    claims=sum((OUT/'claims'/(s['slot_id']+'.json')).is_file() for s in slots())
    value={'protocol':PROTOCOL,'state':state,'ended_utc':now(),
        'prior_consumed':2,'consumed_new':claims,'consumed_total':2+claims,
        'reserved_total_method_s':(2+claims)*300,'unstarted_remaining':38-claims,
        'last_in_memory_slot':(ledger.get('active') or {}).get('slot_id'),
        'error':error,'research_calls_retried':False,'prior_claims_modified':False}
    write_new(OUT/'worker_terminal.json',value)
    return value


def run(*,clock=time.monotonic,entries=None,executor=None,auditor=None,post=None):
    d=admission();ledger=read(OUT/'ledger.json')
    if ledger!=initial_ledger() or GLOBAL_CLAIM.exists() or list((OUT/'claims').iterdir()):
        raise FileExistsError('Continuation consumed/stopped; no restart')
    write_new(GLOBAL_CLAIM,{'protocol':PROTOCOL,'declaration_sha256':sha(OUT/'declaration.json'),
        'started_monotonic':clock(),'started_utc':now(),'prior_consumed':2,'remaining':38,'no_retry':True})
    try:
        started=clock();t=clock()
        if entries is None:
            from run_minimal_comparison import common_entry_points
            entries=common_entry_points()
        write_new(OUT/'imports.json',{'wall_s':clock()-t,'scope':'imports only; no warm model/cache/witness'})
        if executor is None:
            from deadline_dispatch import execute
            executor=execute
        auditor=auditor or cancel_adapter.result_records
        post=post or prior.postcheck
        prep=read(prior.BASE)
        for slot in d['slots']:
            if remaining_calendar()<=0:
                ledger['state']='STOPPED_ORIGINAL_CALENDAR_LIMIT';safe_io.save(OUT/'ledger.json',ledger)
                write_terminal(ledger,ledger['state']);return False
            admission();row=claim(ledger,slot,clock)
            job=next(j for j in prior.p.jobs(slot['problem_id']) if j['id']==slot['id'])
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
            okay=(records['execution']['execution_status'] in prior.p.NORMAL and source_valid and not errors
                  and (records.get('current_schedule_audit') or {}).get('passed') is True)
            if okay and records.get('usable_U_J') is None:
                row['postcheck']={'state':'NOT_APPLICABLE_NO_USABLE_U','passed':True,'new_U':False}
                row['postcheck_wall_s']=0
            elif okay:
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','run','inspect'));parser.add_argument('--checks',type=Path)
    args=parser.parse_args()
    if args.mode=='freeze':
        if args.checks is None:parser.error('--checks required')
        print(freeze(args.checks))
    elif args.mode=='inspect':print({'admitted':bool(admission()),'calendar_remaining_s':remaining_calendar()})
    else:raise SystemExit(0 if run() else 1)
