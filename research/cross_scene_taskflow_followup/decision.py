from collections import Counter
from fractions import Fraction as Q
import math
import time
import numpy as np
from scipy.linalg import expm
from assets import CFG,DATA,base,digest,encode,get_plan,read,tab,valid_c0,write
from diagnostic import differences,physical
from local_domain import gap_table
from model import Problem,event_arrays
from mechanism import neighbors

def records(folder):
    return [read(path.relative_to(DATA)) for path in sorted((DATA/folder).glob("*.json"))]

def gate():
    pools=records("pools")
    choices=[];cases={}
    for case in CFG["cases"]:
        pp=[x for x in pools if x["case"]==case]
        ids=sorted({k for x in pp for k in x["common_ids"]})
        cc={k:read("certificates/"+k+".json") for k in ids}
        safe=[k for k in ids if cc[k]["continuous"]["status"]=="SAFE"]
        best=min(safe,key=lambda k:(cc[k]["continuous"]["E_J"],k));bc=cc[best]
        lb=min([bc["continuous"]["E_bounds"][0],*[cc[k]["continuous"]["E_bounds"][0] for k in safe],
                *[x["least_pinned_SAFE_lower"] for x in pp if x["least_pinned_SAFE_lower"] is not None]])
        flips=[]
        for k,c in cc.items():
            if c["continuous"]["status"]!="HOT" or c["reset"]["status"]!="SAFE":continue
            change=differences(get_plan(best),get_plan(k),bc["physical"],c["physical"])
            struct=bool(change["config_changes"] or change["added_edges"] or change["removed_edges"] or
                        change["dwell_changed"] or change["control_changed"])
            diff=lb-c["continuous"]["E_bounds"][1]
            ratio=diff/lb
            nt=Q(bc["physical"]["nonthermal_J"])-Q(c["physical"]["nonthermal_J"])
            material=ratio>=CFG["material_ratio"]
            passes=diff>0 and struct and (nt>0 or material)
            targets=[x["target"] for x in pp if k in x["common_ids"]]
            loss_upper=bc["continuous"]["E_bounds"][1]-c["continuous"]["E_bounds"][0]
            f=dict(sha=k,case=case,targets=targets,case_best_SAFE=best,strict_energy=diff>0,
                   reliable_gap_lower_J=diff,gap_upper_J=loss_upper,reliable_ratio=ratio,
                   structure=struct,changes_from_best_SAFE=change,nonthermal_saving_J=str(nt),
                   competitive=passes,subthreshold=passes and not material,trigger=passes and material,
                   hotspot=c["continuous"]["hotspot"],peak_tick=c["continuous"]["peak_tick"],
                   peak_lo=c["continuous"]["peak_lo"],peak_hi=c["continuous"]["peak_hi"])
            flips.append(f)
            if f["trigger"]:choices.append(f)
        cases[case]=dict(common_ids=ids,all_safe=safe,best_SAFE=best,best_SAFE_lower_J=lb,
                         flips=flips,strict_competitive=sum(f["competitive"] for f in flips))
    chosen=min(choices,key=lambda f:(-f["reliable_gap_lower_J"],f["case"],f["sha"])) if choices else None
    if chosen:
        case=chosen["case"];num=min(chosen["targets"])
        rec=read("targets/"+case+".json")["targets"][num]
        hot=get_plan(chosen["sha"])
        record=dict(stage=rec["stage"],opt=rec["opt"],hot_plan=[hot[0],sorted(hot[1])])
        groups,ts,hs,hot=neighbors(Problem(case),base(case),record)
        gs={g:[rec["stage"],*groups[g]] for g in CFG["arms"]}
        assert len(set(len(gs[g]) for g in CFG["arms"] if g!="B0"))==1
        write("ablation/groups.json",dict(case=case,target=num,groups=gs,source=chosen["sha"],
              time_order=ts,heat_order=hs))
    write("gate.json",dict(cases=cases,selected=chosen,trigger=bool(chosen),material_threshold=.001))

