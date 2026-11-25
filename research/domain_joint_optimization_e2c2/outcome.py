"""Read-only reconstruction, independent physical recertification and frozen decision."""
import collections
import csv
import gzip
import json
import statistics
from fractions import Fraction
from settings import METHODS,SEEDS,INITIAL,ROOT,clock,read,write,sha

def table(name,rows,keys):
    with (ROOT/name).open("w",encoding="utf8",newline="") as f:
        fields=list(dict.fromkeys([*keys,*(k for row in rows for k in row)]))
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)

def inspect(folder,spec,lb):
    import c1r_assets,bounded
    from base import Problem,key,decode,raw,obj,changes,evaluate,np
    from audit import thermal
    from flow_run import apply_delta
    z=read(folder/"summary.json");p=Problem("D3");plan=None;prev=None;hist=[];mech=[];ph=[]
    events=collections.defaultdict(list);cpset=set();gset=set()
    with gzip.open(folder/"events.jsonl.gz","rb") as f:
        for line in f:
            a=json.loads(line)
            if a["event"]=="move":gset.update(a["st"])
            if a["event"] in ("core_region","selection"):
                cpset.update(a.get("st",a.get("ids",[])))
            if a["event"]=="subproblem":events[a["cycle"]].append(a)
    assert len(gset|cpset)==z["stages"] and len(cpset)==z["cp_stages"]
    with (folder/"accepted.jsonl").open("rb") as f:
        for line in f:
            v=json.loads(line);m=v["metrics"]
            assert m["status"]=="SAFE" and max(m["peak_hi"])<=80 and m["min_deadline_slack_ms"]>=-1e-9
            assert v["before"]==prev and v["t"]<=1800
            new=decode(v["full"]) if plan is None else apply_delta(plan,v)
            assert key(p,new)==v["after"]
            if plan is None:assert v["after"]==INITIAL
            else:
                assert hist[-1][1]["E_bounds"][0]>m["E_bounds"][1] and v["t"]>=hist[-1][0]
                d=changes(p,plan,new);assert d["config"]==v["cfg"] and d["moved"]==v["moved"]
                if v["phase"]=="joint":
                    moving={new[0][i][0] for i in d["moved"]}
                    row=dict(method=z["method"],seed=z["seed"],cycle=v["cycle"],iteration=v["it"],origin=v["origin"],
                         config=len(d["config"]),shifted=len(d["moved"]),support=len(set(d["config"])|set(d["moved"])),
                         shifted_devices=sorted(moving),cross_resource=int(len(moving)>=2),
                         cross_scene=int(len(d["scenes"])>1),before=prev,after=v["after"],
                         gain_lower_mJ=1000*(hist[-1][1]["E_bounds"][0]-m["E_bounds"][1]))
                    assert row["config"]<=12 and row["support"]<=24
                    mech.append(row)
                    if z["method"]=="Hybrid-New" and row["config"]>=2 and row["origin"] not in ("fallback","ordinary_full"):
                        path=folder/"witness.json.gz"
                        if not path.exists():
                            path.write_bytes(gzip.compress(raw(dict(summary=row,before=obj("D3",plan),after=obj("D3",new),certificate=m)),mtime=0))
            hist.append((v["t"],m,v["after"]));prev=v["after"];plan=new
    assert key(p,plan)==z["final"] and decode(z["final_plan"])==plan
    true=evaluate(p,plan,cert=True,trace=True);ev=np.asarray(true.pop("events"))
    assert raw(true)==raw(z["metrics"])
    independent=thermal(p,plan,ev,true,{})
    write(folder/"terminal_certificate.json",dict(sha=prev,continuous=true,independent=independent))
    np.savez_compressed(folder/"terminal_trace.npz",events=ev)
    def at(t):return next((m for s,m,k in reversed(hist) if s<=t),hist[0][1])
    for q in z["phases"]:
        gains=collections.Counter()
        for sub in (events[q["cycle"]] if q["phase"]=="joint" else []):
            source=next(m for _,m,k in hist if k==sub["source"])
            curr=source["E_J"]
            for tag,k,e,b in sub["improvements"]:
                stage="hint" if tag.startswith("hint") else "aux_cp" if tag.startswith("cp") else tag
                gains[stage]+=curr-e;curr=e
        net=q["before"]["E"]-q["after"]["E"]
        if q["phase"]=="joint":assert abs(net-sum(gains.values()))<1e-7
        ph.append(dict(method=z["method"],seed=z["seed"],cycle=q["cycle"],phase=q["phase"],
                before=q["before"]["sha"],after=q["after"]["sha"],net_J=net,hint_J=gains["hint"],aux_cp_J=gains["aux_cp"],
                core_J=gains["compact_core"]+gains["core"],ordinary_full_J=gains["ordinary_full"],fallback_J=gains["fallback"],
                scheduled_end=q["scheduled_end"],actual_end=q["actual_end"]))
    lo,hi=true["E_bounds"]
    row=dict(method=z["method"],seed=z["seed"],status="VERIFIED",E180=at(180)["E_J"],E900=at(900)["E_J"],J=true["E_J"],
         lo=lo,hi=hi,net_pct=100*(1-true["E_J"]/hist[0][1]["E_J"]),peak_upper_C=max(true["peak_hi"]),
         min_slack_ms=true["min_deadline_slack_ms"],last180_mJ=1000*max(0,at(1620)["E_bounds"][0]-hi),
         reliable_LB_J=lb,open_gap_J=hi-lb,stages=z["stages"],coverage=z["stages"]/2400,cp_stages=z["cp_stages"],
         steps=z["moves"],iterations=z["iterations"],accepted=len(hist)-1,sha=prev,**{k:true[k] for k in ("activity_J","base_J","temperature_J","switch_J","external_J")})
    return row,ph,mech,[(z["method"],z["seed"],t,m["E_J"],*m["E_bounds"],k) for t,m,k in hist]

