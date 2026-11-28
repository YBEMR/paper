"""Render the numerical appendix from collected CSV tables."""
from collections import Counter
from summary import HERE,OUT,cases,stats
import json

def fmt(v,d=2,plus=False):
    if v is None or v=="":return "—"
    return format(float(v),("+" if plus else "")+f".{d}f")
def table(cols,rows):
    def line(items):return "| "+" | ".join(str(x) for x in items)+" |"
    return "\n".join([line(cols),line(["---"]*len(cols)),*[line(row) for row in rows]])
def write():
    rows=stats.csvrows
    sections=[]
    def add(title,cols,data,note=""):
        sections.append("## "+title+"\n\n"+table(cols,data)+("\n\n"+note if note else ""))
    fs=rows("flow_pairs");fts=rows("first_safe_summary");co=rows("cohorts")
    for cap in ("20","10"):
        data=[]
        for f in (r for r in fs if r["cap"]==cap):
            x=next(r for r in fts if r["case"]==f["case"] and r["cap"]==cap)
            data.append([f["case"],f["A_safe"]+"／"+f["B_safe"],fmt(f["A_first_s"])+"／"+fmt(f["B_first_s"]),
                fmt(x["median_saved_s"])+"／"+fmt(x["median_saved_pct"],1),
                fmt(f["A_J"],4)+"／"+fmt(f["B_J"],4),fmt(f["B_vs_A_pct"],3,True),
                fmt(f["A60_J"],4),fmt(f["B_vs_A60_pct"],3,True),
                x["B_lower_J"]+"／"+x["overlap_J"]+"／"+x["A_lower_J"]])
        add(cap+" 秒逐流比较",["任务流","安全次数 A／B，各 3 次","首次安全中位秒 A／B","共同配对节时中位秒／%","完整能耗中位 J，A／B","B 对 A，%","同期 A60，J","B 对 A60，%","B 能耗胜／平／负"],data,
            "能耗为成功重复中位数；胜平负按逐次认证区间判定，仅计双方共同成功。缺失用 — 表示。可靠要求至少 2/3 次安全。节时为 A 首次安全时间减 B，相对节时的分母为同次 A 时间。")
    add("开发流与其余登记流",["组别","预算秒","可靠流 A／B","安全次数 A／B（各自分母）","首解 B 较早／共同成功","配对节时中位秒／%","共同可靠流数","B 对 A 平均／最大变化 %","B 对 A60 平均损失 %（流数）"],[
        [{"all":"全部","development":"原开发四流","other_registered":"其余八流"}[r["cohort"]],r["cap"],r["A_reliable"]+"／"+r["B_reliable"],r["A_safe"]+"／"+r["B_safe"]+"（"+r["pairs"]+"）",
        r["B_earlier"]+"／"+r["paired_first_n"],fmt(r["median_saved_first_s"])+"／"+fmt(r["median_saved_first_pct"],1),
        r["common_reliable"],fmt(r["mean_B_vs_A_pct"],3,True)+"／"+fmt(r["max_B_vs_A_pct"],3,True),
        fmt(r["B_mean_gap_ref_pct"],3,True)+"（"+r["B_ref_n"]+"）"] for r in co])
    ms=rows("method_summary");tg=rows("target_stages");th=rows("target_pair_summary")
    data=[]
    for m in ms:
        for tol in ("0","0.01"):
            t=next(r for r in tg if (r["case"],r["cap"],r["arm"],r["tolerance"])==("all",m["cap"],m["arm"],tol))
            data.append([m["arm"]+m["cap"],"严格" if tol=="0" else "+1%",m["safe"]+"/"+m["runs"],m["reliable"]+"/12",t["hits"]+"/"+t["runs"],
                t["no_safe"]+"／"+t["above_target"]+"／"+t["no_reference"],fmt(t["median_hit_s"]),
                t["first_from_search"]+"／"+t["first_from_direct"],t["all_search_deliveries"]+"／"+t["all_direct_deliveries"]])
    add("共同质量目标达成与调频来源",["配置","目标","安全交付","可靠流","达标率","无安全／安全未达标／缺参照","达标者首次中位秒","首达源 搜索／调频","所有达标证书 搜索／调频"],data,
        "每流目标取同期 A60 成功证书上界中位数；容差目标乘 1.01。最后一列按证书交付次数计，同一排程在不同运行或阶段可以再次交付。")
    add("达标配对",["预算秒","容差","配对分母","双方／仅 A／仅 B／均未","双方达标 B−A 中位秒"],[
        [r["cap"],r["tolerance"],r["pairs"],"／".join(r[k] for k in ("both","A_only","B_only","neither")),fmt(r["paired_B_minus_A_median_s"],3,True)]
        for r in th if r["case"]=="all"])
    c=rows("formal_costs")
    add("实际搜索和认证工作量",["配置","名额／实评／时序合法","传播次数","完成层／最大宽度","认证／超温证书","提名／完成调频映射","超温提名／恢复"],[
        [r["arm"]+r["cap"],"／".join(r[k] for k in ("generated","evaluated","legal")),r["propagations"],r["complete_layers"]+"／"+r["max_width"],
        r["certs"]+"／"+r["hot_certs"],r["maps"]+"／"+r["completed_maps"],r["hot_nominated"]+"／"+r["hot_recovered"]] for r in c])
    add("累计互斥开销（秒）",["配置","启动至搜索","实例","构造","搜索认证","提名","交接","调频内核","调频认证","其余","计费墙钟"],[
        [r["arm"]+r["cap"],*[fmt(r[k]) for k in ("before_search_s","instance_s","construct_s","search_cert_s","selection_s","handoff_s","dp_s","dp_cert_s","other_s","charged")]] for r in c],
        "调频内核列为已经返回并落账的计算；截止中断的未闭合调用归入所在开放区间或其余。完整构造每秒实际评价数是观察到的吞吐量，随所选候选组成改变。")
    ph=rows("phase_summary")
    add("阶段切换与提名完成情况",["配置","分界前已有安全解","启动调频／全局改善运行数","首解至提名中位秒","调频启动中位秒","调频启动后剩余中位秒","提名／启动／完成映射","有未完成映射的运行"],[
        [r["arm"]+r["cap"],r["safe_before_split"],r["direct_started_runs"]+"／"+r["direct_improved_runs"],
         fmt(r["median_first_safe_to_selection_s"]),fmt(r["median_tune_start_s"]),fmt(r["median_available_after_tune_start_s"]),
         "／".join(r[k] for k in ("nominated","started","finished")),r["unfinished_map_runs"]] for r in ph if r["case"]=="all"])
    add("重点流的搜索与调频",["流","配置","首个完整候选池中位秒","构造实评／秒","调频启动中位秒","调频首次全局改善中位秒","构造最佳／最终中位 J","提名／启动／完成映射"],[
        [r["case"],r["arm"]+r["cap"],fmt(r["median_first_terminal_s"]),fmt(r["evaluated_per_construct_s"],0),
         fmt(r["median_tune_start_s"]),fmt(r["median_first_tune_improvement_s"]),fmt(r["median_best_search_J"],3)+"／"+fmt(r["median_final_J"],3),
         "／".join(r[k] for k in ("nominated","started","finished"))] for r in ph if r["case"] in ("A02","C11","C12")])
    names={"construction_incomplete":"构造截止，完整池尚未返回","certification_cutoff":"已进入连续认证，截止时认证未返回",
        "all_returned_terminals_certified_HOT":"已返回终端全部认证超温","tested_HOT_other_terminals_unresolved":"已认证终端均超温，其余未判定",
        "no_legal_pool_on_explored_beam":"已探索束出现完整空池","terminal_ready_no_certificate_delivered":"完整终端已返回，未交付证书",
        "cpu_guard":"资源保护","fault":"程序故障","no_SAFE_other_status":"其他认证状态"}
    add("未交付原因",["配置","日志见证","次数"],[[r["arm"]+r["cap"],names.get(r["reason"],r["reason"]),r["runs"]] for r in rows("failure_summary")],
        "逐次失败表另列已完成最深层、完整终端数、认证开始数和返回数。未认证候选与原问题可行性均不据此判定。")
    (HERE/"APPENDIX_zh.md").write_bytes(("# 全部登记任务流确认数据\n\n"+"\n\n".join(sections)+"\n").encode("utf8"))

if __name__=="__main__":write()
