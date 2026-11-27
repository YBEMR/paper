"""Local re-expansion with a full prefix replay and a recoverable candidate ledger."""
import gzip
import hashlib
import json
import numpy as np

from fifo import PAIRS, OFFSETS, unique
from guidance import Guidance

def key(code):
    return hashlib.sha256(code).hexdigest()

class Ledger:
    def __init__(self,ctx):
        self.ctx=ctx
        self.parents={}
        self.events=[]
    def expand(self,parent,j,pairs,offsets):
        pk=self.parents.setdefault(parent.code,len(self.parents))
        for v,q,delta in self.ctx.b.expand(parent,j,pairs,offsets,True):
            self.events.append([pk,j+1,*v.pairs[-1],*q,*delta,*v.timing[4:]])
            yield v
    def dump(self,name):
        # A parent plus pair and final integer quota reconstruct every attempted action byte.
        data=dict(parents=[s.hex() for s in self.parents],columns=["parent_index","window","gpu","npu",
            "quota_A","quota_B","delta_A","delta_B","cost","tail","slack","backlog","post_end","worst_violation_ticks"],
            attempts=self.events)
        with gzip.open(self.ctx.out/(name+".json.gz"),"wt",encoding="utf8",compresslevel=1) as f:
            json.dump(data,f,separators=(",",":"))
        self.parents.clear()
        self.events.clear()

def certify_pool(ctx,name,states,limit,guide=None):
    pool=unique(states)
    ordinary=sorted(pool,key=lambda v:v.ordinary)
    predictions={v.code:guide.predict(v) for v in ordinary} if guide else {}
    order=sorted(ordinary,key=lambda v:(predictions[v.code],v.ordinary)) if guide else ordinary
    rows=[dict(config=v.code.hex(),ordinary=list(v.ordinary[:-1]),prediction=predictions.get(v.code)) for v in order]
    ctx.store(name+"-pool",dict(common_digest=key(b"".join(v.code for v in sorted(pool,key=lambda v:v.code))),
        size=len(pool),ranking=rows))
    tries=0
    for v in order:
        if v.code in ctx.seen:
            continue
        if tries==limit:
            break
        tries+=1
        if ctx.certify(v,name,tries,predictions.get(v.code))[0]["metrics"]["status"]=="SAFE":
            return True
    return False

def backlog(ctx,pair):
    b=ctx.b
    hit=len(b.layers)-2
    start=hit-1
    parents=b.layers[start]
    ledger=Ledger(ctx)
    for j in range(start,len(b.types)):
        offsets=OFFSETS if j==start or (j==hit and pair) else [(0,0)]
        pool=unique(v for parent in parents for v in ledger.expand(parent,j,PAIRS,offsets) if v.timing[-1]==0)
        pool.sort(key=lambda v:v.ordinary)
        ledger.dump("backlog-w%02d"%(j+1))
        ctx.stages.append(dict(window=j+1,legal=len(pool),local_replays=b.replays))
        ctx.checkpoint()
        if not pool:
            return False
        if j+1==len(b.types):
            return certify_pool(ctx,"backlog-terminal",pool,8)
        parents=pool[:12 if j<=hit else 4]
    return False

def anchor_window(ctx,anchor):
    b=ctx.b
    r=b.e.replay(tuple((3,int(v)-10) if v>=10 else (2,int(v)) for v in anchor.code))
    assert r is not None
    rows=[]
    for j,ids in enumerate(b.e.groups):
        post=np.array([r["posts"][i]+b.e.q[i] for i in ids])
        slack=min(b.e.D[i]-post[h] for h,i in enumerate(ids))
        backlog=sum(v>(j+1)*b.e.dur for v in post)
        energy=sum(b.args[5][b.flow.kinds[i],int(anchor.code[i]>=10),anchor.code[i]%10] for i in ids)
        rows.append([int(slack),-int(backlog),-int(energy),j])
    return min(rows)[3],rows

def thermal_block(ctx,method,anchor,first_cert,trace):
    b=ctx.b
    plain,nonthermal=anchor_window(ctx,anchor)
    guide=Guidance(b,anchor,first_cert,trace) if "h" in method else None
    chosen=guide.window if method[0]=="h" else plain
    ctx.store("location",dict(ordinary_w=plain+1,ordinary_keys=nonthermal,selected_w=chosen+1,
              heat=guide.observation if guide else None))
    cuts=np.cumsum([0]+[len(t) for t in b.types])
    for stage,windows in (("single",[chosen]),("adjacent",sorted({chosen,chosen-1 if chosen else 1}))):
        j0=windows[0]
        # Recover the exact prefix already retained by this route's baseline construction.
        parents=[next(v for v in b.layers[j0] if v.code==anchor.code[:cuts[j0]])]
        ledger=Ledger(ctx)
        for j in range(j0,len(b.types)):
            changed=j in windows
            pairs=PAIRS if changed else [anchor.pairs[j]]
            offsets=OFFSETS if changed else [(0,0)]
            pool=unique(v for parent in parents for v in ledger.expand(parent,j,pairs,offsets) if v.timing[-1]==0)
            if len(windows)==2 and j==j0:
                pool=sorted(pool,key=lambda v:v.ordinary)[:4]
            parents=pool
            if not parents:
                break
        ledger.dump(stage+"-attempts")
        complete=[v for v in parents if len(v.code)==b.e.n]
        ctx.stages.append(dict(stage=stage,windows=[j+1 for j in windows],complete=len(complete),local_replays=b.replays))
        ctx.checkpoint()
        if certify_pool(ctx,stage,complete,4,guide if method[1]=="h" else None):
            return True
        if b.closed:
            break
    return False

