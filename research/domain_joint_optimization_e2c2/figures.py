"""Render the 12 verified trajectories and a compact table of the three checkpoints."""
import csv
import gzip
import statistics
from collections import defaultdict
from settings import METHODS,SEEDS,ROOT,read
def render():
    rows=list(csv.DictReader((ROOT/"results.csv").open(encoding="utf8")))
    if len(rows)!=12 or any(r["status"]!="VERIFIED" for r in rows):return
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    traces=defaultdict(list)
    with gzip.open(ROOT/"curves.csv.gz","rt",encoding="utf8") as f:
        for r in csv.DictReader(f):
            traces[r["method"],int(r["seed"])].append((float(r["time_s"]),float(r["J"])))
    colors=["#444444","#0072B2","#D55E00","#009E73"]
    fig,axes=plt.subplots(1,3,figsize=(13.2,4.5),sharey=True,layout="constrained")
    for ax,seed in zip(axes,SEEDS):
        for method,col in zip(METHODS,colors):
            points=traces[method,seed];first=points[0][1];last=points[-1][1]
            t,e=zip(*[(0,first),*points,(1800,last)])
            ax.step(t,e,where="post",label=method,color=col,linewidth=1.6)
            ax.scatter([1800],[last],color=col,s=14,clip_on=False)
        ax.set_title(f"D3   |   seed {seed}")
        ax.set(xlabel="Elapsed time (s)",xlim=(0,1800),xticks=[0,180,900,1800])
        ax.grid(axis="y",alpha=.2);ax.spines["top"].set_visible(False);ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Best certified SAFE energy (J)")
    fig.legend(*axes[0].get_legend_handles_labels(),loc="outside lower center",ncol=4,frameon=False)
    fig.savefig(ROOT/"energy_time.png",dpi=160);plt.close(fig)
    with (ROOT/"decision.md").open("a",encoding="utf8",newline="\n") as f:
        f.write("\n## 完整任务流能耗随时间变化\n\n![三个种子各自的四种方法连续 SAFE 最佳能耗](energy_time.png)\n\n")
        f.write("图中每个台阶对应该运行一次严格接纳。下表各时点取三个种子的中位数，末段节能取逐种子可靠改善下限的中位数。\n\n")
        f.write("|方法|180 s / J|900 s / J|1800 s / J|末 180 s 节能 / mJ|\n|---|---:|---:|---:|---:|\n")
        for method in METHODS:
            subset=[r for r in rows if r["method"]==method]
            values=[statistics.median(float(r[k]) for r in subset) for k in ("E180","E900","J","last180_mJ")]
            f.write("|"+method+"|"+"|".join(f"{v:.6f}" for v in values)+"|\n")
        new=sorted((r for r in rows if r["method"]=="Hybrid-New"),key=lambda r:int(r["seed"]))
        f.write("\n## 种子波动与求解开销\n\n")
        f.write("|Hybrid-New 种子|G3 尝试数|联合子问题数|全流涉及 Stage / 2400|最终安全能耗 / J|\n|---:|---:|---:|---:|---:|\n")
        for r in new:
            f.write(f"|{r['seed']}|{r['steps']}|{r['iterations']}|{r['stages']}|{float(r['J']):.6f}|\n")
        spread=max(float(r["J"]) for r in new)-min(float(r["J"]) for r in new)
        f.write(f"\n相同墙钟预算下，Hybrid-New 的三个终点相差 {spread:.6f} J。每个普通全权限子问题和辅助求解均占用联合阶段的 120 秒额度，可比较的执行量见上表。不同种子面对不同的当前排程，单次子问题耗时也会变化，现有数据不能把终点差额归因于某一项开销。\n")
        with (ROOT/"mechanisms.csv").open(encoding="utf8") as source:
            accepted=[r for r in csv.DictReader(source) if r["method"]=="Hybrid-New" and r["origin"] not in ("fallback","ordinary_full")]
        f.write(f"\n该方法共接纳 {len(accepted)} 次非普通邻域联合改善，其中 {sum(int(r['cross_resource']) for r in accepted)} 次在至少两个设备上同时移时，{sum(int(r['cross_scene']) for r in accepted)} 次改变横跨场景的任务。两类事件可以重叠。完整前后排程及每项证书随运行归档。\n")
if __name__=="__main__":
    render()
    from timing_audit import annotate
    annotate()
