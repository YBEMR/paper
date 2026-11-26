"""Reconstruct each accepted trajectory and independently certify all finished endpoints."""
import collections
import csv
import gzip
import json
import statistics
import time
from fractions import Fraction
from design_d import C2,ROOT,INITIAL,METHODS,SEEDS,clock,read,write
from evidence_d import check_jobs

def table(name,rows,headers):
    fields=list(dict.fromkeys([*headers,*(k for r in rows for k in r)]))
    with (ROOT/name).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)

def stage(tag):
    return "hint" if tag.startswith("hint") else "aux_cp" if tag.startswith("cp") else tag

def inspect_run(folder,spec,lb):
    from outcome import inspect
    row,ph,changes,trajectory=inspect(folder,spec,lb)
    with gzip.open(folder/"events.jsonl.gz","rb") as f:ev=[json.loads(l) for l in f]
    timing=check_jobs(folder,ev,spec["method"])
    mods=timing.pop("modules");z=read(folder/"summary.json")
    assert len(ph)==6 and all(q["actual_end"]<=q["scheduled_end"] for q in ph)
    assert spec["exit_s"]<=900 and z["elapsed_s"]<900 and max(v[2] for v in trajectory)<900
    def at(t):return next((v for v in reversed(trajectory) if v[2]<=t),trajectory[0])
    for t in (180,300,600,900):
        v=at(t);row.update({f"E{t}":v[3],f"lo{t}":v[4],f"hi{t}":v[5]})
    row.update(last180_mJ=1000*max(0,at(720)[4]-row["hi"]),restarts=timing["restarts"],
         init_timeouts=timing["initialization_timeouts"],multi=sum(r["config"]>=2 for r in changes),
         max_support=max([0]+[r["support"] for r in changes]),exit_s=spec["exit_s"])
    modules=[]
    for cycle in (1,2,3):
        rows=[v for v in ev if v["cycle"]==cycle]
        local=[v for v in rows if v["event"]=="subproblem"]
        observed=collections.defaultdict(list)
        for call in mods:
            if call["cycle"]==cycle:observed[call["module"]].append(call)
        inc=collections.Counter();stream_count=collections.Counter()
        energies={r[6]:r[3] for r in trajectory}
        for sub in local:
            e=energies[sub["source"]]
            for origin,k,en,_ in sub["improvements"]:
                mod=stage(origin);inc[mod]+=e-en;stream_count[mod]+=1;e=en
        adopted=[v for v in changes if v["cycle"]==cycle]
        for mod in ("hint","aux_cp","compact_core","fallback","ordinary_full"):
            accepted=[v for v in adopted if stage(v["origin"])==mod]
            rr=observed[mod]
            modules.append(dict(method=row["method"],seed=row["seed"],cycle=cycle,module=mod,calls=len(rr),
                wall_s=sum(v["seconds"] for v in rr),censored=sum(v["censored"] for v in rr),accepted=len(accepted),
                ordered_improvements=stream_count[mod],ordered_gain_J=inc[mod],
                certified_candidates=sum(v["event"]=="certificate" and v["on_time"] and stage(v["stage"])==mod for v in rows),
                multi=sum(v["config"]>=2 for v in accepted),changed_configs=sum(v["config"] for v in accepted),
                max_support=max([0]+[v["support"] for v in accepted])))
        broad=next(x for x in z["phases"] if x["cycle"]==cycle and x["phase"]=="G3")
        hist_g=[v for v in trajectory if (cycle-1)*300<=v[2]<=broad["scheduled_end"]]
        modules.append(dict(method=row["method"],seed=row["seed"],cycle=cycle,module="g3",calls=1,
              wall_s=broad["actual_end"]-(cycle-1)*300,censored=0,accepted=len(hist_g)-int(cycle==1),
              ordered_improvements=len(hist_g)-int(cycle==1),ordered_gain_J=broad["before"]["E"]-broad["after"]["E"],
              certified_candidates=sum(v["event"]=="g3_candidate" and v["status"] in ("SAFE","HOT","OUT_OF_MODEL","UNRESOLVED") for v in rows)))
    assert abs(sum(v["ordered_gain_J"] for v in modules)-(63.39163095183008-row["J"]))<1e-7
    timing.update(exit_s=spec["exit_s"],endpoint_s=z["elapsed_s"],phase_times=z["phases"],
                  late_certificates=sum(v["event"]=="certificate" and not v["on_time"] for v in ev))
    return row,ph,modules,changes,timing,trajectory

