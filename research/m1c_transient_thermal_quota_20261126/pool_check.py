"""Offline, same-pool ablations. Spliced answers are never inputs to retain or run."""
from collections import Counter
from functools import lru_cache
from time import perf_counter
import csv
import gzip
from common import *
from events import build_events
from heat import integrate
from history_check import witness
from expand import expand
from retain import retain,RULES
from run import gzjson

ARM={"H":"HT_w4b4","N":"NT_w4b4","Hs":"HT_w4b4s"}

def physical(c,cfg,right,closed):
    l=c.ledger(cfg,0,right,WINDOW,closed,False)
    if not l[0]:
        return dict(status="TIMING",slack=int(l[-1]))
    # For an open prefix preserve the last OPP across the cut. The artificial
    # terminal transition of the event builder is placed beyond the cut.
    end=right if closed else right+2*WINDOW
    ev=build_events(np.frombuffer(cfg,np.uint8),c.kinds,c.args[2],c.args[3],c.args[4],c.args[6],c.args[7],
                    c.args[9],c.args[10],l[4],l[5],l[6],l[7],0,end)
    if not closed:
        ev=ev[ev[:,0]<right].copy()
        ev[-1,1]=right
    assert ev[0,0]==0 and ev[-1,1]==right and np.all(ev[1:,0]==ev[:-1,1])
    q=integrate(ev,c.p.initial,c.p.G,c.p.cap,35.,np.empty(0,np.int64),True)
    lo=float(max(q[1]));hi=float(max(q[2]))
    if lo>100 or min(q[4])<20: status="OUT_OF_MODEL"
    elif min(q[3])<20 or hi>100 or hi-lo>.001 or q[6]>1e-6: status="UNRESOLVED"
    else: status="SAFE" if hi<=80 else "HOT" if lo>80 else "UNRESOLVED"
    return dict(status=status,peak=hi,lower=lo,slack=int(l[-1]),E=q[0],error_J=q[6])

