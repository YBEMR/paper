"""Bounded one-method/one-post orchestration with explicit process injection.

SIMULATION factories are tested in-process and are never called real fresh
Python evidence. No production process factory or approval consumer exists in
this release. The actual OS boundary still needs the approved single run.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from .gating import require_permit


def run_once(plan,workdir,*,permit,process_factory,clock=time.monotonic):
    kind=require_permit(permit)
    if kind!='SIMULATION' or not callable(process_factory):
        raise PermissionError('ONLY_EXPLICIT_SIMULATED_PROCESS_FACTORY_ALLOWED')
    expected=(plan['research_method_calls_max'],plan['method_seconds_max'],plan['post_calls_max'],
              plan['post_seconds_max'],plan['method_process_wall_seconds'],plan['batch_wall_seconds'])
    if expected!=(1,300,1,60,480,720) or plan.get('retry_count')!=0:
        raise ValueError('UNAPPROVED_BATCH_SCOPE')
    folder=Path(workdir);folder.mkdir(parents=True,exist_ok=False)
    started=clock()
    records={'schema':'g0-one-shot-simulated-supervision-v1','evidence_kind':kind,
        'real_os_process_validation':False,'method_calls':0,'post_calls':0,
        'method':None,'post':None,'stop_reason':None,'events':[]}
    # This is an isolated simulation receipt, not a real research approval claim.
    (folder/'simulation_once.json').write_text(json.dumps({'kind':kind,'one_method_only':True}),encoding='utf-8')
    def remaining():return max(0.,720-(clock()-started))
    try:
        if remaining()<=0:
            records['stop_reason']='BATCH_DEADLINE_BEFORE_METHOD';return records
        records['method_calls']=1
        cap=min(480.,remaining()); slot_start=clock()
        method=process_factory('method',limit_s=cap,method_seconds=300)
        records['method']=deepcopy(method)
        records['method_process_observed_s']=clock()-slot_start
        if clock()-slot_start>cap or remaining()<=0:
            records['stop_reason']='METHOD_PROCESS_DEADLINE';return records
        if method.get('process_state') not in ('COMPLETED','NORMAL_TIME_LIMIT'):
            records['stop_reason']='METHOD_PROCESS_STOP';return records
        result=method.get('result') or {}
        if result.get('execution_state') not in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT'):
            records['stop_reason']='METHOD_FAULT_OR_UNRESOLVED';return records
        if result.get('post_eligible') and result.get('safe_retained') and remaining()>=60:
            records['post_calls']=1
            slot_start=clock()
            post=process_factory('post',limit_s=60,method_seconds=None,candidate=deepcopy(result['safe_candidate']))
            records['post']=deepcopy(post)
            records['post_process_observed_s']=clock()-slot_start
            if clock()-slot_start>60 or remaining()<=0:
                records['stop_reason']='POST_PROCESS_DEADLINE';return records
            state=(post.get('result') or {}).get('state')
            records['stop_reason']='POST_'+str(state) if state in ('THERMAL_VIOLATION','INVALID_SCHEDULE','UNRESOLVED') else (
                'COMPLETED' if state=='SAFE' and post.get('process_state')=='COMPLETED' else 'POST_TECHNICAL_STOP')
        elif result.get('safe_retained'):
            records['stop_reason']='POST_NOT_AUTHORIZED_OR_INSUFFICIENT_FULL_BUDGET'
        else:
            records['stop_reason']='NO_COMPLETE_SAFE_NO_POST'
    except Exception as error:
        records.update(stop_reason='TECHNICAL_FAILURE',error_type=type(error).__name__,error=str(error))
    finally:
        records['batch_elapsed_s']=clock()-started
        (folder/'batch.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    return records
