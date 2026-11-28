"""Read-only tabulation of certified historical results. No restore, DP, thermal integration or certification."""
import csv
import json
from collections import defaultdict
from pathlib import Path
from report import OUT, ROOT, TABLE, CASES, fields, number, markdown, read, table, winner


def main():
    manifest=read(OUT/"nominees.json")
    slots={(r["case"],r["budget"],r["rank"]):r for r in manifest}
    physical={}
    for c in CASES:
        path=ROOT.parent/f"ch3_center_confirmation/lanes/{c}/r1/paired_results/{c}/physical/index.json"
        physical[c]=read(path)["plans"]
    exact=defaultdict(list)
    evaluated={}
    for k,r in slots.items():
        ix=physical[r["case"]][r["seed"]]
        assert ix["mapping"]==r["mapping"]
        identity=(r["case"],r["seed"],ix["trace_sha"])
        exact[identity].append(r)
        p=OUT/"slots"/k[0]/f"{k[1]}-{k[2]}.json"
        if p.is_file():
            q=read(p)["comparison"]
            assert q["seed"]==identity[1] and q["trace"]==identity[2]
            evaluated[identity]=q
    allrows=[]
    by_case=defaultdict(list)
    heat=[]
    for k,r in slots.items():
        c,b,rank=k
        identity=(c,r["seed"],physical[c][r["seed"]]["trace_sha"])
        identical=exact[identity]
        q=evaluated.get(identity)
        points={r["seed"]:r["point"]}
        done={}
        for stage in ("ordinary","thermal"):
            actual=[x["history"][stage] for x in identical if x["history"][stage]["completed"]]
            assert all(x==actual[0] for x in actual)
            if actual:
                z=actual[0]
                if z["point"]:
                    p=z["point"]
                    assert physical[c][p["plan"]]["mapping"]==r["mapping"]
                    points[p["plan"]]=p
                done[stage]=z
        def historical(stage):
            if stage not in done:
                return None
            key=done[stage]["incumbent"]
            return points[key] if key else None
        A,C=historical("thermal"),historical("ordinary")
        if q:
            A,B,C=(q["outcomes"][a] for a in "ABC")
            known={a:True for a in "ABC"}
            methods={a:"physically_checked_seed" for a in "ABC"}
        else:
            B=None
            known=dict(A="thermal" in done and "ordinary" in done,B=False,C="ordinary" in done)
            methods={a:"completed_historical_stage" if known[a] else "unavailable" for a in "ABC"}
            if known["A"]:
                # The SAFE arm updates the guide only on strict improvement. A HOT seed may use a SAFE or HOT ordinary proposal.
                op=done["ordinary"]["point"]
                guide=(op if op and op["status"] in ("SAFE","HOT") else r["point"]) if r["point"]["status"]=="HOT" else C
                if guide["plan"]==r["seed"] and physical[c][guide["plan"]]["trace_sha"]==identity[2]:
                    B=winner([r["point"],done["thermal"]["point"]])
                    known["B"]=True
                    methods["B"]="identical_archived_thermal_input"
        values=dict(A=A,B=B,C=C)
        row=dict(case=c,construction_s=b,rank=rank,seed=r["seed"],seed_trace=identity[2],
                 mapping=r["mapping"],seed_status=r["point"]["status"],seed_peak_C=r["point"]["peak"])
        for a,v in values.items():
            row[a+"_known"]=known[a]
            row[a+"_basis"]=methods[a]
            row.update({a+"_"+key:value for key,value in fields(v if known[a] else None).items()})
        allrows.append(row)
        by_case[c,b].append((known,values))
        if r["point"]["status"]=="HOT":
            heat.append(row)
    table("available_mappings.csv",allrows,list(allrows[0]))
    table("hot_recovery_all.csv",heat,list(allrows[0]))
    pools=[]
    for (c,b),positions in by_case.items():
        row=dict(case=c,construction_s=b,positions=len(positions))
        for a in "ABC":
            available=all(known[a] for known,_ in positions)
            pooled=winner([v[a] for _,v in positions]) if available else None
            row[a+"_pool_complete"]=available
            row.update({a+"_"+k:v for k,v in fields(pooled).items()})
        pools.append(row)
    table("available_pools.csv",pools,list(pools[0]))
    summary=read(ROOT/"decision.json")
    supplementary=dict(all_nominees=len(slots),observed_HOT=len(heat),unique_initial_plan_trace=len(exact),
        known_positions={a:sum(r[a+"_known"] for r in allrows) for a in "ABC"},
        complete_pools_by_arm={a:sum(r[a+"_pool_complete"] for r in pools) for a in "ABC"})
    summary["historical_inventory"]=supplementary
    (ROOT/"decision.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    report=(ROOT/"REPORT_zh.md").read_text(encoding="utf8")
    report=report.split("\n## 全部历史提名的证据清单")[0].rstrip()
    section=["","## 全部历史提名的证据清单","",
        f"完整历史清单有 {len(slots)} 个提名位置、{len(exact)} 组不同的原始排程与轨迹，含 {len(heat)} 个超温候选。下表纳入了尚未进行直接热调频配对、但已经具备完整历史证书的位置。相同排程与相同轨迹哈希才合并记账。",""]
    section+=markdown(["方法","结果已知的位置","所有提名位置均有结果的候选池"],[
        [label,f"{supplementary['known_positions'][a]}/{len(slots)}",f"{supplementary['complete_pools_by_arm'][a]}/24"] for a,label in zip("ABC",("两阶段","直接热调频","仅普通调频"))])
    section+=["","已知结果可包括完整求解后仍无 SAFE。阶段未完成或相应轨迹缺少直接求解时标为未知。该清单单列历史证据；上文的横向对照只统计证据齐全的配对。",""]
    def outcome(r,a):
        return "未完成" if not r[a+"_known"] else ("未恢复" if not r[a+"_plan"] else f"恢复，{r[a+'_J']:.6f} J")
    section+=markdown(["提名任务流","构造（秒）","原始峰温上界（°C）","两阶段","直接热调频","普通调频"],[
        [r["case"],r["construction_s"],number(r["seed_peak_C"],5),*[outcome(r,a) for a in "ABC"]] for r in heat])
    section+=["","完整历史档案中既有证书及 31 列物理轨迹可通过下列索引恢复；本轮实际新求解得到的计划、证书和轨迹存于本研究的 computed 目录。[历史中所有可用的单映射结果](tables/available_mappings.csv) · [各方法可用的完整候选池](tables/available_pools.csv) · [全部超温提名及恢复见证](tables/hot_recovery_all.csv) · [冻结历史物理证据](https://github.com/YBEMR/paper/tree/479f0ce02a1b0d1ed5ba3fd081d647dccec89e12/research/ch3_center_confirmation/lanes)"]
    (ROOT/"REPORT_zh.md").write_text(report+"\n"+"\n".join(section)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
