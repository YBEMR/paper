"""K156: consume only frozen P0 slots 4..40, with unchanged research entries."""
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
sys.path[:0]=[str(ROOT/'p0_execution'),str(ROOT/'p0_batch'),str(ROOT)]
import batch as prior
import safe_io
from run_four_method_comparison import read,sha,now,canonical

PROTOCOL='K156-P0-remaining37-fixed300-once-v1'
OLD=ROOT/'results/p0_execution01'
OUT=ROOT/'results/p0_resume01'
GLOBAL_CLAIM=ROOT/'results/p0_resume_claim01.json'
OFFSET=3
COUNT=37
METHOD_SECONDS=300
AUTHORIZATION='用户确认：修复账本写入和异常终态，必要预检及冻结后继续剩余37次；前三次不重跑，每次300秒，当前模型、参数和热安全不变，不延长预算。'
write_new=prior.write_new


def slots():return prior.p.slots()[OFFSET:]


def deadline_utc():
    start=datetime.fromisoformat(read(OLD/'launcher_claim.json')['started_utc'])
    return start+timedelta(seconds=19200)


def remaining_calendar():return (deadline_utc()-datetime.now(timezone.utc)).total_seconds()


def sources():
    return {**prior.sources(),**{p.relative_to(REPO).as_posix():sha(p)
        for p in sorted(list(HERE.glob('*.py'))+[HERE/'protocol.md'])}}


def prior_inventory():
    return {p.relative_to(REPO).as_posix():sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}


def prior_gate():
    prior.admission()
    terminal=read(OLD/'terminal_receipt.json');review=read(OLD/'failure_review01/review.json')
    if (terminal['state']!='STOPPED_TECHNICAL_ARCHIVE_FAILURE' or terminal['consumed_research_calls']!=3
        or terminal['reserved_method_budget_s']!=900 or terminal['post_verified_SAFE_schedules']!=3
        or review.get('passed') is not True or review['consumed_calls']!=3
        or not all(review['checks'].values())):raise ValueError('Prior three-call review not complete')
    claims=[s for s in prior.p.slots() if (OLD/'claims'/(s['slot_id']+'.json')).exists()]
    if claims!=prior.p.slots()[:3]:raise ValueError('Prior call claims are not exactly slots 1..3')
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
        'slots':slots(),'prior_consumed':3,'prior_reserved_method_s':900,
        'remaining_calls':37,'seconds_each':300,'remaining_reserved_method_s':11100,
        'campaign_call_limit':40,'campaign_reserved_method_s':12000,
        'original_calendar_deadline_utc':deadline_utc().isoformat(),
        'calendar_was_not_reset':True,'method_return_watchdog_s':420,'slot_watchdog_s':480,
        'post_seconds':60,'new_or_reused_initialization':False,
        'precheck_sha256':sha(OUT/'precheck.json'),'protocol_sha256':sha(OUT/'protocol.md'),
        'retry_methods':False,'restore_old_claims':False,'scope':'segmented continuation, not uninterrupted cohort runtime'}
    write_new(OUT/'declaration.json',d)
    safe_io.save(OUT/'ledger.json',initial_ledger())
    publish_status(initial_ledger(),phase='DECLARED')
    admission();return {'frozen':True,'remaining_calls':37,'prior_calls':3,'calendar_remaining_s':remaining_calendar()}


def initial_ledger():
    return {'protocol':PROTOCOL,'state':'DECLARED','prior_consumed':3,'consumed_new':0,
        'consumed_total':3,'reserved_total_method_s':900,'calls':[],'active':None}


