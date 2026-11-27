"""Frozen interfaces and exact FIFO diagnostics. Online callers never open reference plans."""
import os
import sys
from pathlib import Path
from time import perf_counter
HOME_C=Path(__file__).resolve().parent
LAB_C=Path(os.environ.get("U4C_LAB",HOME_C.parents[2])).resolve()
B_SRC=Path(os.environ.get("U4B_SRC",LAB_C/"U4b_worktree/research/u4b_prefix_quota_diagnostic"))
OUT_C=Path(os.environ.get("U4C_RUNS",LAB_C/"U4c_raw"))
os.environ["U4B_RUNS"]=str(OUT_C)
sys.path.insert(0,str(B_SRC))
import shared as frozen
import routes as baseline
from shared import Builder, State, PAIRS, OFFSETS, extra, limits, u, np, src, sha, events, cases, read, put
FOUR=("I06","I03","I07","I11")
ARMS=("Parent","Margin","Small","BlockedSmall","BlockedMix")
def ledger(flow,code):
    return flow.ledger(code,0,flow.p.horizon,flow.eng.dur,False,False,True)
def ends_slack(flow,l):
    n=len(l[4]);post=l[6]+flow.args[4][:n]
    return post,flow.args[5][:n]-post
def detail(flow,code,i,l):
    end,slack=ends_slack(flow,l);i=int(i);rec=flow.p.req[i]
    return dict(i=i,kind=rec["kind"],release=int(flow.release[i]),deadline=int(flow.eng.D[i]),
                device=2+int(code[i]>=10),opp=code[i]%10,ready=int(flow.eng.a[i]),start=int(l[4][i]),
                main_end=int(l[5][i]),post_start=int(l[6][i]),finish=int(end[i]),slack=int(slack[i]))
def conflict(flow,code,l=None):
    if l is None:l=ledger(flow,code)
    end,slack=ends_slack(flow,l);bad=np.flatnonzero(slack<0)
    if not len(bad):return None
    i=min(bad,key=lambda i:(flow.eng.D[i],i))
    return detail(flow,code,i,l)
def margins(flow,code,j,n0):
    l=ledger(flow,code);end,s=ends_slack(flow,l);boundary=(j+1)*flow.eng.dur
    pending=end>boundary
    return dict(current=int(s[n0:].min()),pending=int(s[pending].min()) if np.any(pending) else None,
                all=int(s.min()),backlog=int(pending.sum()),device_free=l[2].tolist(),opp=l[3].tolist(),
                post_free=int(end.max()))
def priority(m):
    return (m["pending"] is not None,-(m["pending"] or 0),-m["current"])
def finite_offsets(b,parent,j,pair):
    a,bb=b.counts[j]
    x,y=b.e.quota(dict(f=parent.timing[:2],k=parent.timing[2:4]),j,pair,(a,bb))
    return list(dict.fromkeys([*OFFSETS,*[(i-x,k-y) for i,k in extra(a,bb,x,y)]]))
