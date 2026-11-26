"""Render case-level breakdowns with links to all pool-level and certificate-level data."""
import csv
from collections import Counter
from statistics import median
from study import CASES,OUT,ROOT,load

def rows(name):
    with (OUT/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def fmt(x,n=6):
    return "—" if x is None or x=="" else f"{float(x):.{n}f}"

def table(headers,items):
    def line(v):return "| "+" | ".join(map(str,v))+" |"
    return "\n".join([line(headers),line(["---"]*len(headers)),*map(line,items)])

def main():
    r=rows("terminal_ablation.csv")
    t=["# 消融与预算明细",
       "同池排名比较共 30 个池。下表的“成功池数”和“工况最低”分别是出现至少一份 SAFE 证书的池数，以及各池最佳 SAFE 能耗的最小值。跨池最低供定位候选质量，实际部署仍需使用预先固定的一种生成和保留规则。"]
    methods={"legacy":"原策略扩展","energy":"普通能耗序","safe_energy":"预计安全能耗序"}
    for mode,title in (("count","等认证次数"),("time","等实际时间")):
        t.append("## "+title)
        if mode=="time":
            t.append("各池及各预算分别采用原策略第 4、8、16 份证书完成的实测时刻。只计截止时已完成的证书。算法共用完整建池开销，晚于截止完成的调用也保存在原始记录中。")
        vals=[]
        for c in CASES:
            for k in ("4","8","16"):
                for meth,cn in methods.items():
                    grp=[v for v in r if (v["case"],v["budget"],v["method"],v["comparison"])==(c,k,meth,mode)]
                    safe=[v for v in grp if v["best"]]
                    def med(key):return median(float(v[key]) for v in safe) if safe else None
                    vals.append([c,k,cn,f"{len(safe)}/{len(grp)}",fmt(min((float(v["best"]) for v in safe),default=None)),
                                fmt(med("first"),1),fmt(med("first_terminal_s"),3),fmt(med("first_s"),3),
                                sum(int(v["n"]) for v in grp)])
        t.append(table(["工况","预算","排序","成功池数","工况最低 J","首次 SAFE 序号中位","首次 SAFE 终端秒中位","含建池秒中位","完成认证总数"],vals))
    t+=["## 固定 H 生成与原前缀",
        "单元格依次为最佳 SAFE 能耗（J）、获得首份 SAFE 的认证序号、从空开始至首份 SAFE 的总秒数。每行只对应一个固定池。"]
    vals=[]
    for c in CASES:
        for k in ("4","8","16"):
            a=[]
            for m in methods:
                v=next(v for v in r if (v["case"],v["pool"],v["budget"],v["method"],v["comparison"])==(c,"H_original",k,m,"count"))
                a.append("—" if not v["best"] else f"{fmt(v['best'])} / {v['first']} / {fmt(v['first_s'],3)}")
            vals.append([c,k,*a])
    t.append(table(["工况","认证数上限",*methods.values()],vals))
    if (OUT/"prefix_ablation.csv").exists():
        t+=["## 第四位前缀对照","终端一律预计安全能耗序；全普通 C2 另按自己的原终端扩展顺序送验。等时明细另存 CSV，缺少证书表示该方法在相应截止点前尚未完成认证。"]
        z=rows("prefix_ablation.csv");vals=[]
        for c in CASES:
            for a,name in (("original","原规则"),("guarded","有条件替换"),("time_cost","同探针时序可行能耗"),("feasible_cost","同探针热时可行能耗"),("C2","全普通 C2")):
                g=[v for v in z if v["case"]==c and v["rule"]==a and v["comparison"]=="count"]
                vals.append([c,name,*[fmt(v["best"]) for v in g],fmt(g[0]["build_s"],3),fmt(g[0]["first_s"],3),fmt(g[0]["elapsed"],3)])
        t.append(table(["工况","前缀","4 次 J","8 次 J","16 次 J","建池秒","4 次内首次 SAFE 总秒","4 次总秒"],vals))
    if (OUT/"validation_ablation.csv").exists():
        t+=["## 冻结后未调负载次序","同一规模的每条序列拥有相同数量的 L、H 窗口、请求和计能时长。末列为冻结算法第 4 份证书完成的时间。所有方法均从空开始。"]
        z=rows("validation_ablation.csv");vals=[]
        for c in CASES:
            for word in sorted({v["order"] for v in z if v["case"]==c}):
                def pick(m,k):
                    return next(v for v in z if v["order"]==word and v["method"]==m and v["comparison"]=="count" and v["budget"]==str(k))
                w=pick("frozen",4)
                vals.append([c,word,fmt(pick("C2",4)["best"]),fmt(pick("C2",16)["best"]),fmt(pick("H_legacy",4)["best"]),fmt(pick("H_legacy",8)["best"]),
                             fmt(pick("H_legacy",16)["best"]),fmt(w["best"]),w["first"] or "—",fmt(w["elapsed"],3)])
        t.append(table(["工况","序列","C2 四次 J","C2 十六次 J","H 原四次 J","H 原八次 J","H 原十六次 J","冻结四次 J","首次 SAFE 序号","四次总秒"],vals))
    (OUT.parent/"消融与预算.md").write_text("\n\n".join(t)+"\n",encoding="utf8")

if __name__=="__main__":main()
