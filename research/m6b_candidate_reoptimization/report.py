"""Generate the Chinese diagnosis from the audited ledgers."""
import statistics as st
from collections import Counter
from pathlib import Path
from inventory import ARCH,ROOT,METHODS,read,readcsv
A=ROOT/"analysis"
def avg(rows,k):return st.mean(float(r[k]) for r in rows) if rows else None
def num(x,p=6):return "—" if x in (None,"") else f"{float(x):.{p}f}"
def pos(x,p=6):return "—" if x in (None,"") else f"{float(x):+.{p}f}"
def tab(h,v):
    return ["| "+" | ".join(h)+" |","|"+"|".join("---" for _ in h)+"|",*["| "+" | ".join(str(x) for x in row)+" |" for row in v],""]
def counts(rows,k):return " / ".join(str(sum(r[k]==v for r in rows)) for v in ("win","tie","loss"))
def yes(v):return v=="True"
def main():
    identity=readcsv(A/"inventory.csv");pairs=readcsv(A/"pairs.csv");eff=readcsv(A/"effects.csv");runs=readcsv(A/"cells.csv")
    qual=readcsv(A/"c10_quality.csv");ranks=readcsv(A/"c10_mapping_ranks.csv");hot=readcsv(A/"hot_witnesses.csv")
    totals=read(A/"verification.json");fixture=read(ARCH/"fixture/result.json");history=read(ARCH/"fixture_identity.json")
    et={m:[x for x in eff if x["source"]==m] for m in METHODS}
    cp={m:{x["category"]:x for x in qual if x["source"]==m} for m in METHODS}
    sf=runs[0];allh=[x for x in eff if yes(x["has_hot"])];real=[x for x in hot if x["arm"]=="H" and yes(x["beats_equal_budget_safe"])]
    unique={(x["case"],x["source"],x["mapping"]) for x in real}
    diff=avg(pairs,"H_nt_minus_zhou"); complete=totals["completed_all"]
    better=sum(x["S_vs_P"]=="win" for x in eff);hwin=sum(x["H_vs_S"]=="win" for x in eff)
    text=["# 历史候选映射的全局调频潜力诊断","",
        f"原算法在 60 秒内已经尝试过多种设备分配。有些分配原来搭配的频率并不合适。对多份原本安全的分配重新选频后，{better}/{len(eff)} 个“来源 × 任务流”结果严格优于只调原最佳安全排程，两算法均按相同规则计量。","",
        f"把部分名额留给历史中只出现过超温结果的映射，正式对照中有 {hwin} 个来源工况进一步节能；存在这种映射的工况为 {len(allh)}/{len(eff)}。正式提名中，{len(unique)} 份不同的来源内独有映射在重新调频后严格胜过相应的多安全映射对照。","",
        f"同等再优化权限下，十二流上本章相对增强 Zhou 的胜 / 平 / 负为 {counts(pairs,'H_nt_vs_zhou')}，完整系统能耗的逐流平均差（本章减 Zhou）为 {pos(diff)} J。竞争结论同时参照各流百分比和绝对差，超温候选只按确实曾生成的身份归因。",""]
    nt=cp["NT"]["all"];zhou=cp["ZQ-Beam"]["all"]
    text += [f"在开发流实际遍历的本章映射中，{nt['beats_native_Zhou']} 份在再优化后严格优于增强 Zhou 的原始历史最佳，{nt['beats_Zhou_P']} 份优于对方原最佳映射调频后的结果，{nt['beats_Zhou_full']} 份优于对方本轮全池最优。本章与增强 Zhou 的全池最佳能耗分别为 {num(nt['best_final'])} 和 {num(zhou['best_final'])} J。",""]
    for arm,label in (("S","多安全映射"),("H","加入超温独有映射")):
        text += [f"{label}的配对平均相对节能率（以 Zhou 为分母）为 {pos(avg(pairs,arm+'_nt_saving_pct'),4)}%。",""]
    text+=["## 候选恢复与公平性","",
        f"冻结回执校验了每条流的 runs.tar.xz、physical.tar.xz 与 event_index.csv.gz。在原始运行中找到 {totals['calls']:,} 次到点认证。按整份三阶段物理计划 SHA 去重，再以所有请求的 GPU/NPU 选择序列去重。原始计划、证书文件逐份验 SHA，全部调用校验配置及证书物理字段。未送入优化的轨迹由冻结事件索引标识；每次实际送入优化都在本单元重放并核对完整事件数组和 NPZ 文件摘要。源级计数在两方拥有同一映射时会各计一次。","",
        "有过 SAFE 又有过 HOT 的映射留在安全类。只有本方有 HOT 且两方都未出现 SAFE 的映射能占 H 的专用名额。本方仅 HOT 而对方曾 SAFE 的映射单列。每流两方共用同一提名数，固定原最佳 SAFE 第一位，其余按最低参考能耗及配置身份决定，两组的共享映射使用一致的历史代表。每个正式单元独立计算首位的 P，C10 的全池结果与正式比较各自计时。","",
        f"普通调频及温度修正调用上一轮冻结程序。只有前一阶段没有产生有效域物理轨迹时才改用预先登记的同映射轨迹。保留每个原始提名，只有连续证书给出严格分离的 SAFE 能耗区间才更新在位解。本次 {totals['replay_M6a_matches']}/24 份首名最终排程与上一轮冻结端点的物理身份一致，逐源差异见单元账本。",""]
    text+=tab(["来源","到点调用","源内有效映射（逐流合计）","其中曾安全","曾安全且曾超温","本方只超温、对方曾安全","两方均无安全记录的本方超温映射","模型外/未决调用"],
        [[m,*[sum(int(x[k]) for x in identity if x["source"]==m) for k in ("ontime_calls","valid_maps","safe_maps","safe_and_hot","other_side_safe","hot_only","excluded")]] for m in METHODS])
    text+=["## 开发流全池质量诊断","",
        ("两方名单全部遍历，以下结果覆盖冻结时间段内两种算法实际认证过的全部有效域映射。" if complete else "有名单未能遍历。以下结果只描述到时已经完成的映射，未遍历部分的质量未知。"),"",
        "表中普通、温度列为该阶段原始 SAFE 结果的最低能耗；最后一列还保留此前已认证的安全在位解。",""]
    text+=tab(["来源","映射范围","处理数","最终有 SAFE","普通最低 J","温度修正最低 J","保留在位后 J","胜本方原最佳调频数","胜 Zhou 原最佳调频数","胜 Zhou 本轮全池最佳数"],
        [[x["source"],{"safe":"曾安全","all":"全部有效域","hot_only":"超温独有"}[x["category"]],x["n"],x["recovered"],num(x["best_ord_raw"]),num(x["best_thermal_raw"]),num(x["best_final"]),x["beats_own_P"],x["beats_Zhou_P"],x["beats_Zhou_full"]] for x in qual])
    for m in METHODS:
        arms={r["arm"]:r for r in runs if r["case"]=="C10" and r["source"]==m}
        text += [f"在等预算筛选中，{m} 两组各获 {arms['S']['nominated']} 个名额。仅安全名单达到 {num(arms['S']['final'])} J，允许热独有后达到 {num(arms['H']['final'])} J；后者距该来源全池最佳 {num(float(arms['H']['final'])-float(arms['ALL']['final']))} J。",""]
        winners=[x for x in ranks if x["source"]==m and x["after_SAFE_rank"]=="1"]
        for x in winners:
            text += [f"{m} 的最优映射最早在束宽 {x['first_width']}、第 {num(x['first_s'],3)} 秒交付，宽度内第 {x['first_beam_rank']} 名。其历史代表为 {x['origin']}，能耗 {num(x['rep_J'])} J，历史参考能耗排名 {x['reference_rank']}，含超温的原始能耗排名 {x['original_energy_rank']}。重新调频后的最佳安全能耗为 {num(x['final_J'])} J。",""]
    text+=["## 十二流等预算对照","","P 只优化原最佳安全映射，S 增加历史安全映射，H 向超温独有映射分配部分同等名额。单位 J。",""]
    text+=tab(["工况","本章 P","本章 S","本章 H","Zhou P","Zhou S","Zhou H","H 本章−Zhou"],
        [[x["case"],*[num(x[k]) for k in ("nt_P","nt_S","nt_H","zhou_P","zhou_S","zhou_H")],pos(x["H_nt_minus_zhou"])] for x in pairs])
    text+=["两种来源的 P、S、H 均在十二条流上交付 SAFE。以下改善量均以紧前方法为基准，正值代表更省电。安全映射多样性的贡献取 S 相对 P，开放超温来源的独立贡献取 H 相对 S。",""]
    effect_table=[]
    for m in METHODS:
        for lbl,group in (("全部",et[m]),("有超温独有候选",[x for x in et[m] if yes(x["has_hot"])])):
            effect_table.append([m,lbl,len(group),counts(group,"S_vs_P"),num(avg(group,"S_gain_J")),num(avg(group,"S_gain_pct"),4),
                                 counts(group,"H_vs_S"),num(avg(group,"H_gain_J")),num(avg(group,"H_gain_pct"),4)])
    text+=tab(["来源","样本","流数","S胜/平/负","S平均改善 J","S平均 %","H胜/平/负","H平均追加 J","H平均追加 %"],effect_table)
    text+=["两算法之间的最终配对在同一批流上比较。子集按至少一方有真实超温独有映射固定。",""]
    group2=[x for x in pairs if int(x["nt_hot_only"])+int(x["zhou_hot_only"])>0]
    text+=tab(["样本","流数","方法","本章胜/平/负","本章−Zhou 平均 J","本章平均相对节能 %"],
        [[tag,len(group),arm,counts(group,arm+"_nt_vs_zhou"),pos(avg(group,arm+"_nt_minus_zhou")) if group else "—",
          num(avg(group,arm+"_nt_saving_pct"),4)] for tag,group in (("全部",pairs),("至少一方有热独有",group2)) for arm in ("P","S","H")])
    text+=["## 普通调频和温度信息各自兑现了多少","","以下按每单元相同入选名单比较。普通阶段包含原始安全在位解，温度追加量按完整最终 SAFE 能耗计算。",""]
    z=[]
    for m in METHODS:
        for arm in ("S","H"):
            group=[x for x in runs if x["source"]==m and x["arm"]==arm]
            z.append([m,arm,len(group),num(st.mean(float(x["original_best"])-float(x["ordinary_incumbent"]) for x in group)),
                      num(avg(group,"thermal_additional_J")),sum(float(x["thermal_additional_J"])>0 for x in group),
                      sum(int(x["hot_completed"]) for x in group),sum(int(x["recover_ordinary"]) for x in group),sum(int(x["recover_final"]) for x in group)])
    text+=tab(["来源","权限","流数","普通平均改善 J","温度平均追加 J","温度追加获益流数","完成的热独有映射","普通恢复安全数","最终保有安全结果数"],z)
    observed=readcsv(A/"map_stages.csv")
    transition=[]
    for arm in ("ALL","S","H"):
        candidates=[x for x in observed if x["arm"]==arm and x["original_status"]=="HOT"]
        recovered=[x for x in candidates if x["ordinary_status"]=="SAFE"]
        transition.append([arm,len(candidates),len(recovered),sum(x["thermal_status"]=="HOT" for x in recovered),
            sum(x["ordinary_status"]!="SAFE" and x["thermal_status"]=="SAFE" for x in candidates),sum(x["best_status"]=="SAFE" for x in candidates)])
    text+=tab(["权限","原代表 HOT 次数","普通恢复 SAFE","普通恢复后温度修正又 HOT","仅在温度步恢复 SAFE","最终保留 SAFE"],transition)
    flips=[x for x in hot if yes(x["safe_then_hot"])]
    distinct={(x["case"],x["source"],x["mapping"]) for x in flips}
    text += [f"在已恢复安全的超温独有映射中，出现 {len(distinct)} 个不同的来源内映射，其普通调频通过 SAFE，随后温度修正再次成为 HOT（合并离线和正式的重复身份）。这种情况下使用已认证的普通调频结果。所有三阶段物理身份、峰温及能耗在独有映射见证表逐项列出。",""]
    if real:
        x=min(real,key=lambda r:float(r["best_J"])-next(float(e["S_J"]) for e in eff if e["case"]==r["case"] and e["source"]==r["source"]))
        text += [f"正式等预算见证来自 {x['case']} 的 {x['source']}。原始 HOT 排程 {num(x['original_J'])} J、{num(x['original_peak'],3)}°C，普通调频为 {x['ordinary_status']}、{num(x.get('ordinary_J'))} J，温度修正为 {x['thermal_status']}、{num(x.get('thermal_J'))} J，最终保留 {num(x['best_J'])} J。",""]
    text+=["## 十二窗指定配置的身份核查","",
        f"完整频率配置摘要为 `{fixture['cfg']}`，物理计划为 `{fixture['original']['plan']}`。原归档全部重复共精确匹配 {fixture['all_scope_matches']} 次，其中本轮两源第一次重复且到点的匹配 {fixture['eligible_matches']} 次。"+
        ("此配置具有本轮真实历史认证身份，其正式入选与否仍取决于预登记排序。" if fixture["eligible_matches"] else "该配置仅作为开发回归夹具，未向正式名单追加名额。"),""]
    text+=tab(["阶段","状态","实测能耗 J","峰温上界 °C","对聊天参照的能耗差 J"],
        [[lbl,fixture[tag]["status"],num(fixture[tag]["J"]),num(fixture[tag]["peak"]),pos(fixture[tag]["J"]-expected)]
         for tag,lbl,expected in (("original","历史配置复算",58.052368),("ordinary","普通调频",57.597755),("thermal","温度修正",57.575511)) if fixture[tag]])
    text+=["## 决策与适用范围",""]
    if hwin==0:
        text+=["正式对照支持优先保留多安全映射再优化。在本批提名规则下，专门为超温来源保留名额没有带来独立胜出。离线全池中的安全恢复另行解释。",""]
    elif len({x["case"] for x in real})<=1:
        text+=["可保留多安全映射再优化。开放超温候选的正式额外收益集中在有限工况；这些见证支持做有针对性的识别诊断，尚不足以证明普遍留出固定比例的名额更好。",""]
    else:
        text+=["在多个工况中出现了同预算下可复核的超温独有节能见证。多安全映射再优化可作为共同路线，构造阶段识别这类有潜力映射具备进一步验证的依据。",""]
    text+=["十二流是已有泛化批次的冻结历史。本轮查的是已有构造结果中已生成的映射以及后处理权限；全池穷尽结论只限实际归档历史，无法推及所有可能映射。原构造时间独立于本次增量时间。","",
        "## 核算与归档",""]
    text+=tab(["阶段","实际核秒","上限"],[[n,num(totals["budgets"][k],3),cap] for k,n,cap in (("gate","恢复与预检",300),("offline","开发流离线全池",1200),("fair","十二流等预算",5760))]+[["合计",num(sum(totals["budgets"].values()),3),7260]])
    st_count=Counter(r["status"] for r in runs)
    text+=[f"共 {len(runs)} 个科研搜索单元（两次离线、48 次正式），其中自然结束 {st_count['NATURAL']}、达到硬墙钟 {st_count['CAP']}。物理证据中有 {totals['unique_physical']} 份不同排程，包含原代表与两阶段输出，按事件块无损保存。全部数组在发布前按 SHA 重组核对。","",
        "[预登记协议](PROTOCOL.md) · [候选与频率身份](archive/identity) · [映射与新增结果配对](analysis/map_stages.csv) · [开发流原调用和新结果](analysis/c10_call_pairs.csv) · [开发流完整排名](analysis/c10_mapping_ranks.csv) · [正式逐流配对](analysis/pairs.csv) · [来源内改善量](analysis/effects.csv) · [热独有见证](analysis/hot_witnesses.csv) · [各次能耗分项](analysis/energy_stages.csv) · [物理证据索引](archive/physical/index.json) · [计时回执](analysis/budget.csv) · [校验清单](SHA256SUMS)。",""]
    text += ["按物理身份恢复单份结果可运行 `python restore.py 排程SHA 新目录`，生成原排程、连续证书和完整 31 列 NPZ 轨迹，同时验证三份内容。历史候选原文件位于冻结 M1-i 各工况 physical.tar.xz 中的 SHA 同名目录。",""]
    env=read(ARCH/"gate_pass.json")
    text += [f"科研代码提交 `{env['source']}`。对跨单元反复送入同一映射的 {totals['shared_matches']} 次完成记录，普通结果、实际引导轨迹及温度修正结果的物理身份均逐项相同。正式候选未入选、已提名及实际交付可从[全部原调用配对账本](analysis/historical_pair_results.csv.gz)核查。",""]
    (ROOT/"REPORT_zh.md").write_text("\n".join(text))
if __name__=="__main__":main()
