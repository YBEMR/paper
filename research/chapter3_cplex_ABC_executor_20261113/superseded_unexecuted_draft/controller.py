"""D283 parent owns process, arrival clocks, limits and final revocation."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,json,os,secrets,subprocess,sys,threading
from pathlib import Path
import psutil
from core import read,save,sha,verify,authorize,Clock,receive_response,IntegrityError,error_record,stop_scope,safe_interval
from windows_job import Job

def emergency_watchdog(out,clock,deadline=620):
    def run():
        delay=max(0,deadline-clock.elapsed)
        time.sleep(delay)
        # Exit releases owned Job handles (KILL_ON_JOB_CLOSE). No scientific credit.
        try:
            p=Path(out)/'emergency_watchdog.txt'
            with p.open('xb') as f:f.write(b'EMERGENCY_DEADLINE; no post-window scientific credit\n');f.flush()
        finally: os._exit(124)
    t=threading.Thread(target=run,name='D283 emergency cleanup watchdog',daemon=True);t.start()

def monitor_reason(elapsed,private,parent_private,available,ack,limits):
    import math
    if any(not math.isfinite(x) or x<0 for x in (elapsed,private,parent_private,available)): return 'INVALID_MONITOR'
    if elapsed>=limits['scientific_seal_s']: return 'SCIENTIFIC_WINDOW_EXPIRED'
    if elapsed>=limits['native_response_cutoff_s'] and not ack: return 'NATIVE_RESPONSE_DEADLINE'
    if private>=limits['worker_soft_private_bytes']: return 'WORKER_MEMORY_LIMIT'
    if parent_private>=limits['parent_private_bytes']: return 'CONTROLLER_MEMORY_LIMIT'
    if available<limits['system_available_floor_bytes']: return 'SYSTEM_MEMORY_LOW'
    return None

class ParentEvents:
    def __init__(self,out,clock):
        self.out=Path(out);self.clock=clock;self.offset=0;self.buffer=b'';self.rows=[]
        self.f=(self.out/'parent_events.jsonl').open('x',encoding='utf-8',newline='\n')
    def poll(self):
        p=self.out/'events.jsonl'
        if not p.exists():return
        with p.open('rb') as f:f.seek(self.offset);chunk=f.read(256*1024);self.offset+=len(chunk)
        self.buffer+=chunk
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            row=dict(parent_received_elapsed_s=self.clock.elapsed,event=json.loads(line))
            self.f.write(json.dumps(row,allow_nan=False)+'\n');self.f.flush();self.rows.append(row)
        if len(self.buffer)>1024*1024: raise IntegrityError('Oversize observation line')
    def close(self):self.f.close()
    def finish(self):
        p=self.out/'events.jsonl'
        while p.exists() and self.offset<p.stat().st_size and self.clock.elapsed<590:self.poll()
        size=p.stat().st_size if p.exists() else 0
        return dict(bytes_read=self.offset,file_bytes=size,trailing_partial_bytes=len(self.buffer),
                    complete=self.offset==size and not self.buffer,completed_elapsed_s=self.clock.elapsed)

def run_owned(argv,out,clock,limits,plan_hash,nonce,job_class=Job):
    out=Path(out);job=None;p=None;cleanup=False;reason=None;errors=[];ack=None;events=None
    accounting={};job_info={};observation_read={};peak=0;parent_peak=0;available=psutil.virtual_memory().available
    if available<limits['minimum_available_at_entry_bytes']:
        return dict(stop_reason='ENTRY_MEMORY_LOW',cleanup_ok=True,worker_started=False,errors=[],available_at_entry=available,events=[])
    try:
        job=job_class(limits['job_and_process_hard_commit_bytes'],active_limit=1);job_info=job.limits()
        events=ParentEvents(out,clock)
        with (out/'stdout.log').open('xb') as stdout,(out/'stderr.log').open('xb') as stderr,(out/'resources.jsonl').open('x',encoding='utf-8',newline='\n') as resources:
            p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=stdout,stderr=stderr,cwd=out,creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(p);owned=psutil.Process(p.pid);parent=psutil.Process()
            save(out/'owned_process.json',dict(pid=p.pid,creation_time=owned.create_time(),job_limits=job_info,protected_before_GO=True,elapsed_s=clock.elapsed))
            p.stdin.write(('D283_GO '+nonce+'\n').encode());p.stdin.flush();p.stdin.close()
            while True:
                events.poll()
                if ack is None and (out/'native_response.json').exists():
                    ack=receive_response(out,clock,plan_hash);save(out/'response_ack.json',ack)
                    if not ack['timely']:reason='LATE_NATIVE_RESPONSE'
                if p.poll() is not None:break
                try:mi=owned.memory_info();cpu=owned.cpu_times();io=owned.io_counters()
                except psutil.NoSuchProcess:continue
                avail=psutil.virtual_memory().available;pm=parent.memory_info().private
                peak=max(peak,mi.private);parent_peak=max(parent_peak,pm)
                resources.write(json.dumps(dict(elapsed_s=clock.elapsed,private_bytes=mi.private,rss_bytes=mi.rss,parent_private_bytes=pm,system_available_bytes=avail,user_cpu_s=cpu.user,kernel_cpu_s=cpu.system,read_bytes=io.read_bytes,write_bytes=io.write_bytes))+'\n');resources.flush()
                reason=reason or monitor_reason(clock.elapsed,mi.private,pm,avail,bool(ack and ack['timely']),limits)
                if sum(f.stat().st_size for f in out.iterdir() if f.is_file())>=limits['evidence_cap_bytes']:reason=reason or 'EVIDENCE_SIZE_LIMIT'
                if reason:
                    save(out/'parent_stop.json',dict(reason=reason,elapsed_s=clock.elapsed));job.terminate();break
                time.sleep(limits['sample_period_s'])
            remaining=max(0,min(10,limits['total_window_s']-clock.elapsed))
            try:p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:reason=reason or 'CLEANUP_TIMEOUT';job.terminate();p.wait(timeout=2)
            observation_read=events.finish();accounting=job.accounting();job_info=job.limits()
            # Process exit and Job accounting completion are distinct observations.
            # Charge a bounded wait to the existing method/cleanup budget.
            until=clock.now()+min(2,max(0,limits['total_window_s']-clock.elapsed))
            while accounting['active_processes'] and clock.now()<until:
                time.sleep(.02);accounting=job.accounting()
            cleanup=p.poll() is not None and accounting['active_processes']==0
    except BaseException as e:
        errors.append(error_record(e));reason=reason or ('EVIDENCE_INTEGRITY' if isinstance(e,IntegrityError) else 'CONTROLLER_ERROR')
    finally:
        if p is not None and p.poll() is None:
            try:
                if job:job.terminate()
                p.kill();p.wait(timeout=min(2,max(.01,620-clock.elapsed)))
            except BaseException as e:errors.append(error_record(e))
        if job:
            try:
                accounting=job.accounting();job_info=job.limits()
                cleanup=(p is None or p.poll() is not None) and accounting['active_processes']==0
                job.close()
            except BaseException as e:cleanup=False;errors.append(error_record(e))
        if events:events.close()
    return dict(stop_reason=reason,cleanup_ok=cleanup,worker_started=p is not None,exit_code=p.returncode if p else None,
        errors=errors,response_ack=ack,job=job_info,job_accounting=accounting,events=events.rows if events else [],
        available_at_entry=available,peak_sampled_private_bytes=peak,peak_parent_private_bytes=parent_peak,cleanup_elapsed_s=clock.elapsed,observation_read=observation_read)

def accept_snapshot(out,clock,plan_hash,owned):
    """No late read can upgrade evidence. Integrity and cleanup can only revoke it."""
    out=Path(out);reasons=[];snap=None
    if not owned.get('cleanup_ok'):reasons.append('CLEANUP_FAILURE')
    if owned.get('stop_reason'):reasons.append(owned['stop_reason'])
    p=out/'worker_receipt.json'
    if p.exists():
        receipt=read(p);stamp=receipt.get('sealed_elapsed_s',1e99)
        if not isinstance(stamp,(int,float)) or not 0<=stamp<590 or clock.elapsed>=590:reasons.append('LATE_SNAPSHOT')
        elif receipt.get('plan_sha256')!=plan_hash or sha(out/'scientific_snapshot.json')!=receipt.get('snapshot_sha256'):reasons.append('EVIDENCE_INTEGRITY')
        else:
            snap=read(out/'scientific_snapshot.json')
            if snap.get('plan_sha256')!=plan_hash or snap.get('in_window_sources_verified') is not True:reasons.append('EVIDENCE_INTEGRITY')
            else:
                try:verify(out,snap['evidence_hashes'])
                except (ValueError,OSError):reasons.append('EVIDENCE_INTEGRITY')
            if snap.get('outcome') in ('IDENTITY_OR_CORRECTNESS_ERROR','BOUND_CONFLICT','CLEANUP_FAILURE'):
                reasons.append('IDENTITY_DRIFT' if snap['outcome']=='IDENTITY_OR_CORRECTNESS_ERROR' else snap['outcome'])
            if snap.get('outcome')=='REDUCTION_CERTIFICATE_ERROR':reasons.append('SCOPED_CORRECTNESS')
            if snap.get('outcome') in ('WORKER_ERROR','WORKER_OUTER_FAILURE'):reasons.append('UNCLASSIFIED_WORKER_ERROR')
    else:reasons.append('NO_SEALED_SCIENTIFIC_SNAPSHOT')
    if owned.get('exit_code') not in (0,None):reasons.append('WORKER_EXIT_ERROR')
    if clock.elapsed>=590:reasons.append('SCIENTIFIC_ACCEPTANCE_LATE')
    # No answer is inferred from retained external initial data.
    success=bool(snap and snap.get('strict_success') is True and not reasons)
    return dict(scientific_snapshot_accepted=not reasons,strict_success=success,outcome=snap.get('outcome') if snap else None,
                reasons=reasons,stop_scope=stop_scope(*reasons),snapshot=snap,affected_arms=(snap or {}).get('affected_arms',[]))

def layered_evidence(result,observation,scenes):
    s=result.get('snapshot') or {};r=s.get('native_response') or {};v=s.get('final_admission') or {};ack=s.get('response_ack') or {}
    timely=ack.get('timely') is True and ack.get('received_elapsed_s',550)<550
    return dict(input_source_identity='PASS' if s.get('in_window_sources_verified') else 'UNKNOWN',
        native_model_runtime_and_parameters='PASS' if s.get('native_model_prepared') else 'NOT_REACHED',
        root_LP_entered=observation['root_LP_entered'],root_LP_completed=observation['root_LP_completed'],
        native_finite_lower_bound=r.get('finite_native_lower_bound') if timely else None,
        native_candidate='PASS' if timely and r.get('vector') else 'NOT_REACHED',
        both_matrix_admission='PASS' if v.get('passed') else ('FAIL' if v else 'NOT_REACHED'),
        independent_legality='PASS' if (v.get('legality') or {}).get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED' else 'NOT_REACHED',
        complete_AB_AC_SAFE='PASS' if safe_interval(s.get('final'),scenes) else ('FAIL' if s.get('final') else 'NOT_REACHED'),
        different_schedule=v.get('same_initial') is False if v else None,
        strict_energy_improvement=result['strict_success'],independent_optimality_proof='UNKNOWN',
        scientific_credit_valid=result['scientific_snapshot_accepted'],revocation_reasons=result['reasons'])

def seal_control_receipt(out,receipt,clock):
    """Charge final writes too; late administrative evidence may only revoke."""
    out=Path(out);save(out/'controller_receipt.json',receipt)
    identity=sha(out/'controller_receipt.json');after_receipt=clock.elapsed
    save(out/'controller_completion.json',dict(receipt_sha256=identity,after_receipt_and_hash_elapsed_s=after_receipt,
        within_method_window=after_receipt<600,scientific_credit_rule='Requires no budget_invalidated.json and normal controller exit'))
    after_completion=clock.elapsed
    if after_completion>=600:
        save(out/'budget_invalidated.json',dict(reason='FINAL_ARCHIVE_EXCEEDED_600',observed_elapsed_s=after_completion,scientific_credit=False))
    return dict(after_final_archive_elapsed_s=after_completion,within_method_window=after_completion<600)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--expected-sha',required=True);parser.add_argument('--approval',type=Path,required=True)
    parser.add_argument('--arm',choices=['A','B','C'],required=True);parser.add_argument('--batch',type=Path,required=True);parser.add_argument('--t0',type=float,required=True)
    args=parser.parse_args();root=args.workspace.resolve();here=Path(__file__).resolve().parent;clock=Clock(args.t0)
    batch=args.batch.resolve();launch=read(batch/(args.arm+'_launch.json'))
    if launch['parent_pid']!=os.getppid() or launch['arm']!=args.arm or launch['start_monotonic']!=args.t0 or launch['plan_sha256']!=args.expected_sha:raise PermissionError('Batch claim mismatch')
    if sys.stdin.readline().strip()!='D284_ARM_GO '+launch['nonce']:raise PermissionError('No protected batch GO')
    if sha(args.plan)!=args.expected_sha:raise IntegrityError('Plan identity')
    plan=read(args.plan);approval=read(args.approval);authorize(approval,args.expected_sha)
    from environment import verify_environment
    verify_environment(plan['environment'])
    if plan['protocol']!='D284-CPLEX-fresh-ABC-executor-v1' or not plan['ready_to_request_independent_scientific_authorization']:
        raise PermissionError('Unsupported protocol')
    # The approved commit must actually contain this frozen plan and code.
    repo=root/'work/publish_repo';prefix=plan['repository_package']+'/'
    for name in ['plan.json']+list(plan['code_hashes']):
        b=subprocess.check_output(['git','-C',str(repo),'show',approval['frozen_commit']+':'+prefix+name],stderr=subprocess.PIPE)
        if hashlib.sha256(b).hexdigest()!=sha(here/name):raise IntegrityError('Approved commit/source mismatch: '+name)
    verify(here,plan['code_hashes']);verify(root,plan['input_hashes']);verify(root,plan['evaluation_source_hashes']);verify(Path('/'),plan['runtime_hashes'])
    clock.check(550)
    if batch!=root/plan['execution_directory']:raise IntegrityError('Batch output identity')
    out=batch/args.arm;out.mkdir(exist_ok=False)
    nonce=secrets.token_hex(16)
    save(out/'approval_consumed.json',approval)
    save(out/'claim.json',dict(plan_sha256=args.expected_sha,parent_pid=os.getpid(),start_monotonic=args.t0,arm=args.arm,nonce=nonce,authorization_consumed=True,maximum_solve_calls=1))
    emergency_watchdog(out,clock)
    argv=[plan['native_runtime']['python'],'-B',str(here/'worker.py'),'--workspace',str(root),'--plan',str(args.plan.resolve()),'--output',str(out),'--t0',repr(args.t0)]
    owned=run_owned(argv,out,clock,plan['limits'],args.expected_sha,nonce)
    result=accept_snapshot(out,clock,args.expected_sha,owned)
    from native import parse_observed_logs
    observation=parse_observed_logs(owned.pop('events',[]))
    observation['parsed_elapsed_s']=clock.elapsed;observation['in_window']=clock.elapsed<590
    if not observation['in_window']:
        observation.update(MIP_start_acceptance='UNKNOWN',root_LP_entered='UNKNOWN',root_LP_completed='UNKNOWN',late_parse_no_credit=True)
        result['reasons'].append('OBSERVATION_PARSE_LATE')
    save(out/'observed_native_summary.json',observation)
    try:verify(here,plan['code_hashes']);verify(root,plan['input_hashes']);verify(root,plan['evaluation_source_hashes']);verify(Path('/'),plan['runtime_hashes'])
    except BaseException as e:result['reasons'].append('IDENTITY_DRIFT');result['identity_error']=error_record(e)
    result['stop_scope']=stop_scope(*result['reasons']);result['strict_success']=bool(result['strict_success'] and not result['reasons'])
    hashes={p.name:sha(p) for p in out.iterdir() if p.is_file()}
    elapsed=clock.elapsed
    if elapsed>=600:result['reasons'].append('TOTAL_WINDOW_EXCEEDED');result['strict_success']=False
    result['scientific_snapshot_accepted']=not result['reasons']
    completion=seal_control_receipt(out,dict(plan_sha256=args.expected_sha,method_elapsed_s=elapsed,method_elapsed_scope='Before final receipt write; controller_completion and terminal record include final archive cost',
        outcome=result,layers=layered_evidence(result,observation,plan['scene_ids']),owned=owned,observation=observation,evidence_hashes=hashes,authorization_consumed=True,retries=0),clock)
    if not completion['within_method_window']:result['strict_success']=False;result['reasons'].append('FINAL_ARCHIVE_EXCEEDED_600')
    print(json.dumps(dict(output=str(out),strict_success=result['strict_success'],outcome=result['outcome'],reasons=result['reasons'],completion=completion,elapsed_s=clock.elapsed)))
    return 0 if not result['reasons'] else 1

if __name__=='__main__':raise SystemExit(main())
