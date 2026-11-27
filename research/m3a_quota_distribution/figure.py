"""Plot one registered paired action from the original per-request replay arrays."""
import io
import csv
import zipfile
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Patch
from summarize import DATA,ROOT,read

folder=next(DATA.glob("A04_*"))
archive=read(folder/"audit.json.gz")
case=archive["physical"]
r2=read(folder/"s2.json.gz")["runs"]
thermal=next(r for r in r2 if r["arm"]=="thermal" and r["repeat"]==1)
action=next(r for r in archive["edges"] if r["stage"]==2 and r["arm"]=="original" and r["action"]==[7,2])
keys=[archive["base"],action["cfg"],thermal["start"],thermal["winner"]]
records=[]
with zipfile.ZipFile(folder/"traces.zip") as z:
    for k in keys:
        if case[k]["fifo_ok"]:
            rows=list(csv.DictReader(io.TextIOWrapper(z.open(k+"/requests.csv"))))
            rec=rows[581]
            times=[int(rec[p]) for p in ("ready","main_start","main_end","post_end")]
        else:
            a=case[k]
            times=[70058,a["starts"][581],a["ends"][581],a["post_finish"][581]]
        records.append([(t-70000)/10 for t in times])
font=FontProperties(fname="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
fig,ax=plt.subplots(figsize=(9.2,3.55))
colors=("#b2c4cc","#25617a","#dc993b")
labels=["原分布 · 原频档","原分布 · GPU 降一档","半周期相位 · 原频档","半周期相位 · GPU 降一档"]
for i,((ready,start,end,finish),lab) in enumerate(zip(records,labels)):
    for x,y,col in zip((ready,start,end),(start,end,finish),colors):
        ax.barh(i,y-x,left=x,height=.47,color=col)
    ax.text(finish+.7,i,f"{finish:.1f} ms",va="center",fontsize=10,
            color="#a03932" if finish>300 else "#1d3c4c")
ax.set(yticks=range(4),xlim=(255,312),ylim=(3.55,-.75),xticks=[260,270,280,290,300,310])
ax.set_yticklabels(labels,fontproperties=font,fontsize=10)
ax.axvline(300,color="#a03932",linestyle="--",lw=1.4)
ax.text(300,-.47,"300 ms 期限",ha="center",va="bottom",fontproperties=font,fontsize=10,color="#a03932")
ax.set_xlabel("自请求释放起的时间（ms），图中放大末段",fontproperties=font,fontsize=10)
ax.set_title("A04  ·  第 8 窗 GPU 降一档时，请求 581 能否按期完成？",loc="left",fontproperties=font,fontsize=14,pad=12)
ax.legend(handles=[Patch(color=c,label=l) for c,l in zip(colors,["GPU 队列等待","GPU 非抢占执行","CPU 后处理"])],
          loc="upper center",bbox_to_anchor=(.44,-.19),ncol=3,frameon=False,prop=font)
ax.spines[['top','right','left']].set_visible(False)
ax.tick_params(axis='y',length=0,pad=8)
fig.subplots_adjust(left=.23,right=.98,top=.82,bottom=.28)
(ROOT/"figures").mkdir(exist_ok=True)
fig.savefig(ROOT/"figures/a04_request_581.png",dpi=160,facecolor="white")
