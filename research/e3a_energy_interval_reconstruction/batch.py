"""Run a group of independent, pinned, wall-capped cells without reusing budgets."""
import argparse,os,signal,subprocess,sys,time
from collections import deque
from shared import HERE,RUN,read,put
def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['diagnostic','comparison']);args=ap.parse_args()
    if args.phase=='comparison':
        assert all((RUN/c/'diagnostic/receipt.json').exists() for c in ('D1','D2','C10'))
        subprocess.run([sys.executable,str(HERE/'gate.py')],check=True)
        if not read(RUN/'gate.json')['open']: return
    else:assert read(RUN/'preflight/receipt.json')['status']=='PASS'
    arms=['diagnostic'] if args.phase=='diagnostic' else list('ABCD')
    cells=deque((c,a) for c in ['D1','D2','C10'] for a in arms)
    # Running C and D concurrently where possible limits time-of-day drift.
    lanes=deque(sorted(os.sched_getaffinity(0)))
    active={};records=[]
    budget=600 if args.phase=='diagnostic' else 300
    for c,a in cells:
        if (RUN/c/a).exists():raise FileExistsError(RUN/c/a)
    logfile=RUN/'batch'/args.phase;logfile.mkdir(parents=True,exist_ok=False)
    while cells or active:
        while cells and lanes:
            case,arm=cells.popleft();cpu=lanes.popleft()
            start=time.monotonic()
            with (logfile/(case+'_'+arm+'.log')).open('wb') as f:
                child=subprocess.Popen(['taskset','-c',str(cpu),sys.executable,str(HERE/'run.py'),case,arm],
                    stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            active[child]=(case,arm,cpu,start)
        for child,(case,arm,cpu,start) in list(active.items()):
            code=child.poll();elapsed=time.monotonic()-start
            if code is None and elapsed<budget-.25:continue
            if code is None:
                os.killpg(child.pid,signal.SIGKILL);code=child.wait()
            records.append(dict(case=case,arm=arm,core=cpu,exit_code=code,supervised_wall_s=elapsed))
            lanes.append(cpu);del active[child]
            put(logfile/'supervisor.json',records)
        if active:time.sleep(.05)
    if any(x['exit_code'] for x in records):raise SystemExit('One or more cells interrupted; see supervisor.json')
if __name__=='__main__':main()
