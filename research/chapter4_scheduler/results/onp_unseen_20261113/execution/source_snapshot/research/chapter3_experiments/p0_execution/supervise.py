"""Single-launch P0 watchdog; only terminate the owned batch process tree."""
from pathlib import Path
import subprocess
import sys
import time
import batch as b


def expiry(ledger,elapsed,now):
    if elapsed>=b.WALL:return 'CALENDAR_LIMIT'
    active=ledger.get('active') or {}
    if active:
        if now-active['slot_start_monotonic']>=b.SLOT_WALL:return 'SLOT_RETURN_LIMIT'
        if active['phase']=='METHOD' and now-active['phase_start_monotonic']>=b.METHOD_RETURN_WALL:
            return 'METHOD_RETURN_CLEANUP_LIMIT'
    return None


def launch():
    b.admission()
    b.write_new(b.OUT/'launcher_claim.json',{'protocol':b.PROTOCOL,'no_retry':True,
        'declaration_sha256':b.sha(b.OUT/'declaration.json'),'script_sha256':b.sha(Path(__file__)),
        'wall_s':b.WALL,'method_return_watchdog_s':420,'slot_watchdog_s':480,'started_utc':b.now()})
    command=[sys.executable,'-B',str(b.HERE/'batch.py'),'run']
    start=time.monotonic();stop=None
    with (b.OUT/'launcher.log').open('xb') as stream:
        proc=subprocess.Popen(command,cwd=b.REPO,stdout=stream,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        print({'event':'P0_STARTED','pid':proc.pid,'slots':40,'method_seconds':300},flush=True)
        while proc.poll() is None:
            try:ledger=b.read(b.OUT/'ledger.json')
            except Exception as exc:
                stop='UNREADABLE_LEDGER:'+type(exc).__name__;break
            stop=expiry(ledger,time.monotonic()-start,time.monotonic())
            if stop:break
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:pass
        kill=None
        if stop and proc.poll() is None:
            kill=subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW).returncode
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:pass
        result={'returncode':proc.poll(),'watchdog_stop':stop,'owned_tree_kill_returncode':kill,
            'wall_s':time.monotonic()-start,'ended_utc':b.now(),'no_retry':True,'command':command}
        b.write_new(b.OUT/'launcher_result.json',result)
        print(result,flush=True)
        return 0 if proc.poll()==0 and stop is None else 1


if __name__=='__main__':raise SystemExit(launch())
