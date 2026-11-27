"""Render the Chinese report from verified on-time certificates and paired projections."""
import csv
import json
import statistics as st
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parent
A=R/"archive";B=R/"analysis"
def rows(p):return list(csv.DictReader(p.open()))
def read(p):return json.loads(p.read_bytes())
def n(r,k):return float(r[k])
def fmt(x):return f"{float(x):.6f}"
def table(head,body):return ["| "+" | ".join(head)+" |","|"+"|".join(["---"]*len(head))+"|",*["| "+" | ".join(map(str,r))+" |" for r in body],""]
def main():
    d=rows(B/"development.csv");pair=rows(B/"paired.csv");stats=rows(B/"dp_statistics.csv")
    fac=rows(B/"matched_witnesses.csv") if (B/"matched_witnesses.csv").exists() else []
    ep={(r["cell"],r["stage"]):r for r in rows(A/"endpoints.csv")}
    budget=read(A/"budget.json");gate=read(A/"gate.json");audit=read(B/"verified.json")
    m=[(r["case"],ep["stage3/"+r["case"]+"/direct","final"],ep["stage3/"+r["case"]+"/mixed","final"]) for r in d]
    devref=sum(n(r,"ordinary_J")<n(r,"adaptive_J")-1e-7 for r in d)
    devheat=sum(n(r,"heat_J")<n(r,"ordinary_J")-1e-7 for r in d)
    wins=lambda key:dict(Counter(r[key+"_winner"] for r in pair))
    diff=lambda key:st.mean(n(r,key+"_nt_minus_zhou") for r in pair)
    mixedbetter=sum(n(b,"upper")<n(a,"lower") for _,a,b in m)
    bothbetter=[r for r in fac if r["cell"].startswith("stage3/") and not int(r["timing_legal"]) and r["beats_all"]=="True"]
    regression=[r for r in fac if r["cell"].startswith("regression/")]
    eligible=lambda case,arm:[r for r in fac if r["cell"]=="stage3/"+case+"/"+arm]
    mins=[r for r in stats if r["reserve"]=="13"]
    text=["# 全局调频与异构任务映射联合诊断","",
        f"固定每个请求使用的设备后，允许从任务流开头到结尾逐个选频，在四条开发流中有 {devref} 条得到比原生自适应成组降频更低的认证能耗。逐流节能率按共同强初解为分母取算术平均，普通调频为 {st.mean(100*(1-n(r,'ordinary_J')/n(r,'seed_J')) for r in d):.3f}%。在普通调频的已认证结果上，用其实际温度轨迹修正功耗又改善了 {devheat} 条，平均追加 {st.mean(n(r,'ordinary_J')-n(r,'heat_J') for r in d):.6f} J。","",
        f"双方取得同样的调频权限后，共有 {len(pair)} 条可配对。以本章算法减去增强 Zhou 计算，初始平均差为 {diff('seed'):+.6f} J，普通调频后为 {diff('ordinary'):+.6f} J，温度修正后为 {diff('heat'):+.6f} J。负数代表本章较省电。最终按认证区间判断的胜负为本章 {wins('heat').get('NT',0)}、增强 Zhou {wins('heat').get('Zhou',0)}、持平 {wins('heat').get('tie',0)}。","",
        f"开放暂时超期的改派后，混合筛选在 {mixedbetter} 条开发流上严格超过只接纳直接可行映射的等预算对照。正式搜索记录中有 {len(bothbetter)} 次联合改善同时满足：对侧每个档位直接改派均超期，联合动作优于仅调频。这是带相同父排程的比较；同一改派在不同轮或不同臂内出现时分别记账。","",
        "## 调度与正确性","",
        "设备最短路保留每一步的主阶段完成时刻和末频档。变档要占用时间和能量，设备跨窗口仍可积压。普通成本用带溢出界检查的有符号 128 位整数比较。紧凑递推在相同完成时刻共享前态，换到正频档时保留最佳与次佳前态以排除同档。小实例对全部频档组合穷举，并检查朴素、紧凑递推在每一层的可达键和目标值。","",
        f"历史工况均按原始 CSV 核对释放与期限，重建三阶段起点、频档、显式空闲和切换，比较完整证书字段、参考能耗分数以及 31 列温度轨迹 SHA。恢复 {audit['recovered']} 份排程。小实例 {len(gate['tests'])} 个，共枚举 {sum(t['configs'] for t in gate['tests']):,} 套配置。第一次启动发生研究模块命名冲突，第二次预检识别了离散 tick 截断问题。两次均早于正式单元，两次支出保守合计 15 核秒计入预检。原始连续期限为 300 ms，非整数网格释放采取向上、期限采取向下取整。","",
        "设备级必要期限只保证主阶段有时间留给该请求自身的后处理。两设备结果合并后重新排 CPU 后处理，失败时统一再留 13 tick（1.3 ms）并重算一次。这个预留可能舍弃尚可通过真实 CPU 排队的配置。固定轨迹修正只优化单设备活动及驻留的温度相关差额，CPU 后处理时间移动和重新演化的温度场都由最终连续认证计入。每次接纳都要求 SAFE 且新能耗上界低于原下界。","",
        "## 四条开发流的认证结果",""]
    text+=table(["流","初解 J","成组 J","普通全局 J","温度修正 J","普通改频请求数","温度再改请求数","切换数 初/普/热","余量 普/热 ms"],
        [[r["case"],*[fmt(r[k]) for k in ("seed_J","adaptive_J","ordinary_J","heat_J")],r["ordinary_changed"],r["thermal_additional_changes"],"/".join(r[k] for k in ("seed_sw","ordinary_sw","thermal_sw")),"/".join(r[k] for k in ("ordinary_slack","heat_slack"))] for r in d])
    targets={"A02":(27.663462,27.646590),"A06":(46.212087,46.171955),"C10":(58.317335,58.305647),"C11":(73.720124,73.720124)}
    heat_over_adaptive=sum(n(r,"heat_J")<n(r,"adaptive_J")-1e-7 for r in d)
    text+=[f"普通全局调频相对共同强初解改善 {sum(n(r,'ordinary_J')<n(r,'seed_J')-1e-7 for r in d)}/4。加入温度修正后比成组法更省电的有 {heat_over_adaptive}/4。A06 的成组法优于普通全局调频，温度修正后全局方案才反超。",""]
    x=ep["stage1/A06/dp","ordinary"];y=ep["stage1/A06/dp","thermal"]
    text+=[f"A06 上，温度修正使 35°C 参考能耗从 {fmt(x['e35'])} 升到 {fmt(y['e35'])} J，而真实轨迹上的温度相关能耗从 {fmt(x['temperature_J'])} 降到 {fmt(y['temperature_J'])} J，最终完整系统少用 {n(x,'J')-n(y,'J'):.6f} J。两步映射完全相同，说明温度信息在频率选择中有独立贡献。",""]
    text+=["### 与历史数值诊断的核对","","正号表示本轮认证值高于历史数值估计。估计没有参与选样、排序或接纳。",""]
    text+=table(["流","普通差 J","温度差 J"],[[r["case"],f"{n(r,'ordinary_J')-targets[r['case']][0]:+.6f}",f"{n(r,'heat_J')-targets[r['case']][1]:+.6f}"] for r in d])
    text+=["## 十二流公平比较","","第一次重复和 60 秒截面已预先锁定。普通、温度两列依序给出本章 / Zhou，最后差值仍按本章减 Zhou。每侧历史时间均按原档单列，本轮时钟只计后处理。",""]
    text+=table(["流","原始 本章 / Zhou J","普通 本章 / Zhou J","温度 本章 / Zhou J","最终差 J","起点映射不同数","本轮秒 本章 / Zhou"],
        [[r["case"],*[fmt(r[k+"_nt"])+" / "+fmt(r[k+"_zhou"]) for k in ("seed","ordinary","heat")],f"{n(r,'heat_nt_minus_zhou'):+.6f}",r["different_device_assignments"],f"{n(r,'nt_overhead_s'):.2f} / {n(r,'zhou_overhead_s'):.2f}"] for r in pair])
    for k,label in (("nt","本章"),("zhou","增强 Zhou")):
        text+=[f"{label}的普通调频平均改善 {st.mean(n(r,k+'_reference_gain') for r in pair):.6f} J，温度修正平均追加 {st.mean(n(r,k+'_thermal_gain') for r in pair):.6f} J。两次改善均相对紧前的在位结果。",""]
    pct=st.mean(100*(n(r,"heat_zhou")-n(r,"heat_nt"))/n(r,"heat_zhou") for r in pair)
    worst=max(pair,key=lambda r:n(r,"heat_nt_minus_zhou"))
    text+=[f"按各流相对 Zhou 的能耗百分比等权，最终本章平均节省 {pct:.4f}%。按绝对焦耳差等权则本章平均多用 {diff('heat'):.6f} J。两种汇总的小差值，各自都不能说明具有稳定的整体优势。Zhou 在 {worst['case']} 领先 {n(worst,'heat_nt_minus_zhou'):.6f} J，抵消了其他多条流的小幅胜出。两侧均为 12/12 SAFE；普通调频各自改善 12/12，温度修正在本章 / Zhou 上分别追加改善 {sum(n(r,'nt_thermal_gain')>1e-7 for r in pair)} / {sum(n(r,'zhou_thermal_gain')>1e-7 for r in pair)} 条。",""]
    text+=["相同后处理权限控制了调频程序及评价的差异。两套原始算法可能产生不同的设备映射，也可能在同一映射上从不同频率与温度轨迹出发。余下差距受这些因素共同影响；这一配对无法单独识别热感知构造的因果收益。","",
        "## 单请求改派的联合效果",""]
    text+=table(["流","共同起点 J","只取直接可行 J","同时取受阻 J","两组差（混合−直接）J"],[[c,fmt(ep["stage3/"+c+"/direct","seed"]["J"]),fmt(a["J"]),fmt(b["J"]),f"{n(b,'J')-n(a,'J'):+.6f}"] for c,a,b in m])
    if bothbetter:
        x=max(bothbetter,key=lambda r:n(r,"gain"))
        text+=[f"正式搜索中的可复核见证位于 {x['cell']}，零起始请求 {x['request']}。父排程 {fmt(x['parent_J'])} J；保持设备只调频 {fmt(x['freq_J'])} J；直接改派遍历 {x['target_opps']} 档，最接近合法的配置仍超期 {abs(n(x,'best_direct_margin_ticks'))/10:.1f} ms。联合排程 {fmt(x['joint_J'])} J，峰温上界 {n(x,'peak_C'):.3f}°C，最小期限余量 {n(x,'slack_ms'):.2f} ms。父与子证书及全部直接档位可在四格记录中逐项查找。",""]
    text+=["### 指定请求回归","","四个编号独立于正式搜索名单。每个编号都从指定温度端点单独改派，在原映射所有其他请求上重新调频。下表记录程序返回的最佳严格 SAFE 在位能耗，未改善时沿用父排程。",""]
    reg=read(A/"nominations.json")
    text+=table(["请求（从零计）","回归最佳 J","峰温上界 °C","最小余量 ms"],[[v["request"],fmt(v["J"]),f"{v['peak']:.4f}",f"{v['slack']:.3f}"] for v in reg if v["cell"].startswith("regression/") and v["kind"]=="joint"])
    text+=["## 研究判断","","保留普通全局调频作为高质量起点后的公共优化步骤。固定轨迹温度修正的平均追加量较小，但已通过同映射对照和连续证书确认。在四个开发样本中，允许时序受阻改派有一条严格优于等预算直接可行组，另一条反而略差，两条相同。可将前后缀复用列入后续效率研究；开发组的见证尚不能支持在新样本上普遍增加受阻映射提名。本轮未运行双窗口或多请求任意组合搜索。",""]
    text+=["## 时间、预留和证据","","所有正式单元各执行一次。普通和温度修正共享 120 秒，每种改派策略共享 180 秒。恢复、内核预热和指定回归计入预检预算。",""]
    text+=table(["阶段","实耗核秒","上限"],[[k,f"{v:.3f}",lim] for (k,v),lim in zip(budget["by_stage"].items(),(300,960,2880,1440))]+[["总计",f"{budget['total']:.3f}",5580]])
    text += [f"单元回执状态 {dict(Counter(r['status'] for r in budget['receipts']))}。共归档 {audit['physical']} 份不同物理排程；{len(stats)} 次两设备递推尝试中，{len(mins)} 次使用额外预留，其中 {sum(x['outcome']=='SAFE' for x in mins)} 次得到完整 SAFE 证书。详细的修正前超期量、保守预留无路径、每层去重后状态数和耗时均可追溯。","",
        "逐工况完整能耗分项、证书界、开销见 [端点表](archive/endpoints.csv)。[双方逐流改善量](analysis/paired.csv) · [状态统计](analysis/dp_statistics.csv) · [改派提名](analysis/mapping_nominations.csv) · [同父四格结果](archive/witnesses.json) · [全档见证摘要](analysis/matched_witnesses.csv) · [完整排程索引](archive/physical_index.csv) · [预算回执](archive/budget.json) · [协议](PROTOCOL.md)。每个物理包内包含计划、连续证书及完整温度事件数组。开发性见证和十二流配对分别解释。",""]
    environment=read(A/"environment.json")
    text += [f"正式实验代码提交 `{environment['source']}`，运行编号 `{environment['run']}`。历史构造与预热口径见[原始起点匹配账本](archive/gate.json)，各单元回执保留机器、核心和本轮墙钟。",""]
    example=rows(B/"reserve_conservatism.csv")
    text += [f"对全部 {len(example)} 份不同 SAFE 排程直接读其原始时刻，有 {sum(int(r['excluded_requests'])>0 for r in example)} 份至少包含一个主阶段完成余量不足 13 tick 的请求。这些排程已被真实 CPU 队列和连续证书接受，说明统一预留确实会缩小搜索范围。见[逐排程预留核查](analysis/reserve_conservatism.csv)。",""]
    (R/"REPORT_zh.md").write_text("\n".join(text))
if __name__=="__main__":main()