def report():
    st=read(ROOT/"execution.json");m=read(ROOT/"manifest.json");rows=[];pairs=[];modules=[];ph=[];changes=[];curves=[];timings={}
    complete={v["tag"]:v for v in st["runs"] if v["status"]=="COMPLETE"}
    for v in m["runs"]:
        tag=v["method"]+"_"+str(v["seed"])
        if tag in complete:
            r,p,mo,c,t,tr=inspect_run(ROOT/"runs"/tag,complete[tag],float(Fraction(m["initial_lower"]["total"])))
            rows.append(r);ph+=p;modules+=mo;changes+=c;curves+=tr;timings[tag]=t
        else:rows.append(dict(method=v["method"],seed=v["seed"],status="INTERRUPTED" if any(z["tag"]==tag for z in st["runs"]) else "NOT_STARTED"))
    idx={(r["method"],r["seed"]):r for r in rows}
    for variant in METHODS[1:]:
        for seed in SEEDS:
            full=idx["Full",seed];other=idx[variant,seed]
            rec=dict(ablation=variant,seed=seed,result="UNRESOLVED")
            if full["status"]==other["status"]=="VERIFIED":
                rec.update(result="win" if other["hi"]<full["lo"] else "loss" if full["hi"]<other["lo"] else "overlap",
                    full_J=full["J"],full_lo=full["lo"],full_hi=full["hi"],ablation_J=other["J"],ablation_lo=other["lo"],ablation_hi=other["hi"],
                    full_minus_ablation_J=full["J"]-other["J"],difference_lo_J=full["lo"]-other["hi"],difference_hi_J=full["hi"]-other["lo"])
            pairs.append(rec)
    table("results.csv",rows,["method","seed","status"]);table("paired.csv",pairs,["ablation","seed","result"])
    table("module_results.csv",modules,["method","seed","cycle","module","calls","wall_s","accepted","ordered_gain_J"])
    table("phase_results.csv",ph,["method","seed","cycle","phase","net_J"])
    table("accepted_changes.csv",changes,["method","seed","cycle","iteration","config","support"])
    with gzip.open(ROOT/"curves.csv.gz","wt",encoding="utf8",newline="") as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(["method","seed","t","J","lo","hi","sha"]);w.writerows(curves)
    verified=len(complete);eligible=[]
    text=["# E2-d 核心算法结构筛选",""]
    if verified==9:
        med={k:statistics.median(idx[k,s]["J"] for s in SEEDS) for k in METHODS}
        for k in METHODS[1:]:
            wins=sum(p["ablation"]==k and p["result"]=="win" for p in pairs)
            if wins>=2 and med[k]<med["Full"]:eligible.append(k)
        decision="优先考虑的简化版本为 "+"、".join(eligible) if eligible else "暂时保留 Full"
        text+=[f"**{decision}。** 九个 D3 终点均已独立重建，经原连续认证器、频域事件及矩阵指数复算。","",
           "|方法|101 / J|102 / J|103 / J|中位数 / J|范围 / J|","|---|---:|---:|---:|---:|---:|"]
        for k in METHODS:
            vals=[idx[k,s]["J"] for s in SEEDS]
            text.append("|"+k+"|"+"|".join(f"{j:.8f}" for j in vals+[med[k]])+f"|{min(vals):.6f}–{max(vals):.6f}|")
        text+=["","差额为 Full 减去消融终点，正值表示消融更省电。严格胜负使用上下界分离，认证区间见 paired.csv。","",
            "|消融|101 / J|102 / J|103 / J|消融胜／负／重叠|","|---|---:|---:|---:|---:|"]
        for k in METHODS[1:]:
            ps=[p for p in pairs if p["ablation"]==k];counts=collections.Counter(p["result"] for p in ps)
            text.append("|"+k+"|"+"|".join(f"{p['full_minus_ablation_J']:+.6f}" for p in ps)+f"|{counts['win']}／{counts['loss']}／{counts['overlap']}|")
        text+=["","## 模块与搜索轨迹","","各阶段顺序净收益在三个种子上合计。接受次数按实际更新下一轮前态的候选计。模块耗时包括构造、求解、物理检查、认证和写入交接记录；进程与通信耗时单列在 timing.json。","",
           "|方法|模块|调用|耗时 / s|接纳|顺序净收益 / J|","|---|---|---:|---:|---:|---:|"]
        for k in METHODS:
            for mod in ("hint","aux_cp","compact_core","fallback","ordinary_full","g3"):
                ms=[r for r in modules if r["method"]==k and r["module"]==mod]
                text.append(f"|{k}|{mod}|{sum(r['calls'] for r in ms)}|{sum(r['wall_s'] for r in ms):.2f}|{sum(r['accepted'] for r in ms)}|{sum(r['ordered_gain_J'] for r in ms):.6f}|")
        text+=["","|方法|联合迭代数 101／102／103|Stage 覆盖 101／102／103|多配置接纳数|最大实际支撑|","|---|---:|---:|---:|---:|"]
        for k in METHODS:
            rr=[idx[k,s] for s in SEEDS]
            text.append("|"+k+"|"+"／".join(str(r["iterations"]) for r in rr)+"|"+"／".join(str(r["stages"]) for r in rr)+f"|{sum(r['multi'] for r in rr)}|{max(r['max_support'] for r in rr)}|")
        text+=["","删除模块所释放的时间可以增加同一联合阶段内的后续迭代；轨迹间的终点差同时包含选点、配置、支撑和迭代数的变化。本轮只对 D3、900 秒作结构判断。两项单独消融不能推出同时删除两个模块的效果。"]
    else:
        decision="正式比较未决"
        text+=[f"**{decision}。** 已独立复核 {verified}/9 个终点。停止状态为 {st['status']}。","",st.get("error","")]
    old=read(ROOT/"preflight"/"historical_103.json")
    text+=["","## 运行工程与预算","",f"E2-c2 的种子 103 在最初两个联合阶段启动工作进程 {old['starts']} 次。原记录缺少导入与资产加载分项，底层原因未知。原辅助阶段 7.55 毫秒越界及退出观测延迟保留在冻结记录中。"]
    if timings:
        text+=[f"本轮正式工作进程重启共 {sum(v['restarts'] for v in timings.values())} 次，就绪超时 {sum(v['initialization_timeouts'] for v in timings.values())} 次。最长辅助阶段 {max(v['aux_max'] for v in timings.values()):.4f} 秒，最长局部子问题 {max(v['local_max'] for v in timings.values()):.4f} 秒，最晚进程退出观测 {max(v['exit_s'] for v in timings.values()):.4f} 秒。"]
    text+=["",f"正式计费 {st['formal_s']:.2f}/8100 秒。预检计费 {st['preflight_s']:.2f} 秒，独立复核、归档及总额见预算回执。各时点能耗、分项、认证区间、末 180 秒收益及期限余量见 results.csv。"]
    (ROOT/"decision.md").write_bytes(("\n".join(text)+"\n").encode())
    write(ROOT/"timing.json",dict(formal=timings,preflight_s=st["preflight_s"],formal_s=st["formal_s"],
          caps=dict(auxiliary=11,local=30,run=900),historical=old["old_timing"]["overruns"]))
    write(ROOT/"decision.json",dict(decision=decision,eligible=eligible,verified=verified,next_runs=0))
if __name__=="__main__":report()
