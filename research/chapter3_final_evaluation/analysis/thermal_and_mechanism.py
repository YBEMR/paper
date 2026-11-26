"""Offline thermal counterfactuals and matched-round evidence, isolated from timed search."""
import csv
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from audit_results import (ROOT, OUT, THERMAL, SEEDS, read, save, rows_of, checked_problem,
                           plan_for, independent_events, evaluate, RESULTS)
from assets import Layout


def thermal():
    rows=[]
    trace=[]
    for case in THERMAL:
        p=checked_problem(case)
        sources={}
        origins=defaultdict(set)
        pool=OUT/"pools"/case
        for r in read(pool/"pool.json"):
            if r.get("plan") and r["in_time"]:
                sources[r["plan"]]=pool/"evidence"
                origins[r["plan"]].add("initial")
        for seed in SEEDS:
            for mode in ("T0","T1","T2","T3"):
                folder=OUT/"cells"/f"{case}_Proposed_{mode}_{seed}"
                for q in sorted((folder/"scores").glob("*.json")):
                    h=q.stem
                    sources[h]=folder/"evidence"
                    origins[h].add(f"{mode}_{seed}")
        for h,base in sorted(sources.items()):
            plan=plan_for(base,h)
            exact=sum(Layout(p,plan[0]).components(plan[1]).values())
            c=evaluate(p,plan,cert=True)
            r=evaluate(p,plan,cert=True,reset=True)
            assert abs(float(exact)+c["temperature_J"]-c["E_J"])<1e-8
            rows.append(dict(case=case,plan=h,common_initial=int("initial" in origins[h]),sources=" ".join(sorted(origins[h])),
                  E35_J=float(exact),E35_exact=str(exact),continuous_J=c["E_J"],continuous_lo=c["E_bounds"][0],
                  continuous_hi=c["E_bounds"][1],reset_J=r["E_J"],reset_lo=r["E_bounds"][0],reset_hi=r["E_bounds"][1],
                  actual_status=c["status"],reset_status=r["status"],actual_peak_C=max(c["peak_hi"]),
                  reset_peak_C=max(r["peak_hi"]),false_safe=int(r["status"]=="SAFE" and c["status"]=="HOT"),
                  reset_safe_unverified=int(r["status"]=="SAFE" and c["status"] in ("OUT_OF_MODEL","UNRESOLVED"))))
    save("pool_revaluation.csv",rows, list(rows[0]) if rows else ["case","plan","common_initial"])
    for case in ("D1","S80","D2"):
        p=checked_problem(case)
        for seed in SEEDS:
            folder=OUT/"cells"/f"{case}_Proposed_T2_{seed}"
            if not (folder/"receipt.json").exists() or read(folder/"receipt.json")["status"]!="COMPLETE":
                continue
            fin=read(folder/"result.json").get("final")
            if not fin:
                continue
            plan=plan_for(folder/"evidence",fin["plan"])
            for label,reset in (("continuous",False),("reset",True)):
                values=np.asarray(evaluate(p,plan,cert=True,reset=reset,trace=True)["events"])
                for ev in values:
                    trace.append(dict(case=case,seed=seed,plan=fin["plan"],evaluation=label,start_tick=int(ev[0]),end_tick=int(ev[1]),
                        boundary=int(ev[0] in p.boundaries),**{f"{node}_{col}":float(ev[offset+i])
                          for offset,col in ((14,"start_C"),(18,"end_C"),(22,"upper_C"))
                          for i,node in enumerate(("CPU1","CPU2","GPU","NPU"))}))
            break
        if trace:
            break
    save("temperature_trace.csv",trace,list(trace[0]) if trace else ["case","seed","plan"])


def paired_mechanism():
    matches=[]
    realized=[]
    for case in ("S32","S80","D1","D2"):
        p=checked_problem(case)
        for seed in SEEDS:
            def file(method):
                return OUT/"cells"/f"{case}_{method}_T3_{seed}"/"rounds.jsonl"
            def key(r):
                return (r["turn"],r["before"]["plan"],tuple((j,tuple(op)) for j,op in r["target"]),len(r["scope"]))
            a={key(r):r for r in rows_of(file("AB")) if r["phase"]=="configuration"}
            for r in rows_of(file("Proposed")):
                if r["phase"]!="configuration":
                    continue
                other=a.get(key(r))
                changes={j:(old,new) for j,old,new in r["real_changes"] if old!=new}
                target_scenes={p.req[j]["scene"] for j,_ in r["target"]}
                if other:
                    extra=sorted({f["selected"] for f in r["feedback"] if f.get("selected") in changes}-set(other["scope"]))
                    matches.append(dict(case=case,seed=seed,turn=r["turn"],prior=r["before"]["plan"],
                         target_ids=" ".join(str(j) for j,_ in r["target"]),size=len(r["scope"]),extra=" ".join(map(str,extra)),
                         ab_status=other["solver"]["status"],pro_status=r["solver"]["status"],
                         ab_J=other["after"]["J"],pro_J=r["after"]["J"],AB_minus_Pro_mJ=1000*(other["after"]["J"]-r["after"]["J"]),
                         strict_pro=int(r["after"]["bounds"][1]<other["after"]["bounds"][0])))
                for f in r["feedback"]:
                    j=f.get("selected")
                    if j is None or j not in changes:
                        continue
                    old,new=changes[j]
                    old_dt=p.dur(3*j+1,*old)
                    new_dt=p.dur(3*j+1,*new)
                    scene=p.req[j]["scene"]
                    realized.append(dict(case=case,seed=seed,turn=r["turn"],prior=r["before"]["plan"],after=r["after"]["plan"],
                        request=j,release_scene=scene,target_scenes=" ".join(map(str,sorted(target_scenes))),
                        crosses_release_scene=int(any(s!=scene for s in target_scenes)),victim=f["victim"],
                        victim_scene=p.req[f["victim"]]["scene"],deficit_ms=f["deficit_ticks"]/10,
                        virtual_release_ms=f["release_ticks"]/10,old_unit=old[0],old_opp=old[1],new_unit=new[0],new_opp=new[1],
                        source_capacity_ms=(old_dt if old[0]!=new[0] else old_dt-new_dt)/10,
                        destination_added_ms=(new_dt/10 if old[0]!=new[0] else 0),
                        whole_round_gain_mJ=1000*(r["before"]["J"]-r["after"]["J"]),
                        matched=int(bool(other)),absent_from_matched_AB=int(j not in other["scope"]) if other else None))
    save("matched_rounds.csv",matches,list(matches[0]) if matches else ["case","seed","turn","prior","extra","strict_pro"])
    save("realized_compensators.csv",realized,list(realized[0]) if realized else ["case","seed","turn","request","source_capacity_ms"])


if __name__=="__main__":
    thermal()
    paired_mechanism()