def audit():
    led=[__import__("json").loads(x) for x in (DATA/"calls.jsonl").read_text(encoding="utf8").splitlines()]
    assert all(r["case"] in ("D1","D2","ALL") for r in led)
    assert all(r["state"]=="OK" and r["elapsed_s"]<=r["limit_s"] for r in led if r["event"]=="end")
    start=read("preflight.json");g=read("gate.json")
    cells=[];summary=[];errors=[];per_candidate=[];max_dE=0.;max_dT=0.
    winners={}
    for case,meta in g["cases"].items():
        p=Problem(case);seed=base(case);baseinfo=start["seeds"][case]
        joined={};propagators={}
        gap0={sig:key in seed[1] for key,sig in gap_table(p,seed[0]).items()}
        main_pools=[r for r in records("pools") if r["case"]==case]
        all_pools=main_pools+[r for r in records("ablation/pools") if r["case"]==case]
        for pool in all_pools:
            assert len(pool["members"])<=5 and len(pool["top"])<=24
            assert pool["pool_hash"]==digest(encode(pool["common_ids"]))
            selected=read("targets/"+case+".json")["targets"][pool["target"]]
            for k in pool["common_ids"]:
                if k==baseinfo["sha"]:continue
                rows,low=get_plan(k)
                assert rows[pool["stage"]][:2]==tuple(pool["opt"])
                for j,(a,b) in enumerate(zip(seed[0],rows)):
                    if a!=b:assert j in pool["members"] and (a[2]==b[2] or b[2]%50==0 and abs(b[2]-a[2])<=500)
                gaps=gap_table(p,rows)
                assert low.issubset(gaps)
                assert all((key in low)==gap0[sig] for key,sig in gaps.items() if sig in gap0)
        ids=sorted({k for pool in all_pools for k in pool["common_ids"]})
        for k in ids:
            c=read("certificates/"+k+".json");pl=get_plan(k)
            ev,sw,ed=event_arrays(p,*pl)
            phy=c["physical"]
            assert ed==list(map(list,phy["edges"])) and list(map(list,sw))==phy["switches"]
            with np.load(DATA/"certificates"/(k+".npz")) as tape:
                assert np.array_equal(tape["events"],ev)
                cont=tape["continuous"];reset=tape["reset"]
            # Independent 6-dimensional affine exponential in seconds. The same
            # event operator acts on both paths. The stored certificate supplies interior extrema.
            X=np.zeros((6,2));X[:4]=p.initial[:,None];X[5]=1.
            for j,line in enumerate(ev):
                t,e=line[:2];b=line[2:6];beta=line[6:10]
                if t in p.boundaries:X[:4,1]=p.initial
                key=(int(e-t),*b,*beta)
                F=propagators.get(key)
                if F is None:
                    A=np.zeros((6,6))
                    A[:4,:4]=(-p.G+np.diag(beta))/p.cap[:,None]
                    A[:4,5]=(p.G@np.full(4,p.ta)+b-35*beta)/p.cap
                    A[4,:4]=beta;A[4,5]=b.sum()-35*beta.sum()+.30
                    F=expm(A*(e-t)/10000);propagators[key]=F
                X=F@X
                max_dT=max(max_dT,np.max(np.abs(X[:4,0]-cont[j,4:8])),np.max(np.abs(X[:4,1]-reset[j,4:8])))
            for col,label in enumerate(("continuous","reset")):
                m=c[label];d=abs(m["E_J"]-X[4,col]);max_dE=max(max_dE,d)
                assert m["E_bounds"][0]<=X[4,col]<=m["E_bounds"][1]
                assert abs(float(Q(phy["nonthermal_J"]))+m["temperature_J"]-m["E_J"])<1e-9
            assert max_dT<1e-7
            joined[k]=c
            per_candidate.append(dict(case=case,sha=k,continuous=c["continuous"]["status"],reset=c["reset"]["status"],
                 real_J=c["continuous"]["E_J"],reset_diagnostic_J=c["reset"]["E_J"],
                 base_J=float(Q(phy["base_J"])),activity_J=float(Q(phy["activity_J"])),switch_J=float(Q(phy["switch_J"])),
                 external_J=float(Q(phy["external_J"])),temperature_J=c["continuous"]["temperature_J"],
                 nonthermal_J=float(Q(phy["nonthermal_J"])),reset_temperature_J=c["reset"]["temperature_J"]))
        for pool in main_pools:
            num=pool["target"];v=read(f"counterfactual/{case}_{num}.json")
            assert v["common_ids"]==pool["common_ids"] and pool["pool_hash"]==v["pool_hash"]
            checks={"C0":lambda c:valid_c0(c["continuous"]),"C1":lambda c:c["continuous"]["status"]=="SAFE",
                    "C2":lambda c:valid_c0(c["continuous"]) and c["reset"]["status"]=="SAFE"}
            for group,fn in checks.items():
                good=sorted((k for k in pool["common_ids"] if fn(joined[k])),key=lambda k:(joined[k]["continuous"]["E_J"],k))
                assert good==v["ranked"][group]
            stats=pool["stats"]
            flips=[f for f in meta["flips"] if f["sha"] in pool["common_ids"]]
            statuses=pool["all_unique_status"]
            resolved=not statuses.get("UNRESOLVED",0)
            hot_covered=statuses.get("HOT",0)==sum(joined[k]["continuous"]["status"]=="HOT" for k in pool["common_ids"])
            scope=("CONFLICT_FOUND" if any(f["competitive"] for f in flips) else
                   "CERTIFICATION_UNRESOLVED" if not resolved or any(joined[k]["reset"]["status"]=="UNRESOLVED" for k in pool["common_ids"]) else
                   "PROVED_ABSENT_IN_SELECTED_FINITE_DOMAIN" if stats["exhausted"] and hot_covered else
                   "NOT_FOUND_IN_LIMITED_SEARCH")
            cells.append(dict(case=case,target=num,stage=pool["stage"],category=read("targets/"+case+".json")["targets"][num]["category"],
                members=" ".join(map(str,pool["members"])),visited=stats["visits"],unique_visited=stats["unique"],
                pool=len(pool["common_ids"]),pinned_top=len(pool["top"]),pinned_SAFE=bool(pool["best_pinned_SAFE"]),
                exhaust=stats["exhausted"],C0=len(v["ranked"]["C0"]),C1=len(v["ranked"]["C1"]),C2=len(v["ranked"]["C2"]),
                C1_minus_C0_J=v["point_gaps_J"].get("C1_minus_C0"),C1_minus_C2_J=v["point_gaps_J"].get("C1_minus_C2"),
                flips=len(flips),competitive=sum(f["competitive"] for f in flips),conclusion=scope,
                searched_HOT=statuses.get("HOT",0),searched_SAFE=statuses.get("SAFE",0),
                unresolved=statuses.get("UNRESOLVED",0),out_of_model=statuses.get("OUT_OF_MODEL",0)))
        best=joined[meta["best_SAFE"]]["continuous"];orig=baseinfo["metrics"]
        savings=orig["E_bounds"][0]-best["E_bounds"][1]
        summary.append(dict(case=case,G3_J=orig["E_J"],best_safe_J=best["E_J"],safe_sha=meta["best_SAFE"],
              safe_peak_hi_C=max(best["peak_hi"]),safe_gain_lower_J=savings,safe_gain_upper_J=orig["E_bounds"][1]-best["E_bounds"][0],
              safe_gain_lower_pct=100*savings/orig["E_bounds"][0],unique_pooled=len(meta["common_ids"]),
              continuous_safe=len(meta["all_safe"]),flips=len(meta["flips"]),competitive=meta["strict_competitive"]))
    if g["trigger"]:
        ab=records("ablation/pools");assert len(ab)==6
        gm=read("ablation/groups.json");case=gm["case"]
        for arm in CFG["arms"]:
            r=read("ablation/pools/"+arm+".json");m=r["best_pinned_SAFE"]
            winners[arm]=dict(members=r["members"],candidates=r["stats"]["unique"],best_pinned=m and m["sha"],energy=m and m["metrics"]["E_bounds"])
        best=winners["B3"]["energy"];caselb=g["cases"][case]["best_SAFE_lower_J"]
        # A missing pinned control has the available unchanged G3 as fallback.
        control_lb=min((winners[a]["energy"] or start["seeds"][case]["metrics"]["E_bounds"])[0] for a in ("B1","B4a","B4b"))
        positive=bool(best and best[1]<min(caselb,control_lb))
        write("ablation/comparison.json",dict(arms=winners,beat_time_and_controls=positive,case_best_SAFE_lower=caselb))
    tab("summary.csv",summary);tab("targets_summary.csv",cells);tab("candidates.csv",per_candidate)
    write("independent_audit.json",dict(unique_replays=len(per_candidate),two_paths_each=True,
        max_energy_difference_J=max_dE,max_endpoint_difference_K=float(max_dT),same_nonthermal_events=True,
        all_unaffected_idle_policies_preserved=True))
    report(summary,cells,g,winners)

