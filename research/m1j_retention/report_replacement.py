"""Write the Chinese report from this replacement batch's audited tables."""
import csv
import gzip
import json
from itertools import product

from paths_j import DATA, METHODS, ROOT, inputs
from analyze_replacement import CUTS, PAIRS

RUN = "45928467468"
GIT = "https://github.com/YBEMR/paper"
AU = f"{GIT}/commit/60c8440acb8f712654630fb62ae9fe5ac86f59de"
RUNTIME = f"{GIT}/actions/runs/{RUN}"
RELEASE = f"{GIT}/releases/tag/m1j-replacement-{RUN}"


def read(file):
    path=DATA/file
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"rt",encoding="utf8",newline="") as f:
        return list(csv.DictReader(f))


def f(x,d=3,signed=False):
    if x in (None,""):
        return "—"
    return format(float(x),("+" if signed else "")+f".{d}f")


def table(header,rows):
    lines=["| "+" | ".join(header)+" |","|"+"|".join("---" for _ in header)+"|"]
    lines.extend("| "+" | ".join(map(str,row))+" |" for row in rows)
    return "\n".join(lines)


def save(name,parts):
    (ROOT/name).write_text("\n\n".join(parts)+"\n",encoding="utf8")


def examples(lineage, paired):
    selected=[]
    definitions=[
        ("热风险下，互补保留的胜例","NT","NT-S","win"),
        ("热风险下，综合前四的胜例","NT-S","NT","loss"),
        ("终局能耗相同或区间重叠","NT","NT-S","tie"),
        ("普通负载风险下互补保留的路径","NC","NC-S","win"),
    ]
    for title,arm,other,outcome in definitions:
        pair=("NT","NT-S") if arm.startswith("NT") else ("NC","NC-S")
        cases={r["case"]:r for r in paired if r["regime"]=="60s" and (r["left"],r["right"])==pair
               and r["result"]==outcome}
        matches=[]
        for row in lineage:
            if row["case"] not in cases or row["method"]!=arm or row["role"]!="best60" or row["source_W4"]!="kept":
                continue
            score_seat=row["scalar_seat"] if arm.endswith("-S") else row["complementary_seat"]
            alternative=row["complementary_seat"] if arm.endswith("-S") else row["scalar_seat"]
            direct=(score_seat not in ("","0") and alternative=="0")
            if outcome!="tie" and not direct:
                continue
            observed=row["other_W4"]=="pruned_in_pool"
            specific=not arm.endswith("-S") and row["complementary_seat"] in ("1","3")
            matches.append(((not observed,not direct,not specific,
                            -abs(float(cases[row["case"]]["saving_pct"])),row["case"],int(row["repeat"]),int(row["window"])),row))
        if not matches:
            selected.append("**"+title+"**。本批 60 秒赢家中，没有同时满足上述胜负和同池换席条件的实例。")
            continue
        _,row=min(matches,key=lambda v:v[0])
        pairrow=cases[row["case"]]
        comp,scalar=int(row["complementary_seat"]),int(row["scalar_seat"])
        action=row["action"]
        form={"kept":"另一方法的实际 W4 也保留了该候选","pruned_in_pool":"另一方法的实际 W4 生成后剪除了该候选",
              "parent_not_kept":"另一方法的实际 W4 在更早窗口已经放弃其父路径",
              "missing_under_kept_parent":"另一方法的实际 W4 保留了父路径，但合法池中未发现该候选",
              "W4_ended_before_window":"另一方法的 W4 在这个窗口前结束"}[row["other_W4"]]
        seat_names={0:"淘汰",1:"能耗席",2:"排空席",3:"风险席",4:"综合席"}
        selected.append(f"**{title} · {row['case']}**。第 {row['repeat']} 次的 {arm} 最佳证书来自 W{row['width']}，"
          f"第 {row['window']} 窗配置动作（GPU 档 / NPU 档 / 两类配额）为 {action}。在该方法实际 W4 的候选池中，"
          f"此前缀的参考能耗为 {f(row['reference_E_J'],5)} J，能耗、排空、风险的零基名次分别为 "
          f"{row['energy_rank']}、{row['drain_rank']}、{row['risk_rank']}。同池按互补规则为{seat_names[comp]}，按综合排序"
          + (f"列第 {scalar} 席。" if scalar else "被淘汰。")
          + f"{form}。该次后代排程通过连续认证，完整能耗 {f(row['terminal_E_J'],5)} J，峰温上界 {f(row['terminal_peak_C'])}°C。"
          f"工况配对节能率（{pair[0]} 相对 {pair[1]}，三次成功重复中位数）为 {f(pairrow['saving_pct'],3,True)}%。"
          f"前缀 `{row['prefix']}`，终端计划 `{row['plan']}`。")
    return selected


