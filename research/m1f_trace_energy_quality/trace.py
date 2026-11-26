"""Replay archived W4 decisions, intersect rankings, and run offline interventions."""
import base64
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path
from time import perf_counter

from long_run import ROOT, BASE, HOLD, inputs
DIAG=Path(os.environ.get("M1F_DIAGNOSTIC",ROOT/"diagnostic_raw")).resolve()
os.environ["M1E_OUTPUT"]=str(DIAG)
sys.path.insert(0,str(BASE))
import experiment as e
from heat import integrate

OUT=ROOT/"data/trace"
np=e.np
W=e.WINDOW

def dumpcsv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader(); w.writerows(rows)

def get_archive(path,accept,checksums):
    assert hashlib.sha256(path.read_bytes()).hexdigest()==checksums[path.name]
    result={}
    with tarfile.open(path,"r|xz") as tar:
        for member in tar:
            if accept(member.name):
                result[member.name]=tar.extractfile(member).read()
    return result

def representative(records):
    safe=[r for r in records if r["cert"]["metrics"]["status"]=="SAFE"]
    if safe:return min(safe,key=lambda r:r["cert"]["metrics"]["E_J"])
    return min(records,key=lambda r:max(r["cert"]["metrics"]["peak_hi"]))

def arm_sources(archive_root,case,checksums):
    files=get_archive(archive_root/f"{case}_search.tar.xz",
        lambda s:any(s.endswith("/"+m+"/"+f) for m in ("NC","NT") for f in ("w4.json.gz","run.json")),checksums)
    arms={}
    for m in ("NC","NT"):
        stem=f"runs/{case}/{m}/"
        log=json.loads(gzip.decompress(files[stem+"w4.json.gz"]))
        records=json.loads(files[stem+"run.json"])["records"][:4]
        rec=representative(records)
        arms[m]=dict(log=log,records=records,rep=rec,plan=rec["cert"]["plan_sha256"])
    wanted={v["plan"] for v in arms.values()}
    phys=get_archive(archive_root/f"{case}_certificates.tar.xz",lambda s:s.split("/")[-2] in wanted,checksums)
    for m,d in arms.items():
        stem=f"physical/evidence/{case}/{d['plan']}/"
        plan=phys[stem+"plan.json"].strip()
        assert hashlib.sha256(plan).hexdigest()==d["plan"]
        d["cfg"]=bytes(k+(10 if u==3 else 0) for u,k,t in json.loads(plan)["rows"][1::3])
        assert e.digest(d["cfg"])==d["rep"]["id"]
        with np.load(io.BytesIO(phys[stem+"trace.npz"])) as f:d["trace"]=f["events"]
    return arms

def rank(pool,risks):
    items=[dict(s,risk=risks[k]) for k,s in pool.items()]
    order=sorted(items,key=lambda s:(round(s["energy"],11),s["config"]))
    return [s["id"] for s in e.diverse(order,False)]

def replay(c,method,arm,decisions,swap=None):
    states=[e.initial(c)]
    beams=[]; first_switch=None; boundary_data={}
    for j in range(c.windows):
        parents={s["id"]:s for s in states}
        log=dict(actions=[],groups=[])
        pool,ok=e.expand(c,j,states,"NT",perf_counter(),float("inf"),log)
        assert ok and pool
        if swap is None:
            old=[r for r in arm["log"]["actions"] if r[0]==j+1]
            assert len(old)==len(log["actions"])
            for new,prior in zip(log["actions"],old):
                assert tuple(new[:11])==tuple(prior[:11]) and new[11]==prior[11] and tuple(new[13:])==tuple(prior[13:])
        if j==c.windows-1:
            top=e.ranking(pool,"safe_energy")[:4]
            if swap is None:
                assert [s["id"] for s in top]==[r["id"] for r in arm["records"]]
            break
        _,a,b=e.window_types(c,j)
        loads={}
        ordinary={}
        for k,s in pool.items():
            g,n,x,y=s["action"]
            key=(s["parent"],g,n)
            if key not in loads:
                loads[key]=e.load_planes(c,j,parents[s["parent"]],g,n,a,b)
            p=loads[key]
            ordinary[k]=max(p[:,0]+p[:,1:]@(x,y))
        thermal={k:s["risk"] for k,s in pool.items()}
        if swap is None:
            for row in old:
                if row[9]=="valid":assert row[12]==(ordinary if method=="NC" else thermal)[row[6]]
        ranked={m:rank(pool,r) for m,r in (("NC",ordinary),("NT",thermal))}
        policy=method if j!=swap else ("NC" if method=="NT" else "NT")
        kept=ranked[policy]
        if swap is None:
            assert kept==arm["log"]["beam"][j]
            if set(ranked["NC"])!=set(ranked["NT"]) and first_switch is None:first_switch=j
            for m,ids in ranked.items():
                for i,k in enumerate(ids,1):
                    s=pool[k];parent=parents[s["parent"]]
                    decisions.append(dict(case=c.label,actual_path=method,window=j+1,score=m,slot=i,config=k,parent=s["parent"],
                            action="/".join(map(str,s["action"])),E35_partial=s["energy"],drain_tick=s["drain"],
                            load_risk=ordinary[k],heat_risk_C=thermal[k],pred_peak_C=s["peak"],
                            enter_C="/".join(f"{x:.8f}" for x in parent["temperature"]),
                            end_C="/".join(f"{x:.8f}" for x in s["temperature"])))
            prefix=arm["cfg"][:int(c.release.searchsorted((j+1)*W))]
            state=pool[e.digest(prefix)]
            assert state["config"]==prefix and state["id"] in kept
            boundary_data[j+1]=state["temperature"]
        beams.append(kept)
        states=[pool[k] for k in kept]
    return top,beams,first_switch,boundary_data

