"""Pin and account entire process families, including reaped and orphaned grandchildren."""
import ctypes,fcntl,json,math,os,resource,signal,subprocess,sys,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ["TRANSFER_ROOT"])
CASES=("A02","A06","C10","C11")
HZ=os.sysconf("SC_CLK_TCK")
T=time.perf_counter


def spent():
    return sum(u.ru_utime+u.ru_stime for u in (resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)))


def save(p,obj):
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,sort_keys=True)+"\n")
    tmp.replace(p)


def live(group):
    total=0
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():continue
        try:stats=(p/"stat").read_text().rsplit(")",1)[1].split()
        except (FileNotFoundError,ProcessLookupError):continue
        if int(stats[3])==group:
            total+=sum(int(stats[k]) for k in (11,12,13,14))
    return total/HZ


def subreaper():
    assert ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)==0


def monitored(dest,command,wall,limit,extra=None):
    dest.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,U1_OUT=str(dest/"scratch"),M1G_RAW=str(dest/"warm"),NUMBA_CACHE_DIR=str(dest/"jit"),**(extra or {}))
    start=T()
    env["CELL_START"]=str(start)
    p=subprocess.Popen(command,env=env,start_new_session=True,stdout=(dest/"stdout.log").open("wb"),stderr=(dest/"stderr.log").open("wb"))
    reason="natural"
    while p.poll() is None:
        if spent()+live(p.pid)>=limit-.25:
            reason="cpu_guard"
            break
        if T()>=start+wall-.018:
            reason="wall"
            break
        time.sleep(min(.025,max(.001,start+wall-.018-T())))
    try:os.killpg(p.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    p.wait()
    while True:
        try:os.wait4(-1,0)
        except ChildProcessError:break
    actual=T()-start
    if reason=="natural" and p.returncode:reason="fault"
    return dict(start=start,wall=actual,charged=min(actual,wall),bound=wall,rc=p.returncode,reason=reason,core=min(os.sched_getaffinity(0)),accounted_now=spent())


def preflight():
    subreaper()
    p=ROOT/"guards"
    p.mkdir(exist_ok=True)
    code="import os,time;os.fork();exec('while True: pass')"
    for name,wall,allow,expected in (("wall",.35,6,"wall"),("cpu",8,1.25,"cpu_guard")):
        dst=p/name
        before=spent()
        r=monitored(dst,[sys.executable,"-c",code],wall,before+allow)
        r["actual_cpu"]=spent()-before
        assert r["reason"]==expected and r["actual_cpu"]<=allow and r["actual_cpu"]>0.1
        assert r["wall"]<wall+.2
        save(dst/"receipt.json",r)
    save(p/"passed.json",{"passed":True,"ticks":HZ,"cpu_test_includes_fork":True})


def lane(job):
    ix,cpu=job
    case=CASES[ix]
    os.sched_setaffinity(0,{cpu})
    subreaper()
    folder=ROOT/"formal"/case
    folder.mkdir(parents=True,exist_ok=False)
    limit=374.
    seq=[("A",10),("B",10),("A",20),("B",20),("A",60)]
    n=0
    for rep in (1,2,3):
        # Keep each matched pair adjacent and rotate the long reference through the block.
        pairs=[seq[:2],seq[2:4]]
        if (ix+rep)%2:pairs.reverse()
        order=[]
        for j,pair in enumerate(pairs):
            order+=pair if (ix+rep+j)%2 else pair[::-1]
        order.insert((ix+rep)%3*2,seq[4])
        for arm,cap in order:
            if limit-spent()<cap+.25:
                save(folder/"stop.json",dict(next=[rep,arm,cap],cpu=spent(),reason="insufficient remaining CPU"))
                return
            dest=folder/f"r{rep}-{arm}-{cap}"
            r=monitored(dest,[sys.executable,"-Bu",str(HERE/"transfer.py"),case,arm,str(cap),str(dest)],cap,limit)
            n+=1
            r.update(case=case,arm=arm,rep=rep,order=n)
            save(dest/"receipt.json",r)
            if r["reason"] in ("cpu_guard","fault"):
                raise RuntimeError((case,arm,cap,r))
        print("complete",case,rep,round(spent(),2),flush=True)
    save(folder/"account.json",dict(cpu_s=spent(),cells=n))


def main():
    action=sys.argv[1]
    if action=="preflight":
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        preflight()
        return
    assert (ROOT/"guards/passed.json").exists()
    if action=="diagnostic":
        subreaper()
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        dest=ROOT/sys.argv[2]
        prior=sum(json.loads(p.read_bytes())["accounted_now"] for p in ROOT.glob("diag*/receipt.json"))
        if dest.exists() or 119-prior<2:raise RuntimeError("diagnostic already assigned or CPU exhausted")
        script="probe.py" if sys.argv[2].startswith("diag_probe") else "fixed.py"
        r=monitored(dest,[sys.executable,"-Bu",str(HERE/script),str(dest)],350,119-prior)
        save(dest/"receipt.json",r)
        print(r)
        if r["reason"]!="natural":raise RuntimeError((dest,r))
        return
    assert action=="formal" and (ROOT/"fixed_pass.json").exists()
    lock=(ROOT/"formal.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (ROOT/"formal").exists(),"formal dispatch already registered"
    cores=sorted(os.sched_getaffinity(0))[::2][:4]
    assert len({Path(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read_text() for c in cores})==4
    with ProcessPoolExecutor(4) as pool:list(pool.map(lane,enumerate(cores)))
    total=spent()
    save(ROOT/"formal_account.json",dict(actual_cpu_s=total,limit=1500,cores=cores))
    assert total<=1500


if __name__=="__main__":main()