def main():
    receipt=json.loads((DATA/"batch_receipt.json").read_bytes())
    vp=json.loads((DATA/"paths/verification.json").read_bytes())
    med=read("medians.csv")
    pair=read("paired_cases.csv")
    interactions=read("interactions.csv")
    gcon=read("group_contrasts.csv")
    gcov=read("group_coverage.csv")
    gint=read("group_interactions.csv")
    lineage=read("paths/lineage.csv.gz")
    cases=inputs()
    def contrast(cut,a,b,group="all"):
        return next(r for r in gcon if (r["group"],r["regime"],r["left"],r["right"])==(group,cut,a,b))
    def cover(cut,m,group="all"):
        return next(r for r in gcov if (r["group"],r["regime"],r["method"])==(group,cut,m))
    def inter(cut,group="all"):
        return next(r for r in gint if (r["group"],r["regime"])==(group,cut))
    def cw(r):
        return f"{r['win']}/{r['tie']}/{r['loss']}，{f(r['mean_pct'],3,True)}%（{r['paired']}）" if r["paired"]!="0" else "共同可靠 SAFE 0"
    def energy(r):
        return (f(r["SAFE_J"],4) if r["SAFE_J"] else "—")+f"（{r['n_SAFE']}/3）"
    cov60=" / ".join(cover("60s",m)["reliable"] for m in METHODS)
    nt, nc=contrast("60s","NT","NT-S"),contrast("60s","NC","NC-S")
    ix=inter("60s")
    report=["# M1-j　热感知互补式前缀保留的收束验证",
      f"四种方法在 12 条公开任务流上完成 144 次同批计时。60 秒时，NT / NT-S / NC / NC-S 分别在 **{cov60}** 条流上可靠取得 SAFE。"
      f"热风险下用互补保留代替综合前四，共同可靠 SAFE 的 {nt['paired']} 条流平均节能 **{f(nt['mean_pct'],3,True)}%**；普通负载风险下，"
      f"对应的 {nc['paired']} 条流平均节能 **{f(nc['mean_pct'],3,True)}%**。正值表示互补保留更省能。"
      f"在四格均可靠成功的 {ix['four_safe']} 条流上，平均能耗交互为 **{f(ix['mean_interaction_J'],4,True)} J**，"
      f"逐流按 NC-S 能耗归一的平均交互为 **{f(ix['mean_interaction_pct'],3,True)}%**。",
      f"[逐工况配对](paired_results.md) · [路径审计](path_examples.md) · [逐次原始证书与排程](data/evidence) · [完整逐事件卷]({RELEASE}) · [计时批次]({RUNTIME})",
      "## 文献对照与实验设计",
      "Maity 等在 RTSS 2022 论文第 403–404 页的定义 6 和算法 3 中，将时延余量与热余量加权得到统一适应度，各层按分数降序保留前 W 个。"
      "NT、NC 在每个非终端窗口依次给参考能耗、排空时间、对应风险、综合名次各一席，每次从剩余候选选择。NT-S、NC-S 则按同一个综合键取前四。"
      "综合键使用相同三个经验名次之和，每项名次为严格更优候选数；并列处理、剩余席参考能耗回填、N 生成器、FIFO、热模型、扩束、终端排序和连续认证均来自冻结代码。"
      "NT 与 NT-S 用主动热风险，NC 与 NC-S 用普通负载风险。本实验定位为受 F-DTM 启发的同核机制比较。"
      "论文的方法差异最多支持具体机制的辨析；首创性还需要更广的文献证据。[论文 DOI](https://doi.org/10.1109/RTSS55097.2022.00041) · [逐项原文与源码核查](RETENTION_AUDIT.md)",
      "两批结果分开保存。本报告的全部成绩来自用户授权的替代批，使用 M1-i 的 12 条 35°C 输入。每通道使用一台独立 GitHub Linux 运行机并固定到一个逻辑核，"
      "同流四种方法及三次重复在同机同核运行。六条通道选用六台运行机，原协议则在同一主机固定六核。每台负责两条流，"
      "三次重复测量的是墙钟波动；独立的统计单位为任务流。原会话截图报告的 33,286 份认证不计入本表。[替代批登记](replacement/PROTOCOL.md) · [各机环境](data/environment)",
      "## 固定束宽与共同墙钟",
      "可靠成功指三次中至少两次按时取得 SAFE。各方法先取该流成功重复的中位能耗，按两方能耗区间是否分离判胜负。"
      "节能率分母为右边方法的能耗，各流等权。括号给出共同可靠成功的流数。W4/K4 取 W4 阶段前四份按时完成的证书，同一轨迹也提供 10、30、60 秒截面。",
      table(["截面","可靠 SAFE：NT / NT-S / NC / NC-S","NT 对 NT-S：胜/平/负，平均节能","NC 对 NC-S","NT 对 NC","NT-S 对 NC-S"],
            [[cut," / ".join(cover(cut,m)["reliable"] for m in METHODS),
            *[cw(contrast(cut,a,b)) for a,b in PAIRS[:4]]] for cut in CUTS]),
      "## 四格共同分母上的独立贡献与交互",
      "同一流先算热风险下的互补收益 T = E(NT-S) − E(NT)，以及普通风险下的互补收益 C = E(NC-S) − E(NC)。"
      "互补主效应取 (T+C)/2。热风险主效应取两个保留策略下普通风险改用热风险后的平均能耗下降。"
      "能耗交互 T−C 为正，表示互补保留的节能幅度在主动热风险下更大。覆盖交互对全部 12 条流的可靠成功指示作相同差分，表中给出条数净和。"
      "能耗交互仅对四格均可靠成功的流有定义。正/交零/负按照每流四项能耗数值界保守相加后的区间判定，这些界限衡量数值误差，不能替代跨流统计置信区间。",
      table(["截面","四格共同 SAFE","互补主效应 J","热风险主效应 J","能耗交互 J","交互/NC-S %","正/交零/负","覆盖交互（条）"],
            [[cut,inter(cut)["four_safe"],*[f(inter(cut)[k],4,True) for k in ("mean_retention_main_J","mean_thermal_main_J","mean_interaction_J","mean_interaction_pct")],
               "/".join(inter(cut)[k] for k in ("positive","overlap_zero","negative")),inter(cut)["coverage_sum"]] for cut in CUTS]),
      f"60 秒的能耗交互在共同成功的流中分布为 {ix['positive']} 正、{ix['overlap_zero']} 个区间含零、{ix['negative']} 负。"
      f"按流归一后的中位交互为 {f(ix['median_interaction_pct'],3,True)}%。四格均成功的子集可能排除风险最大、最难取得首解的流，"
      "应同时报告覆盖差异和具体败例。[逐流四格交互](data/interactions.csv) · [同编号重复交互](data/interactions_repeats.csv)",
      "## 长度与负载结构",
      table(["60 秒分组","流数","可靠 SAFE：NT / NT-S / NC / NC-S","NT 对 NT-S","NC 对 NC-S","四格共同 SAFE","平均交互 J"],
            [[g,cover("60s","NT",g)["flows"]," / ".join(cover("60s",m,g)["reliable"] for m in METHODS),
              cw(contrast("60s","NT","NT-S",g)),cw(contrast("60s","NC","NC-S",g)),inter("60s",g)["four_safe"],
              f(inter("60s",g)["mean_interaction_J"],4,True)] for g in ("A","B","C")]),
      "A 组含 6 条常规等量轻重窗流，B 组含 2 条非等量流，C 组含 4 条长流。以下能耗为 60 秒成功重复的中位数，括号内给出成功重复数。",
      table(["长流","请求数",*METHODS],
            [[c["case"],c["requests"],*[energy(next(r for r in med if (r["case"],r["method"],r["regime"])==(c["case"],m,"60s"))) for m in METHODS]]
             for c in cases if c["group"]=="C"]),
      "## 证书、预算与论文定位",
      f"替代批共发出 {receipt['calls']:,} 份连续证书，{receipt['ontime']:,} 份按时完成，{receipt['late']:,} 份跨截止。"
      f"共有 {receipt['unique_plans']:,} 个工况内不同物理排程。144 条轨迹的比较预算为 8,640 单核秒，实测循环停止时间总和 {receipt['measured_wall_sum_s']:.3f} 秒，"
      f"W4 截面少于四份按时证书的轨迹有 {receipt['fixed_under_four']} 条。与冻结 M1-i 的两种原方法共核过 {receipt['historical_checked']} 份固定证书，"
      f"其中 {receipt['historical_same_plan']} 份计划身份一致、{receipt['historical_same_status']} 份认证状态一致，能耗最大绝对差 {receipt['maximum_historical_energy_difference_J']:.3g} J。"
      "逐次原件、同一计划各次认证耗时以及失败状态保留在每工况证据包中。[预算回执](data/batch_receipt.json) · [逐证书冻结对照](data/historical_fixed.csv) · [调用明细](data/calls.csv.gz) · [576 个截面与 12 次物理重放核验](data/verification.json) · [各事件卷校验值](data/event_volumes.csv)",
      "本轮至此结束 NT 机制消融，进入论文章节定位与成果整理。正文以有限墙钟下的跨窗热状态、可行覆盖和已认证完整系统能耗为主线。"
      "互补保留的独立收益和与热风险的交互按上表的分母、方向及反例陈述。适用范围限于冻结 P1 画像和这 12 条已公开诊断任务流。"]
    save("README.md",report)
    rows=[]
    for c,cut in product(cases,CUTS):
        sample=[r for r in med if r["case"]==c["case"] and r["regime"]==cut]
        j=next(r for r in interactions if r["case"]==c["case"] and r["regime"]==cut)
        v=[]
        for a,b in PAIRS[:4]:
            p=next(r for r in pair if (r["case"],r["regime"],r["left"],r["right"])==(c["case"],cut,a,b))
            label={"win":"胜","tie":"平","loss":"负","only_left":"仅左 SAFE","only_right":"仅右 SAFE","neither":"双方未可靠 SAFE"}[p["result"]]
            v.append(label+(" "+f(p["saving_pct"],3,True)+"%" if p["saving_pct"] else ""))
        rows.append([c["case"],cut,*[energy(next(r for r in sample if r["method"]==m)) for m in METHODS],*v,f(j["interaction_J"],4,True)])
    save("paired_results.md",["# 逐工况四方法配对","单位为 J。括号为三次重复中的 SAFE 次数，达两次方计可靠成功。表中百分比分母为右侧方法。"
         "数值精度更高的原始上下界、峰温、期限余量和首解时间见 CSV。[逐重复四截面](data/repetitions.csv) · [逐工况中位数](data/medians.csv) · [全部六对](data/paired_cases.csv) · [同编号重复](data/paired_repeats.csv)",
         table(["流","截面",*METHODS,"NT/NT-S","NC/NC-S","NT/NC","NT-S/NC-S","交互 J"],rows)])
    save("path_examples.md",["# 实际保留与剪除的前缀",
         f"对四种方法的 48 个 W4 构造逐窗执行同池换席，核对 144 个在线 W4 阶段的父身份及固定认证顺序。"
         f"{vp['W4_pool_observations']} 个有候选的非终端池中，{vp['different_sets']} 个因规则改变而更换了入选四席集合。"
         f"共记录 {vp['candidates']:,} 次候选观察。对固定证书及 60 秒最佳证书逐次追溯，验证 {vp['verified_prefix_links']:,} 个真实祖先与实际产生它的束宽。"
         "逐窗池记录含候选及父身份、动作、风险、能耗、名次和两套座次。一个池在不同方法下出现可计作多次观察。",
         *examples(lineage,pair),
         "实例按实际 60 秒工况胜负和最佳证书筛选，优先展示对方也生成后剪除的候选，再优先分项席。"
         "同池换席定位局部剪枝。更宽束搜索、后续保留与终端认证机会也会影响最终成绩；个例不足以将全部终局能耗差归给一个窗口。"
         "[各工况全池](data/paths) · [逐祖先去留与证书对应](data/paths/lineage.csv.gz) · [核验回执](data/paths/verification.json)"])


if __name__=="__main__":
    main()
