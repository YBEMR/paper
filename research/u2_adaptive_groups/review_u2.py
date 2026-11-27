"""Offline, immutable-certificate verification and matched endpoint/round/call analysis."""
import csv
import hashlib
import json
import os
import tarfile
import tempfile
import zlib
from collections import Counter, defaultdict
from functools import lru_cache
from fractions import Fraction
from pathlib import Path
from statistics import median
import numpy as np

HERE=Path(__file__).resolve().parent
DEST=HERE/"results";TABLE=HERE/"tables"
LOCAL=("Single2","Fixed2","Adaptive2","ThermalUnion")
METHODS=("Q4","W4",*LOCAL,"NT")
PAIRS=(("Fixed2","Single2"),("Adaptive2","Fixed2"),("ThermalUnion","Adaptive2"),
       ("Adaptive2","W4"),("ThermalUnion","W4"),("Adaptive2","NT"),("ThermalUnion","NT"))
REG=Path(os.environ["NT_ROOT"])/"research/m1i_generalization/registration"
PHY=Path(os.environ["NT_ROOT"])/"research/m1_transient_thermal_quota_20261126/frozen/p1/config"
tables=defaultdict(list);counts=Counter()

def read(p):return json.loads(p.read_bytes())
def sha(b):return hashlib.sha256(b).hexdigest()
def lines(p):return [json.loads(s) for s in p.read_bytes().splitlines() if s.endswith(b"}")] if p.exists() else []
def better(a,b):return a is not None and (b is None or a["bounds"][1]<b["bounds"][0])
def best(rows,cut):
    b=None
    for r in rows:
        if r["t"]<=cut and r["status"]=="SAFE" and better(r,b):b=r
    return b
def relation(a,b):
    if not a or not b:return "only_left" if a else "only_right" if b else "neither"
    return "win" if better(a,b) else "loss" if better(b,a) else "tie"
def add(name,base,**rest):tables[name].append(dict(base,**rest))
def unpack(src,tmp):
    info=read(src/"archive.json");path=tmp/"physical.tar.gz";total=hashlib.sha256()
    with path.open("wb") as f:
        for v in info["parts"]:
            b=(src/v["name"]).read_bytes();assert sha(b)==v["sha256"] and len(b)==v["bytes"]
            f.write(b);total.update(b)
    assert total.hexdigest()==info["sha256"]
    with tarfile.open(path) as tar:tar.extractall(tmp,filter="data")
    root=tmp/src.name
    index=read(root/"event_index.json")
    @lru_cache(maxsize=192)
    def block(key):
        b=zlib.decompress((root/"event_blocks"/key).read_bytes());assert sha(b)==key
        return b
    checked={};by_path={}
    for r in index:
        if "partial" in r:counts["partial_arrays"]+=1;continue
        # Every numerical trace is reconstructed from its indexed blocks and checked end-to-end.
        b=b"".join(block(k) for k in r["blocks"]);assert sha(b)==r["sha256"]
        if r["sha256"] not in checked:
            a=np.frombuffer(b,dtype="<f8").reshape(r["shape"]);assert a.shape[1]==31 and a[0,0]==0
            assert np.array_equal(a[:-1,1],a[1:,0]) and np.array_equal(a[:-1,18:22],a[1:,14:18])
            checked[r["sha256"]]=(float(np.sum(a[:,26:30])),float(np.max(a[:,22:26])),float(a[-1,1]))
        by_path[r["path"]]=r["sha256"]
    counts["blocks"]+=info["blocks"];counts["arrays"]+=len(by_path)
    return root,checked,by_path

def profiles():
    result={}
    for file in ("gpu_profiles","cpu_npu_profiles"):
        with (PHY/(file+".csv")).open() as f:
            for r in csv.DictReader(f):
                if not r["stage"].endswith(".main"):continue
                if file!="gpu_profiles" and r["domain"]!="npu":continue
                u=2 if file=="gpu_profiles" else 3
                result[r["stage"][0],u,int(r["k"])]=(int(r["ticks"]),Fraction(r["busy_W"]),Fraction(r["idle_W"]))
    return result

