"""Render four transparent tables directly from audited CSV evidence."""
from collections import Counter
from common import CASES,DATA,ROOT
from validate_run import csvread

NAMES=dict(original="原规则",time_energy="时间能耗",joint="热/期限余量",suffix="后缀热需求",guarded="有条件替换")

def table(head,rows):
    def line(r):return "| "+" | ".join(map(str,r))+" |"
    return "\n".join([line(head),line(["---"]*len(head)),*map(line,rows)])
def num(s,n=3):
    return f"{float(s):.{n}f}" if s not in ("",None) else "—"

def main():
    au=DATA/"audit"; base=DATA/"historical"
    path=csvread(base/"path.csv"); sp=csvread(base/"splices.csv"); free=csvread(au/"path_from_empty.csv")
    arms=("HT_w4b4","NT_w4b4","HT_w4b4s")
    texts=["# 逐窗口保留、同池反事实与从空消融",
           "路径以固定提交中 49.601232 J 的 L800 连续认证计划为准。H 是原热边界配额，N 是非热几何配额，Hs 是增加时序筛查的热边界配额。三个历史方法均使用热排序。",
           "## 历史路径与其他可接续前缀",
           "位置 1 至 4 按实际保留顺序，末窗为送验顺序。× 表示本窗生成后淘汰，空白表示父路径已丢失。最后一列列出每个历史方法四个保留前缀中，接上同一历史剩余动作后全程 SAFE 的个数。"]
    rows=[]
    for j in range(1,11):
        rr=[next(r for r in path if r["arm"]==a and int(r["window"])==j) for a in arms]
        ranks=[r["rank"] or ("×" if r["reason"]=="pruned" else "") for r in rr]
        safe=[sum(v["status"]=="SAFE" for v in sp if v["window"]==str(j) and v["arm"]==a) for a in arms]
        rows.append([j,rr[0]["action"],*ranks,num(rr[0]["predicted_peak"]),num(rr[0]["reference_peak"]),
                     num(rr[0]["repeat_load_risk"]),num(rr[0]["reference_next_peak"]),"/".join(map(str,safe))])
    texts.append(table(["窗","动作 (GPU档,NPU档,A配额,B配额)","H 位置","N 位置","Hs 位置","前缀预测 °C","连续前缀 °C",
                       "重复负载预测 °C","沿已证动作至下一窗 °C","接续 SAFE 数 H/N/Hs"],rows))
    texts+=["## 同一候选池的第四位", "每个单元格为四个所选前缀中固定后缀接续 SAFE 的数量。池与前三位完全相同。第 10 窗直接认证终端，无后缀可试。"]
    d=csvread(DATA/"same_pool/decisions.csv")
    rows=[]
    for g in ("H","N","Hs"):
        for j in range(1,11):
            v=[next(x for x in d if x["generator"]==g and x["window"]==str(j) and x["rule"]==k) for k in list(NAMES)[:4]]
            rows.append([g,j,v[0]["pool"],v[0]["tested"],v[0]["tested_safe"],*[s["kept_safe"] for s in v]])
    texts.append(table(["生成","窗","合法池","离线检查","其中 SAFE","原规则","时间能耗","热/期限余量","后缀热需求"],rows))
    texts+=["## 从空搜索的 L800 路径","× 表示生成后淘汰，末 表示终端已经生成、未列入四个认证位置，缺 表示本窗未生成，· 表示参考父前缀在早先窗口已经丢失。"]
    rows=[]
    for a in sorted({r["arm"] for r in free}):
        g,k=a.split("_",1); vv=[r for r in free if r["arm"]==a]
        rows.append([g,NAMES[k],*[v["rank"] or {"pruned":"×","parent_lost":"·","not_generated":"缺","terminal_not_certified":"末"}[v["reason"]] for v in vv]])
    texts.append(table(["生成","第四位",*range(1,11)],rows))
    texts+=["## 从空消融与等实耗普通强基线",
            "所有在线搜索先计候选扩展、保留与前瞻，再计全程连续认证和证书写入。下表按每个方法实测墙钟时间分别截断普通 C2 同一条扩宽轨迹。前瞻秒数包括备选集、探针生成、FIFO、热传播与选择。— 表示该预算未取得 SAFE。"]
    rows=[]
    ee={(z["case"],z["arm"]):z for z in csvread(au/"equal_time.csv")}
    ss=csvread(au/"summary.csv")
    for case in CASES:
        for g in (("H","N","Hs") if case=="L800" else ("H",)):
            for k in NAMES:
                a=g+"_"+k
                z=next(v for v in ss if v["case"]==case and v["arm"]==a); e=ee[case,a]
                rows.append([case,g,NAMES[k],z["safe"],num(z["best_J"],6),num(z["min_peak_C"]),num(z["seconds"],2),
                             z["look_fifo"],z["thermal_steps"],num(z["look_s"],3),e["ordinary_completed"],num(e["ordinary_best_J"],6)])
    texts.append(table(["工况","生成","第四位","SAFE/4","最低 SAFE J","最低送验峰温 °C","总秒","前瞻 FIFO","前瞻热步","前瞻秒",
                       "等时普通认证数","等时普通 SAFE J"],rows))
    texts+=["完整原始数值与证书身份见[搜索摘要](data/audit/summary.csv)、[逐次认证](data/audit/terminals.csv)、[同池第四位](data/same_pool/decisions.csv)和[同秒数截断](data/audit/equal_time.csv)。"]
    (ROOT/"逐窗与消融.md").write_text("\n\n".join(texts)+"\n",encoding="utf-8")

if __name__=="__main__":main()
