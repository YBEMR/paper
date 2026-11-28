"""A neutral, read-only ancestor for isolated timed solves using frozen transfer.main."""
import fcntl
import gc
import hashlib
import json
import multiprocessing as mp
import os
import signal
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE=Path(__file__).resolve().parent
PREV=HERE.parent/"ch4_quota_transfer"
sys.path.insert(0,str(PREV))
import control

ROOT=Path(os.environ["WARM_ROOT"])
FROZEN=Path(os.environ["TRANSFER_ROOT"])
T=time.perf_counter

def verify_driver():
    from hashlib import sha256
    expected=json.loads((PREV/"results/budget.json").read_bytes())["setup"]["sources"]
    for name,sha in expected.items():
        assert sha256((FROZEN/"driver"/name).read_bytes()).hexdigest()==sha,name
    return len(expected)

class WarmChild:
    """Popen-compatible fork for the previous process-family supervisor."""
    def __init__(self,command,*,env,start_new_session,stdout,stderr):
        assert start_new_session
        self.returncode=None
        self.pid=os.fork()
        if self.pid:return
        try:
            os.setsid()
            os.dup2(stdout.fileno(),1)
            os.dup2(stderr.fileno(),2)
            os.environ.update(env)
            import transfer
            from simplified import expand
            # The parent initialized the immutable numeric runtime; all run-local
            # builders, counters, candidate pools and evidence are created below.
            transfer.init=lambda:expand
            transfer.f.CPU=min(os.sched_getaffinity(0))
            case,arm,cap,dest=command[-4:]
            transfer.main(case,arm,int(cap),Path(dest))
            os._exit(0)
        except BaseException:
            traceback.print_exc()
            os._exit(1)

    def poll(self):
        if self.returncode is None:
            pid,status=os.waitpid(self.pid,os.WNOHANG)
            if pid:self.returncode=os.waitstatus_to_exitcode(status)
        return self.returncode

    def wait(self):
        if self.returncode is None:
            _,status=os.waitpid(self.pid,0)
            self.returncode=os.waitstatus_to_exitcode(status)
        return self.returncode

def prepare(cores):
    os.sched_setaffinity(0,{cores[0]})
    pre=ROOT/"preparation"
    pre.mkdir()
    os.environ.update(U1_OUT=str(pre/"scratch"),M1G_RAW=str(pre/"template"),NUMBA_CACHE_DIR=str(pre/"jit"))
    control.ROOT=ROOT
    control.preflight()
    def timeout(*args):
        raise TimeoutError("preparation resource limit")
    signal.signal(signal.SIGPROF,timeout)
    signal.signal(signal.SIGALRM,timeout)
    signal.setitimer(signal.ITIMER_PROF,238-control.spent())
    signal.alarm(420)
    import transfer
    source_count=verify_driver()
    f,m=transfer.f,transfer.m
    f.CPU=cores[0]
    started=T()
    runtime=f.warm()
    from simplified import expand
    dp_start=T()
    tests=m.small_gate()
    control.save(pre/"kernels.json",dict(driver_objects=source_count,neutral_runtime=runtime,dp_cases=tests,dp_wall=T()-dp_start))
    checks=[]
    for arm in ("A","B"):
        begin=T()
        api=m.RUN[0]
        path=pre/("neutral-"+arm)
        path.mkdir()
        flow=api.Flow("LL",35,"NEUTRAL_LL",path)
        parent=api.e.initial(flow)
        log=dict(actions=[],groups=[])
        fn=transfer.make(expand,arm,"bare")
        pool,ok=fn(flow,0,[parent],"NT",begin,begin+10,log)
        elapsed=T()-begin
        assert ok and pool and log["actions"] and elapsed<10,(arm,elapsed)
        checks.append(dict(arm=arm,word="LL",requests=len(flow.p.req),windows=flow.windows,initial_prefix_bytes=len(parent["config"]),
                           slots=sum(g["slots"] for g in log["groups"]),legal=len(pool),end_s=elapsed,
                           max_predicted_peak=float(max(v["peak"] for v in pool.values()))))
        assert checks[-1]["initial_prefix_bytes"]==0
    del flow,parent,pool,log,fn
    api.e.p1.CFG["instances"].pop("NEUTRAL_LL",None)
    gc.collect()
    signal.alarm(0)
    signal.setitimer(signal.ITIMER_PROF,0)
    control.save(pre/"gate.json",dict(passed=True,checks=checks,runtime_wall=T()-started))
    return transfer

def main():
    start=T()
    ROOT.mkdir(exist_ok=False)
    control.ROOT=ROOT
    allocated=sorted(os.sched_getaffinity(0)); cores=allocated[::2][:4]
    assert len({Path(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read_text() for c in cores})==4
    try:
        prepare(cores)
    except BaseException:
        control.save(ROOT/"preparation_account.json",dict(passed=False,actual_cpu_s=control.spent(),wall_s=T()-start,error=traceback.format_exc()))
        raise
    os.sched_setaffinity(0,set(allocated))
    native=control.monitored
    ns=dict(native.__globals__,subprocess=SimpleNamespace(Popen=WarmChild))
    control.monitored=FunctionType(native.__code__,ns,native.__name__,native.__defaults__)
    baseline=control.spent()
    assert baseline<=240
    control.save(ROOT/"preparation_account.json",dict(passed=True,actual_cpu_s=baseline,wall_s=T()-start,limit=240))
    print("neutral preflight passed",baseline,flush=True)
    formal_start=T()
    try:
        with ProcessPoolExecutor(4,mp_context=mp.get_context("fork")) as pool:
            list(pool.map(control.lane,enumerate(cores)))
    finally:
        actual=control.spent()-baseline
        control.save(ROOT/"formal_account.json",dict(actual_cpu_s=actual,limit=1500,cores=cores,elapsed_parallel_s=T()-formal_start))
    assert actual<=1500

if __name__=="__main__":main()