def report():
    start=clock();s=read(ROOT/"execution.json");man=read(ROOT/"manifest.json");rows=[];ph=[];mech=[];pairs=[]
    lookup={z["tag"]:z for z in s["runs"]};curves=[]
    for v in man["runs"]:
        tag=v["method"]+"_"+str(v["seed"])
        if lookup.get(tag,{}).get("status")=="COMPLETE":
            row,phase,witness,trajectory=inspect(ROOT/"runs"/tag,v,float(Fraction(man["initial_lower"]["total"])))
            rows.append(row);ph+=phase;mech+=witness;curves+=trajectory
        else:rows.append(dict(method=v["method"],seed=v["seed"],status=lookup.get(tag,{}).get("status","NOT_STARTED")))
    idx={(x["method"],x["seed"]):x for x in rows}
    for seed in SEEDS:
        n=idx["Hybrid-New",seed]
        for baseline in METHODS[:-1]:
            b=idx[baseline,seed];r=dict(baseline=baseline,seed=seed,result="UNRESOLVED")
            if n["status"]==b["status"]=="VERIFIED":
                r.update(result="win" if n["hi"]<b["lo"] else "loss" if b["hi"]<n["lo"] else "overlap",
                    delta_mJ=1000*(b["J"]-n["J"]),delta_lo_mJ=1000*(b["lo"]-n["hi"]),delta_hi_mJ=1000*(b["hi"]-n["lo"]))
            pairs.append(r)
    table("results.csv",rows,["method","seed","status"]);table("paired.csv",pairs,["baseline","seed","result"])
    table("phase_results.csv",ph,["method","seed","cycle","phase","net_J"]);table("mechanisms.csv",mech,["method","seed","origin","support"])
    with gzip.open(ROOT/"curves.csv.gz","wt",encoding="utf8",newline="") as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(["method","seed","time_s","J","lo","hi","sha"]);w.writerows(curves)
    verified=[z for z in rows if z["status"]=="VERIFIED"]
    lines=["# D3 完整任务流混合联合节能验证",""]
    if len(verified)<12:
        title="正式比较未决"
        lines += [f"**{title}。** 12 个预定终点中有 {len(verified)} 个已独立核验。阶段状态为 {s['status']}。",
                  "",s.get("error",""),"","异常记录保留在 execution.json 和 logs/。未产生终点的配对保持未决。"]
    else:
        med={m:statistics.median(r["J"] for r in rows if r["method"]==m) for m in METHODS}
        wins={m:sum(x["result"]=="win" for x in pairs if x["baseline"]==m) for m in METHODS[:-1]}
        evidence=[r for r in mech if r["method"]=="Hybrid-New" and r["config"]>=2 and r["origin"] not in ("ordinary_full","fallback")]
        passed=all(v>=2 for v in wins.values()) and all(med["Hybrid-New"]<med[m] for m in wins) and bool(evidence)
        title="D3 达到后续验证条件" if passed else "D3 未达到后续验证条件"
        lines += [f"**{title}。** 12 个独立运行的终点均通过连续热认证、独立事件及矩阵指数复核。","",
              "|方法|种子 101 / J|种子 102 / J|种子 103 / J|中位数 / J|中位净节能率|","|---|---:|---:|---:|---:|---:|"]
        for m in METHODS:
            vals=[idx[m,n]["J"] for n in SEEDS]
            lines.append("|"+m+"|"+"|".join(f"{v:.8f}" for v in [*vals,med[m]])+f"|{100*(1-med[m]/man['source_J']):.3f}%|")
        lines+=["","正配对差表示 Hybrid-New 节能。表内为完整系统能耗点估计差；严格胜负按上下界判定。","",
                "|基线|101 / mJ|102 / mJ|103 / mJ|严格胜／负／区间重叠|","|---|---:|---:|---:|---:|"]
        for m in METHODS[:-1]:
            pp=[z for z in pairs if z["baseline"]==m];t=collections.Counter(z["result"] for z in pp)
            lines.append("|"+m+"|"+"|".join(f"{z['delta_mJ']:.3f}" for z in pp)+f"|{t['win']}／{t['loss']}／{t['overlap']}|")
        lines+=["","## 实际联合更新","",f"Hybrid-New 接纳 {len(evidence)} 项非普通回退的多配置联合改善。"]
        if evidence:
            a=max(evidence,key=lambda z:z["gain_lower_mJ"])
            lines.append(f"最强一次发生在种子 {a['seed']} 第 {a['cycle']} 周期，可靠节能 {a['gain_lower_mJ']:.3f} mJ，变档 {a['config']} 项、移时 {a['shifted']} 项、支撑并集 {a['support']} 项。所有接纳的前后排程可由该运行的 accepted.jsonl 完整恢复。")
        newph=[r for r in ph if r["method"]=="Hybrid-New" and r["phase"]=="joint"]
        sums=[sum(r[k] for r in newph) for k in ("hint_J","aux_cp_J","core_J","fallback_J","ordinary_full_J")]
        lines+=["",("三个种子的联合阶段合计，提示、紧凑辅助 CP、完整 Core、回退及第四次普通全权限邻域的顺序增量分别为 "+"、".join(f"{x:.5f}" for x in sums)+" J。"),
                "","各终点的热认证区间、能耗分项、峰温上界、期限余量、原全局下界及未闭合差距见 results.csv。阶段收益和实际支撑见 phase_results.csv、mechanisms.csv。完整轨迹见 curves.csv.gz。"]
        if not passed and (wins["G3"]<2 or med["Hybrid-New"]>=med["G3"]):
            lines+=["","保留 E2-c1-r 的局部机制证据，暂停扩展当前算法。"]
        elif not passed:lines+=["","现有配对不足以将最终安全能耗优势归因于新机制。"]
        else:lines+=["","证据支持后续消融和其他工况验证。本轮范围止于 D3，尚未检验跨工况优势。"]
        lines+=["","阶段收益沿已发生的搜索轨迹累计。本轮没有 Single 消融，不能从这些增量推断多配置协调的普遍独立贡献。"]
    lines+=["","## 预算","",f"预检计费 {s['preflight_s']:.2f}/900 s，正式运行计费 {s['main_charge']:.2f}/21600 s。核验及归档见 snapshot.json 与预算回执。"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
    write(ROOT/"audit.json",dict(title=title,verified=len(verified),audit_s=clock()-start,finished=__import__("time").time()))
if __name__=="__main__":report()
