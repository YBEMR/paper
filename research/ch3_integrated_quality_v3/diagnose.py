"""Recover first-repeat V2 candidates; gate the online experiment using an independent SAFE comparator."""
import csv
import json
import os
import signal
import tarfile
import time
import zlib
from pathlib import Path
START=time.perf_counter()
from hot import OUT,V2,census,nominees,upper,peak,refine_hot,handoff,valid,v2,f,m
import evidence as ev
import audit as qa
import numpy as np

DEST=OUT/"history"
CASES=("A03","A04","A06","C10","C12")
ev.ROOT=V2
def table(name,rows):
    with (DEST/(name+".csv")).open("w",newline="") as file:
        w=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator="\n")
        w.writeheader();w.writerows(rows)

def material(folder):
    ev.verify(folder)
    maps={};certs={}
    for file in folder.glob("*.tar"):
        with tarfile.open(file,"r:") as arc:
            for ent in arc:
                key,kind=ent.name.split("/")
                if key!="blocks":
                    value=json.loads(zlib.decompress(arc.extractfile(ent).read()))
                    if kind=="plan":maps[key]=v2.identity(value)
                    else:certs[key]=value
    return maps,certs

def main():
    DEST.mkdir(parents=True)
    m.CLOCK=START
    warm=f.warm()
    old=V2/"archive"
    pins={p[2:]:h for h,p in (line.split("  ",1) for line in (V2/"SHA256SUMS").read_text().splitlines())}
    def pinned(path):
        assert f.digest(path.read_bytes())==pins[path.relative_to(V2).as_posix()]
    runs=V2/"tables/runs.csv";pinned(runs)
    with runs.open() as file:
        reference={r["case"]:r for r in csv.DictReader(file) if r["rep"]=="1" and r["version"]=="multi"}
    flows=[];selected=[];indexed=[];qualifying=[]
    for code in CASES:
        obj=next(o for o in m.u2.CASES if m.label(o)==code)
        lane=old/code;phys=lane/"physical";cell=lane/"r1-multi"
        for p in [cell/"search.jsonl",cell/"refine.jsonl",cell/"receipt.json",lane/"lane.json",*phys.glob("*")]:pinned(p)
        maps,certs=material(phys)
        idx=f.read(phys/"index.json")["plans"]
        events=f.readlog(cell/"search.jsonl")
        seed=f.best(events,55)["point"]
        base=reference[code]
        assert f.read(cell/"receipt.json")["cut"]==55 and float(base["construction_J"])==seed["J"]
        oldpts=[e["point"] for e in events if e["event"]=="certificate" and e["t"]<=55]
        incumbent=seed
        for e in f.readlog(cell/"refine.jsonl"):
            if e["event"]=="certificate" and e["t"]<=60 and f.strict(e["point"],incumbent):
                incumbent=e["point"]
        assert incumbent["plan"]==base["plan"] and incumbent["bounds"][0]==float(base["lower"])
        qa.checked(incumbent,certs)
        safe,hot,only,plans=census(events,maps.__getitem__)
        for e in events:
            if e["event"]!="certificate" or e["t"]>55:continue
            p=e["point"];key=p["plan"];qa.checked(p,certs);mkey=maps[key]
            indexed.append(dict(case=code,t=e["t"],width=e["width"],plan=key,mapping=f.digest(mkey),
                 status=p["status"],mapping_class=("SAFE" if mkey in safe else "HOT-only" if mkey in only else "excluded"),
                 upper=p["bounds"][1],peak=p["peak"],slack=p["slack"],trace=idx[key]["trace_sha"]))
        assert hot
        energy,cool=nominees(only)
        # Both extrema on the same mapping get one call, using the online energy representative.
        chosen=[] if energy is None else [(energy,"energy")]
        if cool is not None and maps[cool["point"]["plan"]]!=maps[energy["point"]["plan"]]:
            chosen.append((cool,"peak"))
        eligible=bool(energy and upper(energy)[0]<seed["bounds"][0])
        flows.append(dict(case=code,certificates=len(oldpts),unique_plans=len(set(p["plan"] for p in oldpts)),
            safe_maps=len(safe),hot_maps=len(hot),shared_maps=len(set(safe)&set(hot)),hot_only=len(only),
            energy_plan=energy["point"]["plan"] if energy else None,peak_plan=cool["point"]["plan"] if cool else None,
            eligible=eligible,historical_four_J=incumbent["J"],historical_four_plan=incumbent["plan"],
            seed_lower=seed["bounds"][0],historical_four_lower=incumbent["bounds"][0]))
        for e,role in chosen:
            p=e["point"];key=p["plan"];dest=DEST/code/role;source=dest/"original"
            ev.restore(code,key,source)
            eng,flow,start=handoff(obj,dest/"replay",source,p)
            # Independently reproduce the HOT schedule including its true trajectory.
            d,tr=eng.cert(start[0],start[1])
            orig=start[2];a=orig["metrics"];b=d["metrics"]
            assert f.digest(start[3].tobytes())==idx[key]["trace_sha"]
            delta=float(np.max(np.abs(start[3][:,14:]-tr[:,14:])))
            eng_delta=abs(a["E_J"]-b["E_J"])
            comparison=dict(plan=key,original_trace=idx[key]["trace_sha"],replay_trace=f.digest(tr.tobytes()),
                max_numeric_trace_delta=delta,energy_delta=eng_delta,exact_metrics=a==b,
                different_metrics=[k for k,v in a.items() if v!=b[k]],original_metrics=a,replay_metrics=b)
            f.save(dest/"replay_audit.json",comparison)
            print(code,role,"replay",delta,eng_delta,comparison["different_metrics"],flush=True)
            assert d["plan_sha256"]==key and f.raw(orig["E35_exact"])==f.raw(d["E35_exact"])
            assert f.raw(orig["switches"])==f.raw(d["switches"])
            assert np.array_equal(start[3][:,:14],tr[:,:14]) and valid(tr,eng.p.horizon)
            assert a["status"]==b["status"]=="HOT" and a["min_deadline_slack_ms"]==b["min_deadline_slack_ms"]
            assert a["E_bounds"][0]<=b["E_J"]<=a["E_bounds"][1] and b["E_bounds"][0]<=a["E_J"]<=b["E_bounds"][1]
            assert all(max(al,bl)<=min(ah,bh) for al,ah,bl,bh in zip(a["peak_lo"],a["peak_hi"],b["peak_lo"],b["peak_hi"]))
            assert np.allclose(start[3][:,14:],tr[:,14:],rtol=1e-12,atol=1e-10)
            steps=[]
            local=refine_hot(eng,flow,start,dest,lambda event,**kw:steps.append(dict(event=event,**kw)))
            f.save(dest/"stages.json",steps)
            points={s["stage"]:s["point"] for s in steps if s["event"]=="certificate"}
            q,t=points.get("ordinary"),points.get("thermal")
            beat=bool(f.strict(local,incumbent))
            witness=role=="energy" and eligible and beat
            row=dict(case=code,role=role,mapping=f.digest(plans[key]),plan=key,t=e["t"],raw_J=p["J"],raw_upper=p["bounds"][1],
                raw_peak=p["peak"],seed_lower=seed["bounds"][0],online_selected=(role=="energy" and eligible),
                ordinary_status=q["status"] if q else None,ordinary_J=q["J"] if q else None,
                ordinary_peak=q["peak"] if q else None,thermal_status=t["status"] if t else None,
                thermal_J=t["J"] if t else None,thermal_peak=t["peak"] if t else None,best_safe_J=local["J"] if local else None,
                safe_upper=local["bounds"][1] if local else None,best_safe_plan=local["plan"] if local else None,
                historical_four_J=incumbent["J"],gain_J=incumbent["J"]-local["J"] if local else None,
                beat=beat,witness=witness)
            selected.append(row)
            if witness:qualifying.append(row)
        print(code,"only",len(only),"nominated offline",len(chosen),"eligible",eligible,flush=True)
    assert len(selected)<=10
    table("flows",flows);table("diagnosis",selected);table("candidate_identity",indexed)
    elapsed=time.perf_counter()-START
    prior=21.0  # First two interface attempts charged 12 + 9 seconds.
    assert prior+elapsed<120
    f.save(DEST/"gate.json",dict(passed=bool(qualifying),witnesses=qualifying,elapsed_s=elapsed,prior_s=prior,total_s=prior+elapsed,
        core=f.CPU,warm=warm,cap=120,distinct=len(selected),source=os.environ["GITHUB_SHA"],run=os.environ["GITHUB_RUN_ID"]))
    text=["# 第三轮历史诊断","",f"按指定五条任务流逐张恢复了首重复 55 秒内的 {len(indexed)} 张证书。含预热的本次单核用时 {elapsed:.3f} 秒，前次核验另按 21 秒记账，合计 {prior+elapsed:.3f}／120 核秒。实际优化 {len(selected)} 个不同 HOT-only 映射。有 {len(qualifying)} 个见证同时满足在线提名规则并严格胜过历史四安全映射终点。","",
        "| 任务流 | 选择依据 | 原 HOT 能耗 J | 普通调频 | 温度修正 | 历史四映射 J | 相对历史节省 J | 在线门槛 |","|---|---|---:|---|---|---:|---:|---|"]
    for r in selected:
        def show(k):return f"{r[k+'_status']} {r[k+'_J']:.6f} J" if r[k+'_status'] else "无可评价排程"
        delta="—" if r["gain_J"] is None else f"{r['gain_J']:.6f}"
        text.append(f"| {r['case']} | {'最低能耗' if r['role']=='energy' else '最低峰温'} | {r['raw_J']:.6f} | {show('ordinary')} | {show('thermal')} | {r['historical_four_J']:.6f} | {delta} | {'通过' if r['online_selected'] else '未入选'} |")
    text+=["","[全部映射分类与两个极值](archive/history/flows.csv) · [逐候选记录](archive/history/candidate_identity.csv) · [调频及严格区间核对](archive/history/diagnosis.csv) · [物理排程及证书](archive/history)",""]
    from hot import ROOT
    (ROOT/"HISTORY_zh.md").write_text("\n".join(text))
    if not qualifying:
        (ROOT/"REPORT_zh.md").write_text("# 第三轮集成版本决策\n\n**保留第二轮四安全映射版本。** 历史诊断没有出现满足在线第四位置提名条件、且调频后严格胜过同批四映射终点的见证。按预登记停止，正式运行 0/72 次，正式预算使用 0/4320 核秒。在线逐流比较与第四位置机会成本没有观测值。\n\n"+"\n".join(text[2:]))
if __name__=="__main__":
    main()
