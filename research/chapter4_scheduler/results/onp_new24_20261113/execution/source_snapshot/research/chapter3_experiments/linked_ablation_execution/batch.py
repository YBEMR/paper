"""K173 six-slot once-only orchestration; no scientific module imports."""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
SCIENCE=HERE.parent
REPO=SCIENCE.parents[1]
OUT=SCIENCE/'results/linked_ablation_execution01'
GLOBAL_CLAIM=SCIENCE/'results/linked_ablation_execution_claim01.json'
if str(SCIENCE) not in sys.path:sys.path.insert(0,str(SCIENCE))
from linked_ablation_execution import registry
PROTOCOL=registry.PROTOCOL
COUNT=6
METHOD_SECONDS=300
POST_SECONDS=60
CALENDAR_SECONDS=3600
METHOD_RETURN_SECONDS=420
SLOT_SECONDS=480


def now():return datetime.now(timezone.utc)
def sha(path):return registry.sha(path)
def read(path):return registry.read(path)


def write_new(path,value):
    return registry.write_new(path,value)


def save(path,value):
    return registry.save(path,value)


def expected_slots():
    return [{'ordinal':i+1,'slot_id':case+'__'+arm,'case_id':case,'variant':arm,
             'method_seconds':300,'post_seconds_max':60}
        for i,(case,arm) in enumerate((('base__R1','A'),('base__R1','B'),('base__R1','C'),
                                      ('base__R3','C'),('base__R3','B'),('base__R3','A')))]


def load_declaration(path):
    return registry.load_declaration(Path(path))


def require_slots(declaration):
    actual=declaration.get('slots')
    if not isinstance(actual,list) or len(actual)!=COUNT:raise ValueError('exactly six frozen slots required')
    for slot,expected in zip(actual,expected_slots()):
        if any(slot.get(k)!=v for k,v in expected.items()):raise ValueError('fixed six-slot order/budget drift')
    return actual


def initial_ledger():
    return {'protocol':PROTOCOL,'state':'DECLARED','consumed':0,
        'reserved_method_budget_s':0,'post_consumed':0,'reserved_post_budget_s':0,
        'calls':[],'active':None}


def remaining_calendar(global_claim,clock,utc_clock):
    utc_stop=datetime.fromisoformat(global_claim['calendar_deadline_utc'])
    return min(global_claim['calendar_deadline_monotonic']-clock(),
               (utc_stop-utc_clock()).total_seconds())


def status(ledger,phase):
    save(OUT/'status.json',{'protocol':PROTOCOL,'state':ledger['state'],'phase':phase,
        'consumed':ledger['consumed'],'reserved_method_budget_s':ledger['reserved_method_budget_s'],
        'post_consumed':ledger['post_consumed'],'active':ledger['active'],'updated_utc':now().isoformat()})


def actual_consumption():
    consumed=sum((OUT/'claims'/(s['slot_id']+'.json')).is_file() for s in expected_slots())
    posts=sum((OUT/'claims'/(s['slot_id']+'__post.json')).is_file() for s in expected_slots())
    return consumed,posts


def terminal(state,*,error=None,global_claim=None):
    consumed,posts=actual_consumption()
    result={'protocol':PROTOCOL,'state':state,'consumed':consumed,
        'reserved_method_budget_s':consumed*300,'post_consumed':posts,
        'reserved_post_budget_s':posts*60,'unstarted_slots':COUNT-consumed,
        'error':error,'ended_utc':now().isoformat(),'no_retry':True,
        'claim_files_override_stale_progress':True,'research_result_created_by_batch':False}
    if global_claim is not None:result['calendar_deadline_utc']=global_claim['calendar_deadline_utc']
    write_new(OUT/'batch_terminal.json',result)
    return result


def claim_slot(ledger,slot,global_claim,*,clock,utc_clock):
    n=ledger['consumed']
    if (n>=COUNT or slot!=require_slots({'slots':expected_slots()})[n]
        or ledger.get('active') is not None or ledger['reserved_method_budget_s']!=n*300
        or [r['slot_id'] for r in ledger['calls']]!=[s['slot_id'] for s in expected_slots()[:n]]
        or ledger['state'] not in ('DECLARED','RUNNING')):
        raise ValueError('once-only prefix/order/reservation mismatch')
    if remaining_calendar(global_claim,clock,utc_clock)<=0:raise TimeoutError('CALENDAR_LIMIT_BEFORE_CLAIM')
    stamp=clock()
    record=dict(slot,protocol=PROTOCOL,declaration_sha256=global_claim['declaration_sha256'],
        claimed_utc=utc_clock().isoformat(),slot_start_monotonic=stamp,
        slot_deadline_monotonic=min(stamp+SLOT_SECONDS,global_claim['calendar_deadline_monotonic']),
        state='CONSUMED_BEFORE_LAUNCH',no_retry=True)
    # The immutable claim is authoritative even if the next ledger write fails.
    write_new(OUT/'claims'/(slot['slot_id']+'.json'),record)
    ledger['calls'].append(record)
    ledger.update(state='RUNNING',consumed=n+1,reserved_method_budget_s=(n+1)*300,
        active={'slot_id':slot['slot_id'],'phase':'METHOD',
                'slot_start_monotonic':stamp,'slot_deadline_monotonic':record['slot_deadline_monotonic']})
    save(OUT/'ledger.json',ledger);status(ledger,'METHOD')
    return record


