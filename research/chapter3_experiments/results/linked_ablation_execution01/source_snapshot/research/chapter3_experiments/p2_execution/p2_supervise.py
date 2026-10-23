"""K161 P2 uniquely named watchdog; compact status and independent terminal."""
from pathlib import Path
import subprocess
import sys
import time
import p2_controller as r
from datetime import datetime,timedelta
import safe_io


def expiry(status,now):
    if r.remaining_calendar()<=0:return 'P2_CALENDAR_LIMIT'
    active=status.get('active') or {}
    if active:
        if now-active['slot_start_monotonic']>=480:return 'SLOT_RETURN_LIMIT'
        if active['phase']=='METHOD' and now-active['phase_start_monotonic']>=420:
            return 'METHOD_RETURN_LIMIT'
    return None


def process_terminal(returncode,stop,worker):
    complete=(returncode==0 and stop is None and isinstance(worker,dict)
              and worker.get('state')=='COMPLETED' and worker.get('consumed_new')==40)
    return {'protocol':r.PROTOCOL,'state':'COMPLETED' if complete else 'STOPPED_PROCESS_OR_WORKER_FAILURE',
        'returncode':returncode,'watchdog_stop':stop,'worker_terminal':worker,
        'stale_running_ledger_is_not_authoritative':True,'research_retry':False}


def launch():
    r.admission()
    started_utc=r.now()
    r.write_new(r.OUT/'launcher_claim.json',{'protocol':r.PROTOCOL,'no_retry':True,
        'script_sha256':r.sha(Path(__file__)),'declaration_sha256':r.sha(r.OUT/'declaration.json'),
        'calendar_deadline_utc':(datetime.fromisoformat(started_utc)+timedelta(seconds=r.WALL)).isoformat(),'started_utc':started_utc})
    command=[sys.executable,'-B',str(r.HERE/'p2_controller.py'),'run']
    start=time.monotonic();stop=None
    with (r.OUT/'launcher.log').open('xb') as stream:
        proc=subprocess.Popen(command,cwd=r.REPO,stdout=stream,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        print({'event':'P2_40_STARTED','pid':proc.pid,'P2_calendar_s_left':r.remaining_calendar()},flush=True)
        while proc.poll() is None:
            try:status=safe_io.read_small(r.OUT/'status.json')
            except Exception as exc:stop='UNREADABLE_COMPACT_STATUS:'+type(exc).__name__;break
            stop=expiry(status,time.monotonic())
            if stop:break
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        killed=None
        if stop and proc.poll() is None:
            killed=subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW).returncode
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:pass
        worker_path=r.OUT/'worker_terminal.json'
        try:worker=r.read(worker_path) if worker_path.exists() else None
        except Exception as exc:worker={'state':'UNREADABLE','error':str(exc)}
        terminal=process_terminal(proc.poll(),stop,worker)
        terminal.update(ended_utc=r.now(),process_wall_s=time.monotonic()-start,
                        owned_tree_kill_returncode=killed)
        r.write_new(r.OUT/'process_terminal.json',terminal)
        r.write_new(r.OUT/'launcher_result.json',{'returncode':proc.poll(),'watchdog_stop':stop,
            'wall_s':terminal['process_wall_s'],'ended_utc':r.now(),'no_retry':True})
        print(terminal,flush=True)
        return 0 if terminal['state']=='COMPLETED' else 1


if __name__=='__main__':raise SystemExit(launch())
