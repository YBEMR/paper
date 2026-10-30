"""Single G0 process plus optional independent post. No legacy method queue."""
from pathlib import Path
import secrets
import subprocess
import time
from fractions import Fraction

from .launch_contract import (ROOT,HERE,INPUT,SCOPE,sha,read,save,digest,
                              load_authorized,consume_claim,verify_plan)
from ..chapter3_method_entry_executor.monitor import ProcessMonitor,default_host_probe,host_gate


class Runtime:
    clock=staticmethod(time.monotonic)
    sleep=staticmethod(time.sleep)
    monitor=staticmethod(ProcessMonitor)
    probe=staticmethod(default_host_probe)
    @staticmethod
    def launch(args,stdout,stderr):
        return subprocess.Popen(args,cwd=str(ROOT),stdout=stdout,stderr=stderr,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def _slot(ctx,output,mode,batch_deadline,rt,candidate=None):
    """Internal test seam only. Production run() always constructs Runtime."""
    folder=Path(output)/mode;folder.mkdir(exist_ok=False)
    start=rt.clock();cap=480 if mode=='method' else 60
    if batch_deadline-start<cap:raise TimeoutError('INSUFFICIENT_FULL_SLOT_BUDGET')
    token=secrets.token_hex(24)
    t={'mode':mode,'token':token,'plan_sha256':ctx['plan_sha256'],
       'approval_sha256':ctx['approval_sha256'],'process_started_monotonic_s':start,
       'absolute_deadline_monotonic_s':start+cap}
    if mode=='post':t.update(candidate=candidate,candidate_sha256=digest(candidate))
    save(folder/'ticket.json',t,exclusive=True)
    args=[ctx['plan']['python_executable'],'-B','-m','research.chapter3_g0_real_entry.actual_worker',
          '--plan',ctx['plan_file'],'--approval',ctx['approval_file'],
          '--approval-sha256',ctx['approval_sha256'],'--ticket',str(folder/'ticket.json'),
          '--token',token,'--mode',mode]
    proc=monitor=None;released=False
    result={'mode':mode,'process_started_monotonic_s':start,'wall_limit':False,'error':None,
            'worker':None,'cleanup_verified':None,'returncode':None}
    try:
        with (folder/'stdout.txt').open('x',encoding='utf-8') as out,(folder/'stderr.txt').open('x',encoding='utf-8') as err:
            save(folder/'launch_attempt.json',{'ticket_sha256':sha(folder/'ticket.json')},exclusive=True)
            proc=rt.launch(args,out,err);result['pid']=proc.pid
            monitor=rt.monitor(proc.pid,clock=rt.clock)
            monitor.sample(force=True)
            if monitor.root_identity is None:raise RuntimeError('UNVERIFIED_WORKER_OWNERSHIP')
            save(folder/'monitor_ready.json',{'token':token,'plan_sha256':ctx['plan_sha256'],'pid':proc.pid})
            released=True
            while proc.poll() is None:
                monitor.sample()
                if rt.clock()>=t['absolute_deadline_monotonic_s']:
                    result['wall_limit']=True;monitor.terminate_owned(force=True);break
                rt.sleep(min(.25,t['absolute_deadline_monotonic_s']-rt.clock()))
            result['returncode']=proc.poll()
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e)
        if monitor is not None:monitor.terminate_owned(force=True)
        elif proc is not None and not released:proc.kill()
    finally:
        # Cleanup has no permission to evaluate candidates or spawn another worker.
        if monitor is not None:
            try:
                session=folder/'work'/'matlab'/'session.json'
                if mode=='method' and session.is_file():
                    tree=read(session).get('process_tree_at_ready',{})
                    monitor.register_identities(tree.get('identities',[]),source='same-slot MATLAB session file')
                if monitor.cleanup_verified() is not True:monitor.terminate_owned(force=True)
                end=min(batch_deadline,start+cap,rt.clock()+10)
                while monitor.cleanup_verified() is False and rt.clock()<end:rt.sleep(.1)
                result['cleanup_verified']=monitor.cleanup_verified()
                save(folder/'memory.json',{'summary':monitor.summary(),'samples':monitor.samples,
                     'scope':'observed PID/create-time only; sampled RSS, not OS containment'})
            except Exception as e:result['error']='MONITOR_CLEANUP:'+str(e)
        f=folder/'result.json'
        if f.is_file():
            try:
                envelope=read(f)
                if (envelope.get('plan_sha256')!=ctx['plan_sha256'] or envelope.get('token')!=token
                        or envelope.get('input_sha256')!=ctx['plan']['input_sha256']):
                    raise ValueError('WORKER_RECEIPT_IDENTITY')
                result['worker']=envelope
            except Exception as e:result['error']='RECEIPT:'+str(e)
        result['process_elapsed_s']=rt.clock()-start
        result['within_process_deadline']=result['process_elapsed_s']<=cap
        save(folder/'slot_result.json',result)
    return result


