"""Create the per-condition Chinese tables and links to the complete replicate curves."""
import json
from analyze import DATA,readcsv
from design import ROOT,REG,METHODS

def fmt(x,n=3):
    return "—" if x in (None,"") else f"{float(x):.{n}f}"

def main():
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    med=readcsv(DATA/"medians.csv")
    ix={(r["case"],r["regime"],r["method"]):r for r in med}
    pairs={(r["case"],r["regime"],r["right"]):r for r in readcsv(DATA/"paired_cases.csv") if r["left"]=="NT"}
    lines=["# M1-i 逐工况结果与全部曲线","",
        "每格报告成功重复的最低 SAFE 能耗中位数（J），括号给出三次中成功的次数。只有一次成功时仍显示该实测值，主配对统计要求至少两次成功。— 表示该截面三次都没有 SAFE。峰温是最低能耗 SAFE 排程的连续峰温上界，期限余量取其最紧请求。原始三次的证书、首解时间与开销均可按编号追溯。[每次重复](data/repetitions.csv) · [逐次成对比较](data/paired_repeats.csv)",""]
    for group in "ABCD":
        rows=[c for c in cases if c["group"]==group]
        lines.extend([f"## {group} 组","","| 工况 · 次序 | 环境 | 请求 | 截面 | NT | NC | ZQ-Beam | C2 |","|---|---:|---:|---|---:|---:|---:|---:|"])
        for c in rows:
            for cut in ("W4/K4","10s","30s","60s"):
                r=[ix[c["case"],cut,m] for m in METHODS]
                v=[fmt(x["SAFE_J"],4)+"（"+x["n_SAFE"]+"/3）" for x in r]
                first=cut=="W4/K4"
                lines.append("| "+" | ".join([c["case"].split("_")[0]+" · "+c["word"] if first else "",str(c["ambient"])+"°C" if first else "",str(c["requests"]) if first else "",cut,*v])+" |")
        lines.extend(["",f"![{group}组三次独立计时的完整最优改善阶梯](figures/quality_{group}.png)","",
              "下表为 60 秒时的分项中位数。构造时间含排序，认证时间含物理证据写盘。未取得 SAFE 的工况仍报告实际最冷认证峰温。","",
              "| 工况 | 方法 | 首次 SAFE（s） | SAFE 峰温（°C） | SAFE 期限余量（ms） | 最冷认证峰温（°C） | 构造（s） | 认证（s） | 认证数 |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
        for c in rows:
            for m in METHODS:
                x=ix[c["case"],"60s",m]
                lines.append("| "+" | ".join([c["case"].split("_")[0],m,*[fmt(x[k],n) for k,n in
                        (("first_SAFE_s",2),("peak_C",3),("slack_ms",2),("min_cert_peak_C",3),("build_s",2),("cert_write_s",2),("certs",0))]])+" |")
        lines.append("")
    lines.extend(["## 各工况对 NT 的 60 秒配对","",
                 "正值表示 NT 节能，分母是表头对照方法的工况中位能耗。不同时满足可靠 SAFE 条件时只写覆盖方向。","",
                 "| 工况 | 任务流 | 环境 | 对 NC | 对 ZQ-Beam | 对 C2 |","|---|---|---:|---:|---:|---:|"])
    for c in cases:
        out=[]
        for m in METHODS[1:]:
            r=pairs[c["case"],"60s",m]
            out.append(f"{float(r['saving_pct']):+.3f}%" if r["saving_pct"] else
                       {"only_left":"仅 NT","only_right":"仅对照","neither":"双方均未达 2/3"}[r["result"]])
        lines.append("| "+" | ".join([c["case"].split("_")[0],c["word"],str(c["ambient"])+"°C",*out])+" |")
    lines.extend(["","[全部时间截面的六种配对](data/paired_cases.csv) · [全部能耗改善时刻](data/improvements.csv) · [同一流三温度变化](data/ambient_paired.csv)",""])
    (ROOT/"results.md").write_text("\n".join(lines))
if __name__=="__main__":main()
