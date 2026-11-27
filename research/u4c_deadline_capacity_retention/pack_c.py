"""Losslessly pack new runs and compare only certified, timely incumbents with the frozen C route."""
import csv
import gzip
import struct
import platform
import subprocess
from collections import Counter
import psutil
from foundation import *
from archive_results import pack
pack.DEST=HOME_C/"results"

def table(name,rows):
    out=HOME_C/"tables"/(name+".csv");out.parent.mkdir(exist_ok=True)
    with out.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def metrics(k,m,r):
    good=r["delivered"];final=good[-1] if good else {};p=r["phases"]
    peak=struct.unpack("<d",bytes.fromhex(final["peak"]))[0] if final else None
    return dict(case=k,arm=m,SAFE=int(bool(good)),first_s=good[0]["t"] if good else None,
                first_phase=good[0]["phase"] if good else None,first_plan=good[0]["plan"] if good else None,first_J=good[0]["J"] if good else None,
                last_s=final.get("t"),J=final.get("J"),lo=final["bounds"][0] if good else None,
                hi=final["bounds"][1] if good else None,peak_C=peak,slack_ms=final.get("slack"),
                plan=final.get("plan"),wall_s=r["wall_s"],stop=r["receipt"]["status"],cpu=r["receipt"]["cpu"],
                fallback=int(r.get("fallback",False)),done_cert=r["completed_certificates"],started_cert=r["started_certificates"],
                actions=r["counts"].get("q4_action",0),supplements=r["counts"].get("supplement",0),
                open_checks=r["counts"].get("open_done",0),branch_skips=r["counts"].get("branch_skip",0),
                terminal_skips=r["counts"].get("terminal_skip",0),**{tag+"_s":p.get(tag,0.) for tag in ("model","construct","terminal","fallback","group")})
def main():
    psutil.Process().cpu_affinity([8])
    arms=[*ARMS,"Control"]
    if "--joint" in sys.argv:arms.append(read(HOME_C/"joint_decision.json")["arm"])
    rows=[]
    for k,o in cases().items():
        phy=pack.Physics(k)
        for m in arms:
            pack.pack_unit(OUT_C/(k+"-"+m),phy,o)
            run=read(pack.DEST/k/f"runs/{m}.json")
            for lost in run["partial"]:
                paths=[p.parent for p in (OUT_C/(k+"-"+m)).rglob("plan.json") if p.parent.name==lost["plan"]]
                assert len(paths)==1
                for n,h in lost["files"].items():
                    data=(paths[0]/n).read_bytes();assert sha(data)==h
                    pack.zipped(pack.DEST/k/"fragments"/(m+"-"+lost["plan"])/(n+".gz"),data)
            rows.append(metrics(k,m,run))
        phy.close()
        rows.append(metrics(k,"C",read(B_SRC/"results"/k/"runs/C.json")))
        print("archived",k,len(phy.plans),flush=True)
    table("routes",rows)
    baseline_rows={r["case"]:r for r in rows if r["arm"]=="C"}
    both=[];summ=[]
    for m in ["C",*arms]:
        arm=[r for r in rows if r["arm"]==m]
        totals=Counter();gains=[];losses=[];improved=[];worse=[];delta=0.
        for r in arm:
            k=r["case"];old=baseline_rows[k];common=bool(r["SAFE"] and old["SAFE"])
            if r["SAFE"]>old["SAFE"]:gains.append(k)
            if r["SAFE"]<old["SAFE"]:losses.append(k)
            if common:
                delta+=r["J"]-old["J"]
                if r["hi"]<old["lo"]:improved.append(k)
                if old["hi"]<r["lo"]:worse.append(k)
            both.append(dict(case=k,arm=m,common=common,energy_delta=r["J"]-old["J"] if common else None,
                             same_plan=r["plan"]==old["plan"] if common else None,
                             first_delta=r["first_s"]-old["first_s"] if common else None,
                             last_delta=r["last_s"]-old["last_s"] if common else None))
            totals.update({n:r[n] for n in ("SAFE","actions","fallback","construct_s","done_cert","wall_s")})
        summ.append(dict(arm=m,**totals,gains=" ".join(gains),losses=" ".join(losses),improvements=" ".join(improved),
                         worse=" ".join(worse),common_energy_delta_J=delta,wall_cut=sum(r["stop"]=="wall" for r in arm)))
    table("paired",both);table("summary",summ)
    if "--joint" not in sys.argv:
        def pick(names):
            eligible=[r for r in summ if r["arm"] in names and not r["losses"] and (r["gains"] or r["improvements"])]
            return min(eligible,key=lambda r:(-r["SAFE"],r["common_energy_delta_J"],names.index(r["arm"])))["arm"] if eligible else None
        ret=pick(ARMS[:2]);gen=pick(ARMS[2:])
        historical=dict(retention=ret,generation=gen)
    live={r["case"]:r for r in rows if r["arm"]=="Control"}
    live_rows=[];scores={}
    for m in ["C",*arms]:
        sample=[r for r in rows if r["arm"]==m];gains=[];loss=[];better=[];worse=[];mechanism=[];total=0.
        for r in sample:
            k=r["case"];v=live[k]
            if r["SAFE"] and not v["SAFE"]:gains.append(k)
            if v["SAFE"] and not r["SAFE"]:loss.append(k)
            common=r["SAFE"] and v["SAFE"]
            if common:
                total+=r["J"]-v["J"]
                if r["hi"]<v["lo"]:better.append(k)
                if r["lo"]>v["hi"]:worse.append(k)
            if (k in gains or k in better) and r["first_phase"]=="terminal" and r["first_plan"]!=v["first_plan"]:mechanism.append(k)
            live_rows.append(dict(case=k,arm=m,control_SAFE=v["SAFE"],SAFE=r["SAFE"],first_phase=r["first_phase"],control_first_phase=v["first_phase"],
                                  J_delta=r["J"]-v["J"] if common else None,first_delta=r["first_s"]-v["first_s"] if common else None,
                                  last_delta=r["last_s"]-v["last_s"] if common else None,same_plan=r["plan"]==v["plan"] if common else None))
        scores[m]=dict(gains=gains,losses=loss,better=better,worse=worse,common_delta=total,direct_evidence=mechanism)
    table("paired_live",live_rows);put(HOME_C/"tables/live_summary.json",scores)
    if "--joint" not in sys.argv:
        def eligible(names):
            good=[]
            for name in names:
                hist=next(r for r in summ if r["arm"]==name);v=scores[name]
                if not hist["losses"] and (hist["gains"] or hist["improvements"]) and not v["losses"] and v["direct_evidence"]:good.append(name)
            return min(good,key=lambda m:(-len(scores[m]["gains"]),scores[m]["common_delta"],names.index(m))) if good else None
        ret=eligible(ARMS[:2]);gen=eligible(ARMS[2:])
        put(HOME_C/"joint_decision.json",dict(historical=historical,retention=ret,generation=gen,eligible=bool(ret and gen),
                                            arm=(ret+"+"+gen) if ret and gen else None))
if __name__=="__main__":main()