def process_ok(receipt):
    return (isinstance(receipt,dict) and receipt.get('returncode')==0
        and receipt.get('process_closed') is True and receipt.get('watchdog_stop') is None)


def run(declaration_path,*,executor=None,auditor=None,post=None,post_auditor=None,
        declaration_loader=None,clock=time.monotonic,utc_clock=now):
    """Run exact fixed prefix once; injection points support pure fake tests."""
    declaration_path=Path(declaration_path)
    loader=load_declaration if declaration_loader is None else declaration_loader
    declaration=loader(declaration_path)
    slots=require_slots(declaration)
    # Ignore non-execution proposal state fields; registry owns authorization.
    slots=[{k:s[k] for k in expected_slots()[0]} for s in slots]
    if declaration_path.resolve()!= (OUT/'declaration.json').resolve():
        raise ValueError('only frozen linked_ablation_execution01 declaration is executable')
    if GLOBAL_CLAIM.exists() or (OUT/'batch_terminal.json').exists():raise FileExistsError('campaign already consumed/stopped; no restart')
    if (OUT/'ledger.json').exists() and read(OUT/'ledger.json')!=initial_ledger():
        raise FileExistsError('nonempty campaign ledger cannot restart')
    for name in ('claims','calls'):(OUT/name).mkdir(parents=True,exist_ok=True)
    if any((OUT/'claims').iterdir()) or any((OUT/'calls').iterdir()):raise FileExistsError('existing claims/calls forbid restart')
    started_mono=clock();started_utc=utc_clock()
    global_claim={'protocol':PROTOCOL,'declaration_sha256':sha(declaration_path),
        'started_monotonic':started_mono,'started_utc':started_utc.isoformat(),
        'calendar_deadline_monotonic':started_mono+CALENDAR_SECONDS,
        'calendar_deadline_utc':(started_utc+timedelta(seconds=CALENDAR_SECONDS)).isoformat(),
        'call_limit':6,'method_seconds_limit':1800,'post_calls_limit':6,'post_seconds_limit':360,
        'no_retry':True,'calendar_not_restarted':True}
    write_new(GLOBAL_CLAIM,global_claim)
    ledger=initial_ledger()
    try:
        save(OUT/'ledger.json',ledger);status(ledger,'STARTED')
        if executor is None or post is None:
            from linked_ablation_execution import supervise
            executor=supervise.run_method if executor is None else executor
            post=supervise.run_post if post is None else post
        if auditor is None or post_auditor is None:
            from linked_ablation_execution import audit
            auditor=audit.audit_slot if auditor is None else auditor
            post_auditor=audit.audit_post if post_auditor is None else post_auditor
        for slot in slots:
            if remaining_calendar(global_claim,clock,utc_clock)<=0:
                ledger.update(state='STOPPED_CALENDAR_LIMIT',active=None)
                save(OUT/'ledger.json',ledger)
                return terminal(ledger['state'],global_claim=global_claim)
            current=loader(declaration_path)
            if current!=declaration or sha(declaration_path)!=global_claim['declaration_sha256']:
                raise ValueError('frozen declaration/source drift before new call')
            folder=OUT/'calls'/slot['slot_id']
            if folder.exists():raise FileExistsError('new child output folder already exists before consumption')
            row=claim_slot(ledger,slot,global_claim,clock=clock,utc_clock=utc_clock)
            folder.mkdir(exist_ok=False)
            errors=[]
            try:
                process=executor(slot,folder,declaration_path,
                    slot_deadline_monotonic=row['slot_deadline_monotonic'],
                    calendar_deadline_utc=global_claim['calendar_deadline_utc'],clock=clock)
            except BaseException:
                errors.append(traceback.format_exc())
                process={'returncode':None,'process_closed':False,'watchdog_stop':'EXECUTOR_EXCEPTION',
                         'error':errors[-1]}
            write_new(folder/'method_process.json',process)
            source_ok=True
            try:
                if loader(declaration_path)!=declaration or sha(declaration_path)!=global_claim['declaration_sha256']:
                    raise ValueError('source/declaration drift after method')
            except BaseException:
                source_ok=False;errors.append(traceback.format_exc())
            okay=process_ok(process) and source_ok and not errors
            if okay:
                try:method_audit=auditor(folder,slot,declaration)
                except BaseException:
                    errors.append(traceback.format_exc());method_audit={'passed':False,'can_continue':False,
                        'eligible_for_post':False,'classification':'AUDIT_EXCEPTION','error':errors[-1]}
            else:
                method_audit={'passed':False,'can_continue':False,'eligible_for_post':False,
                    'classification':'PROCESS_OR_SOURCE_FAILURE','errors':errors}
            write_new(folder/'audit.json',method_audit)
            row.update(method_process=process,method_audit=method_audit,errors=errors)
            write_new(OUT/'claims'/(slot['slot_id']+'__method_return.json'),row)
            okay=(okay and method_audit.get('passed') is True and method_audit.get('can_continue') is True
                  and type(method_audit.get('eligible_for_post')) is bool)
            if okay and method_audit.get('eligible_for_post') is True:
                if clock()>=row['slot_deadline_monotonic'] or remaining_calendar(global_claim,clock,utc_clock)<=0:
                    okay=False;row['post_audit']={'passed':False,'reason':'NO_TIME_FOR_UNIQUE_POST'}
                else:
                    post_inputs={name:sha(folder/name) for name in
                        ('result.json','wrapper_raw_result.json','input_config.json','input_instance.json')}
                    write_new(OUT/'claims'/(slot['slot_id']+'__post.json'),
                        {'slot_id':slot['slot_id'],'post_seconds':60,'claimed_utc':utc_clock().isoformat(),
                         'no_retry':True,'new_U':False})
                    ledger['post_consumed']+=1;ledger['reserved_post_budget_s']+=60
                    ledger['active'].update(phase='POST');save(OUT/'ledger.json',ledger);status(ledger,'POST')
                    try:
                        post_process=post(slot,folder,declaration_path,
                            slot_deadline_monotonic=row['slot_deadline_monotonic'],
                            calendar_deadline_utc=global_claim['calendar_deadline_utc'],clock=clock)
                    except BaseException:
                        errors.append(traceback.format_exc());post_process={'returncode':None,
                            'process_closed':False,'watchdog_stop':'POST_EXECUTOR_EXCEPTION','error':errors[-1]}
                    write_new(folder/'post_process.json',post_process)
                    try:
                        if loader(declaration_path)!=declaration or sha(declaration_path)!=global_claim['declaration_sha256']:
                            raise ValueError('source/declaration drift after post')
                        post_result=(post_auditor(folder,slot,declaration,method_audit)
                            if process_ok(post_process) else {'passed':False,'new_U':False,'reason':'POST_PROCESS_FAILURE'})
                        preserved={name:sha(folder/name) for name in post_inputs}
                        if preserved!=post_inputs:
                            post_result={'passed':False,'new_U':False,'reason':'POST_CHANGED_METHOD_EVIDENCE',
                                'before':post_inputs,'after':preserved}
                    except BaseException:
                        errors.append(traceback.format_exc());post_result={'passed':False,'new_U':False,'error':errors[-1]}
                    write_new(folder/'post_audit.json',post_result)
                    row.update(post_process=post_process,post_audit=post_result)
                    okay=(post_result.get('passed') is True and post_result.get('new_U') is False
                          and process_ok(post_process) and not errors)
            elif okay:
                row['post_audit']={'passed':True,'new_U':False,'state':'NOT_APPLICABLE_NO_SAFE_U'}
            row.update(state='COMPLETED' if okay else 'BLOCKED',ended_utc=utc_clock().isoformat(),
                slot_wall_seconds=clock()-row['slot_start_monotonic'])
            write_new(OUT/'claims'/(slot['slot_id']+'__result.json'),row)
            ledger.update(state='RUNNING' if okay else 'BLOCKED',active=None)
            save(OUT/'ledger.json',ledger);status(ledger,'BETWEEN_SLOTS')
            if not okay:return terminal('BLOCKED',global_claim=global_claim)
        ledger.update(state='COMPLETED',active=None)
        save(OUT/'ledger.json',ledger);status(ledger,'COMPLETED')
        return terminal('COMPLETED',global_claim=global_claim)
    except BaseException:
        error=traceback.format_exc()
        try:return terminal('STOPPED_EXCEPTION',error=error,global_claim=global_claim)
        except BaseException:
            consumed,posts=actual_consumption()
            return {'state':'STOPPED_EXCEPTION_UNARCHIVED','consumed':consumed,
                'reserved_method_budget_s':consumed*300,'post_consumed':posts,
                'error':error,'terminal_archive_error':traceback.format_exc(),'no_retry':True}


if __name__=='__main__':
    if str(SCIENCE) not in sys.path:sys.path.insert(0,str(SCIENCE))
    parser=argparse.ArgumentParser();parser.add_argument('--declaration',type=Path,required=True)
    outcome=run(parser.parse_args().declaration)
    print(json.dumps(outcome,ensure_ascii=False))
    raise SystemExit(0 if outcome['state']=='COMPLETED' else 1)
