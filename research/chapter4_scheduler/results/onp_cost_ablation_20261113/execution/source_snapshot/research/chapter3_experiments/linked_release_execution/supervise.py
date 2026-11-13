"""One fresh owned child per method/post; bounded hidden Windows process."""
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parent.parents[1]


def utc_now():return datetime.now(timezone.utc)


def stop_reason(*,phase_started,now,watchdog_s,slot_deadline_monotonic,
                calendar_deadline_utc,utc_clock=utc_now):
    if utc_clock()>=datetime.fromisoformat(calendar_deadline_utc):return 'CALENDAR_LIMIT'
    if now>=slot_deadline_monotonic:return 'SLOT_RETURN_LIMIT'
    if now-phase_started>=watchdog_s:return 'METHOD_RETURN_LIMIT' if watchdog_s==420 else 'POST_RETURN_LIMIT'
    return None


def kill_owned_tree(proc):
    """Only the live Popen root created by this supervisor; no name-wide kill."""
    if proc.poll() is not None:return {'attempted':False,'reason':'OWNED_ROOT_ALREADY_EXITED'}
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    if sys.platform=='win32':
        killed=subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],
            capture_output=True,creationflags=flags,timeout=20)
        result={'attempted':True,'owned_root_pid':proc.pid,'returncode':killed.returncode}
    else:
        proc.kill();result={'attempted':True,'owned_root_pid':proc.pid,'scope':'owned_root_only_non_windows'}
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:result['root_wait_timeout']=True
    return result


def run_child(command,folder,phase,*,watchdog_s,slot_deadline_monotonic,
              calendar_deadline_utc,clock=time.monotonic,utc_clock=utc_now,
              popen_factory=subprocess.Popen,tree_killer=kill_owned_tree):
    started=clock();stop=stop_reason(phase_started=started,now=started,watchdog_s=watchdog_s,
        slot_deadline_monotonic=slot_deadline_monotonic,calendar_deadline_utc=calendar_deadline_utc,utc_clock=utc_clock)
    if stop:return {'returncode':None,'process_closed':True,'watchdog_stop':stop,'launched':False,'phase':phase}
    folder=Path(folder)
    with (folder/(phase+'_launch.claim.json')).open('x',encoding='utf-8') as claim:
        claim.write('{"one_process_only":true,"no_retry":true}\n')
    proc=None;kill=None
    with (folder/(phase+'_stdout.log')).open('xb') as stream:
        try:
            proc=popen_factory(command,cwd=REPO,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            while proc.poll() is None:
                stop=stop_reason(phase_started=started,now=clock(),watchdog_s=watchdog_s,
                    slot_deadline_monotonic=slot_deadline_monotonic,
                    calendar_deadline_utc=calendar_deadline_utc,utc_clock=utc_clock)
                if stop:break
                try:proc.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
            if stop is None:
                stop=stop_reason(phase_started=started,now=clock(),watchdog_s=watchdog_s,
                    slot_deadline_monotonic=slot_deadline_monotonic,
                    calendar_deadline_utc=calendar_deadline_utc,utc_clock=utc_clock)
            if stop and proc.poll() is None:kill=tree_killer(proc)
        except BaseException:
            if proc is not None and proc.poll() is None:kill=tree_killer(proc)
            raise
    return {'phase':phase,'returncode':proc.poll(),'process_closed':proc.poll() is not None,
        'watchdog_stop':stop,'owned_root_pid':proc.pid,'owned_tree_kill':kill,
        'process_wall_seconds':clock()-started,'launched':True,
        'root_exit_does_not_certify_matlab_cleanup':True,
        'descendant_cleanup_must_pass_worker_evidence_audit':True,'no_retry':True}


def run_method(slot,folder,declaration_path,**limits):
    command=[sys.executable,'-B',str(HERE/'worker.py'),'--declaration',str(declaration_path),
        '--slot-id',slot['slot_id'],'--out',str(folder)]
    return run_child(command,folder,'method',watchdog_s=420,**limits)


def run_post(slot,folder,declaration_path,**limits):
    command=[sys.executable,'-B',str(HERE/'post_worker.py'),'--declaration',str(declaration_path),
        '--slot-id',slot['slot_id'],'--out',str(folder)]
    return run_child(command,folder,'post',watchdog_s=60,**limits)
