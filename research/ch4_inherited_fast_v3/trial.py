"""Frozen C route with a fresh strict-integrator wrapper inside each native worker."""
import ctypes
import fcntl
import inspect
import json
import os
import resource
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path

HERE=Path(__file__).resolve().parent
FIRST=HERE.parent/"ch4_inherited_fast_v1"
SECOND=HERE.parent/"ch4_inherited_fast_v2"
ROOT=Path(os.environ["INTEGRATED_RUN"])
spec=spec_from_file_location("round_one",FIRST/"run.py")
v1=module_from_spec(spec)
spec.loader.exec_module(v1)
sys.path.insert(0,str(SECOND))
from incremental import Integration,continuation,HEAT_BLOB,np

CASES=("A01","A02","A03","A04","A05","A06","B07","B08","C09","C10","C11","C12")
T=time.perf_counter


def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,sort_keys=True)+"\n")
    tmp.replace(path)


def warm(cpu):
    global solver,original,resume
    solver=v1.initialize(cpu)
    import heat
    original=heat.integrate
    lib=ROOT/"clock.so"
    subprocess.run(["cc","-O2","-shared","-fPIC",str(SECOND/"clock.c"),"-o",str(lib)],check=True)
    resume=continuation(original,lib)
    ev=np.zeros((2,14));ev[:,0]=[0,2];ev[:,1]=[2,4]
    args=(ev,np.full(4,35.),np.eye(4),np.ones(4),35.,np.empty(0,np.int64),True)
    k=Integration("incremental",original,resume,"neutral")
    k.times=Counter()
    for n in range(2):
        k.ordinal=n
        assert all(np.array_equal(a,b) for a,b in zip(original(*args),k(*args)))


def bind(obj,arm,folder,stage):
    import heat
    assert heat.integrate is original
    kernel=Integration("full" if arm=="C1" else "incremental",original,resume,
                       (obj["case"],obj["input_sha256"],HEAT_BLOB,obj["horizon_ticks"]))
    kernel.ordinal=0
    def measured(*args):
        if not args[-1]:
            return original(*args)
        kernel.times=Counter()
        out=kernel(*args)
        assert kernel.source is None or kernel.source<kernel.ordinal
        v1.write(folder/(stage+"-integrals.jsonl"),dict(ordinal=kernel.ordinal,events=kernel.rows,
                 reused=kernel.reused,source=kernel.source,cache_bytes=kernel.storage,
                 rss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,**kernel.times))
        kernel.ordinal+=1
        kernel.latest=None
        return out
    heat.integrate=measured
    return kernel


def regression():
    m=solver.m
    obj=next(o for o in m.u2.CASES if m.label(o)=="C10")
    folder=ROOT/"regression"
    folder.mkdir(exist_ok=True)
    history=HERE.parent/"ch3_integrated_quality_v3/archive/history/C10/energy"
    src=history/"original"
    expected=json.loads((src/"certificate.json").read_bytes())
    point=m.endpoint(expected)
    assert point["status"]=="HOT"
    kernel=bind(obj,"C2",folder,"regression")
    eng,flow,init=solver.handoff(obj,folder/"precheck",src,point)
    for number in range(2):
        d,tr=eng.cert(init[0],eng.replay(init[0]))
        assert m.endpoint(d)==point and np.array_equal(tr,init[3])
        if number:assert kernel.reused==len(tr)
    fresh=eng.out/"evidence"/obj["case"]/point["plan"]
    eng,flow,init=solver.handoff(obj,folder/"handoff",fresh,point)
    events=[]
    dest=folder/"refine"
    dest.mkdir(exist_ok=True)
    m.CLOCK=T()
    best=solver.refine_hot(eng,flow,init,dest,lambda tag,**kw:events.append(dict(event=tag,**kw)))
    assert events==json.loads((history/"stages.json").read_bytes())
    certs=[e for e in events if e["event"]=="certificate"]
    assert [e["point"]["status"] for e in certs]==["SAFE","HOT"] and best==certs[0]["point"]
    for e in certs:
        rel=Path(e["stage"])/"evidence"/obj["case"]/e["point"]["plan"]
        actual=json.loads((dest/rel/"certificate.json").read_bytes())
        archived=json.loads((history/rel/"certificate.json").read_bytes())
        del actual["cert_s"],archived["cert_s"]
        assert actual==archived
        with np.load(dest/rel/"trace.npz") as a,np.load(history/rel/"trace.npz") as b:
            assert np.array_equal(a["events"],b["events"])
    write_json(ROOT/"regression.json",dict(seed=point,stages=certs,best=best,
        full_hot_hit=len(init[3]),integrals=[json.loads(l) for l in (folder/"regression-integrals.jsonl").read_text().splitlines()]))


def cell(obj,folder,arm,cap):
    f=solver.f
    worker=f.worker
    phases=[]
    def launch(fn,args,until):
        stage=fn.__name__
        assert stage in ("search","refine")
        def child(*args):
            bind(obj,arm,folder,stage)
            fn(*args)
        # The original fork/join/alarm policy is retained. wait4 also returns exact per-child accounting.
        waitpid=os.waitpid
        def wait_with_usage(pid,flags):
            childpid,status,usage=os.wait4(pid,flags)
            if childpid>0:
                phases.append(dict(stage=stage,rss_KiB=usage.ru_maxrss,cpu_s=usage.ru_utime+usage.ru_stime))
            return childpid,status
        os.waitpid=wait_with_usage
        try:return worker(child,args,until)
        finally:os.waitpid=waitpid
    f.worker=launch
    start=time.process_time()
    try:v1.cell(solver,obj,folder,"O",cap)
    finally:f.worker=worker
    rc=json.loads((folder/"receipt.json").read_bytes())
    assert len(phases)==1+bool(rc["post"])
    rc.update(variant=arm,resources=phases,parent_cpu_s=time.process_time()-start)
    write_json(folder/"receipt.json",rc)


def lane(job):
    cpu,codes=job
    os.sched_setaffinity(0,{cpu})
    solver.f.CPU=cpu
    for case in codes:
        obj=next(o for o in solver.m.u2.CASES if solver.m.label(o)==case)
        for rep in range(1,4):
            caps=(10,20) if (obj["index"]+rep)%2 else (20,10)
            for cap in caps:
                modes=("C1","C2") if (obj["index"]+rep+cap//10)%2 else ("C2","C1")
                for arm in modes:
                    folder=ROOT/"raw"/case/f"r{rep}-{arm}-{cap}"
                    if folder.exists():
                        rc=json.loads((folder/"receipt.json").read_bytes())
                        assert rc["variant"]==arm and rc["cap"]==cap and rc["cpu"]==cpu
                    else:cell(obj,folder,arm,cap)
        print("complete",case,flush=True)


def main():
    ROOT.mkdir(exist_ok=True,parents=True)
    lock=(ROOT/"run.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cores=sorted(os.sched_getaffinity(0))[::2][:6]
    assert len(cores)==6
    assert len({Path(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read_text() for c in cores})==6
    warm(cores[0])
    if not (ROOT/"regression.json").exists():
        pid=os.fork()
        if pid==0:
            try:regression()
            except BaseException:
                import traceback
                traceback.print_exc()
                os._exit(1)
            os._exit(0)
        assert os.waitpid(pid,0)[1]==0
    print("recovery gate passed",flush=True)
    with ProcessPoolExecutor(6) as pool:
        list(pool.map(lane,[(c,CASES[i::6]) for i,c in enumerate(cores)]))


if __name__=="__main__":
    main()
