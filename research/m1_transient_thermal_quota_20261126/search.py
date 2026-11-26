import argparse
import csv
import gzip
import json
from time import perf_counter
from mechanism import ROOT, ORDER, WINDOW, Case, digest, np, p1, archive_means

ARMS = ("C","D","D-quarter")
WIDTH = 4
LIMIT_S = 300


def diverse(ordered, closed):
    from bisect import bisect_left
    metrics = ("energy","drain","risk")
    values = {k:sorted(round(float(s[k]),11) for s in ordered) for k in metrics}
    def value(s,k):
        return round(float(s[k]),11)
    def key(s,k):
        return (value(s,k),value(s,"energy"),s["config"])
    def compromise(s):
        # Equal pools make sums of dense empirical percentiles comparable.
        return (sum(bisect_left(values[k],value(s,k)) for k in metrics),*key(s,"energy"))
    chosen = [ordered[0]]
    ids = {ordered[0]["id"]}
    for fn in (lambda s:key(s,"drain"),lambda s:key(s,"risk"),compromise):
        if len(chosen)==len(ordered):
            break
        best = min((s for s in ordered if s["id"] not in ids),key=fn)
        ids.add(best["id"])
        chosen.append(best)
    return [chosen[0],*sorted(chosen[1:],key=lambda s:key(s,"risk"))] if closed else chosen


