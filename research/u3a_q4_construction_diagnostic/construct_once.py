"""Observe the frozen function at the candidate and retained-state boundaries."""
import gzip
import inspect
import textwrap
from datetime import datetime, timezone
from runtime import *

def capture(engine, fourth):
    layers=[]
    overhead=0.
    def observe(j,c,r,pair,q,ext,nr):
        nonlocal overhead
        start=perf_counter()
        if len(layers)==j:
            layers.append(dict(attempts=[], retained=[]))
        score=None if nr is None else nr["cost"]+(nr["tail"] if j+1==len(engine.groups) else 0)
        layers[j]["attempts"].append(dict(parent=u.encoded(c).hex(),f=r["f"],k=r["k"],
            pair=pair,quota=q,extension=u.encoded(ext).hex(),score=score))
        overhead+=perf_counter()-start
    def retain(j,states):
        nonlocal overhead
        start=perf_counter()
        layers[j]["retained"]=[u.encoded(c).hex() for c,_,_ in states]
        overhead+=perf_counter()-start
    source=textwrap.dedent(inspect.getsource(fourth.Engine.construct))
    marker="                if nr is None:continue"
    last="    c,r,h=states[0];"
    assert source.count(marker)==1 and source.count(last)==1
    source=source.replace(marker,"                observe(j,c,r,pair,q,ext,nr)\n"+marker)
    source=source.replace(last,"        retain(j,states)\n"+last)
    scope=dict(fourth.Engine.construct.__globals__,observe=observe,retain=retain)
    exec(compile(source,"<frozen construct + two observers>","exec"),scope)
    start=times()
    cr,meta=scope["construct"](engine,"quota",4)
    timing=duration(start)
    timing["observers_wall_s"]=overhead
    return cr,meta,layers,timing

def ranked(layer):
    by_config={}
    for a in layer["attempts"]:
        if a["score"] is not None:
            k=a["parent"]+a["extension"]
            by_config.setdefault(k,a["score"])
            assert by_config[k]==a["score"]
    return sorted(by_config,key=lambda k:(by_config[k],k))

def run(obj,stack):
    code,dest,flow,engine,_=case_context(obj,stack)
    history=read(dest/"history.json")
    marker=dest/"construction_start.json"
    if marker.exists():
        assert (dest/"construction.json").is_file(), "Interrupted unit; inspect recorded pool, never relaunch."
        return
    with marker.open("x") as f:
        json.dump(dict(pid=os.getpid(),utc=datetime.now(timezone.utc).isoformat()),f)
    cr,meta,layers,timing=capture(engine,stack[1])
    (dest/"raw_pool.json.gz").write_bytes(gzip.compress(raw(layers),compresslevel=5,mtime=0))
    assert raw(meta)==raw(history["construction"])
    for j,layer in enumerate(layers):
        # Original lexicographic order is unit then OPP, equivalent to canonical byte order.
        assert ranked(layer)[:4]==layer["retained"]
        assert len(layer["attempts"])==30*meta["scenes"][j]["input_states"]
        assert sum(a["score"] is not None for a in layer["attempts"])==meta["scenes"][j]["feasible_candidates"]
    retained=layers[-1]["retained"]
    if cr:
        cfg,r=cr
        assert u.encoded(cfg).hex()==retained[0]
        key,_=full(obj["case"],engine,cfg,r)
        assert key==history["native"]["key"]
    else:
        assert not retained and "native" not in history
    save(dest/"construction.json",dict(meta=meta,timing=timing,retained=retained,
        source_sha256=sha(Path(stack[1].__file__).read_bytes()),matched_historical_metadata=True))
    print(code,len(layers),len(retained),flush=True)

if __name__=="__main__":
    stack=u.stack()
    for f,h in stack[1].PIN.items():
        b=(INPUTS/"p1/research/cross_scene_taskflow_diagnostic"/f).read_bytes()
        assert b==(u.FOUR/"p1"/f).read_bytes() and stack[1].blob(b)==h
    for obj in u.CASES:run(obj,stack)
