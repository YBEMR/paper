"""Consolidate prior evidence and the continuation using the frozen interval comparisons."""
import csv
import json
from collections import Counter
import sys
from prepare import OLD, OUT, ROOT
sys.path.insert(0,str(OLD))
import report


def rows(name):
    with (ROOT/"tables"/name).open() as f:
        return list(csv.DictReader(f))


def provenance(name, old_keys):
    data = rows(name)
    def identity(r):
        return (r["case"],r["construction_s"],r.get("rank"))
    for r in data:
        r["batch"] = ("previous" if identity(r) in old_keys else "supplemental") if r["complete"] == "True" else "incomplete"
    report.table(name,data,list(data[0]))
    return data


def main():
    report.ROOT, report.OUT, report.TABLE = ROOT, OUT, ROOT/"tables"
    report.main()
    tables = {}
    for name, totals in [("mappings.csv",(96,40)),("pools.csv",(24,10))]:
        with (OLD/"tables"/name).open() as f:
            old = {(r["case"],r["construction_s"],r.get("rank")):r for r in csv.DictReader(f) if r["complete"]=="True"}
        data = provenance(name,old)
        assert len(data)==totals[0] and len(old)==totals[1]
        for r in data:
            key = (r["case"],r["construction_s"],r.get("rank"))
            if key in old:
                assert all(r[k]==v for k,v in old[key].items())
        tables[name] = data
    pools, slots = tables["pools.csv"], tables["mappings.csv"]
    dec = json.loads((ROOT/"decision.json").read_bytes())
    prep = json.loads((ROOT/"acquisition.json").read_bytes())
    dec.pop("budget")
    dec["budget_receipt"] = "out/budget.json"
    counts = {name:dict(Counter(r["batch"] for r in data)) for name,data in tables.items()}
    dec["provenance"] = counts
    maxloss = max((p for p in pools if p["B_vs_A"]=="higher"),key=lambda p:float(p["B_minus_A_J"]),default=None)
    maxpct = max((p for p in pools if p["B_vs_A"]=="higher"),key=lambda p:float(p["B_minus_A_pct"]),default=None)
    dec["max_absolute_pool_loss"],dec["max_relative_pool_loss"] = maxloss,maxpct
    dec["safe_coverage"] = {layer:{a:sum(r[a+"_status"]=="SAFE" for r in data) for a in "ABC"} for layer,data in (("slots",slots),("pools",pools))}
    (ROOT/"decision.json").write_text(json.dumps(dec,ensure_ascii=False,indent=2)+"\n")
    hot = rows("hot_recovery.csv")
    witnesses = []
    for row in hot:
        k = row["seed"]
        c = row["case"]
        slot = next(r for r in slots if r["case"]==c and r["seed"]==k)
        for tag in ("seed","A","B","C"):
            plan = k if tag=="seed" else row[tag+"_plan"]
            certs = sorted((OUT/"evidence"/c).glob("**/"+plan+"/certificate.json")) if plan else []
            if plan:
                assert certs, (c,tag,plan)
            witnesses.append(dict(case=c,rank=row["rank"],construction_s=row["construction_s"],arm=tag,
                seed=k,plan=plan,peak_upper_C=row["seed_peak_C"] if tag=="seed" else slot[tag+"_peak_upper_C"],
                energy_J=slot["seed_J" if tag=="seed" else tag+"_J"], certificate=certs[0].relative_to(ROOT).as_posix() if certs else ""))
    report.table("hot_witnesses.csv",witnesses,list(witnesses[0]) if witnesses else ["case","arm","plan","certificate"])
    report_file = ROOT/"REPORT_zh.md"
    lines = [l for l in report_file.read_text(encoding="utf8").splitlines() if "本次累计计费" not in l and not ("600 核秒" in l and "时钟" in l)]
    lines += ["","## 续跑证据与开销","",
              f"冻结批次贡献 {counts['mappings.csv'].get('previous',0)} 个位置、{counts['pools.csv'].get('previous',0)} 个池；本批补齐 {counts['mappings.csv'].get('supplemental',0)} 个位置、{counts['pools.csv'].get('supplemental',0)} 个池。仍缺 {counts['mappings.csv'].get('incomplete',0)} 个位置、{counts['pools.csv'].get('incomplete',0)} 个池。每行 batch 标明来源。历史已完成阶段按证书复用，历史截断阶段按冻结规则补算。","",
              "按 A、B、C 顺序，认证 SAFE 的位置数为 "+"、".join(str(dec['safe_coverage']['slots'][a]) for a in "ABC")+"，候选池数为 "+"、".join(str(dec['safe_coverage']['pools'][a]) for a in "ABC")+"。"]
    if maxloss:
        lines+=["",f"最大绝对整池损失为 {maxloss['case']}（{maxloss['construction_s']} 秒），增加 {float(maxloss['B_minus_A_J']):.6f} J。最大相对损失为 {maxpct['case']}（{maxpct['construction_s']} 秒），增加 {float(maxpct['B_minus_A_pct']):.5f}%。"]
    lines+=["",f"原批次保留 595.011 核秒。本次档案准备耗时 {prep['total_preparation_wall_s']:.3f} 秒墙钟，单独记账。补充计算限额为 600 核秒，最终回执含编译、恢复、调频、认证和科学结果写入。固定候选池诊断只评价排程质量。","","[两处超温候选的逐方法证书索引](tables/hot_witnesses.csv) · [档案校验与分段计时](acquisition.json) · [两批累计预算回执](out/budget.json)"]
    match = json.loads((OUT/"checkpoint/match.json").read_bytes())
    cols = [str(i) for i,n in enumerate(match["unequal_entries"]) if n]
    lines += ["",f"C10 普通阶段的独立匹配复算具有相同的物理排程、物理事件和认证端点。完整轨迹在零起算的第 {', '.join(cols)} 列存在数值差异，起终节点温度的最大绝对差为 {match['max_temperature_trace_delta_C']:.6g} °C。A 与 C 采用历史已完成阶段的原证书和原轨迹；B 单独从原始超温提名求解。复算轨迹单独归档。两次档案准备分别耗时 {prep['previous_preparation_wall_s']:.3f} 和 {prep['total_preparation_wall_s']:.3f} 秒。","", "[匹配复核、两份轨迹哈希和逐列差异](out/checkpoint/match.json)"]
    report_file.write_text("\n".join(lines)+"\n",encoding="utf8")


if __name__=="__main__":
    main()
