"""Build the Chinese chapter report from audited tables with explicit denominators."""
from collections import Counter
from pathlib import Path
import pandas as pd
from audit_results import HERE,ROOT,RESULTS,CASES,MAIN,THERMAL


def fmt(x,n=4):
    return "缺失" if pd.isna(x) else f"{x:.{n}f}"


def md(cols,rows):
    return "\n".join(["| "+" | ".join(cols)+" |","|"+"|".join("---" for _ in cols)+"|",
                      *["| "+" | ".join(map(str,r))+" |" for r in rows]])


def span(xs,n=3):
    s=pd.Series(xs).dropna()
    if s.empty: return "缺失（0/3）"
    return f"{fmt(s.median(),n)} [{fmt(s.min(),n)}, {fmt(s.max(),n)}]（{len(s)}/3）"


def main():
    records=pd.read_csv(RESULTS/"endpoints.csv")
    pos=pd.read_csv(RESULTS/"logical_positions.csv")
    pairs=pd.read_csv(RESULTS/"paired_savings.csv")
    main=pos[pos.comparison=="main"]
    abl=records[(records["mode"]=="T3")&records["method"].isin(["Compact","AB","Proposed"])&records.case.isin(CASES[:4])]
    th=pos[pos.comparison=="thermal"].copy()
    pool=pd.read_csv(RESULTS/"pool_revaluation.csv")
    matched=pd.read_csv(RESULTS/"matched_rounds.csv")
    actual=pd.read_csv(RESULTS/"realized_compensators.csv")
    quality=pd.read_csv(RESULTS/"quality.csv")
    ncomplete=sum(records.receipt=="COMPLETE")
    nsafe=sum(main.status=="SAFE")
    docs=["# 第三章正式实验报告",
        f"六个工况、三个固定种子共登记 165 个运行单元。{ncomplete} 个单元收回完整运行回执，126 个主比较位置中有 {nsafe} 个通过原连续认证并符合计时协议的 SAFE 终点。热实验中的九个 T3 位置各引用同一工况与种子的 Proposed 执行。",
        "## 整体竞争力",
        "各格给出三个种子的完整 SAFE 能耗中位数、范围及有效数，单位为 J。有限种子的观测用于描述本批次表现。",
        md(["方法",*CASES],[[m,*[span(main[(main.case==c)&(main.method==m)].SAFE_J,5) for c in CASES]] for m in MAIN]),
        "节能率按同工况、同种子的完整 SAFE 排程配对计算，分母为基线能耗。正值表示 Proposed 耗能较低。下表单位为 %。",
        md(["基线",*CASES],[[m,*[span(pairs[(pairs.case==c)&(pairs.baseline==m)].savings_pct,3) for c in CASES]] for m in MAIN[:-1]])]
    attempts = pd.read_csv(RESULTS / "execution_attempts.csv")
    interrupted = attempts[attempts.status == "INTERRUPTED"]
    if len(interrupted):
        lost = interrupted.observed_charged_lower_s.sum()
        docs.insert(2, f"本批共启动 {len(attempts)} 次。D1 种子 101 的 {len(interrupted)} 个单元在首次运行时中断，"
                    f"已有 61 个完成回执。按统一恢复规则，这 6 个单元从原候选池重新运行，随后执行尚未启动的 98 个单元。"
                    f"中断日志合计可确认至少 {lost:.1f} 秒已计费时间，包含各单元分摊的原构造时间，实际终止时刻未知。"
                    f"每个登记单元在比较表占一个位置。首次日志、补跑标记和额外耗时见[逐次运行记录](execution_attempts.csv)。")
    ga=pairs[pairs.baseline=="GA"].verdict.value_counts()
    ab=pairs[pairs.baseline=="AB"].verdict.value_counts()
    docs.insert(docs.index("## 整体竞争力")+1,
        f"按同工况、同种子的认证区间比较，Proposed 相对 GA 有 {ga.get('strict_win',0)} 次能耗更低、"
        f"{ga.get('strict_loss',0)} 次更高、{ga.get('same_plan',0)} 次排程完全相同。相对普通邻域 AB，"
        f"对应为 {ab.get('strict_win',0)} 次更低、{ab.get('strict_loss',0)} 次更高、{ab.get('same_plan',0)} 次相同。"
        "GA 用于衡量与全配置基线的整体竞争力，AB 用于衡量引入关键区间反馈后的变化。")
    for c in CASES:
        d=main[(main.case==c)&(main.status=="SAFE")].groupby("method").SAFE_J.median()
        if len(d):
            leaders="、".join(d.index[(d-d.min()).abs()<1e-10])
            docs.append(f"- {c} 的最低方案中位数为 {d.min():.6f} J，由 {leaders} 取得；各方法的有效种子数见上表。".replace("；","，"))
    docs.extend(["构造型文献方法的原始阶段与共同初解回退记录见 [独立构造表](native_construction.csv)。下面统计配置阶段保留的方案来源，同一 SHA 也由本源构造得到时计入本源。",
        md(["方法","本源构造","共同初解","其他来源或无端点"],[[m,
            sum(main.loc[main.method==m,"configuration_source"]=="native"),
            sum(main.loc[main.method==m,"configuration_source"]=="common"),
            sum(~main.loc[main.method==m,"configuration_source"].isin(["native","common"]))] for m in ("Greedy","Adapted-ETA-TS","Adapted-eFLS")]),
        "## 关键执行区间反馈的独立贡献",
        "共同初解、开放规模、配置求解器和时序后处理按冻结协议配对。下表给出相对共同初解的配置阶段节能，以及配置终点到最终解的额外节能，各取有效完整种子的中位数，单位为 mJ。",
        md(["工况","方法","配置阶段","后处理","有效数"],[[c,m,
            fmt(1000*g.config_gain_J.median(),4),fmt(1000*g.post_gain_J.median(),4),f"{len(g)}/3"]
            for c in CASES[:4] for m in ("Compact","AB","Proposed")
            for g in [abl[(abl.case==c)&(abl.method==m)&(abl.status=="SAFE")]]]),
        f"正式批次找到 {len(matched)} 个同前态、同目标、同轮次和同规模的匹配轮次。{len(actual)} 条反馈记录对应实际改变配置的补偿请求；同一请求可在不同种子或轮次出现。".replace("；","，")])
    if len(matched):
        with_extra=matched[matched.extra.notna()]
        docs.append(f"其中 {len(with_extra)} 个匹配轮次实际改变了 AB 邻域之外的补偿请求。{int(with_extra.strict_pro.sum())} 个这样的轮次取得了认证区间严格分离的额外节能。")
        if len(with_extra):
            docs.append(md(["工况","种子","配置轮次（从 1 起）","AB 邻域外实际改动的请求","AB 减 Proposed（mJ）"],
                [[r.case,r.seed,r.turn+1,r.extra,fmt(r.AB_minus_Pro_mJ,3)] for r in with_extra.itertuples()]))
    if len(actual):
        cross=actual[actual.crosses_release_scene==1]
        docs.append(f"{len(cross)} 条实际补偿记录的请求与至少一个目标请求分属不同释放场景。逐项数据包括实际源设备释放的运行时间、目标设备增加的时间，以及虚拟超期缺口。[实际补偿记录](realized_compensators.csv)")
    docs.extend(["图 4 单列冻结 G2 的历史机制证据。D1 种子 101 的第 4 个配置轮次使用相同前态、8 个目标和 12 个开放请求。轻载场景的请求 8、12 均从 NPU 移至 GPU，每个释放 39.6 ms 的 NPU 容量、占用 33.8 ms 的 GPU 时间。反馈试算中最大受阻请求的缺口从 55.2 ms 降至 15.6 ms，第二次补偿后试算总违约归零。真实认证的轮后结果为 AB 9.676590 J、Proposed 9.482367 J，相差 194.222 mJ。该差值属于两个联合排程整体。历史 D1 种子 102 的中断单独保留。",
        "## 热感知贡献",
        "同一工况内，T0、T1、T2、T3 使用同一组非热合法初解候选，各自依据指定规则选择并搜索。表中温度为连续峰温认证上界。能耗与温度按终点真实认证为 SAFE 或 HOT 的排程汇总，HOT 保留原标签。SAFE 比例以三个预登记种子为分母。",
        md(["工况","模式","连续能耗 J","峰温 °C","SAFE","HOT","超出温区","未决","无排程","其余"],[
           [c,m,span(g.loc[g.status.isin(["SAFE","HOT"]),"actual_J"],5),span(g.loc[g.status.isin(["SAFE","HOT"]),"peak_hi"],3),
            *[sum(g.status==s) for s in ("SAFE","HOT","OUT_OF_MODEL","UNRESOLVED","NO_SCHEDULE")],
            sum(~g.status.isin(["SAFE","HOT","OUT_OF_MODEL","UNRESOLVED","NO_SCHEDULE"]))] for c in THERMAL for m in ("T0","T1","T2","T3")
            for g in [th[(th.case==c)&(th["mode"]==m)]]]),
        "下面将同一排程分别按 E35、连续电热和场景重置规则复评，固定排程后即可量出评价本身带来的差别。完整候选并集以每个工况的排程 SHA 去重，各模式的初解 SHA 和终点 SHA 另见逐次结果。",
        md(["工况","池范围","排程数","连续−E35 中位数 J","连续−重置中位数 J","重置 SAFE 且真实 HOT","重置 SAFE 且真实未能认证"],[
         [c,label,len(g),fmt((g.continuous_J-g.E35_J).median(),5),fmt((g.continuous_J-g.reset_J).median(),5),
          int(g.false_safe.sum()),int(g.reset_safe_unverified.sum())] for c in THERMAL for label,mask in [("共同初解",pool.common_initial==1),("搜索候选并集",pool.common_initial>=0)]
          for g in [pool[(pool.case==c)&mask]]])])
    same=0
    same_cfg=0
    compare=0
    paired_modes={m:[] for m in ("T0","T1","T2")}
    from audit_results import plan_for,OUT
    for c in THERMAL:
        for seed in (101,102,103):
            d=th[(th.case==c)&(th.seed==seed)].set_index("mode")
            if d.plan.notna().all() and all(d.receipt=="COMPLETE"):
                compare+=1
                same+=int(d.plan.nunique()==1)
                cfgs={}
                for mode,x in d.iterrows():
                    pl=plan_for(OUT/"cells"/x.id/"evidence",x.plan)
                    cfgs[mode]=tuple(a[:2] for a in pl[0][1::3])
                same_cfg+=int(len(set(cfgs.values()))==1)
                ref=d.loc["T3"]
                for mode,observations in paired_modes.items():
                    alt=d.loc[mode]
                    if alt.status==ref.status=="SAFE":
                        observations.append(dict(same_config=cfgs[mode]==cfgs["T3"],same_plan=alt.plan==ref.plan,
                            delta_mJ=1000*(alt.actual_J-ref.actual_J),alt_lower=alt.actual_hi<ref.actual_lo,
                            t3_lower=ref.actual_hi<alt.actual_lo))
    t2=th[th["mode"]=="T2"]
    docs.append(f"在四种模式均取得完整终点的 {compare} 组种子配对中，{same_cfg} 组最终主阶段配置完全一致，{same} 组完整排程 SHA 也完全一致。T2 有 {sum((t2.selected_status=='SAFE')&(t2.actual_status=='HOT'))} 个最终输出被连续认证判为 HOT。仅凭没有 HOT 的有限样本无法估计其他环境的误判率。")
    mode_rows=[]
    for mode,obs in paired_modes.items():
        mode_rows.append([mode,len(obs),sum(x["same_config"] for x in obs),sum(x["same_plan"] for x in obs),
            fmt(pd.Series([x["delta_mJ"] for x in obs],dtype=float).median(),3),sum(x["alt_lower"] for x in obs),
            sum(x["t3_lower"] for x in obs)])
    docs.extend(["下表在相同工况和种子内，将各模式输出与 T3 配对。能耗差为该模式减 T3，均取最终连续认证能耗。只有两个认证区间严格分离时，才记为一方更低。固定排程复评可直接量出评价规则的影响。各模式独立搜索的终点差异还包含在墙钟预算内实际探索的候选和轮数。",
        md(["模式","SAFE 配对数","主配置相同","完整排程相同","能耗差中位数（mJ）","该模式更低","T3 更低"],mode_rows)])
    safe_peaks=th.loc[th.status=="SAFE","peak_hi"].dropna()
    if len(safe_peaks)==len(th):
        docs.append(f"本批 {len(th)} 个热模式输出的连续峰温上界范围为 {safe_peaks.min():.2f}–{safe_peaks.max():.2f} °C，"
                    f"距离 80 °C 限值至少 {80-safe_peaks.max():.2f} °C。这些工况可以检验温度修正对能耗评价和搜索路径的影响，"
                    "硬温限拦截高温终点的作用仍缺少直接观测。")
    docs.extend(["## 适用边界与解质量",
        "六个实例逐一验证 G1 温度屏障、温度斜率、初始平衡和忙闲功耗差，使用全物理域解析下界 L。U 是主比较最佳 SAFE 排程的认证上端。(U−L)/U 给出相对该方案仍可能节省的比例上限。",
        md(["工况","L（J）","U（J）","U−L（J）","差距上限（%）"],[[r.case,fmt(r.lower_J,6),fmt(r.best_SAFE_upper_J,6),fmt(r.absolute_gap_J,6),fmt(r.gap_pct_of_upper,3)] for r in quality.itertuples()]),
        "图 6 的请求规模和场景顺序随工况共同变化。这些观测适用于 P1 画像、35 °C 环境、原热容、300 ms 期限及本批计算预算。D1 与 D2 可在相同请求总数下比较负载顺序。F1 与 F2 的总请求数和场景组成均有差别。参考目标的搜索穷尽仅涉及相应开放域和参考目标。",
        "## 复核与论文图表",
        "逐次计时、实际种子和原始证书见 [逐次终点](endpoints.csv)、[登记位置](logical_positions.csv)、[同前态匹配轮次](matched_rounds.csv) 与 [逐种子节能率](paired_savings.csv)。向量图、360 dpi PNG 和原始绘图 CSV 位于 [图表目录](figures/)。完整排程、逐事件温度上下界信息、证书、搜索日志、运行回执和构造池见 [原始归档索引](../archive/manifest.json)。",
        "正式执行使用 [冻结协议](../PROTOCOL.md) 和 [参数锁](../execution_lock.json)。重新归档原始文件与 SHA 核对使用 analysis/archive_batch.py，统计及绘图使用 analysis 目录的脚本。"])
    (RESULTS/"report_zh.md").write_text("\n\n".join(docs)+"\n",encoding="utf8",newline="\n")


if __name__=="__main__":
    main()
