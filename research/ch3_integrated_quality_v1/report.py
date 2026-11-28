"""Render the preregistered decision from audited physical intervals and matched times."""
import csv
import json
import statistics as st
from pathlib import Path
ROOT=Path(__file__).resolve().parent
T=ROOT/"tables"
def rows(p):
    with (T/p).open(newline="") as f:return list(csv.DictReader(f))
def v(x,p=6):return "—" if x=="" or x is None else f"{float(x):.{p}f}"
def nums(rs,k):return [float(r[k]) for r in rs if r[k] not in ("",None)]
def avg(rs,k):
    x=nums(rs,k);return st.mean(x) if x else None
def md(rs,k):
    x=nums(rs,k);return st.median(x) if x else None
def tab(h,vals):
    return ["| "+" | ".join(h)+" |","|"+"|".join("---" for _ in h)+"|",*["| "+" | ".join(map(str,r))+" |" for r in vals],""]
def main():
    d=json.loads((T/"decision.json").read_bytes());f=rows("flows.csv");a=rows("runs.csv");pairs=rows("paired_repeats.csv");hist=rows("historical_diagnostic.csv")
    arms={k:[r for r in a if r["version"]==k] for k in ("original","integrated")};post=arms["integrated"]
    decision="采用集成版" if d["adopt"] else "保留原版"
    text=["# 第三章高质量调度算法首轮集成决策","",f"**建议{decision}。** 两个版本都从空排程开始，各自最多用 60 秒。原版可靠交付安全排程的任务流有 {d['reliable']['original']}/12，集成版有 {d['reliable']['integrated']}/12。在 {d['common']} 条共同可靠任务流上，集成版完整系统能耗的平均节能率为 {v(d['mean_saving_pct'],4)}%，平均每流节省 {v(d['mean_saving_J'])} J。按三次重复的中位能耗及证书区间，集成版严格胜 {d['win']} 条、区间重叠 {d['tie']} 条、严格负 {d['loss']} 条。","",
        "原版把搜索时间都用于继续尝试任务分配和频档。集成版先让同一搜索给出已认证的安全方案，再固定每个请求使用的设备，从头到尾重新选择频档。随后利用当前安全方案的实际温度轨迹再选一次。三阶段都按完整系统能耗决策，一旦候选超温、超期、超时或认证能耗未严格改善，仍可交付之前的安全方案。","",
        "## 完整路线的等预算比较","",
        "一个任务流在三次运行中至少两次按时获得 SAFE 即为可靠成功。主指标先按流对各自成功重复取中位数，再将各流等权平均；节能率分母为原版。中位数上下界分别从各重复认证下界、上界取中位数。转为运行序号配对的结果另列。",""]
    text+=tab(["任务流","SAFE 次数 原／集","原版中位 J","集成版中位 J","节省 J","节能率 %","严格判定"],
        [[r["case"],r["original_safe"]+" / "+r["integrated_safe"],v(r["original_J"]),v(r["integrated_J"]),v(r["gain_J"]),v(r["gain_pct"],4),
          {"win":"集成胜","tie":"区间重叠","loss":"原版胜","unpaired":"无可靠配对"}[r["strict"]]] for r in f])
    lost=[r["case"] for r in f if int(r["original_safe"])>=2 and int(r["integrated_safe"])<2]
    gained=[r["case"] for r in f if int(r["original_safe"])<2 and int(r["integrated_safe"])>=2]
    text += [f"按已登记的三个条件，可靠覆盖由 {d['reliable']['original']} 变为 {d['reliable']['integrated']}，共同流平均节能率为 {v(d['mean_saving_pct'],4)}%，严格胜出 {d['win']}/{d['common']}。原版可靠而集成版失去可靠覆盖的流有 {len(lost)} 条，反向新增 {len(gained)} 条。",""]
    counts=lambda a,k:sum(r["strict"]==k for r in a)
    text += [f"全部三次均成功的流数为原版 {d['full_success']['original']}/12、集成版 {d['full_success']['integrated']}/12。36 个同流同编号重复配对中，集成版严格胜 {counts(pairs,'win')} 次、区间重叠 {counts(pairs,'tie')} 次、严格负 {counts(pairs,'loss')} 次、无法配对 {counts(pairs,'unpaired')} 次。这个重复层面的计数只作补充。",""]
    text+=["## 同一起点的阶段收益","",
        f"集成版有 {sum(r['search_cut']=='55' for r in post)}/36 次按短构造路线进入交接条件，{sum(r['ordinary_delivered']=='True' for r in post)} 次交付普通阶段结果，{sum(r['thermal_delivered']=='True' for r in post)} 次交付温度阶段结果。其余未交付阶段沿用最近安全在位解；原始提名的状态单列。",""]
    s=[]
    for name,k,en,rawstat in (("普通全局调频","ordinary_gain_J","ordinary_J","ordinary_raw_status"),("温度修正追加","thermal_gain_J","thermal_J","thermal_raw_status")):
        vals=nums(post,k)
        s.append([name,len(vals),sum(x>0 for x in vals),v(avg(post,k)),v(md(post,k)),sum(r[rawstat]=="HOT" for r in post)])
    text+=tab(["机制","有安全基准次数","严格节能次数","平均节省 J","中位节省 J","原始提名 HOT 次数"],s)
    text+=["逐流下表均为同一路线的三次重复；能耗列为各阶段在位能耗中位数，收益列先在每次运行内相减再取均值。不同独立运行的构造排程可能不同。",""]
    text+=tab(["流","构造终点 J","普通终点 J","温度终点 J","普通平均节省 J","温度平均追加 J"],
        [[r["case"],*[v(fn([q for q in post if q["case"]==r["case"]],k)) for fn,k in ((md,"search_J"),(md,"ordinary_J"),(md,"thermal_J"),(avg,"ordinary_gain_J"),(avg,"thermal_gain_J"))]] for r in f])
    text+=["## 首次交付、温度、期限及求解开销","","首个 SAFE 和最终最优方案的交付时刻均从本次起表，含实例准备。峰温使用连续证书上界。下表对每种方法的成功重复汇总；最紧余量和最高峰另外报告。",""]
    text+=tab(["版本","首次 SAFE 中位 s","最终最优交付中位 s","最高峰温 °C","最小期限余量 ms","切换中位数"],
        [[{"original":"原版","integrated":"集成版"}[arm],v(md(x,"first_safe_s"),3),v(md(x,"final_best_delivered_s"),3),v(max(nums(x,"peak"),default=None),3),
          v(min(nums(x,"slack"),default=None),3),v(md(x,"switches"),1)] for arm,x in arms.items()])
    text+=["下表是每次运行的平均墙钟秒数。搜索认证列包括相应 FIFO 重放、连续认证与原生证据写盘。调频认证列包括建物理事件、连续认证与写盘。已完成证书的纯连续积分时间为嵌套观测，不再加到总时间。其余列含进程及日志、时序预筛、未完成调频等未归入前列的时间。",""]
    text+=tab(["版本","建实例","构造","搜索重放认证留档","交接","已完成 DP","调频认证留档","其余","总计","其中完成的连续积分"],
        [[{"original":"原版","integrated":"集成版"}[arm],*[v(avg(x,k),3) for k in ("instance_s","construct_s","search_replay_cert_evidence_s","handoff_s","dp_s","refine_cert_evidence_s","other_s","delivery_s","completed_cert_kernel_s")]] for arm,x in arms.items()])
    decomposition=rows("decomposition.csv");losses=[q for q in decomposition if q["strict"]=="loss"]
    if losses:
        text += [f"在 {len(losses)} 次同编号严格失利中，集成版构造终点比原版 60 秒终点平均多耗 {-avg(losses,'original60_minus_integrated_search_J'):.6f} J，随后普通调频平均追回 {avg(losses,'ordinary_gain_J'):.6f} J，温度修正再追回 {avg(losses,'thermal_gain_J'):.6f} J。两条独立构造轨迹的起点差包含计时波动及搜索机会差，不能全部归因于预留五秒。见[逐次能耗差分解](tables/decomposition.csv)。",""]
    original=arms["original"]
    text+=["## 搜索最后五秒与历史截面","",
        f"本轮原版同一条搜索轨迹从第 55 秒继续至第 60 秒，有 {sum(x>0 for x in nums(hist,'native_55_to_60_gain_J'))} 次进一步改善，在两个截面均有 SAFE 的 {len(nums(hist,'native_55_to_60_gain_J'))} 次中平均减少 {v(avg(hist,'native_55_to_60_gain_J'))} J。集成版的阶段收益与这项搜索机会分别报告。冻结泛化批次的 60 秒结果作为历史参照写入独立表，其实例装载口径及运行环境不能替代本轮等预算比较。","",
        "## 证据及复核","",
        f"正式 {d['cells']} 个单元合计 {d['charged_core_s']:.3f} / 4320 核秒；十二台单流运行环境的通用预热合计 {d['warmed_s']:.3f} 秒，独立接口预检（含其机器预热）{d['preflight_s']:.3f} 秒，离线压缩核验合计 {d['offline_pack_s']:.3f} 秒。每流两种方法、三个重复在同一台机器的同一个逻辑核串行执行；轮换表及环境信息保存在各流 lane.json 中。跨流并行只用于组织独立样本。","",
        f"保存了按流去重的 {d['physical']:,} 个物理排程、连续证书和可无损恢复的 31 列事件数组。所有计入的证书先核对排程 SHA、证书上下界、分项能耗、温度、余量与切换数，再对物理证据块重组验 SHA。绝对截止上的进行中计算由定时器中止；截止后监督清理的墙钟单独保留。","",
        f"正式科研提交 `{d['source']}`。单份证据可用 `python evidence.py 流编号 排程SHA 新目录` 离线恢复。","",
        "[冻结协议](PROTOCOL.md) · [逐次结果与物理量](tables/runs.csv) · [十二流配对](tables/flows.csv) · [实际阶段端点](tables/stages.csv) · [同编号重复](tables/paired_repeats.csv) · [时间回执](tables/timing_receipts.csv) · [历史截面诊断](tables/historical_diagnostic.csv) · [完整证据](archive) · [SHA-256 清单](SHA256SUMS)。",""]
    (ROOT/"REPORT_zh.md").write_text("\n".join(text))
if __name__=="__main__":main()
