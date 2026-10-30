"""Fresh process bootstrap. Never executed by preparation or simulations."""
import argparse
import os
from pathlib import Path
import time


def main():
    p=argparse.ArgumentParser()
    for k in ('plan','approval','approval-sha256','ticket','token','mode'):p.add_argument('--'+k,required=True)
    a=p.parse_args()
    from .launch_contract import read,save
    t=read(a.ticket);folder=Path(a.ticket).parent
    while not (folder/'monitor_ready.json').is_file():
        if time.monotonic()>=t['absolute_deadline_monotonic_s']:return 3
        time.sleep(.01)
    from .gating import consume_worker_ticket
    permit=consume_worker_ticket(a.plan,a.approval,a.approval_sha256,a.ticket,a.token,a.mode)
    from .launch_contract import ROOT,INPUT
    from .worker import execute_method,execute_post
    start=t['process_started_monotonic_s']
    exitcode=0
    try:
        if a.mode=='method':
            result=execute_method(ROOT/INPUT,permit.context['plan']['input_sha256'],folder/'work',
                                  permit=permit,started_at=start)
        else:
            result=execute_post(ROOT/INPUT,permit.context['plan']['input_sha256'],t['candidate'],
                                permit=permit,started_at=start)
    except Exception as e:
        result={'state':'TECHNICAL_FAILURE','execution_state':'TECHNICAL_FAILURE',
                'error_type':type(e).__name__,'reason':str(e)}
        exitcode=1
    envelope={'token':a.token,'plan_sha256':permit.context['plan_sha256'],
              'input_sha256':permit.context['plan']['input_sha256'],'result':result}
    save(folder/'result.json',envelope)
    return 2 if a.mode=='post' and result.get('state') in ('THERMAL_VIOLATION','INVALID_SCHEDULE') else exitcode


if __name__=='__main__':raise SystemExit(main())
