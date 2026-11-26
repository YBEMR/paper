"""Offline only. Follow recorded parents, then splice one frozen certified suffix."""
from common import *
from attribution import sets, advance, empty
from diagnose import entry

ARMS=("HT_w4b4","NT_w4b4","HT_w4b4s")
def witness(c):
    d=OLD/"data/search/L800/HT_w4b4"
    cert=min((v for v in load(d/"result.json")["certificates"] if v["status"]=="SAFE"),key=lambda v:v["E"])
    h=next(v["history"] for v in load(d/"beam.json") if v["id"]==cert["config"])
    assert abs(cert["E"]-49.601232268650534)<1e-10 and digest(materialize(c,h))==cert["config"]
    return h,cert

def main():
    verify_inputs()
    out=DATA/"historical"
    c=Case("L800",out)
    h,ref=witness(c)
    ref_ids=[digest(materialize(c,h[:j])) for j in range(11)]
    trace_dir=OLD/"data/search/L800/HT_w4b4/evidence/L800"/ref["plan"]
    with np.load(trace_dir/"trace.npz") as f:
        trace=f["events"]
    path=[]; splices=[]; memo={}
    for arm in ARMS:
        d=OLD/"data/search/L800"/arm
        beam=load(d/"beam.json")
        certs=load(d/"result.json")["certificates"]
        ancestry={digest(materialize(c,v["history"][:j])):True for v in beam if any(v["id"]==s["config"] for s in certs) for j in range(1,11)}
        with gzip.open(d/"proposals.csv.gz","rt") as f:
            trials=list(csv.DictReader(f))
        p=empty(c)
        for j,act in enumerate(h,1):
            child=ref_ids[j]
            kept=[v for v in beam if v["window"]==j]
            rank=next((v["rank"] for v in kept if v["id"]==child),None)
            proposals=[v for v in trials if int(v["window"])==j and v["parent"]==ref_ids[j-1]]
            z=next((v for v in proposals if v["config"]==child and v["result"]=="valid"),None)
            o,n,th,_,_=sets(c,p,j-1,tuple(act[:2]),arm.endswith("s"))
            conditional=tuple(act[2:]) in (n if arm.startswith("N") else th)
            upto=c.p.horizon if j==10 else j*WINDOW
            exact=entry(c,trace,upto)[2]
            next_exact=entry(c,trace,(j+1)*WINDOW if j<9 else c.p.horizon)[2]
            path.append(dict(arm=arm,window=j,parent=ref_ids[j-1],child=child,action=act,
                          parent_reached=bool(proposals),conditional_action=conditional,generated=bool(z),rank=rank,
                          reason="retained" if rank else "parent_lost" if not proposals else "pruned" if z else "not_generated",
                          descendant_certified=child in ancestry,reference_peak=exact,predicted_peak=z and z["predicted_peak"],
                          repeat_load_risk=z and z["risk"],reference_next_peak=next_exact))
            for v in kept:
                cfg=materialize(c,v["history"]+h[j:])
                key=digest(cfg)
                if key not in memo:
                    l=c.ledger(cfg,0,c.p.horizon,WINDOW,True,False)
                    m=dict(full=key,status="TIMING",slack_ticks=int(l[-1]))
                    if l[0]:
                        cert,_=c.certify(cfg)
                        a=cert["metrics"]
                        m.update(status=a["status"],energy=a["E_J"],peak=max(a["peak_hi"]),plan=cert["plan_sha256"])
                    memo[key]=m
                formal=any(key==s["config"] for s in certs)
                splices.append(dict(arm=arm,window=j,rank=v["rank"],prefix=v["id"],history=v["history"],
                                  has_any_certified_descendant=v["id"] in ancestry,exact_completion_certified=formal,**memo[key]))
            p=advance(c,p,j-1,act)
    write_rows(out/"path.csv",path);write_rows(out/"splices.csv",splices)
    assert [v["rank"] for v in path[:10]][1:8]==[4]*7
    print("archived first loss",[(arm,next((r["window"] for r in path if r["arm"]==arm and not r["rank"]),None)) for arm in ARMS],
          "unique splice plans",len(memo),flush=True)

if __name__=="__main__":
    main()
