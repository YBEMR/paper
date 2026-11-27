"""Matched fixed-layer and physical-delivery audit. No end-to-end solver is called."""
import contextlib
import functools
import gzip
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter as clock
from types import SimpleNamespace

from benchmark_budget import OUT, PULSE, save

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ.get("U4_COST_LAB", HERE.parents[2])).resolve()
A = LAB / "U4a_worktree/research/u4a_integrated_fast_scheduler"
B = LAB / "U3b_worktree/research/u3b_blockage_triggered_quota"
CASES = ("I03","I05","I06","I07","I09","I11","I02","I12")
TWO = {"I03","I07","I12"}
ATTEMPT = int(sys.argv[1]) if __name__ == "__main__" else 0
PS = None

def pulse(name, limit):
    save(PULSE, dict(attempt=ATTEMPT,stage=name,limit=limit,start=time.monotonic()))

def read(path):
    return json.loads(path.read_bytes())

def sha(data):
    return hashlib.sha256(data).hexdigest()

def raw(obj):
    def native(v):
        if isinstance(v, bytes):
            return v.hex()
        return v.item()
    return json.dumps(obj,sort_keys=True,allow_nan=False,separators=(",",":"),default=native).encode()

def rows(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_bytes().splitlines()]

def append(name, item):
    with (OUT/name).open("ab") as f:
        f.write(raw(item)+b"\n")

def archived_events(root, unit):
    for name in unit["journal"]:
        data = gzip.decompress((root/name).read_bytes())
        assert sha(data) == Path(name).name.split(".")[0]
        for line in data.splitlines():
            yield json.loads(line)

class Meter:
    """Exclusive wall-time buckets. Any uninstrumented caller code is residual."""
    def __init__(self):
        self.wall = Counter()
        self.calls = Counter()
        self.path = []
        self.cleanup = contextlib.ExitStack()

    @contextlib.contextmanager
    def span(self, name):
        start = clock()
        node = [0.]
        self.path.append(node)
        try:
            yield
        finally:
            gross = clock()-start
            self.path.pop()
            self.wall[name] += gross-node[0]
            self.calls[name] += 1
            if self.path:
                self.path[-1][0] += gross

    def hook(self, owner, name, group, generator=False):
        is_dict = isinstance(owner,dict)
        get = owner.__getitem__ if is_dict else lambda k:getattr(owner,k)
        put = owner.__setitem__ if is_dict else lambda k,v:setattr(owner,k,v)
        original = get(name)
        def wrapper(*a,**kw):
            with self.span(group):
                return original(*a,**kw)
        def iterate(*a,**kw):
            it = original(*a,**kw)
            while True:
                with self.span(group):
                    try: v = next(it)
                    except StopIteration: return
                yield v
        put(name,iterate if generator else wrapper)
        self.cleanup.callback(put,name,original)

def measure(fn, name):
    pulse(name,15)
    w, c = clock(),time.process_time()
    result = fn()
    return result, dict(wall_s=clock()-w,cpu_s=time.process_time()-c)