def search(case, arm, dest):
    target = dest/case/arm
    target.mkdir(parents=True,exist_ok=False)
    c = Case(case,target)
    improved = arm in ("C2","D2")
    fine = 2500 if arm in ("D-quarter","D2") else WINDOW
    thermal = arm not in ("C","C2")
    # Equal warm-up before the clock. No instance-dependent schedules are evaluated.
    warm = bytes([0])
    c.ledger(warm,0,10000,10000,False)
    c.propagate(c.p.initial,np.r_[c.args[-3][:,0],c.args[-2][:,0]],1.)
    initial = dict(config=b"",f=(0,0),k=(0,0),temperature=c.p.initial,peak=max(c.p.initial),
                   energy=0.0,id=digest(b""),history=[],action=(),parent=None)
    states = [initial]
    history,trials,certificates = [],[],[]
    start = perf_counter()
    last_window = c.windows-1
    timed_out = False
    summary = []
    for j in range(c.windows):
        prior = states
        unique = {}
        window_start = perf_counter()
        lo,hi = j*WINDOW,(j+1)*WINDOW
        closed = j==last_window
        num_actions = len(trials)
        for parent in prior:
            for action,tail in c.candidates(j,parent):
                if perf_counter()-start>=LIMIT_S:
                    timed_out = True
                    break
                cfg = parent["config"]+tail
                key = digest(cfg)
                if key in unique:
                    trials.append((j,parent["id"],*action,key,"duplicate",None,None,None,None,None))
                    continue
                ledger = c.ledger(cfg,lo,hi,fine,closed,thermal)
                ok,cost,f,k = ledger[:4]
                if not ok:
                    trials.append((j,parent["id"],*action,key,"timing",int(ledger[-1]),None,None,None,None))
                    continue
                pred = parent["temperature"]
                pk = parent["peak"]
                if thermal:
                    for mean in ledger[8]:
                        pred = c.propagate(pred,mean,fine/WINDOW)
                        pk = max(pk,max(pred))
                if closed:
                    # Final cost must include the 301 ms tail (and no open-boundary return).
                    if thermal:
                        tail_ledger = c.ledger(cfg,hi,c.p.horizon,fine,True)
                        for i,mean in enumerate(tail_ledger[8]):
                            h = min(fine,c.p.horizon-hi-i*fine)/WINDOW
                            pred = c.propagate(pred,mean,h)
                            pk = max(pk,max(pred))
                    cost += c.base*c.p.horizon/WINDOW
                state = dict(id=key,config=cfg,f=f,k=k,temperature=pred,peak=pk,
                             energy=cost,action=action,parent=parent["id"],history=parent["history"]+[action])
                if improved:
                    g,n,x,y = action
                    kinds = c.kinds[len(parent["config"]):len(cfg)]
                    a,b = np.bincount(kinds,minlength=2)
                    spans = c.eng.length
                    finish_g = max(lo,parent["f"][0]+5*(parent["k"][0]!=g))+(a-x)*spans["A",2,g]+(b-y)*spans["B",2,g]
                    finish_n = max(lo,parent["f"][1]+5*(parent["k"][1]!=n))+x*spans["A",3,n]+y*spans["B",3,n]
                    state["drain"] = max(max(f),max(ledger[6]+c.args[4][:len(cfg)]))
                    if thermal:
                        state["risk"] = pk if closed else max(pk,max(c.propagate(pred,ledger[8].mean(axis=0),1.0)))
                    else:
                        state["risk"] = (max(finish_g,finish_n)-lo)/WINDOW
                unique[key] = state
                trials.append((j,parent["id"],*action,key,"valid",int(ledger[-1]),cost,pk if thermal else None,
                               state.get("drain"),state.get("risk")))
            if timed_out:
                break
        if timed_out or not unique:
            states = []
            break
        ordered = sorted(unique.values(),key=lambda s:(round(s["energy"],11),s["config"]))
        if improved:
            ordered = diverse(ordered,closed)
        elif thermal:
            others = sorted(ordered[1:],key=lambda s:(max(0.,s["peak"]-80.),round(s["energy"],11),s["config"]))
            ordered = [ordered[0],*others]
        states = ordered[:WIDTH]
        for rank,s in enumerate(states,1):
            history.append(dict(window=j,rank=rank,parent=s["parent"],id=s["id"],action=s["action"],
                                history=s["history"],energy=s["energy"],peak=s["peak"] if thermal else None,
                                end_temperature=s["temperature"] if thermal else None,
                                risk=s.get("risk"),drain=s.get("drain")))
        summary.append(dict(window=j,parents=len(prior),actions=len(trials)-num_actions,valid_unique=len(unique),
                            seconds=perf_counter()-window_start))
    search_s = perf_counter()-start
    for rank,s in enumerate(states,1):
        if perf_counter()-start>LIMIT_S-1:
            timed_out = True
            break
        t = perf_counter()
        cert,trace = c.certify(s["config"])
        elapsed = perf_counter()-start
        cert_time = perf_counter()-t
        assert elapsed<=LIMIT_S
        assert abs(s["energy"]-cert["E35_J"])<1.e-8
        m = cert["metrics"]
        # Confirm inherited averages for this complete plan against the independent
        # physical event ledger (no temperature or certificate used by the search).
        if thermal:
            predicted = c.p.initial
            peak = max(predicted)
            for tick in range(0,c.p.horizon,fine):
                end = min(tick+fine,c.p.horizon)
                predicted = c.propagate(predicted,archive_means(trace,tick,end),(end-tick)/WINDOW)
                peak = max(peak,max(predicted))
            assert max(abs(predicted-s["temperature"]))<1.e-8 and abs(s["peak"]-peak)<1.e-8
        certificates.append(dict(rank=rank,id=s["id"],plan=cert["plan_sha256"],status=m["status"],E=m["E_J"],
                    E_bounds=m["E_bounds"],E35=cert["E35_J"],peak=max(m["peak_hi"]),peak_lo=max(m["peak_lo"]),
                    predicted_peak=s["peak"] if thermal else None,slack_ms=m["min_deadline_slack_ms"],
                    hotspot=m["hotspot"],peak_s=m["peak_tick"][m["hotspot"]]/10000,served=c.eng.n,
                    elapsed_s=elapsed,cert_and_storage_s=cert_time))
    total = perf_counter()-start
    with gzip.open(target/"trials.csv.gz","wt",encoding="utf-8",newline="") as stream:
        w = csv.writer(stream)
        w.writerow(["window","parent","gpu","npu","x","y","config","result","slack_tick","reference_score","pred_peak","drain_tick","risk"])
        w.writerows(trials)
    p1.put(target/"beam.json",history)
    result = dict(case=case,arm=arm,timeout=timed_out,total_s=total,search_s=search_s,windows=summary,
                  proposal_count=len(trials),fifo_count=sum(x[7]!="duplicate" for x in trials),
                  certificates=certificates)
    p1.put(target/"result.json",result)
    print(case,arm,round(total,2),"s",len(trials),"proposals",
          [(v["status"],round(v["E"],5),round(v["peak"],5)) for v in certificates],flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",default="data/e1")
    parser.add_argument("--improved",action="store_true")
    parser.add_argument("--cases",nargs="+",choices=ORDER,default=ORDER)
    args = parser.parse_args()
    assert json.loads((ROOT/"data/e0/gate.json").read_text())["status"]=="PASS"
    calibration = json.loads((ROOT/"data/e0/window_calibration.json").read_text())
    use_quarter = any(max(r["from_recursive"])<=80<max(r["true_peak_hi"]) for r in calibration)
    arms = ARMS if use_quarter else ARMS[:2]
    if args.improved:
        arms = ("C2","D2")
    for case in args.cases:
        for arm in arms:
            search(case,arm,ROOT/args.out)


if __name__=="__main__":
    main()