def report(summary,cells,g,winners):
    rows=["# P1 v1.1 剩余节能空间与跨场景热冲突",""]
    rows+=["**"+("达到跨场景热冲突门槛，已作有限预算六组消融。" if g["trigger"] else "本轮未发现达到门槛的跨场景热冲突，停止时热联合机制探索。")+"**","",
           "## 普通时间资源协调的剩余安全节能","",
           "|工况|原 G3 能耗/J|本轮最佳连续 SAFE/J|严格节能下界/J|严格节能下界|共同池不同计划|连续 HOT、重置 SAFE|有竞争力|",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        rows.append(f"|{r['case']}|{r['G3_J']:.9f}|{r['best_safe_J']:.9f}|{math.floor(r['safe_gain_lower_J']*1e8)/1e8:.8f}|{math.floor(r['safe_gain_lower_pct']*1e5)/1e5:.5f}%|{r['unique_pooled']}|{r['flips']}|{r['competitive']}|")
    rows+=["","每个工况的比较对象均为指定 G3 排程。候选固定目标主任务的替代配置，搜索允许至多四个时间或资源相关 Stage 协调。跨目标汇总对完整排程去重。","",
           "## 冻结候选池的反事实评价","",
           "|工况/目标 Stage|时间阻塞类别|访问的不同计划数|共同池|C0/C1/C2 可行数|C1−C0/J|C1−C2/J|",
           "|---|---|---:|---:|---|---:|---:|"]
    labels={"solo":"单任务可放置","post":"移动 post 可解除","competitor_required":"须移动竞争任务","unclassified":"未取得类别见证"}
    for r in cells:
        a=r["C1_minus_C0_J"];b=r["C1_minus_C2_J"]
        delta=lambda v:"未决" if v is None else f"{v:.9f}"
        rows.append(f"|{r['case']} / {r['stage']}|{labels[r['category']]}|{r['unique_visited']}|{r['pool']}|{r['C0']}/{r['C1']}/{r['C2']}|{delta(a)}|{delta(b)}|")
    rows+=["","三组按同一真实连续系统能耗排序。逐池可靠能耗差区间及可行集合差异见 counterfactual/，每个候选的活动、域基准、温度修正、切换及外部能量见 candidates.csv。","",
           "## 冲突、消融与立项",""]
    nf=sum(len(c["flips"]) for c in g["cases"].values())
    if not nf:rows+=["共同池内没有连续 HOT、仅重置边界温度后 SAFE 的候选，因此没有可归因于热继承的竞争性能耗损失、热违规位置或配置变化。"]
    for case,c in g["cases"].items():
        for f in c["flips"]:
            d=f["changes_from_best_SAFE"];n=f["hotspot"]
            rows.append(f"\n{case} 计划 {f['sha'][:16]} 的真实热违规位于 {['CPU1','CPU2','GPU','NPU'][n]}，见证时刻 {f['peak_tick'][n]/10:.2f} ms，峰温下界 {f['peak_lo'][n]:.6f}°C。相对本轮最佳 SAFE 的可靠净节能下界 {f['reliable_gap_lower_J']:.9f} J，非温度相关节能 {float(Q(f['nonthermal_saving_J'])):.9f} J，配置变化 Stage {d['config_changes']}。完整资源边和驻留变化见 gate.json。")
    if winners:
        comp=read("ablation/comparison.json")
        rows+=["","六组目标恢复、候选数及能耗界见 ablation/comparison.json。"+
               ("B3 严格优于阶段一和同规模普通对照，取得该目标上的有限机制正例。第三章核心创新仍需更广证据。" if comp["beat_time_and_controls"] else "B3 未同时超过阶段一最佳 SAFE 和同规模普通对照，独立节能收益未证实。暂不作为第三章核心创新。")]
    else:
        rows+=["","六组消融未触发，270 s 配额取消。同规模时热关联选择的独立节能收益未测得。现有证据不足以支持把时热联合关联作为第三章核心创新。"]
    total=sum(r["exhaust"] for r in cells)
    categories=Counter(r["conclusion"] for r in cells)
    rows+=["",f"逐目标证据分级：在指定有限域内证实无竞争性冲突 {categories['PROVED_ABSENT_IN_SELECTED_FINITE_DOMAIN']} 项，有限搜索内未发现 {categories['NOT_FOUND_IN_LIMITED_SEARCH']} 项，认证未决 {categories['CERTIFICATION_UNRESOLVED']} 项，发现严格竞争性冲突 {categories['CONFLICT_FOUND']} 项。阶段一各目标访问计数合计，连续认证 HOT {sum(r['searched_HOT'] for r in cells)} 次，SAFE {sum(r['searched_SAFE'] for r in cells)} 次，超出有效温区 {sum(r['out_of_model'] for r in cells)} 次。"]
    rows+=["","## 结论边界","",f"共筛查 {len(cells)} 个冻结目标，其中 {total} 个完成其指定有限邻域的放置和空闲控制遍历。阶段二逐一认证固定共同池。每目标至多保留 24 个按能耗排序的候选，另含参照。未入池候选未作统一重置反事实验证。对更大邻域、其他起点或全局最优均无结论。",
           "","初解工件身份见 preflight.json，实际访问数及未覆盖范围见 pools/ 和 targets_summary.csv，独立仿射指数复核见 independent_audit.json。"]
    (DATA/"decision.md").write_bytes(("\n".join(rows)+"\n").encode())