def accounting(req,profile,parent,child,ids):
    before=parent["rows"][1::3];after=child["rows"][1::3]
    changed=[i for i,(a,b) in enumerate(zip(before,after)) if a[:2]!=b[:2]]
    assert changed==ids and changed and all(a[0]==b[0] for a,b in zip(before,after))
    u,k=before[ids[0]][:2];assert all(before[i][:2]==[u,k] and after[i][:2]==[u,k-1] for i in ids)
    dev=[i for i,a in enumerate(before) if a[0]==u];pos=dev.index(ids[0]);assert dev[pos:pos+len(ids)]==ids
    def freq(pos):return before[dev[pos]][1] if 0<=pos<len(dev) else 0
    sums=[];single=[];busy=Fraction(0)
    for j,i in enumerate(ids,pos):
        typ=req[i]["kind"];t,power,_=profile[typ,u,k];nt,new_power,_=profile[typ,u,k-1];idle=profile[typ,u,0][2]
        busy+=(t*power-nt*new_power)/10000
        delta=((power-idle)*t-(new_power-idle)*nt)/10000
        sums.append(delta)
        a,b=freq(j-1),freq(j+1)
        sw=int(a!=k-1)+int(k-1!=b)-int(a!=k)-int(k!=b)
        single.append(delta-Fraction(3,2000)*sw)
    a,b=freq(pos-1),freq(pos+len(ids))
    boundary=int(a!=k-1)+int(k-1!=b)-int(a!=k)-int(k!=b)
    return dict(length=len(ids),unit=u,old_opp=k,new_opp=k-1,requests=ids,windows=sorted({int(req[i]["scene"]) for i in ids}),
        busy35_saving_J=float(busy),reference_busy_increment_saving_J=float(sum(sums)),
        group_boundary_reference_J=float(sum(sums)-Fraction(3,2000)*boundary),singleton_max_reference_J=float(max(single)),
        singleton_nonpositive=sum(v<=0 for v in single),all_singletons_nonpositive=all(v<=0 for v in single))

