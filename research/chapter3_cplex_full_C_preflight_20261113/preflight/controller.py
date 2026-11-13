"""Finite, one-use D282 launcher. The only real worker cannot optimize."""
import time
ENTRY=time.perf_counter()
import argparse,json,subprocess,sys
from pathlib import Path
import psutil
from common import read,save,sha,verify_files,monitor_decision,classify,claim_once
from windows_job import Job

def run_owned(argv,out,t0,limits):
    """Shared by synthetic control children and the single frozen real worker."""
    out=Path(out);job=None;p=None;reason=None;cleanup=False;returncode=None
    samples=[];peak_private=peak_rss=0;initial_available=psutil.virtual_memory().available
    start=time.perf_counter();job_limits={};accounting={};error=None
    if initial_available<limits['minimum_available_at_entry_bytes']:
        return dict(stop_reason='ENTRY_MEMORY_LOW',cleanup_ok=True,worker_started=False,exit_code=None,
                    available_at_entry=initial_available,elapsed_s=time.perf_counter()-t0)
    try:
        job=Job(limits['worker_hard_commit_bytes'],active_limit=1);job_limits=job.limits()
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr,(out/'resources.jsonl').open('x',encoding='utf-8',newline='\n') as resources:
            p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,cwd=out,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(p)
            owned=psutil.Process(p.pid);parent=psutil.Process()
            save(out/'owned_process.json',dict(pid=p.pid,creation_time=owned.create_time(),job_limits=job_limits,
                started_elapsed_s=time.perf_counter()-t0,protected_before_go=True))
            p.stdin.write(b'D282_GO\n');p.stdin.flush();p.stdin.close()
            while p.poll() is None:
                now=time.perf_counter();available=psutil.virtual_memory().available
                try:
                    mi=owned.memory_info();cpu=owned.cpu_times();io=owned.io_counters()
                except psutil.NoSuchProcess:break
                parent_private=parent.memory_info().private
                sample=dict(elapsed_s=now-t0,worker_private=mi.private,worker_rss=mi.rss,
                    user_cpu_s=cpu.user,kernel_cpu_s=cpu.system,read_bytes=io.read_bytes,write_bytes=io.write_bytes,
                    parent_private=parent_private,available_bytes=available)
                resources.write(json.dumps(sample)+'\n');resources.flush()
                peak_private=max(peak_private,mi.private);peak_rss=max(peak_rss,mi.rss)
                reason=monitor_decision(now-t0,mi.private,parent_private,available,limits)
                if sum(f.stat().st_size for f in out.iterdir() if f.is_file())>limits['evidence_cap_bytes']:reason='EVIDENCE_SIZE_LIMIT'
                if reason:
                    job.terminate();break
                time.sleep(limits['sample_period_s'])
            remaining=min(limits['cleanup_reserve_s'],max(0,limits['total_window_s']-(time.perf_counter()-t0)))
            try:p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                reason=reason or 'CLEANUP_TIMEOUT';job.terminate()
                p.wait(timeout=2)
            until=time.perf_counter()+min(2,max(0,limits['total_window_s']-(time.perf_counter()-t0)))
            accounting=job.accounting()
            while accounting['active_processes'] and time.perf_counter()<until:
                time.sleep(.02);accounting=job.accounting()
            returncode=p.returncode;cleanup=p.poll() is not None and accounting['active_processes']==0
            job_limits=job.limits()
    except BaseException as e:
        error=dict(type=type(e).__name__,message=str(e));reason=reason or 'CONTROLLER_EXCEPTION'
    finally:
        if p is not None and p.poll() is None:
            try:
                if job:job.terminate()
                p.kill();p.wait(timeout=2)
            except BaseException as e:cleanup=False;error=dict(type='CleanupFailure',message=str(e))
        if job:
            try:
                accounting=job.accounting();job_limits=job.limits()
                cleanup=(p is None or p.poll() is not None) and accounting['active_processes']==0
                job.close()
            except BaseException as e:cleanup=False;error=dict(type='JobCleanupFailure',message=str(e))
    return dict(worker_started=p is not None,exit_code=p.returncode if p is not None else returncode,
        stop_reason=reason,error=error,cleanup_ok=cleanup,job=job_limits,job_accounting=accounting,
        peak_sampled_private_bytes=peak_private,peak_sampled_rss_bytes=peak_rss,
        available_at_entry=initial_available,run_and_cleanup_s=time.perf_counter()-start,
        elapsed_s=time.perf_counter()-t0)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--expected-sha',required=True)
    args=parser.parse_args();root=args.workspace.resolve();here=Path(__file__).resolve().parent
    plan_path=args.plan.resolve()
    if sha(plan_path)!=args.expected_sha:raise ValueError('Frozen plan identity mismatch')
    plan=read(plan_path)
    if plan['protocol']!='D282-CPLEX-C-native-load-no-solve-v1' or plan['maximum_native_model_loads']!=1 or plan['optimization_authorized'] is not False:
        raise ValueError('Unsupported scope')
    # The current D282 user request expressly authorizes this one no-solve load.
    # A plan file never grants a later scientific solve authorization.
    out=claim_once(root/plan['execution_directory'],dict(protocol=plan['protocol'],plan_sha256=args.expected_sha,
        user_decision_reference=plan['user_decision_reference'],authorization_scope='ONE_COMPLETE_C_NATIVE_LOAD_READBACK_ONLY',
        optimization_authorized=False,consumed=True,started_elapsed_s=time.perf_counter()-ENTRY))
    stop=None;owned={};worker=None
    try:
        verify_files(here,plan['code_hashes']);verify_files(root,plan['input_hashes'])
        for path,h in plan['runtime_hashes'].items():
            if sha(path)!=h:raise ValueError('Installed runtime drift')
        if time.perf_counter()-ENTRY>=plan['limits']['worker_deadline_s']:raise TimeoutError('No startup budget')
        argv=[plan['python'],'-B',str(here/'worker.py'),'--workspace',str(root),'--plan',str(plan_path),
              '--output',str(out),'--t0',repr(ENTRY)]
        owned=run_owned(argv,out,ENTRY,plan['limits'])
        if (out/'worker_receipt.json').exists():
            if (out/'worker_receipt.json').stat().st_size>1024*1024:raise ValueError('Oversize worker receipt')
            worker=read(out/'worker_receipt.json')
        stop=owned.get('stop_reason') or classify(worker,owned.get('exit_code'),owned.get('cleanup_ok'),time.perf_counter()-ENTRY,plan['limits'])
        verify_files(here,plan['code_hashes']);verify_files(root,plan['input_hashes'])
    except BaseException as e:stop='INTEGRITY_OR_CONTROLLER_FAILURE';owned['exception']=dict(type=type(e).__name__,message=str(e))
    files={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    elapsed=time.perf_counter()-ENTRY
    if elapsed>plan['limits']['total_window_s']:stop='TOTAL_WINDOW_EXCEEDED'
    save(out/'controller_receipt.json',dict(status=stop,passed=stop=='PASS',plan_sha256=args.expected_sha,
        method_elapsed_s=elapsed,owned=owned,scientific_evidence_hashes=files,
        optimization_calls=0,no_retry=True,authorization_consumed=True))
    print(json.dumps(dict(status=stop,elapsed_s=time.perf_counter()-ENTRY,output=str(out)),ensure_ascii=True))
    return 0 if stop=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