def main():
    out=DATA/"same_pool"
    c=Case("L800",out)
    hist,cert=witness(c); answer=materialize(c,hist)
    measure=lru_cache(maxsize=4096)(lambda cfg,right,closed:physical(c,cfg,right,closed))
    ref=measure(answer,c.p.horizon,True)
    assert abs(ref["E"]-cert["E"])<1e-8 and abs(ref["peak"]-cert["peak"])<1e-8
    timeline=[]; selection=[]; probes=[]; labels=[]; witnesses=[]; scores=[]
    start=perf_counter()
    for gen,arm in ARM.items():
        legacy=OLD/"data/search/L800"/arm
        old=load(legacy/"beam.json")
        formal=load(legacy/"result.json")["certificates"]
        certified={v["id"]:v for v in old if any(t["config"]==v["id"] for t in formal)}
        ancestors=[{digest(materialize(c,v["history"][:j+1])) for v in certified.values()} for j in range(10)]
        with gzip.open(legacy/"proposals.csv.gz","rt") as f:
            old_rows=list(csv.DictReader(f))
        states=[initial(c)]
        for j in range(c.windows):
            rows=[]
            pool,expired=expand(c,j,states,gen,True,Counter(),rows)
            expected=[(v["parent"],*(int(v[k]) for k in ("g","n","x","y")),v["config"],v["result"])
                      for v in old_rows if int(v["window"])==j+1]
            assert not expired and [(v[1],*v[2:7],v[9]) for v in rows]==expected
            reference=answer[:len(next(iter(pool.values()))["config"])]
            target=digest(reference)
            decisions={};considered={};slate=set(); original_ids=[]
            for rule in RULES:
                forecasts=[];count=Counter()
                beam,metrics=retain(c,j,list(pool.values()),rule,count,forecasts)
                ids=[s["id"] for s in beam];decisions[rule]=ids
                if rule=="original":
                    states=beam;original_ids=ids
                    assert ids==[v["id"] for v in old if v["window"]==j+1]
                assert ids[:3]==original_ids[:3] and (j<9 or ids==original_ids)
                slate.update([*ids,*(m["id"] for m in metrics)])
                considered[rule]=set(pool) if rule=="original" or j==9 else {*(ids[:3]),*(m["id"] for m in metrics)}
                scores.append(dict(generator=gen,window=j+1,rule=rule,metrics=metrics,counts=dict(count)))
                if rule=="suffix":
                    # Audit each shortlist member's selected probe at the exact horizon it predicts.
                    bykey={(v["prefix"],tuple(v["action"])):v for v in forecasts}
                    for m in metrics:
                        s=pool[m["id"]]; act=tuple(m["probe"])
                        v=bykey[s["id"],act]
                        cfg=s["config"]+c.extension(*window_types(c,j+1),*act)
                        final=j+2==c.windows
                        result=measure(cfg,c.p.horizon if final else (j+2)*WINDOW,final)
                        probes.append(dict(generator=gen,window=j+1,id=s["id"],action=act,
                                      next_config=digest(cfg),predicted=v["projected_peak"],timing=v["ok"],**result))
                        assert v["ok"]==(result["status"]!="TIMING")
            if target in pool:slate.add(target)
            exhaustive=(gen=="N" and j==4) or (gen=="Hs" and j==0)
            test_ids=sorted(pool if exhaustive else slate)
            results={}
            for key in test_ids:
                s=pool[key]; full=s["config"]+answer[len(reference):]
                metric=measure(full,c.p.horizon,True);results[key]=metric
                labels.append(dict(generator=gen,window=j+1,id=key,parent=s["parent"],action=s["action"],
                                   full=digest(full),in_slate=key in slate,descendant_certified=key in ancestors[j],**metric))
            for rule,ids in decisions.items():
                selected=[results[k] for k in ids]
                selection.append(dict(generator=gen,window=j+1,rule=rule,pool=len(pool),tested=len(test_ids),
                                 scope="full" if exhaustive else "shortlist_and_reference",generated=target in pool,
                                 reference_in_considered=target in considered[rule],reference_rank=(ids.index(target)+1) if target in ids else None,
                                 fourth=ids[3],fourth_splice=selected[3]["status"],kept_safe=sum(s["status"]=="SAFE" for s in selected),
                                 tested_safe=sum(v["status"]=="SAFE" for v in results.values()),
                                 first_three_safe=sum(s["status"]=="SAFE" for s in selected[:3])))
            if exhaustive:
                # Independently replay best positive on either side of the old retention decision.
                for kept in (True,False):
                    eligible=[k for k in results if (k in original_ids)==kept and results[k]["status"]=="SAFE"]
                    if eligible:
                        key=min(eligible,key=lambda k:results[k]["E"])
                        cfg=pool[key]["config"]+answer[len(reference):]
                        q,_=c.certify(cfg)
                        assert q["metrics"]["status"]=="SAFE" and abs(q["metrics"]["E_J"]-results[key]["E"])<1e-8
                        witnesses.append(dict(generator=gen,window=j+1,kept=kept,prefix=key,plan=q["plan_sha256"],E=results[key]["E"]))
            timeline.append(dict(generator=gen,window=j+1,pool_digest=digest("".join(sorted(pool)).encode()),
                                 valid=len(pool),proposals=len(rows),reference_generated=target in pool))
        print("same pools checked",gen,"elapsed",round(perf_counter()-start,2),flush=True)
    for name,records in (("pools",timeline),("decisions",selection),("fixed_suffix_labels",labels),
                         ("matched_horizon_predictions",probes),("witnesses",witnesses)):
        write_rows(out/(name+".csv"),records)
    gzjson(out/"rule_scores.json.gz",scores)
    save(out/"runtime.json",dict(offline_s=perf_counter()-start,cache_hits=measure.cache_info().hits,cache_misses=measure.cache_info().misses))

if __name__=="__main__":
    main()
