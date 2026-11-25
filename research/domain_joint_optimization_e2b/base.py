"""Read frozen modules. Numerical workers write only to their own run directory."""
import csv,gzip,hashlib,json,os,sys,time
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
ROOT=Path(__file__).resolve().parent
E2=ROOT.parent/"domain_joint_optimization_e2a"
BASE="d313094505db8eb1114b0d5859210b058f7bfa76"
sys.path.insert(0,str(E2))
from assets_e2 import OLD,E1,FOLLOW,REPO,DOM,raw,sha,obj,decode,archived,Problem,Layout,evaluate,transitions,np
from reference_objective import Core,Access
from master import cp,solver

def clock():return time.perf_counter()
def read(path):return json.loads(Path(path).read_bytes())
def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp");t.write_bytes(raw(data)+b"\n");t.replace(p)
def table(path,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");writer.writeheader();writer.writerows(rows)
def key(p,plan):return sha(raw(obj(p.case,plan)))
def bins(p):
    result={}
    for i in range(p.n):result.setdefault(p.req[i//3]["release_tick"]//2500,[]).append(i)
    return result
def components(m):
    return {k:m[k] for k in ("E_J","E_bounds","peak_hi","min_deadline_slack_ms","activity_J","base_J",
                               "temperature_J","switch_J","external_J","switch_count","status")}
def unit_lists(rows):
    work=[[] for _ in range(4)]
    for i,(u,k,t) in enumerate(rows):work[u].append(i)
    return [sorted(a,key=lambda i:(rows[i][2],i)) for a in work]
def changes(p,base,plan):
    before,after=base[0],plan[0]
    cfg=[i for i,(a,b) in enumerate(zip(before,after)) if a[:2]!=b[:2]]
    shifted=[i for i,(a,b) in enumerate(zip(before,after)) if a[2]!=b[2]]
    left=unit_lists(before);right=unit_lists(after)
    edges=lambda seq:{(u,i,j) for u,work in enumerate(seq) for i,j in zip(work,work[1:])}
    old,new=edges(left),edges(right);inversions=[]
    for u,work in enumerate(right):
        rank={i:k for k,i in enumerate(left[u])};seen=[]
        for i in work:
            if i in rank:
                # All original relative order inversions, including jumps over fixed neighbors.
                for j in reversed(seen):
                    if rank[j]<=rank[i]:break
                    inversions.append((u,j,i))
                import bisect
                bisect.insort(seen,i,key=rank.__getitem__)
    return dict(config=cfg,moved=shifted,only_timing=sorted(set(shifted)-set(cfg)),inversions=inversions,
                removed_edges=sorted(old-new),added_edges=sorted(new-old),gap_added=sorted(plan[1]-base[1]),
                gap_removed=sorted(base[1]-plan[1]),scenes=sorted({p.req[i//3]["scene"] for i in set(cfg+shifted)}))
def dynamic_region(p,plan,st,sf,mode):
    rows,low=plan;lay=Layout(p,rows);st=set(st);envelopes=[];intervals=[[] for _ in range(3)]
    for i in sorted(st):
        u0,k0,t=rows[i];req=p.req[i//3]
        options=p.options[i] if i in sf else [(u0,k0)]
        for u,k in options:
            if mode<3 and u!=u0:continue
            d=p.dur(i,u,k);lo=max(0,t-500,req["release_tick"]);hi=min(t+500,req["deadline_tick"]-d,p.horizon-d)
            if hi<lo:continue
            envelopes.append([i,u,k,lo,hi,hi+d]);intervals[DOM[u]].append((lo,hi+d))
    gaps={}
    for (d,i),(sig,owners) in lay.gaps.items():
        _,a,b,_,_=sig
        allowed=i in st or any(j in st for j in owners) or any(l<=b and a<=h for l,h in intervals[d])
        gaps[sig]=(allowed,(d,i) in low)
    identity=key(p,plan)
    return dict(envelopes=envelopes,prior=gaps,source=identity,identity=sha(raw([identity,sorted(st),envelopes,sorted(gaps.items())])))