def inspect_case(code,obj,root,verified,indices,profile):
    with (REG/"inputs"/obj["input"]).open() as f:req=list(csv.DictReader(f))
    assert len(req)==obj["requests"]
    trace_index={r["sha256"]:r for r in read(root/"event_index.json") if "sha256" in r}
    busy_cache={}
    def busy_energy(key,trace,plan):
        if key not in busy_cache:
            rec=trace_index[trace]
            data=b"".join(zlib.decompress((root/"event_blocks"/k).read_bytes()) for k in rec["blocks"])
            a=np.frombuffer(data,dtype="<f8").reshape(rec["shape"])
            ticks=np.r_[a[:,0],a[-1,1]];main=plan["rows"][1::3]
            energy=np.zeros(len(main))
            for unit in (2,3):
                ids=np.array([i for i,row in enumerate(main) if row[0]==unit],dtype=int)
                starts=np.array([main[i][2] for i in ids],dtype=int)
                ends=starts+np.array([profile[req[i]["kind"],unit,main[i][1]][0] for i in ids],dtype=int)
                lo=np.searchsorted(ticks,starts);hi=np.searchsorted(ticks,ends)
                assert np.array_equal(ticks[lo],starts) and np.array_equal(ticks[hi],ends)
                integrated=np.r_[0.,np.cumsum(a[:,26+unit])]
                energy[ids]=integrated[hi]-integrated[lo]
            busy_cache[key]=energy
        return busy_cache[key]
    def evidence(folder,key):
        e=folder/"evidence"/obj["case"]/key
        c=read(e/"certificate.json");p=read(e/"plan.json")
        assert sha((e/"plan.json").read_bytes().strip())==key==c["plan_sha256"]
        trace=indices[(e/"trace.npz").relative_to(root).as_posix()]
        node,peak,horizon=verified[trace];m=c["metrics"]
        assert horizon==obj["horizon_ticks"] and abs(node+m["external_J"]-m["E_J"])<1e-8 and abs(peak-max(m["peak_hi"]))<1e-7
        assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1] and m["min_deadline_slack_ms"]>=0
        if m["status"]=="SAFE":assert peak<=80 and min(m["minimum_lo"])>=20
        return p,c,trace
    env=read(root/"environment.json");previous_end=0.
    with (HERE/"registration/roster.csv").open() as f:roster=[r for r in csv.DictReader(f) if r["case"]==obj["case"]]
    for slot in roster:
        cell=root/("r"+slot["repeat"])/slot["method"];rec=read(cell/"receipt.json");assert 0<=rec["charged_s"]<=60
        if (cell/"ready.json").exists():
            assert read(cell/"ready.json")["cpu"]==[env["cpu"]]
            start=read(cell/"clock.json")["start"];assert start>=previous_end
            previous_end=start+rec["new_s"];counts["executed"]+=1
        else:assert rec["status"] in ("NO_W4_SAFE","NO_REMAINING_BUDGET")
    for rep in (1,2,3):
        d=root/f"r{rep}";key=dict(case=code,rep=rep);seed=read(d/"seed.json")
        nt=lines(d/"NT/certs.jsonl");fixed=[r for r in nt if r["width"]==4 and r["t"]<=60][:4]
        assert fixed==seed["rows"];seedbest=best(fixed,60)
        assert seed["plan"]==(seedbest["plan"] if seedbest else None)
        if len(fixed)==4:assert fixed[-1]["t"]==seed["charge"]==seed["fourth_s"]
        add("seeds",key,K=seed["K"],fourth_s=seed["fourth_s"],cost_s=seed["charge"],plan=seed["plan"],J=seed["J"],
            terminal_statuses=[r["status"] for r in fixed],cert_s=sum(r["t"]-r["began"] for r in fixed),host=read(root/"environment.json")["host"])
        snapshots={};curvelist={};costs={};records={}
        for method in METHODS:
            mk=dict(key,method=method);folder=d/method
            receipt=read(folder/"receipt.json") if method!="W4" else dict(status="READOUT",charge=seed["charge"],charged_s=seed["charge"],new_s=0)
            rows=lines(folder/"certs.jsonl") if method!="W4" else []
            archive=folder/"search/physical" if method=="NT" else folder
            lookup={}
            for r in rows:
                if r["plan"] not in lookup:
                    p,c,tr=evidence(archive,r["plan"])
                    lookup[r["plan"]]=(p,c,tr)
                c=lookup[r["plan"]][1]
                assert r["bounds"]==c["metrics"]["E_bounds"] and r["status"]==c["metrics"]["status"] and r["J"]==c["metrics"]["E_J"]
            counts["timed_calls"]+=len(rows);counts["unique_within_cell"]+=len(lookup)
            merged=fixed+rows if method in LOCAL else fixed if method=="W4" else rows
            curvelist[method]=merged
            winner=None
            for r in merged:
                if r["t"]<=60 and r["status"]=="SAFE" and better(r,winner):
                    winner=r;add("improvements",mk,t=r["t"],J=r["J"],plan=r["plan"])
            snaps={t:best(merged,t) for t in (10,30,60)}
            for t,z in snaps.items():
                add("curves",mk,cut_s=t,J=z["J"] if z else None,plan=z["plan"] if z else None,
                    first_SAFE_s=next((r["t"] for r in merged if r["t"]<=t and r["status"]=="SAFE"),None))
            snapshots[method]=snaps;costs[method]=receipt["charged_s"]
            candidates=[r for r in rows if r["kind"]=="candidate" and r["t"]<=60];matched_rounds=[]
            native=read(folder/"rounds.json") if (folder/"rounds.json").exists() else {}
            if method in LOCAL and (folder/"handoff.json").exists():
                hp=read(folder/"handoff.json");orig=evidence(d/"NT/search/physical",seed["plan"])
                p,c,tr=lookup[seed["plan"]]
                assert p==orig[0] and c["metrics"]==orig[1]["metrics"] and tr==orig[2]==hp["trace_sha"]
                add("handoffs",mk,**hp)
            for z in lines(folder/"pools.jsonl"):
                for rank,x in enumerate(z["candidates"],1):
                    add("pools",mk,turn=z["turn"]+1,ref_rank=rank,**x)
            for z in native.get("rounds",[]):
                before=z["before"] if "before" in z else native["final"]["plan_sha256"];beforep,beforec,_=lookup[before]
                accepted=z.get("accepted");evaluated=z.get("evaluated",[])
                for x in evaluated:
                    p,c,_=lookup[x["plan"]]
                    a=accounting(req,profile,beforep,p,x["ids"])
                    busy=busy_energy(before,lookup[before][2],beforep)-busy_energy(x["plan"],lookup[x["plan"]][2],p)
                    m=c["metrics"];old=beforec["metrics"]
                    dt=next(r for r in candidates if r["plan"]==x["plan"] and r["turn"]==z["turn"])
                    add("candidate_effects",mk,turn=z["turn"]+1,parent=before,plan=x["plan"],ref_rank=x["ref_rank"],
                        actual_main_busy_saving_J=float(np.sum(busy)),actual_changed_busy_saving_J=float(np.sum(busy[x["ids"]])),
                        accepted=x["plan"]==accepted,status=m["status"],J=m["E_J"],system_saving_J=old["E_J"]-m["E_J"],activity_saving_J=old["activity_J"]-m["activity_J"],
                        switch_delta=m["switch_count"]-old["switch_count"],switch_saving_J=old["switch_J"]-m["switch_J"],thermal_saving_J=old["temperature_J"]-m["temperature_J"],
                        peak_C=max(m["peak_hi"]),parent_peak_C=max(old["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],parent_slack_ms=old["min_deadline_slack_ms"],
                        cert_archive_s=dt["t"]-dt["began"],cert_kernel_s=dt["kernel_s"],**a)
                after=lookup[accepted][1] if accepted else beforec
                add("rounds",mk,turn=z["turn"]+1,parent=before,accepted=accepted,accepted_length=z.get("group_size",0),stop=z.get("stop"),
                    pool=z.get("pool_size",0),certs=len(evaluated),ref_ranks=[x["ref_rank"] for x in evaluated],scan=z.get("scan"),legal=z.get("legal"),J=after["metrics"]["E_J"])
                matched_rounds.append(after["metrics"]["E_J"])
            if method in LOCAL and seedbest:
                for n in range(4):
                    v=matched_rounds[min(n,len(matched_rounds))-1] if n and matched_rounds else seed["J"]
                    add("mechanism_axes",mk,axis="completed_rounds",budget=n,actual=min(n,len(matched_rounds)),carried=n>len(matched_rounds),J=v)
                for n in range(7):
                    v=best([seedbest,*candidates[:n]],60)
                    add("mechanism_axes",mk,axis="new_candidate_certificates",budget=n,actual=min(n,len(candidates)),carried=n>len(candidates),J=v["J"])
            best60=snaps[60]
            record=dict(status=receipt["status"],elapsed_s=receipt["charged_s"],charge_s=receipt["charge"],new_wall_s=receipt["new_s"],
                SAFE=bool(best60),J=best60["J"] if best60 else None,first_SAFE_s=next((r["t"] for r in merged if r["status"]=="SAFE" and r["t"]<=60),None),
                best_certified_s=best60["t"] if best60 else None,first_gain_s=next((r["t"] for r in merged if seedbest and r["t"]<=60 and r["status"]=="SAFE" and better(r,seedbest)),None),
                seed_J=seed["J"] if method in (*LOCAL,"W4","NT") else None,rounds=len(matched_rounds),calls=len(rows),candidates=len(candidates),
                handoff_calls=sum(r["kind"]=="intake" for r in rows),HOT=sum(r["status"]=="HOT" for r in rows),
                cert_kernel_s=sum(r["kernel_s"] for r in rows),cert_archive_s=sum(r["t"]-r["began"] for r in rows),after_cut=sum(r["t"]>60 for r in rows),
                native_accepted=native.get("final",{}).get("plan_sha256"),native_final_J=native.get("final",{}).get("metrics",{}).get("E_J"))
            add("runs",mk,**record);records[method]=record
        for left,right in PAIRS:
            for cut in (10,30,60):
                a,b=snapshots[left][cut],snapshots[right][cut]
                delta=b["J"]-a["J"] if a and b else None
                add("pairs",key,left=left,right=right,cut_s=cut,left_J=a["J"] if a else None,right_J=b["J"] if b else None,
                    saving_J=delta,saving_pct=100*delta/b["J"] if delta is not None else None,relation=relation(a,b))
        for method in ("Adaptive2","ThermalUnion"):
            limit=costs[method];a=best(curvelist[method],limit);b=best(nt,limit)
            hit=next((r["t"] for r in nt if a and r["status"]=="SAFE" and r["t"]<=60 and not better(a,r)),None)
            add("equal_time",key,method=method,charged_s=limit,local_J=a["J"] if a else None,NT_J=b["J"] if b else None,
                saving_J=b["J"]-a["J"] if a and b else None,relation=relation(a,b),NT_first_matches_local_s=hit,local_best_s=a["t"] if a else None)
        for r in read(d/"Q4_causal_audit/audit.json"):
            ep,ec,tr=evidence(d/"Q4_causal_audit",r["causal"])
            assert r["causal_J"]==ec["metrics"]["E_J"];add("q4_causal",key,**r)

def emit(name,rows):
    if not rows:return
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (TABLE/(name+".csv")).open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fields,lineterminator="\n");w.writeheader()
        for row in rows:w.writerow({k:json.dumps(v,separators=(",",":")) if isinstance(v,(dict,list)) else v for k,v in row.items()})

def groups(rows,keys):
    result=defaultdict(list)
    for r in rows:result[tuple(r[k] for k in keys)].append(r)
    return result

def meds(rows,col):
    vs=[r[col] for r in rows if r[col] is not None]
    return median(vs) if vs else None

def summarize():
    for (code,left,right,t),rows in groups(tables["pairs"],("case","left","right","cut_s")).items():
        sts=Counter(r["relation"] for r in rows)
        add("case_pairs",dict(case=code,left=left,right=right,cut_s=t),median_saving_J=meds(rows,"saving_J"),median_pct=meds(rows,"saving_pct"),
            eligible=sum(r["saving_J"] is not None for r in rows),wins=sts["win"],ties=sts["tie"],losses=sts["loss"],only_left=sts["only_left"],only_right=sts["only_right"],neither=sts["neither"])
    for (code,method),rows in groups(tables["runs"],("case","method")).items():
        add("case_methods",dict(case=code,method=method),safe=sum(r["SAFE"] for r in rows),median_J=meds(rows,"J"),
            elapsed_s=meds(rows,"elapsed_s"),best_s=meds(rows,"best_certified_s"),candidates=meds(rows,"candidates"),rounds=meds(rows,"rounds"),
            kernel_s=meds(rows,"cert_kernel_s"),archive_s=meds(rows,"cert_archive_s"))
    for (code,method),rows in groups(tables["equal_time"],("case","method")).items():
        status=Counter(r["relation"] for r in rows)
        add("case_equal_time",dict(case=code,method=method),median_saving_J=meds(rows,"saving_J"),elapsed_s=meds(rows,"charged_s"),
            local_best_s=meds(rows,"local_best_s"),NT_matches_s=meds(rows,"NT_first_matches_local_s"),
            wins=status["win"],ties=status["tie"],losses=status["loss"],unpaired=sum(status[k] for k in ("only_right","only_left","neither")))
    for (left,right),rows in groups([r for r in tables["case_pairs"] if r["cut_s"]==60],("left","right")).items():
        matched=[r for r in rows if r["eligible"]==3]
        case_sign=lambda r:"win" if r["wins"]>=2 else "loss" if r["losses"]>=2 else "tie" if r["ties"]>=2 else "mixed"
        sign=Counter(case_sign(r) for r in matched)
        add("contrast_summary",dict(left=left,right=right),paired_cases=len(matched),wins=sign["win"],ties=sign["tie"],losses=sign["loss"],mixed=sign["mixed"],
            mean_case_saving_J=np.mean([r["median_saving_J"] for r in matched]) if matched else None,
            median_case_saving_J=meds(matched,"median_saving_J"),mean_case_pct=np.mean([r["median_pct"] for r in matched]) if matched else None,
            stable_wins=sum(r["wins"]==3 for r in matched),stable_losses=sum(r["losses"]==3 for r in matched))
    # Compare neighborhood choices at identical round budgets and candidate-certificate budgets.
    axes={(r["case"],r["rep"],r["method"],r["axis"],r["budget"]):r for r in tables["mechanism_axes"]}
    for (code,rep,method,axis,n),a in axes.items():
        for left,right in PAIRS[:3]:
            if method!=left:continue
            b=axes[code,rep,right,axis,n]
            add("axis_pairs",dict(case=code,rep=rep,left=left,right=right,axis=axis,budget=n),
                saving_J=b["J"]-a["J"],left_actual=a["actual"],right_actual=b["actual"],left_carried=a["carried"],right_carried=b["carried"])
    for (left,right,axis,n),rows in groups(tables["axis_pairs"],("left","right","axis","budget")).items():
        percase=[meds(part,"saving_J") for part in groups(rows,("case",)).values()]
        add("axis_summary",dict(left=left,right=right,axis=axis,budget=n),paired_cases=len(percase),median_case_saving_J=median(percase),
            mean_case_saving_J=float(np.mean(percase)),both_reached=sum(not r["left_carried"] and not r["right_carried"] for r in rows))
    for tag,predicate in [
        ("all_singletons_nonpositive",lambda r:r["all_singletons_nonpositive"] and r["length"]>1),
        ("some_singletons_nonpositive",lambda r:r["singleton_nonpositive"]>0 and r["length"]>1),
        ("adaptive_nonfixed",lambda r:r["method"]=="Adaptive2" and r["length"] not in (1,4,8,16,32,64)),
        ("thermal_outside_reference_two",lambda r:r["method"]=="ThermalUnion" and r["ref_rank"]>2),
        ("thermal_second",lambda r:r["method"]=="ThermalUnion" and r["ref_rank"]>1)]:
        candidates=[r for r in tables["candidate_effects"] if r["method"] in LOCAL and r["rep"]==1 and r["accepted"] and r["system_saving_J"]>0 and predicate(r)]
        for r in sorted(candidates,key=lambda a:(-a["system_saving_J"],a["case"],a["turn"]))[:3]:
            add("examples",dict(category=tag),**r)
    for n,rows in list(tables.items()):emit(n,rows)

def figure(codes):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors=["#228066","#777777","#9b6a40","#ef912d","#aa4485","#69429c","#155fa7"]
    lines_by=groups(tables["improvements"],("case","method","rep"))
    fig,axes=plt.subplots(4,3,figsize=(12,11))
    for code,ax in zip(codes,axes.flat):
        for m,color in zip(METHODS,colors):
            reps=[sorted(lines_by.get((code,m,k),[]),key=lambda r:r["t"]) for k in (1,2,3)]
            ts=sorted({r["t"] for rows in reps for r in rows}|{60.})
            xx=[];yy=[]
            for t in ts:
                js=[[r["J"] for r in rows if r["t"]<=t] for rows in reps]
                valid=[x[-1] for x in js if x]
                if len(valid)>=2:xx.append(t);yy.append(median(valid))
            if xx:ax.step(xx,yy,where="post",label=m,color=color,lw=1.5,ls="--" if m in ("W4","ThermalUnion") else "-")
        ax.set(title=code,xlim=(0,60));ax.ticklabel_format(style="plain",axis="y",useOffset=False);ax.grid(alpha=.2)
    lines_map={}
    for ax in axes.flat:
        hs,ls=ax.get_legend_handles_labels();lines_map.update(zip(ls,hs))
    fig.supxlabel("Charged elapsed time (s)",y=.052);fig.supylabel("Certified total energy (J)")
    fig.legend(lines_map.values(),lines_map.keys(),ncol=7,loc="lower center",frameon=False)
    fig.tight_layout(rect=(.018,.07,1,1));fig.savefig(TABLE/"quality.png",dpi=160);plt.close(fig)

def main():
    TABLE.mkdir(exist_ok=True)
    cases=[r for r in read(REG/"cases.json")["cases"] if r["ambient"]==35];profile=profiles()
    for obj in cases:
        code=obj["case"].split("_")[0]
        with tempfile.TemporaryDirectory() as tmp:
            root,verified,paths=unpack(DEST/code,Path(tmp))
            inspect_case(code,obj,root,verified,paths,profile)
    assert len(tables["runs"])==252 and len(tables["curves"])==756 and len(tables["pairs"])==756 and len(tables["seeds"])==36
    summarize();figure([o["case"].split("_")[0] for o in cases])
    counts.update({k:len(v) for k,v in tables.items()})
    (TABLE/"verification.json").write_text(json.dumps(dict(counts),indent=2)+"\n")
    print(dict(counts),flush=True)
if __name__=="__main__":main()
