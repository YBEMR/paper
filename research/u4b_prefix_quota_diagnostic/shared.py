"""Shared interfaces to the frozen checkout; target-blind environment setup."""
import os
import sys
import json
import gzip
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ.get("U4B_LAB", HERE.parents[2])).resolve()
A = Path(os.environ.get("U4A_SRC", LAB/"U4a_worktree/research/u4a_integrated_fast_scheduler"))
RAW = Path(os.environ.get("U4B_RUNS", LAB/"U4b_raw"))
os.environ.update(U3B_SRC=os.environ.get("U3B_SRC", str(LAB/"U3b_worktree/research/u3b_blockage_triggered_quota")),
                  U3A_INPUTS=os.environ.get("U3A_INPUTS", str(LAB/"U3a_inputs")), U4_RUNS=str(RAW))
os.environ.setdefault("NUMBA_CACHE_DIR",str(LAB/"U3b_compute_cache"))
sys.path.insert(0,str(A))
spec = importlib.util.spec_from_file_location("frozen_protocol", A/"experiment.py")
src = importlib.util.module_from_spec(spec)
spec.loader.exec_module(src)
from fifo import Builder, State, PAIRS, OFFSETS
archive_spec=importlib.util.spec_from_file_location("u4a_verified_archive",A/"verify_archive.py")
archive=importlib.util.module_from_spec(archive_spec)
archive_spec.loader.exec_module(archive)
trace_reader=archive.trace_reader
np, u = src.np, src.u
FOCUS = ("I03","I05","I06","I07","I09","I11")

def read(p):
    return json.loads(p.read_bytes())

def put(p, v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=1,default=lambda x:x.item())+"\n",encoding="utf8")

def sha(b):
    return hashlib.sha256(b).hexdigest()

def cases():
    return {o["id"]:o for o in read(A/"registration/cases.json") if o["cohort"]=="independent"}

def limits(b):
    return np.cumsum([len(t) for t in b.types]).tolist()

def extra(a,b,x,y):
    total=x+y
    lo,hi=max(0,total-b),min(a,total)
    return sorted({(ax,total-ax) for ax in (lo,(lo+hi)//2,hi)} | {(0,0),(a,0),(0,b),(a,b)})

def events(root, run):
    for name in run["journal"]:
        data=gzip.decompress((root/name).read_bytes())
        assert sha(data)==Path(name).name.split(".")[0]
        for line in data.splitlines():
            yield json.loads(line)

def hot(tr):
    lower=tr[:,18:22]-tr[:,30:31]
    indices=np.flatnonzero(lower.max(axis=1)>80.)
    if not len(indices):
        return None
    i=int(indices[0]);node=int(np.argmax(lower[i]))
    return dict(tick=int(tr[i,1]),node=node,lower_C=float(lower[i,node]),rows=i+1,
                events_sha256=sha(tr[:i+1,:14].astype("<f8").tobytes()))

def settled_key(code, tick, b):
    for j,n in enumerate(limits(b)[:-1],1):
        if tick<=j*b.e.dur-5:
            return code[:n]
    return code

def open_events(flow,code,cut):
    """Open FIFO intervals only. Future release decisions cannot write before cut."""
    e,p=flow.eng,flow.p
    assert len(code)<e.n and cut==int(flow.release[len(code)]//e.dur)*e.dur-5
    l=flow.ledger(code,0,cut,e.dur,False,False,True)
    start,end,post,down=l[4:8]
    kinds=flow.kinds[:len(code)]
    spans=[[],[],[],[]]
    switches=[[],[],[],[]]
    finish=[0]*4
    opp=[0]*4
    for i,v in enumerate(code):
        unit=3 if v>=10 else 2
        k=v-10*(unit==3)
        spans[0].append((e.ps[i],e.a[i],0,kinds[i]))
        spans[1].append((post[i],post[i]+e.q[i],0,kinds[i]))
        spans[unit].append((start[i],end[i],k,kinds[i]))
        old=opp[unit]
        if down[i]:
            switches[unit].append((finish[unit],finish[unit]+5,old,0))
            old=0
        if old!=k:
            switches[unit].append((start[i]-5,start[i],old,k))
        finish[unit],opp[unit]=end[i],k
    ticks={0,cut,*[t for t in p.boundaries if 0<t<cut]}
    for group in spans+switches:
        for s,z,*_ in group:
            if 0<s<cut:ticks.add(s)
            if 0<z<cut:ticks.add(z)
    grid=np.array(sorted(ticks));left=grid[:-1]
    ev=np.empty((len(left),14));ev[:,0],ev[:,1]=left,grid[1:]
    busy,beta,_,idle,idle_beta=flow.args[6:11]
    for unit in range(4):
        k=np.zeros(len(left),int)
        changing=np.zeros(len(left),bool)
        for s,z,old,new in switches[unit]:
            lft,rgt=grid.searchsorted([s,z])
            changing[lft:rgt]=True
            k[rgt:]=new
        ev[:,10+unit]=idle[unit,k]
        ev[:,2+unit]=idle[unit,k]+3.*changing
        ev[:,6+unit]=idle_beta[unit,k]
        if spans[unit]:
            s,z,levels,types=np.array(sorted(spans[unit]),dtype=int).T
            ix=np.searchsorted(s,left,side="right")-1
            on=(ix>=0)&(left<z[ix])
            ii=ix[on]
            assert np.array_equal(k[on],levels[ii]) and not changing[on].any()
            ev[on,2+unit]=busy[types[ii],unit,levels[ii]]
            ev[on,6+unit]=beta[types[ii],unit,levels[ii]]
    return ev

def open_proof(flow,code,cut):
    from heat import integrate
    ev=open_events(flow,code,cut);p=flow.p
    out=integrate(ev,p.initial,p.G,p.cap,float(p.ta),np.empty(0,np.int64),True)
    tr=np.column_stack((ev,out[10]))
    return hot(tr),float(max(out[2])),tr