def admission():
    d=read(OUT/'declaration.json')
    if (d.get('protocol')!=PROTOCOL or d.get('authorization')!=AUTHORIZATION
        or d.get('source_sha256')!=sources() or d.get('slots')!=slots()
        or d.get('prior_consumed')!=3 or d.get('prior_reserved_method_s')!=900
        or d.get('remaining_calls')!=37 or d.get('seconds_each')!=300
        or d.get('remaining_reserved_method_s')!=11100 or d.get('campaign_call_limit')!=40
        or d.get('campaign_reserved_method_s')!=12000
        or d.get('original_calendar_deadline_utc')!=deadline_utc().isoformat()
        or d.get('calendar_was_not_reset') is not True
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
    count=ledger['consumed_new']
    if (ledger['state'] not in ('DECLARED','RUNNING') or ledger.get('active') is not None
        or count>=37 or slot!=slots()[count] or slot['ordinal']<4
        or ledger['consumed_total']!=3+count or ledger['reserved_total_method_s']!=(3+count)*300
        or [r['slot_id'] for r in ledger['calls']]!=[s['slot_id'] for s in slots()[:count]]):
        raise ValueError('Slot prefix, budget, prior exclusion or active claim mismatch')
    if (OLD/'claims'/(slot['slot_id']+'.json')).exists():raise FileExistsError('Prior claim cannot be replayed')
    write_new(OUT/'claims'/(slot['slot_id']+'.json'),dict(slot,no_retry=True,claimed_utc=now()))
    stamp=clock();row=dict(slot,state='RUNNING',slot_start_monotonic=stamp,started_utc=now())
    ledger['calls'].append(row)
    ledger.update(state='RUNNING',consumed_new=count+1,consumed_total=count+4,
        reserved_total_method_s=(count+4)*300,
        active={'slot_id':slot['slot_id'],'phase':'METHOD','slot_start_monotonic':stamp,
                'phase_start_monotonic':stamp})
    safe_io.save(OUT/'ledger.json',ledger);publish_status(ledger,phase='METHOD')
    return row


def write_terminal(ledger,state,error=None):
    # An independent exclusive file; never replace a possibly locked ledger.
    claims=sum((OUT/'claims'/(s['slot_id']+'.json')).is_file() for s in slots())
    value={'protocol':PROTOCOL,'state':state,'ended_utc':now(),
        'prior_consumed':3,'consumed_new':claims,'consumed_total':3+claims,
        'reserved_total_method_s':(3+claims)*300,'unstarted_remaining':37-claims,
        'last_in_memory_slot':(ledger.get('active') or {}).get('slot_id'),
        'error':error,'research_calls_retried':False,'prior_claims_modified':False}
    write_new(OUT/'worker_terminal.json',value)
    return value


def run(*,clock=time.monotonic,entries=None,executor=None,auditor=None,post=None):
    d=admission();ledger=read(OUT/'ledger.json')
    if ledger!=initial_ledger() or GLOBAL_CLAIM.exists() or list((OUT/'claims').iterdir()):
        raise FileExistsError('Continuation consumed/stopped; no restart')
    write_new(GLOBAL_CLAIM,{'protocol':PROTOCOL,'declaration_sha256':sha(OUT/'declaration.json'),
        'started_monotonic':clock(),'started_utc':now(),'prior_consumed':3,'remaining':37,'no_retry':True})
    try:
        started=clock();t=clock()
        if entries is None:
            from run_minimal_comparison import common_entry_points
            entries=common_entry_points()
        write_new(OUT/'imports.json',{'wall_s':clock()-t,'scope':'imports only; no warm model/cache/witness'})
        if executor is None:
            from dispatch import execute
            executor=execute
        auditor=auditor or prior.p.result_records
        post=post or prior.postcheck
        prep=read(prior.PREP/'declaration.json')
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
            okay=records['execution']['execution_status'] in prior.p.NORMAL and source_valid and not errors
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','run','inspect'));parser.add_argument('--checks',type=Path)
    args=parser.parse_args()
    if args.mode=='freeze':
        if args.checks is None:parser.error('--checks required')
        print(freeze(args.checks))
    elif args.mode=='inspect':print({'admitted':bool(admission()),'calendar_remaining_s':remaining_calendar()})
    else:raise SystemExit(0 if run() else 1)