def init_runtime(temp):
    global src, fifo, np, stack, psutil, PS, split_main, split_post, expand, native, cpu
    import psutil
    PS = psutil.Process()
    allowed = PS.cpu_affinity()
    cores_before = psutil.cpu_percent(interval=.4,percpu=True)
    # The original online batch uses hardware threads 0,2,4,6. Prefer an outside core.
    cpu = min([k for k in allowed if k>=8 and k%2==0] or allowed,key=lambda k:cores_before[k])
    PS.cpu_affinity([cpu])
    for key in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        os.environ[key] = "1"
    cache = temp/"numba"
    shutil.copytree(LAB/"U3b_compute_cache",cache)
    os.environ.update(U3B_SRC=str(B),U3A_INPUTS=str(LAB/"U3a_inputs"),U4_RUNS=str(temp),
                      NUMBA_CACHE_DIR=str(cache))
    sys.path.insert(0,str(A))
    spec = importlib.util.spec_from_file_location("u4_source_experiment", A/"experiment.py")
    src = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(src)
    import fifo
    np = src.np
    t,c=clock(),time.process_time()
    stack = src.u.stack()
    src.old.warm(stack)
    # Split the exact original loops at the CPU queue boundary for diagnostic timing only.
    text=inspect.getsource(fifo.timing.py_func)
    head=text[text.index("def timing("):text.index("    slack=10**9")]
    tail=text[text.index("    slack=10**9"):]
    scope={"np":np}
    exec(head.replace("def timing(","def mainpart(")+"    return finish,levels,ends,tail_late,features,tail_features\n",scope)
    exec("def postpart(ends,post_length,deadlines,boundary,horizon,tail_late,finish,levels,features,tail_features):\n"+tail,scope)
    from numba import njit
    split_main,split_post = njit(scope["mainpart"]),njit(scope["postpart"])
    template=stack[0].template()
    builder=fifo.Builder(template,template.eng)
    cfg=np.frombuffer(bytes([0,10,0]),np.uint8)
    args=(*builder.args,10000)
    f,k,ends,late,features,tf=split_main(cfg,*args)
    split_post(ends,args[3],args[2],args[-1],args[-2],late,f,k,features,tf)
    assert PS.cpu_affinity()==[cpu]
    native=stack[2].builder("NT")[0].__globals__
    expand=stack[0].e.expand
    original=inspect.getsource(stack[0].e.build)
    assert 'parents = diverse(ordered, False)' in original and 'if width > len(parents)' in original
    packages={k:importlib.metadata.version(k) for k in ("numpy","numba","scipy","psutil")}
    save(OUT/f"environment-{ATTEMPT}.json",dict(cpu=cpu,allowed=allowed,core_initial_percent=cores_before,
        logical=psutil.cpu_count(),physical=psutil.cpu_count(logical=False),processor=platform.processor(),
        system=platform.platform(),python=sys.version,packages=packages,utc=time.time(),warm_stack_cpu_s=time.process_time()-c,
        warm_stack_wall_s=clock()-t,process_to_ready_cpu_s=time.process_time(),thread_env={k:os.environ[k] for k in
        ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMBA_NUM_THREADS","NUMEXPR_NUM_THREADS")},
        frozen={str(p.relative_to(LAB)):sha(p.read_bytes()) for p in (A/"experiment.py",A/"eventlog.py",B/"fifo.py",
                 Path(inspect.getsourcefile(expand)),Path(stack[1].__file__))},
        probe_source_sha256=sha(Path(__file__).read_bytes()),protocol_sha256=sha((HERE/"PROTOCOL.md").read_bytes())))

def prepare(code,temp):
    obj=next(o for o in read(A/"registration/cases.json") if o["id"]==code)
    ctx=src.Unit(obj,"Base",temp,stack,1e9)
    w,c=clock(),time.process_time()
    ctx.models()
    b=fifo.Builder(ctx.flow,ctx.e)
    model=dict(wall_s=clock()-w,cpu_s=time.process_time()-c)
    root=A/"results"/code
    base=read(root/"runs/Base.json")
    by_id={}
    acts=defaultdict(list)
    for a in archived_events(root,base):
        if a[0]=="parent": by_id[a[1]]=bytes.fromhex(a[2])
        if a[0]=="q4_action": acts[a[2]].append(a)
        if a[:2]==["store","base"]:
            info=a[2]
            break
    j=max(acts)
    assert len(info["layers"])==j+1
    ids=list(dict.fromkeys(a[1] for a in acts[j]))
    lookup={b"":(0,)*10}
    if j:
        for _,p,prev,pair,q,_,state in acts[j-1]:
            cfg=by_id[p]+ctx.flow.extension(b.types[prev],*b.counts[prev],*pair,*q)
            lookup[cfg]=tuple(state)
    parents=[(p,fifo.State(by_id[p],lookup[by_id[p]],())) for p in ids]
    nt_expected=defaultdict(lambda:{"actions":[],"groups":[],"beam":[]})
    nlayer=2 if code in TWO else 1
    layer=0
    for a in archived_events(root,read(root/"runs/NT10.json")):
        if a[0]=="nt_actions":
            assert a[1]==4
            nt_expected[layer]["actions"].append(a[2])
        if a[0]=="nt_groups":
            v=dict(a[2]);del v["end_s"]
            nt_expected[layer]["groups"].append(v)
        if a[0]=="nt_beam":
            nt_expected[layer]["beam"]=a[2]
            layer+=1
            if layer==nlayer:break
    assert layer==nlayer
    if not info["terminal"]:
        method="NT60"
        chosen=read(root/"runs/NT60.json")["delivered"][0]
    elif code in ("I02","I12"):
        method="Base";chosen=base["delivered"][0]
    else:
        method="Base";chosen=base["certificates"][0]
    key=chosen["plan"]
    witness=next(v for line in gzip.decompress((root/"physical/plans.jsonl.gz").read_bytes()).splitlines()
                 if (v:=json.loads(line))["certificate"]["plan_sha256"]==key)
    cfg=src.u.encoded([entry[:2] for entry in witness["plan"]["rows"][1::3]])
    identity=dict(input_sha256=obj["input_sha256"],parents=[sha(v.code) for p,v in parents],j=j+1,
        quick_actions=len(acts[j]),quick_archive_sha256=sha(raw(acts[j])),cert_plan=key,cert_config=sha(cfg),
        cert_status=chosen["status"],cert_phase=chosen["phase"],cert_route=method,cert_sequence=chosen["n"],
        archive_time_s=chosen["t"],archive_trace_sha256=witness["trace_sha256"],model=model,
        nt_archive_sha256=[sha(raw(nt_expected[k])) for k in range(nlayer)],
        sources={m:sha((root/"runs"/(m+".json")).read_bytes()) for m in {"Base","NT10",method}})
    append("inputs.jsonl",dict(case=code,attempt=ATTEMPT,**identity))
    return SimpleNamespace(id=code,obj=obj,ctx=ctx,b=b,parents=parents,qactions=acts[j],j=j,info=info,
            nt=nt_expected,parents_nt={0:[native["initial"](ctx.flow)]},cfg=cfg,witness=witness,chosen=chosen,method=method)

def quick(s,mode,out,m):
    j,b=s.j,s.b
    b.ext_cache.clear()
    states={};observed=[]
    journal=src.Journal(out)
    digest=hashlib.sha256()
    scope=b.expand.__func__.__globals__
    if m:
        m.hook(b.e,"quota","quota")
        m.hook(b.flow,"extension","extension")
        def split(cfg,kinds,ready,deadlines,postlen,lengths,threshold,horizon,boundary):
            with m.span("main_and_tail_features"):
                ends0,levels,ends,late,feat,tail=split_main(cfg,kinds,ready,deadlines,postlen,lengths,threshold,horizon,boundary)
            with m.span("cpu_stable_sort_and_post"):
                return split_post(ends,postlen,deadlines,boundary,horizon,late,ends0,levels,feat,tail)
        old=scope["timing"];scope["timing"]=split;m.cleanup.callback(scope.__setitem__,"timing",old)
        # Transform only the reference-score line; every returned state is verified.
        exp=inspect.getsource(fifo.Builder.expand)
        import textwrap
        exp=textwrap.dedent(exp)
        line=next(x for x in exp.splitlines() if "result=(*timing_row" in x)
        exp=exp.replace(line,'            with meter.span("reference_dot"):\n    '+line)
        env=dict(scope,meter=m)
        exec(exp,env)
        expand_quick=functools.partial(env["expand"],b)
        m.hook(journal,"emit","research_journal")
    else: expand_quick=b.expand
    def run():
        for pid,p in s.parents:
            if mode=="full" or m: journal.emit("parent",pid,p.code)
            for v,q,delta in expand_quick(p,j,fifo.PAIRS,[(0,0)],False):
                pair=v.pairs[-1]
                observed.append((pid,pair,q,delta,v.timing,v.code))
                if mode=="full" or m: journal.emit("q4_action",pid,j,pair,q,delta,v.timing)
                else: digest.update(v.code)
                if v.timing[-1]==0: states.setdefault(v.code,v)
        def rank():
            return sorted(states.values(),key=lambda v:(v.timing[4]+(v.timing[5] if j+1==len(b.types) else 0),v.code))
        if m:
            with m.span("sort"): ranked=rank()
        else: ranked=rank()
        chosen=[v.code.hex() for v in ranked[:4]]
        shortlist=[v.code.hex() for v in ranked[:12]] if j+1==len(b.types) else []
        if mode=="full" or m:
            journal.emit("store","base_layer",dict(window=j+1,retained=chosen,terminal=shortlist))
        else: journal.emit("minimal",s.obj["input_sha256"],j+1,digest.hexdigest(),chosen,shortlist,clock())
        journal.close()
        return chosen,shortlist
    (chosen,shortlist),cost=measure(run,f"{s.id} quick {mode}")
    assert chosen==s.info["layers"][j]["retained"] and shortlist==s.info["terminal"]
    actual=[["q4_action",pid,j,pair,q,delta,st] for pid,pair,q,delta,st,cfg in observed]
    assert raw(actual)==raw(s.qactions)
    return dict(**cost,work=len(actual),ordered_sha256=sha(b"".join(v[-1] for v in observed)),
                decision_sha256=sha(raw([chosen,shortlist])),observed_states_sha256=sha(raw(actual)),
                legal=sum(v[-2][-1]==0 for v in observed),distinct_legal=len(states))

class Sink(list):
    def __init__(self,original,group,mode,digest,seen):
        self.frozen,self.group,self.mode,self.digest,self.seen=original,group,mode,digest,seen
    def append(self,item):
        self.seen.append(item)  # symmetric observational reference, checked outside the timer
        if self.mode!="lean":
            self.frozen.append(item)
        elif self.group=="actions":
            self.digest.update(bytes.fromhex(item[6]));self.digest.update(item[9].encode())

def nt_layer(s,j,mode,out,m,omit_groups=False):
    flow=s.ctx.flow
    journal=src.Journal(out)
    digest=hashlib.sha256()
    log={};seen={k:[] for k in ("actions","groups","beam")}
    for k in seen:
        log[k]=Sink(src.ListSink(SimpleNamespace(j=journal),4,k),k,mode,digest,seen[k])
    expand_scope=expand.__globals__
    if m:
        m.hook(flow.eng,"quota","quota")
        m.hook(flow,"extension","extension")
        m.hook(flow,"candidates","candidate_generator",generator=True)
        m.hook(flow,"ledger","fifo_and_moments")
        m.hook(flow,"propagate","thermal_prediction")
        for name in ("load_planes","anchors","synthesize","grouped_means"):
            m.hook(expand_scope,name,"calibration")
        m.hook(np.linalg,"solve","calibration")
        m.hook(journal,"emit","research_journal")
        for sink in log.values():m.hook(sink.frozen,"append","research_record_build")
    run_expand=expand
    if omit_groups:
        # Only statements whose sole consumer is the research log are removed.
        source=inspect.getsource(expand)
        lo=source.index("                calibration = dict(")
        hi=source.index("                assert set(pilots)",lo)
        assert "moment_hash=" in source[lo:hi] and "synthesize" not in source[lo:hi]
        source=source[:lo]+source[hi:]
        lo=source.index('            log["groups"].append(')
        hi=source.index("    return pool, True",lo)
        assert source[lo:hi].count("log[")==1 and "calibration=calibration" in source[lo:hi]
        scope=dict(expand_scope)
        exec(source[:lo]+source[hi:],scope)
        run_expand=scope["expand"]
    def run():
        pool,complete=run_expand(flow,j,s.parents_nt[j],"NT",clock(),float("inf"),log)
        assert complete and pool
        def selection():
            ordered=sorted(pool.values(),key=lambda v:(round(v["energy"],11),v["config"]))
            parents=native["diverse"](ordered,False)
            picked={v["id"] for v in parents}
            if len(parents)<4:
                parents += [v for v in ordered if v["id"] not in picked][:4-len(parents)]
            return parents
        if m:
            with m.span("rank_and_diverse"): selected=selection()
        else: selected=selection()
        ids=[v["id"] for v in selected]
        log["beam"].append(ids)
        if mode=="lean":journal.emit("minimal",s.obj["input_sha256"],j+1,digest.hexdigest(),ids,clock())
        journal.close()
        return selected
    selected,cost=measure(run,f"{s.id} NT {j+1} {mode}")
    actual={"actions":seen["actions"],"groups":[{k:v for k,v in item.items() if k!="end_s"} for item in seen["groups"]],"beam":seen["beam"][0]}
    keys=("actions","beam") if omit_groups else tuple(actual)
    assert all(raw(actual[k])==raw(s.nt[j][k]) for k in keys), ("NT archive mismatch",s.id,j,[(k,sha(raw(actual[k])),sha(raw(s.nt[j][k]))) for k in keys])
    s.parents_nt[j+1]=selected
    return dict(**cost,work=len(actual["actions"]),groups=len(actual["groups"]),
        ordered_sha256=sha(b"".join(bytes.fromhex(v[6]) for v in actual["actions"])),
        decision_sha256=sha(raw(actual["beam"])),observed_states_sha256=sha(raw(actual)),
        actions_sha256=sha(raw(actual["actions"])),
        legal=sum(v[9]=="valid" for v in actual["actions"]))

def certificate(s,mode,out,m):
    unit=s.ctx
    eng=unit.e if s.method=="Base" else unit.flow.eng
    eng.out=out
    groups=eng.cert.__func__.__globals__
    heat=groups["evaluate"].__globals__
    journal=src.Journal(out)
    rank=s.chosen["n"]
    if m:
        for name in ("transitions","event_arrays","independent_events"):
            m.hook(groups,name,"event_construction_and_crosscheck")
        m.hook(heat,"independent_events","cert_independent_events")
        m.hook(heat,"integrate","continuous_integrator")
        m.hook(groups,"evaluate","cert_metrics_trace_list")
        m.hook(groups,"put","plan_cert_json_archive")
        m.hook(np,"savez_compressed","compressed_trace_archive")
        m.hook(eng,"build","plan_build_and_refcheck")
        m.hook(eng,"cert","cert_assembly")
        m.hook(journal,"emit","research_journal")
    def run():
        started=clock()
        if mode!="lean":
            if s.method=="Base":journal.emit("choice","terminal",rank,s.cfg)
            journal.emit("cert_start",rank,s.chosen["phase"],clock()-started,s.cfg)
        if s.method=="Base":
            if m:
                with m.span("causal_timing"):state=unit.stack[3](unit.flow,s.cfg)
            else:state=unit.stack[3](unit.flow,s.cfg)
            d,tr=eng.cert(src.genes(s.cfg),state)
        else:
            if m:
                with m.span("causal_timing"):d,tr=unit.flow.certify(s.cfg)
            else:d,tr=unit.flow.certify(s.cfg)
        metrics=d["metrics"]
        record=dict(n=rank,phase=s.chosen["phase"],plan=d["plan_sha256"],status=metrics["status"],
            J=metrics["E_J"],bounds=metrics["E_bounds"],peak=max(metrics["peak_hi"]),slack=metrics["min_deadline_slack_ms"],
            kernel_s=d["cert_s"],t=clock()-started)
        if mode!="lean":journal.emit("cert",record)
        if metrics["status"]=="SAFE":journal.emit("delivered",record,clock()-started)
        if mode=="lean":journal.emit("minimal",s.obj["input_sha256"],sha(s.cfg),record["plan"],record["status"],clock()-started)
        journal.close()
        return d,tr
    (d,tr),cost=measure(run,f"{s.id} certificate {mode}")
    path=out/"evidence"/s.obj["case"]/d["plan_sha256"]
    old=s.witness["certificate"]
    real=read(path/"certificate.json")
    assert raw(read(path/"plan.json"))==raw(s.witness["plan"])
    assert all(raw(real[k])==raw(old[k]) for k in old if k!="cert_s")
    with np.load(path/"trace.npz") as f:
        assert np.array_equal(tr,f["events"])
    td=sha(tr.tobytes());assert td==s.witness["trace_sha256"]
    return dict(**cost,work=len(tr),ordered_sha256=sha(s.cfg),decision_sha256=d["plan_sha256"],
        observed_states_sha256=td,certificate_sha256=sha(raw({k:v for k,v in real.items() if k!="cert_s"})),
        status=real["metrics"]["status"],evaluate_inclusive_s=d["cert_s"],
        physical_bytes=sum(p.stat().st_size for p in path.iterdir()))

def snapshot(label):
    ps=psutil
    seeds={}
    for p in ps.process_iter(["name","cpu_times"]):
        try:seeds[p.pid]=(p.info["name"],sum(p.info["cpu_times"][:2]))
        except (ps.Error,TypeError):pass
    a=clock();load=ps.cpu_percent(interval=.4,percpu=True)
    busy=[]
    for pid,(name,prior) in seeds.items():
        try: delta=sum(ps.Process(pid).cpu_times()[:2])-prior
        except ps.Error:continue
        if delta>.015:busy.append((name,pid,round(delta/(clock()-a),3)))
    busy.sort(key=lambda x:-x[2])
    append("load.jsonl",dict(label=label,attempt=ATTEMPT,utc=time.time(),per_core=load,core=cpu,
           busy=busy[:12],threads=PS.num_threads()))
    return [v for v in busy if v[1]!=PS.pid and v[2]>=.5 and v[0].lower().startswith(("python","matlab"))]

def main():
    pulse("startup, cache, target-blind warm-up",90)
    with tempfile.TemporaryDirectory(prefix="u4-cost-") as d:
        temp=Path(d)
        init_runtime(temp)
        done={(r["case"],r["rep"],r["stage"],r["mode"]) for r in rows(OUT/"raw.jsonl")}
        for idx,case in enumerate(CASES):
            jlist=range(2 if case in TWO else 1)
            modes={"full","lean","probe"}
            if all((case,rep,k,m) in done for rep in range(3) for k in ["quick","certificate",*["nt"+str(j+1) for j in jlist]] for m in modes):
                continue
            pulse("prepare "+case,30)
            busy=snapshot(case+" before")
            if busy:
                time.sleep(1)
                assert not snapshot(case+" recheck"),("concurrent scientific process",busy)
            path=temp/case;path.mkdir()
            s=prepare(case,path)
            for rep in range(3):
                for name,fn in [("quick",quick),*[(f"nt{j+1}",functools.partial(nt_layer,j=j)) for j in jlist],("certificate",certificate)]:
                    order=["full","lean"] if (idx+rep)%2==0 else ["lean","full"]
                    for mode in order+["probe"]:
                        if (case,rep,name,mode) in done:
                            continue
                        folder=path/f"{rep}-{name}-{mode}";folder.mkdir()
                        meter=Meter() if mode=="probe" else None
                        if name=="nt2" and 1 not in s.parents_nt:
                            # Restore four archived parent states by exact identities without repeating search.
                            restore_nt_second(s)
                        with meter.cleanup if meter else contextlib.nullcontext():
                            result=fn(s,mode=mode,out=folder,m=meter)
                        if meter:
                            result["exclusive_wall_s"]=dict(meter.wall)
                            result["probe_calls"]=dict(meter.calls)
                            result["residual_wall_s"]=result["wall_s"]-sum(meter.wall.values())
                            assert result["residual_wall_s"]>=-1e-6
                        append("raw.jsonl",dict(case=case,rep=rep,stage=name,mode=mode,attempt=ATTEMPT,
                            start_order=order[0],cpu=cpu,utc=time.time(),**result))
                        if name=="nt1" and case in TWO and not (OUT/(case+"-parents.json")).exists():
                            save_parents(s)
            snapshot(case+" after")
        pulse("cleanup",30)
    print("Complete",flush=True)

def save_parents(s):
    serialized=[]
    for p in s.parents_nt[1]:
        serialized.append({k:(v.hex() if k=="config" else v.tolist() if isinstance(v,np.ndarray)
                              else v.item() if isinstance(v,np.generic) else v) for k,v in p.items()})
    (OUT/(s.id+"-parents.json")).write_bytes(raw(serialized)+b"\n")

def restore_nt_second(s):
    parents=read(OUT/(s.id+"-parents.json"))
    for p in parents:
        p["config"]=bytes.fromhex(p["config"])
        p["temperature"]=np.asarray(p["temperature"])
        assert sha(p["config"])==p["id"]
    assert [p["id"] for p in parents]==s.nt[0]["beam"]
    s.parents_nt[1]=parents

if __name__=="__main__":
    main()