def post_state(slot,method,instance):
    """Semantic negative receipts outrank expected nonzero exit codes."""
    if slot.get('error') or slot.get('cleanup_verified') is not True:return 'TECHNICAL_FAILURE'
    envelope=slot.get('worker') or {};p=envelope.get('result') or {};state=p.get('state')
    if not slot.get('within_process_deadline'):return 'POST_TIME_LIMIT_UNRESOLVED'
    if p.get('identity')!={'input_sha256':digest(instance),'candidate_sha256':digest(method['safe_candidate'])}:
        return 'POST_IDENTITY_CONFLICT'
    if slot.get('returncode') not in (0,2):return 'POST_TECHNICAL_FAILURE'
    if state in ('THERMAL_VIOLATION','INVALID_SCHEDULE','UNRESOLVED'):return 'POST_'+state
    if state!='SAFE' or slot.get('returncode')!=0:return 'POST_TECHNICAL_FAILURE'
    raw=p.get('evaluation') or {};scenes=raw.get('scenes') or {}
    ids={s['id'] for s in instance['scenarios']}
    if (raw.get('rankable_energy') is not True or set(scenes)!=ids
            or any(v.get('state')!='SAFE' or v.get('complete') is not True
                   or Fraction(v.get('covered_until_s','-1'))!=Fraction(instance['window_ms'])/1000
                   for v in scenes.values())):return 'POST_INCOMPLETE_RECEIPT'
    try:
        a,b=map(Fraction,method['weighted_energy_J']);c,d=map(Fraction,raw['weighted_energy_J'])
        if min(a,c)<0 or a>b or c>d or max(a,c)>min(b,d):return 'POST_ENERGY_CONFLICT'
    except Exception:return 'POST_INCOMPLETE_RECEIPT'
    return 'COMPLETE_POST_SAFE'


def run(plan_file,approval_file,approval_sha256,output):
    """Real dispatcher. Calling requires a later explicit user budget approval."""
    rt=Runtime();start=rt.clock();deadline=start+720
    ctx=load_authorized(plan_file,approval_file,approval_sha256)
    gate=host_gate(rt.probe(ROOT))
    if not gate['passed']:raise RuntimeError('HOST_GATE_FAILED_NO_CLAIM')
    claim=consume_claim(ctx,output)
    report={'plan_sha256':ctx['plan_sha256'],'claim':str(claim),'method_calls':0,'post_calls':0,
            'method':None,'post':None,'recovery':None,'stop_reason':None}
    output=Path(output)
    save(output/'host_prelaunch.json',gate)
    try:
        report['method_calls']=1
        method=_slot(ctx,output,'method',deadline,rt);report['method']=method
        verify_plan(ctx['plan'])
        common=read(ROOT/INPUT)
        from .persistence import recover
        report['recovery']=recover(output/'method'/'work'/'checkpoints',ctx,common['config'],
                                  common['instance'],method['process_started_monotonic_s'])
        m=((method.get('worker') or {}).get('result') or {})
        if (method['error'] or method['cleanup_verified'] is not True or method['wall_limit']
                or method['returncode']!=0 or not method['within_process_deadline']):
            report['stop_reason']='METHOD_ABNORMAL_SAFE_CHECKPOINT_PRESERVED';return report
        if m.get('execution_state') not in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT'):
            report['stop_reason']='METHOD_FAULT_OR_NO_SAFE';return report
        if m.get('safe_retained') and m.get('post_eligible'):
            verify_plan(ctx['plan'])
            if deadline-rt.clock()<60:raise TimeoutError('NO_FULL_POST_BUDGET')
            report['post_calls']=1
            post=_slot(ctx,output,'post',deadline,rt,m['safe_candidate']);report['post']=post
            report['stop_reason']=post_state(post,m,common['instance'])
        else:report['stop_reason']='NO_COMPLETE_SAFE_NO_POST'
    except Exception as e:report['stop_reason']='TECHNICAL_STOP:'+type(e).__name__+': '+str(e)
    finally:
        report['batch_elapsed_s']=rt.clock()-start
        save(output/'batch.json',report)
    return report


def main():
    import argparse
    p=argparse.ArgumentParser()
    for x in ('plan','approval','approval-sha256','output'):p.add_argument('--'+x,required=True)
    a=p.parse_args()
    print(run(a.plan,a.approval,a.approval_sha256,a.output)['stop_reason'])


if __name__=='__main__':main()