def sliced(events,left,right):
    a=events[(events[:,1]>left)&(events[:,0]<right),:14].copy()
    assert len(a)
    a[:,0]=np.maximum(a[:,0],left)-left
    a[:,1]=np.minimum(a[:,1],right)-left
    assert a[0,0]==0 and a[-1,1]==right-left
    return a

def heat(c,events,temp):
    return integrate(events,np.asarray(temp),c.p.G,c.p.cap,float(c.p.ta),np.empty(0,np.int64),True)

def window_stats(c,word,arms,forecasts,states,winrows):
    for m,d in arms.items():
        tr=d["trace"]; cfg=np.frombuffer(d["cfg"],dtype=np.uint8)
        other=np.frombuffer(arms["NT" if m=="NC" else "NC"]["cfg"],dtype=np.uint8)
        full=c.ledger(d["cfg"],0,c.p.horizon,W,True,False)
        tmp=c.p.initial.copy(); accum=0.; states[m]=[tmp]
        for j,l in enumerate(word):
            left=j*W; right=(j+1)*W if j+1<len(word) else c.p.horizon
            ids=np.where((c.release>=left)&(c.release<(j+1)*W))[0]
            part=sliced(tr,left,right)
            out=heat(c,part,tmp)
            end=out[10][-1,4:8].copy()
            finish=full[6][ids]+c.args[4][ids]
            slack=(c.args[5][ids]-finish)/10.
            chosen=cfg[ids];alt=other[ids]
            ng=chosen<10; types=c.kinds[ids]
            freq=lambda v: "/".join(map(str,sorted(set(map(int,v))))) or "—"
            form=forecasts[m].get(j+1)
            winrows.append(dict(case=c.label,method=m,window=j+1,load=l,requests=len(ids),
                GPU_A=int(np.sum(ng&(types==0))),GPU_B=int(np.sum(ng&(types==1))),
                NPU_A=int(np.sum(~ng&(types==0))),NPU_B=int(np.sum(~ng&(types==1))),
                GPU_OPP=freq(chosen[ng]),NPU_OPP=freq(chosen[~ng]-10),
                moved_to_GPU_from_other=int(np.sum(ng&(alt>=10))),moved_to_NPU_from_other=int(np.sum(~ng&(alt<10))),
                same_device_OPP_up=int(np.sum((ng==(alt<10))&(chosen>alt))),
                same_device_OPP_down=int(np.sum((ng==(alt<10))&(chosen<alt))),
                entering_C="/".join(f"{v:.7f}" for v in tmp),leaving_C="/".join(f"{v:.7f}" for v in end),
                predicted_boundary_C="/".join(f"{v:.7f}" for v in form) if form is not None else None,
                window_peak_hi_C=max(out[2]),energy_J=out[0],temp_dependent_J=sum(out[9]),
                E35_J=out[0]-sum(out[9]),min_deadline_slack_ms=float(min(slack)),
                requests_finish_after_window=int(np.sum(finish>(j+1)*W))))
            accum+=out[0];tmp=end;states[m].append(end)
        assert abs(accum-d["rep"]["cert"]["metrics"]["E_J"])<1e-7

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    decision_rows=[]; summary=[]; wins=[]; splices=[]; heat_tests=[]; interventions=[]; registry={}
    for phase,src in inputs():
        root=Path(os.environ.get("M1F_DEV_SOURCE",BASE) if phase=="development8" else os.environ.get("M1F_HOLD_SOURCE",HOLD))
        hashes={v["file"]:v["sha256"] for v in json.loads((root/"evidence/manifest.json").read_bytes())}
        case=src.stem;size,word=case.split("_")
        c=e.reordered(e.case_for("L"+size[1:]),"L"+size[1:],word); c.eng.out=DIAG/"offline"
        arms=arm_sources(root/"evidence",case,hashes)
        outputs={}; forecasts={}; temps={}; cached={}
        def certify(cfg):
            key=e.digest(cfg)
            if key not in cached:
                v=c.ledger(cfg,0,c.p.horizon,W,True,False)
                slack=int(v[-1])/10.
                if v[0]:
                    cert,_=c.certify(cfg)
                    phys=cert["metrics"]
                    result=dict(config=key,plan=cert["plan_sha256"],status=phys["status"],E_J=phys["E_J"],
                          E35_J=cert["E35_J"],temp_J=phys["temperature_J"],peak_hi_C=max(phys["peak_hi"]),min_slack_ms=phys["min_deadline_slack_ms"])
                else:
                    result=dict(config=key,plan=None,status="TIMING",E_J=None,E35_J=None,temp_J=None,peak_hi_C=None,min_slack_ms=slack)
                cached[key]=result
                registry[case+"/"+key]=dict(config_b64=base64.b64encode(cfg).decode(),**result)
            return cached[key]
        for m,d in arms.items():
            _,beams,first,temps_pred=replay(c,m,d,decision_rows)
            outputs[m]=beams;forecasts[m]=temps_pred
            own=certify(d["cfg"])
            assert own["plan"]==d["plan"] and abs(own["E_J"]-d["rep"]["cert"]["metrics"]["E_J"])<1e-8
        order=next((i for i,(a,b) in enumerate(zip(outputs["NC"],outputs["NT"])) if a!=b),None)
        diff=next((i for i,(a,b) in enumerate(zip(outputs["NC"],outputs["NT"])) if set(a)!=set(b)),None)
        firstplan=next((int(c.release[i]//W+1) for i,(a,b) in enumerate(zip(arms["NC"]["cfg"],arms["NT"]["cfg"])) if a!=b),None)
        window_stats(c,word,arms,forecasts,temps,wins)
        for m,d in arms.items():
            if diff is not None:
                top,_,_,_=replay(c,m,d,[],swap=diff)
                for k,s in enumerate(top,1):
                    interventions.append(dict(case=case,base_policy=m,swapped_window=diff+1,rank=k,**certify(s["config"])))
        for j in range(1,c.windows):
            split=int(c.release.searchsorted(j*W))
            for past in arms:
                for future in arms:
                    cfg=arms[past]["cfg"][:split]+arms[future]["cfg"][split:]
                    splices.append(dict(case=case,boundary=j,transition=word[j-1:j+1],prefix=past,suffix=future,**certify(cfg)))
            for future,d in arms.items():
                ev=sliced(d["trace"],j*W,c.p.horizon)
                for past in arms:
                    out=heat(c,ev,temps[past][j])
                    heat_tests.append(dict(case=case,boundary=j,transition=word[j-1:j+1],events_from=future,initial_from=past,
                            suffix_E_J=out[0],suffix_temp_J=sum(out[9]),suffix_peak_hi_C=max(out[2])))
                native=heat_tests[-2 if future=="NC" else -1]["suffix_E_J"]
                expected=sum(r["energy_J"] for r in wins if r["case"]==case and r["method"]==future and r["window"]>j)
                assert abs(native-expected)<1e-7
        ns={m:certify(d["cfg"]) for m,d in arms.items()}
        dual=all(v["status"]=="SAFE" for v in ns.values())
        summary.append(dict(phase=phase,case=case,first_order_divergence=(order+1 if order is not None else None),
           first_membership_divergence=(diff+1 if diff is not None else None),first_representative_action_difference=firstplan,
           NC_status=ns["NC"]["status"],NT_status=ns["NT"]["status"],NC_E_J=ns["NC"]["E_J"],NT_E_J=ns["NT"]["E_J"],
           NC_peak=ns["NC"]["peak_hi_C"],NT_peak=ns["NT"]["peak_hi_C"],NC_slack_ms=ns["NC"]["min_slack_ms"],NT_slack_ms=ns["NT"]["min_slack_ms"],
           delta_NT_minus_NC_E35_J=ns["NT"]["E35_J"]-ns["NC"]["E35_J"],delta_NT_minus_NC_temp_J=ns["NT"]["temp_J"]-ns["NC"]["temp_J"],
           paired_saving_pct=100*(ns["NC"]["E_J"]-ns["NT"]["E_J"])/ns["NC"]["E_J"] if dual else None,
           same_plan=ns["NC"]["plan"]==ns["NT"]["plan"]))
        print("trace",case,flush=True)
    for f,rows in (("summary.csv",summary),("same_pool_decisions.csv",decision_rows),("physical_windows.csv",wins),("prefix_suffix.csv",splices),
                   ("fixed_suffix_temperature.csv",heat_tests),("one_window_intervention.csv",interventions)):
        dumpcsv(OUT/f,rows)
    with gzip.open(OUT/"offline_plans.json.gz","wb") as f:f.write(e.p1.raw(registry))
if __name__=="__main__":main()
