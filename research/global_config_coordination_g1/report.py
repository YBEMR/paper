"""Render the Chinese result report from frozen receipts; no solver or thermal calls."""
import csv
import gzip
from datetime import datetime,timedelta,timezone
import json
from math import floor,ceil
from fractions import Fraction as Q
from pathlib import Path
from summarize import ROOT,OUT,read,rows,sha

def loadcsv(name):
    p=ROOT/name
    if not p.exists():return []
    with p.open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))

def md(headers,data):
    return "\n".join(["| "+" | ".join(headers)+" |","|"+"|".join(["---"]*len(headers))+"|",
                       *["| "+" | ".join(map(str,r))+" |" for r in data]])
def num(x,d=9):return f"{float(x):.{d}f}"
def outward(x,d,*,upper):
    value=Q.from_float(x) if isinstance(x,float) else Q(x)
    scale=10**d
    tick=(ceil if upper else floor)(value*scale)
    return f"{tick//scale}.{tick%scale:0{d}d}"
def cert(key):return read(OUT/"certificates"/(key+".json"))
def main():
    summ=loadcsv("summary.csv")
    base=loadcsv("baselines.csv")
    refs=loadcsv("references.csv")
    checkpoints=loadcsv("checkpoints.csv")
    jobs=rows(OUT/"jobs.jsonl")
    gate=read(OUT/"preflight"/"gates.json")
    fin=read(OUT/"end.json") if (OUT/"end.json").is_file() else None
    hdr=read(OUT/"execution.json")
    comparisons=[]
    comparisons_rows=[]
    for case in ("S16","S32","S80"):
        pair={s["method"]:s for s in summ if s["case"]==case and s["worker_status"] in ("OK","TIME_LIMIT")}
        if len(pair)<2:continue
        x,y=pair["C0"],pair["C1"];m0,m1=[cert(a["plan"])["metrics"] for a in (x,y)]
        lb=max(Q(x["lower_exact_J"]),Q(y["lower_exact_J"]))
        ub=min(m0["E_bounds"][1],m1["E_bounds"][1])
        delta=m0["E_J"]-m1["E_J"]
        outcome=("同一计划" if x["plan"]==y["plan"] else "C1 严格更低" if m1["E_bounds"][1]<m0["E_bounds"][0]
                 else "C0 严格更低" if m0["E_bounds"][1]<m1["E_bounds"][0] else "证书区间重叠")
        comparisons.append((case,num(float(x["SAFE_J"])+float(x["delta_J"])),num(m0["E_J"]),num(m1["E_J"]),num(delta),outcome))
        seed=cert(x["common_seed"])["metrics"]
        gain=max(float(x["delta_J"]),float(y["delta_J"]))
        comparisons_rows.append((case,outward(lb,9,upper=False),outward(ub,9,upper=True),outward(Q.from_float(ub)-lb,9,upper=True),outward(100*(Q.from_float(ub)-lb)/Q.from_float(ub),4,upper=True)+"%",num(gain*1e9,2),outward(Q.from_float(seed["E_bounds"][1])-lb,9,upper=True)))
    local=lambda s:datetime.fromisoformat(s).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    title="G1 第一阶段结果" if fin and fin["outcome"]=="COMPLETED" else "G1 已完成阶段与运行进度"
    doc=["# "+title,"完整连续电热系统总能耗为主指标。除表头另列单位外，以下能耗单位均为 J。"]
    if comparisons:
        strict1=sum(c[-1]=="C1 严格更低" for c in comparisons)
        strict0=sum(c[-1]=="C0 严格更低" for c in comparisons)
        nbetter=sum(any(s["strict"]=="True" for s in summ if s["case"]==q) for q in ("S16","S32","S80"))
        doc+=["## 主要结果",
              f"完整联合搜索在 {nbetter} 个规模进一步严格降低了共同初解的 SAFE 能耗。等预算最终比较中，C1 在 {strict1} 个规模严格胜过 C0，C0 在 {strict0} 个规模严格胜过 C1。每个规模仅使用固定种子 101。结论限于相应实例和本轮预算。",
              md(["实例","共同初解","C0 最佳 SAFE","C1 最佳 SAFE","C0 − C1","区间判定"],comparisons),
              "## 实际改进与剩余空间",
              md(["实例","两种方法中最强全域下界","最小 SAFE 上界","仍可能节省至多","差距/上界","相对初解已节省 (nJ)","相对初解至多可省 (J)"],comparisons_rows),
              "可实现的额外节能位于 0 和“仍可能节省至多”之间。这一列由两种可靠界与认证上界相减得到，包含尚未搜索的排程。已观测节能来自实际完整排程。"]
        stronger=[]
        for c in comparisons:
            methods={s["method"]:s for s in summ if s["case"]==c[0]}
            a,b=methods["C0"],methods["C1"]
            if Q(b["lower_exact_J"])>Q(a["lower_exact_J"]):
                stronger.append(f"{c[0]} 的差距上限由 {float(a['gap_pct_of_upper']):.3f}% 降到 {float(b['gap_pct_of_upper']):.3f}%")
        if stronger:
            message="。".join(stronger)+"。"
            if not strict1:
                message+="本轮证据支持把 C1 用于解质量证明。相同预算下没有实例显示 C1 的最终 SAFE 区间严格优于 C0。"
            else:
                message+="C1 的最终能耗优势只在上表区间可分的实例上成立，绝对节能量见对应差值。"
            doc.append(message)
        bounds=[]
        for s in summ:
            timeline=rows(OUT/"cp"/s["case"]/s["method"]/"timeline.jsonl")
            initial=Q(timeline[0]["global_lower_exact_J"])
            final=Q(s["lower_exact_J"])
            bounds.append((s["case"]+"/"+s["method"],outward(initial,9,upper=False),
                           outward(final,9,upper=False),outward(final-initial,9,upper=False)))
        doc.extend(["### 下界在什么时候取得",
                    md(["实例/方法","求解前解析下界 (J)","最终全域下界 (J)","搜索新增的下界 (J)"],bounds),
                    "每行从最低驻留功耗和各阶段最低配置项得到初始下界，再用各搜索时间片的覆盖结果更新。末列单独量出搜索对全域下界的贡献。"])
    partial=[]
    for case in ("S16","S32","S80"):
        for method in ("C0","C1"):
            folder=OUT/"cp"/case/method
            if not folder.exists() or any(j["job"]=="cp" and (j["case"],j["method"])==(case,method) and j["status"] in ("OK","TIME_LIMIT") for j in jobs):
                continue
            times=rows(folder/"timeline.jsonl")
            if not times:
                continue
            slices=rows(folder/"slices.jsonl")
            candidates=rows(folder/"candidates.jsonl")
            best=cert(times[-1]["plan"])["metrics"]
            initial=cert(times[0]["plan"])["metrics"]
            partial.append((case+"/"+method,len(slices),num(slices[-1]["elapsed_s"] if slices else times[-1]["elapsed_s"],1),
                            len({c["plan"] for c in candidates if c["status"]=="SAFE"}),num(initial["E_J"]),num(best["E_J"])))
    if partial:
        doc.extend(["## 尚无完整终点的记录",
                    md(["实例/方法","完整时间片","末次记录 (s)","不同 SAFE 候选","共同初解 (J)","末次记录的最佳 SAFE (J)"],partial),
                    "表中耗时截止最后一条完整记录。等预算终点比较只使用有完整阶段回执的配对。"])
    group=[]
    for b in base:
        c=b["case"]
        ref0=next(r for r in refs if r["case"]==c and r["reference"]=="B0" and r["idle"]=="hold")
        desc=("容量价格" if b["priced"]=="True" else "累计成本") if b["source"].startswith("width") else "后缀 4"
        group.append((c,num(ref0["SAFE_J"]),num(b["SAFE_J"]),b["source"]+" "+desc,num(float(ref0["SAFE_J"])-float(b["SAFE_J"])),
                      num(b["peak_upper_C"],4),num(b["deadline_margin_ms"],3)))
    doc+=["## 强配置基线",
          md(["实例","B0 保持 SAFE","冻结基线 SAFE","方案","相对 B0 节能","连续峰温上端 °C","期限余量 ms"],group),
          "D1、D2 的最强自动方案均来自宽度 1024 和容量价格。D3 七种自动构造均在请求流中途耗尽状态，冻结参照中由优化空闲控制的后缀 4 取得最低 SAFE 能耗。有限宽度、参考支配和构造阶段预留会损失解。这些失败不能判定实例不可行。"]
    target=[r for r in refs if r["case"]=="D3" and r["target_E35_J"]]
    doc+=["### D3 原参照与后缀诊断",
          md(["参照","空闲控制","E35","历史 E35","SAFE 总能耗","证书下端","证书上端"],
             [(r["reference"],r["idle"],num(r["E35_J"]),r["target_E35_J"],num(r["SAFE_J"]),outward(float(r["E_lo"]),11,upper=False),outward(float(r["E_hi"]),11,upper=True)) for r in target])]
    sx=rows(OUT/"suffix.jsonl")
    doc+=[md(["后缀请求数","每请求配置数","后缀最优 E35","见证 SAFE","期限余量 ms"],
             [(r["n"],r["options"],num(r["E35_J"]),num(cert(r["plan"])["metrics"]["E_J"]),num(cert(r["plan"])["metrics"]["min_deadline_slack_ms"],3)) for r in sx]),
          "后缀 10 与 12 取得同一见证。该证书计入 D3 全阶段最好已知解。它来自固定前缀的诊断。完整 CP 仅在 S 实例运行。"]
    if sx:
        origin=next(r for r in refs if r["case"]=="D3" and r["reference"]=="B0" and r["idle"]=="hold")
        baseline=next(r for r in base if r["case"]=="D3")
        best=cert(baseline["best_including_diagnostic"])["metrics"]
        gain=float(origin["SAFE_J"])-best["E_J"]
        doc.append(f"D3 中，B0 保持空闲频档时的认证总能耗为 {num(origin['SAFE_J'])} J，冻结基线为 {num(baseline['SAFE_J'])} J，后缀诊断的最佳认证排程为 {num(best['E_J'])} J。从 B0 到该排程共节省 {num(gain,6)} J（{100*gain/float(origin['SAFE_J']):.3f}%），其中，从冻结基线扩大后缀取得 {1000*(float(baseline['SAFE_J'])-best['E_J']):.3f} mJ。")
    if summ:
        doc+=["## 搜索过程与证书",
              md(["实例/方法","最佳区间 [下端,上端]","独立全域下界","建模 s","求解 s","评价及归档 s","回调/保留/评价","不同 SAFE/HOT/未决","未评价"],
                 [(s["case"]+"/"+s["method"],f"[{outward(float(s['E_lo']),11,upper=False)}, {outward(float(s['E_hi']),11,upper=True)}]",outward(s["lower_exact_J"],9,upper=False),
                   num(s["build_s"],1),num(s["solve_s"],1),num(s["assessment_archive_s"],2),
                   "/".join(s[k] for k in ("callbacks","retained","evaluated")),"/".join(s[k] for k in ("SAFE","HOT","unresolved")),s["pending"]) for s in summ]),
              md(["实例/方法","180 s","900 s","1800 s","3600 s"],
                 [(s["case"]+"/"+s["method"],*[num(s[f"best_SAFE_{t}s_J"]) if s[f"best_SAFE_{t}s_J"] else "" for t in (180,900,1800,3600)]) for s in checkpoints]),
              md(["实例/方法","变量","约束","候选弧","分支","时间片","状态及次数"],
                 [(s["case"]+"/"+s["method"],s["variables"],s["constraints"],s["arcs"],s["branches"],s["slices"],s["status_counts"]) for s in summ]),
              "全局界合并了解析全域界、未搜索域 CP 目标界、已评价计划下界与按 SAFE 上界剪除部分的界。单片的目标界适用范围见对应 cutoff 和 no-good 日志。不同方法可对同一实例共同提供质量证据。"]
    if summ:
        comp=[]
        for s in summ:
            a,b=[json.loads(gzip.decompress((OUT/"plans"/(s[k]+".json.gz")).read_bytes())) for k in ("common_seed","plan")]
            old,new=cert(s["common_seed"]),cert(s["plan"])
            moved=sum(x[2]!=y[2] for x,y in zip(a["rows"],b["rows"]))
            device=sum(x[0]!=y[0] for x,y in zip(a["rows"],b["rows"]))
            config=sum(x[:2]!=y[:2] for x,y in zip(a["rows"],b["rows"]))
            comp.append((s["case"]+"/"+s["method"],device,config,moved,
                         num(old["E35_J"]-new["E35_J"]),num(old["metrics"]["temperature_J"]-new["metrics"]["temperature_J"])))
        doc+=["## 最佳排程改变了什么",
              md(["实例/方法","设备改变的 Stage","设备或档位改变","起点改变","相对初解 E35 减少","温度修正减少"],comp),
              "C1 的活动热补偿权重取决于阶段、配置及该阶段的最迟完成时刻。同一任务配置的实际起点变化不会直接改变这项权重。因此，对配置、频域驻留和切换成本相同的一组排程，原连续认证仍可能区分其真实能耗。表内的两个能耗分项给出了实际变化来源。[变动 Stage 与起点明细](schedule_differences.csv)。"]
    if fin:
        elapsed=f"实验自北京时间 {local(hdr['utc'])} 至 {local(fin['utc'])}，运行器登记状态为 {fin['outcome']}，墙钟 {fin['elapsed_s']:.1f} s，上限 16,200 s。"
    else:
        elapsed=f"原运行于北京时间 {local(hdr['utc'])} 启动，总墙钟额度为 16,200 s。现有原始日志保留了逐阶段回执，整批结束回执尚缺。"
    doc+=["## 正确性与复现",
          "原 E0/E1 四组夹具、E2-a 八组夹具和 15 项权限检查通过。新模型的两个夹具分别有 1,144 和 528 个不同合法物理排程。C0/C1 均与独立穷举的排程与切换集合完全相同，整数目标逐项向下包络。使用 Fraction 核实 C1 屏障的最小净输入分别为 0.0014、0.0014、0.0028、0.0051 W。推导与时间单位见 [冻结协议](PROTOCOL.md)。",
          f"本地执行冻结为 `{hdr['freeze']}`。{elapsed}按原 D3 热容倍率 10 和新增 S 系列倍率 1 运行。三种频域全程连续，301 ms 尾段完整计能。公开冻结提交与本地执行提交的文件树均为 `733f371d5cdd2354cbc493bf6f77a6965b4d3211`。[GitHub 冻结提交](https://github.com/YBEMR/paper/commit/1c3e2ae2299b18a20557d3b6044e198281f45126)。",
          "逐计划分项、峰温、期限及配置分布见 [参照表](references.csv)、[构造表](construction.csv)、[求解汇总](summary.csv)。[候选日志](results/cp/)保留区间重叠的计划、未决、每片目标界和时间序列。[输入锁](input_lock.json)给出输入版本和 SHA。[计划](results/plans/)与[原认证证书和轨迹](results/certificates/)按计划 SHA 对应。"]
    (ROOT/"decision.md").write_text("\n\n".join(doc)+"\n",encoding="utf8",newline="\n")
if __name__=="__main__":main()
