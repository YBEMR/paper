"""Figure 4 from a paired G2 mechanism witness, with independently reconstructed ledgers."""
import csv
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from setup_inputs import G2,checked_problem
sys.path.insert(0,str(G2))
from archive import verify
from model import transitions,independent_events
from profiles import CFG

DEST=HERE/"figure4"
def read(p):
    return json.loads(p.read_bytes())

def table(name,rows):
    with (DEST/name).open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    DEST.mkdir(exist_ok=True)
    manifest=read(G2/"archive_manifest.json")
    part=G2/manifest["main_D1"]["entry"]
    assert read(part)["sha256"]==manifest["main_D1"]["sha256"]
    p=checked_problem("D1")
    ghz=[list(map(float,CFG["cpu"]["f"])),[float(x)/1000 for x in CFG["gpu"]["freq_MHz"]],list(map(float,CFG["npu"]["f"]))]
    with tempfile.TemporaryDirectory() as tmp:
        verify(part,Path(tmp))
        get=lambda method:Path(tmp)/"runs"/("main_D1_"+method+"_101")
        def round3(method):
            return next(z for ln in (get(method)/"rounds.jsonl").read_bytes().splitlines()
                        if (z:=json.loads(ln))["phase"]=="configuration" and z["turn"]==3)
        ab,pro=round3("AB"),round3("Proposed")
        assert ab["before"]["plan"]==pro["before"]["plan"] and ab["target"]==pro["target"]
        assert len(ab["scope"])==len(pro["scope"])==12
        targets={i for i,_ in pro["target"]}
        changed={i for i,x,y in pro["real_changes"] if x!=y}
        extra={f["selected"] for f in pro["feedback"]}&changed-set(ab["scope"])
        assert extra=={8,12} and pro["after"]["bounds"][1]<ab["after"]["bounds"][0]
        tasks,frequencies=[],[]
        for phase in ("before","after"):
            h=pro[phase]["plan"]
            base=get("Proposed")/"evidence"
            blob=gzip.decompress((base/"plans"/(h+".json.gz")).read_bytes())
            assert hashlib.sha256(blob).hexdigest()==h
            obj=json.loads(blob)
            rows=[tuple(v) for v in obj["rows"]]
            low=frozenset(tuple(v) for v in obj["low"])
            switches=transitions(p,rows,low)[1]
            assert switches==independent_events(p,rows,low)[1]
            cert=read(base/"certificates"/(h+".json"))
            assert cert["plan"]==h and cert["metrics"]["status"]=="SAFE" and list(map(list,switches))==cert["switches"]
            for i,(u,k,t) in enumerate(rows):
                j=i//3
                role="compensator" if j in extra else "target" if j in targets else "other"
                tasks.append(dict(phase=phase,plan=h,request=j,stage=("pre","main","post")[i%3],role=role,
                             release_scene=p.req[j]["scene"],unit=u,opp=k,start_tick=t,finish_tick=p.finish(i,rows[i])))
            for d in range(3):
                last=op=0
                for s,e,dom,old,new in switches:
                    if dom!=d:
                        continue
                    assert op==old
                    for a,b,tag in ((last,s,"dwell"),(s,e,"switch")):
                        if b>a:
                            frequencies.append(dict(phase=phase,plan=h,domain=d,start_tick=a,finish_tick=b,
                                               state=tag,opp=op,frequency_GHz=ghz[d][op],next_opp=new))
                    last,op=e,new
                if last<p.horizon:
                    frequencies.append(dict(phase=phase,plan=h,domain=d,start_tick=last,finish_tick=p.horizon,
                                       state="dwell",opp=op,frequency_GHz=ghz[d][op],next_opp=op))
        feedback=[{k:v for k,v in f.items() if k not in ("chain","interval","old","virtual_op")} for f in pro["feedback"]]
        table("feedback.csv",feedback)
        table("schedules.csv",tasks)
        table("frequency.csv",frequencies)
        table("paired.csv",[dict(batch="historical_G2",case="D1",seed=101,zero_based_turn=3,
              prior=pro["before"]["plan"],prior_J=pro["before"]["J"],AB=ab["after"]["plan"],AB_J=ab["after"]["J"],
              Proposed=pro["after"]["plan"],Proposed_J=pro["after"]["J"],scope_each=12,
              ab_solver=ab["solver"]["status"],proposed_solver=pro["solver"]["status"])])
    plot(tasks,frequencies,p.horizon)


def plot(tasks,frequencies,horizon):
    plt.rcParams.update({"font.family":["Times New Roman","SimSun","DejaVu Sans"],"svg.fonttype":"none",
                         "svg.hashsalt":"ch3-g2-D1-101-turn3","font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axs=plt.subplots(4,1,figsize=(7.1,7.5),height_ratios=[1.3,1.3,1,1],layout="constrained")
    colors={"compensator":"#247368","target":"#36659a","other":"#e3e6e8"}
    for ax,(lo,hi),title in zip(axs[:2],[(.12,.34),(1.80,2.16)],["(a) 轻载阶段的补偿请求","(b) 重载请求的主阶段"]):
        for ix,phase in enumerate(("before","after")):
            for r in tasks:
                if r["phase"]!=phase or r["stage"]!="main":
                    continue
                s,e=r["start_tick"]/10000,r["finish_tick"]/10000
                if s>=hi or e<=lo:
                    continue
                y=3-2*ix-(r["unit"]-2)
                ax.barh(y,e-s,left=s,height=.65,color=colors[r["role"]],edgecolor="white",linewidth=.55)
                if (r["role"]=="compensator" or (r["role"]=="target" and r["request"] in (125,134,145))) and lo<(s+e)/2<hi:
                    ax.text((s+e)/2,y,str(r["request"]),ha="center",va="center",color="white",fontsize=8)
        ax.set(yticks=[3,2,1,0],yticklabels=["交换前 GPU","交换前 NPU","交换后 GPU","交换后 NPU"],xlim=(lo,hi),ylim=(-.5,3.55))
        ax.set_title(title,loc="left",fontsize=10)
        ax.set_xlabel("执行时间（s）")
    for ax,d in zip(axs[2:],(1,2)):
        for phase,color,style in (("before","#626971","--"),("after","#206b68","-")):
            fs=[r for r in frequencies if r["domain"]==d and r["phase"]==phase]
            x=[r["start_tick"]/10000 for r in fs]+[horizon/10000]
            y=[r["frequency_GHz"] for r in fs]+[fs[-1]["frequency_GHz"]]
            ax.step(x,y,where="post",color=color,ls=style,lw=1.55 if phase=="before" else 1.05,label="交换前" if phase=="before" else "交换后")
        ax.axvline(1,color=".60",lw=.8,ls=":")
        ax.set_xlim(0,horizon/10000)
        ax.set_ylabel("频率（GHz）")
        ax.set_title("(c) GPU 频域" if d==1 else "(d) NPU 频域",loc="left",fontsize=10)
        ax.set_xlabel("执行时间（s）")
    axs[2].legend(handles=[*axs[2].get_legend_handles_labels()[0],Line2D([],[],ls=":",color=".6",label="场景切换")],
                  loc="upper left",frameon=False,ncol=3,fontsize=8)
    vector=DEST/"capacity_exchange.svg"
    fig.savefig(vector,metadata={"Date":None})
    vector.write_bytes(b"\n".join(line.rstrip() for line in vector.read_bytes().splitlines())+b"\n")
    fig.savefig(DEST/"capacity_exchange.png",dpi=360)
    plt.close(fig)


if __name__=="__main__":
    main()
