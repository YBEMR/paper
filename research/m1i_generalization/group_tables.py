"""Render the prespecified grouped comparisons without pooling thermal replicates."""
from analyze import DATA,readcsv
from design import ROOT,METHODS

def main():
    coverage=readcsv(DATA/"group_coverage.csv");pairs=readcsv(DATA/"group_pairs.csv")
    group_names={"ABC35":"35°C 的 12 条新流","A":"A · 等量新次序","B":"B · 非等量负载","C":"C · 960/1280 请求",
                 "D25":"D · 同两条流在 25°C","D45":"D · 同两条流在 45°C"}
    lines=["# 分组成功率、成对能耗及热压力响应","",
        "覆盖表以工况为分母。每格三个数依次为至少一次、至少两次、全部三次取得 SAFE 的工况数。配对表只在两方均至少两次 SAFE 的工况上统计胜平负及平均节能。仅 NT 和仅对照两列保留不能计算节能率的工况。",""]
    for group,label in group_names.items():
        lines.extend(["## "+label,"","| 截面 | 工况数 | NT | NC | ZQ-Beam | C2 |","|---|---:|---:|---:|---:|---:|"])
        for cut in ("W4/K4","10s","30s","60s"):
            sub=[r for r in coverage if (r["group"],r["regime"])==(group,cut)]
            ix={r["method"]:r for r in sub}
            cells=["/".join(ix[m][k] for k in ("at_least_one","at_least_two","all_three")) for m in METHODS]
            lines.append("| "+" | ".join([cut,sub[0]["flows"],*cells])+" |")
        lines.extend(["","| 截面 | NT 对照 | 共同 SAFE | NT 胜/平/负 | 平均节能率 | 中位节能率 | 仅 NT | 仅对照 | 均不足 |",
                      "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for r in pairs:
            if r["group"]!=group or r["left"]!="NT":continue
            percent=lambda v:f"{float(v):+.3f}%" if v else "—"
            lines.append("| "+" | ".join([r["regime"],r["right"],r["paired"],"/".join(r[k] for k in ("win","tie","loss")),
                                         percent(r["mean_saving"]),percent(r["median_saving"]),r["only_left"],r["only_right"],r["neither"]])+" |")
        lines.append("")
    lines.extend(["## 同一流在三个环境下的变化","",
       "表内为 60 秒时三次的成功数和完整 SAFE 能耗中位数（J）。能耗变化只在该温度和 35°C 同时至少两次成功时给出，差值为当前环境减去 35°C。","",
       "| 次序 | 方法 | 25°C 成功数 / 能耗 | 35°C 成功数 / 能耗 | 45°C 成功数 / 能耗 | 25−35 （J） | 45−35 （J） |",
       "|---|---|---:|---:|---:|---:|---:|"])
    ambient=readcsv(DATA/"ambient_paired.csv")
    for stream in dict.fromkeys(r["flow"] for r in ambient):
        for m in METHODS:
            ix={r["ambient"]:r for r in ambient if (r["flow"],r["regime"],r["method"])==(stream,"60s",m)}
            cell=lambda r:r["success"]+"/3 · "+(f"{float(r['SAFE_J']):.4f}" if r["SAFE_J"] else "—")
            delta=lambda r:f"{float(r['delta_J_vs35']):+.4f}" if r["delta_J_vs35"] else "—"
            lines.append("| "+" | ".join([stream.split("_")[1],m,*(cell(ix[t]) for t in ("25","35","45")),
                                          delta(ix["25"]),delta(ix["45"])])+" |")
    lines.extend(["","![同一任务流的三温度比较](figures/ambient.png)","",
                  "[所有六种方法配对](data/group_pairs.csv) · [每方法中位开销](data/group_coverage.csv) · [各工况与重复](results.md)",""])
    (ROOT/"groups.md").write_text("\n".join(lines))
if __name__=="__main__":main()
