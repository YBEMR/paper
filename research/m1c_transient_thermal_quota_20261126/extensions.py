"""Locate the first downstream divergence for every historical SAFE splice."""
from common import *
from history_check import ARMS,witness
from diagnose import entry

def main():
    out=DATA/"historical"
    c=Case("L800",out)
    h,cert=witness(c)
    with (out/"splices.csv").open(encoding="utf-8") as f: rows=list(csv.DictReader(f))
    events=[];cache={}
    for arm in ARMS:
        loc=OLD/"data/search/L800"/arm
        beam=load(loc/"beam.json")
        ranks={(r["window"],r["id"]):r for r in beam}
        with gzip.open(loc/"proposals.csv.gz","rt") as f:
            trial={(int(r["window"]),r["parent"],r["config"]):r for r in csv.DictReader(f) if r["result"]=="valid"}
        for r in rows:
            if r["arm"]!=arm or r["status"]!="SAFE":continue
            window=int(r["window"]); parent=r["prefix"]; path=ranks[window,parent]["history"]+h[window:]
            record=dict(arm=arm,window=window,prefix=parent,plan=r["plan"],exact_completion_certified=r["exact_completion_certified"])
            record["first_loss"]="certified"
            for j in range(window+1,11):
                child=digest(materialize(c,path[:j]))
                if (j,child) in ranks:
                    parent=child;continue
                z=trial.get((j,parent,child))
                record.update(loss_window=j,first_loss="generated_pruned" if z else "not_generated",child=child)
                if z:
                    k=r["plan"]
                    if k not in cache:
                        with np.load(out/"evidence/L800"/k/"trace.npz") as f:cache[k]=f["events"]
                    tr=cache[k]
                    exact=entry(c,tr,j*WINDOW if j<10 else c.p.horizon)[2]
                    following=entry(c,tr,(j+1)*WINDOW if j<9 else c.p.horizon)[2]
                    record.update(prefix_peak=float(z["predicted_peak"]),true_prefix_peak=exact,
                                  repeated_load_peak=float(z["risk"]),true_next_peak=following)
                break
            assert (record["first_loss"]=="certified")==(r["exact_completion_certified"]=="True")
            events.append(record)
    write_rows(out/"downstream_losses.csv",events)

if __name__=="__main__":
    main()
