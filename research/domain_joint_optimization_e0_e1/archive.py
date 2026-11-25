import math
import numpy as np
from scipy.linalg import expm
from common import *
from compact import Layout,permissions
from inputs import restore
from model import Problem,independent_events
from heat import evaluate
from validation import common_grid,membership

def recert(p,plan,cache):
    lay=Layout(p,plan[0]);normalized=(plan[0],lay.normalize(plan[1]));k=store_plan(p.case,normalized)
    if k in cache:return k,cache[k]
    m=evaluate(p,normalized,cert=True,trace=True);tr=np.array(m.pop("events"))
    a,b=common_grid(lay.events(normalized[1]),tr[:,:14]);assert np.array_equal(a,b)
    _,sw=independent_events(p,*normalized);assert sw==lay.switches(normalized[1])
    val=lay.components(normalized[1]);assert abs(float(sum(val.values()))+m["temperature_J"]-m["E_J"])<1e-8
    x=np.r_[p.initial,0.,1.];memo={};err=0.
    for row in tr:
        t,e=row[:2];q=row[2:6];beta=row[6:10];key=(e-t,*q,*beta)
        if key not in memo:
            A=np.zeros((6,6));A[:4,:4]=(-p.G+np.diag(beta))/p.cap[:,None];A[:4,5]=(p.G@np.full(4,p.ta)+q-35*beta)/p.cap
            A[4,:4]=beta;A[4,5]=q.sum()-35*beta.sum()+.30;memo[key]=expm(A*(e-t)/10000)
        x=memo[key]@x;err=max(err,max(abs(x[:4]-row[18:22])))
    assert m["status"]=="SAFE" and m["E_bounds"][0]<=x[4]<=m["E_bounds"][1] and err<1e-7
    dest=ROOT/"e1/certificates";dest.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(dest/(k+".npz"),events=tr)
    save("e1/certificates/"+k+".json",dict(sha=k,case=p.case,metrics=m,E35=val,switches=sw,expm_J=x[4],max_endpoint_error_K=err))
    cache[k]=m;return k,m

def gantt(p,plans,ids):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():font_manager.fontManager.addfont(str(font));plt.rcParams["font.family"]=font_manager.FontProperties(fname=str(font)).get_name()
    fig,axes=plt.subplots(3,2,figsize=(18,11),sharex=True,sharey=True)
    colors=["#09666A","#C06431","#325CA8","#793E75"]
    z0=min([10000]+[rs[i][2] for _,(rs,_),_ in plans for i in ids])-65
    z1=max(p.finish(i,rs[i]) for _,(rs,_),_ in plans for i in ids)+90
    output=[];em=[]
    for ax,(label,pl,m) in zip(axes.flat,plans):
        rs,low=pl;lay=Layout(p,rs)
        for u,work in enumerate(lay.by_unit):
            for s,e,k,i in work:
                if e<z0 or s>z1:continue
                mob=i in ids;scene=p.req[i//3]["scene"]
                ax.barh(3-u,(e-s)/10,left=s/10,height=.50,color=colors[u] if mob else "#dce0e4",edgecolor="white",linewidth=.5)
                if mob:
                    ax.annotate(str(i),(s/10,3-u+.25),xytext=(0,3 if i!=311 else 13),textcoords="offset points",fontsize=8,color=colors[u])
                output.append(dict(plan=label,stage=i,scene=scene,local=int(mob),device=NODES[u],opp=k,start_ms=s/10,end_ms=e/10))
        for a,b,d,k,f in lay.switches(low):
            if b<z0 or a>z1:continue
            for u in MEMBERS[d]:ax.barh(3-u,(b-a)/10,left=a/10,height=.75,color="#20252a",alpha=.75)
        ax.axvline(1000,ls="--",color="#a92337",lw=1)
        ax.set_title(f"{label}    {m['E_J']:.6f} J",loc="left",fontsize=12)
        ax.set_yticks([3,2,1,0],NODES);ax.tick_params(labelleft=True,labelbottom=True)
        ax.grid(axis="x",alpha=.18);ax.set_xlim(z0/10,z1/10);ax.set_ylim(-.6,3.9)
        base=plans[0][1][0]
        for i in ids:
            u,k,s=rs[i];w,f,t=base[i]
            em.append(dict(plan=label,stage=i,release_scene=p.req[i//3]["scene"],unit=NODES[u],opp=k,start_ms=s/10,
                end_ms=p.finish(i,rs[i])/10,old_unit=NODES[w],old_opp=f,shift_ms=(s-t)/10))
    fig.suptitle("D2 跨场景资源协调：共同 G3、历史见证及各权限组独立解",fontsize=17,x=.06,ha="left")
    fig.supxlabel("绝对时间（ms）　彩色为五个局部 Stage，灰色为固定任务，黑条为切换，虚线为场景边界")
    fig.tight_layout(rect=[0,.04,1,.95]);fig.savefig(ROOT/"e1/D2_gantt.png",dpi=150);plt.close(fig)
    table("e1/D2_timeline.csv",output);table("e1/D2_changes.csv",em)

def archive():
    regions=read("regions.json");results=[];values=[];cache={};d2=[]
    audited=[]
    for name,r0 in regions["regions"].items():
        if "ids" not in r0:continue
        r=restore(r0);p=Problem(r["case"]);_,base=archived(p.case);basek,bm=recert(p,base,cache)
        hist=None;history_groups=[]
        if p.case!="D3":
            _,hp=archived(p.case,True);hk,hm=recert(p,hp,cache);hist=(hk,hm)
            history_groups=next(t["membership"] for t in read("e0/replay.json") if t["case"]==p.case and t["historical"])
        rr=[read(f"e1/logs/{name}_P{g}.json") for g in range(4)]
        avail=[(basek,"G3")];best=[];LB=[max(x["LB"] for x in rr[g:]) for g in range(4)]
        if name=="D2":d2=[("原始 G3",base,bm),("v1.1 历史见证",hp,hm)]
        for g,z in enumerate(rr):
            pl=load_plan(z["own_plan"]);k,m=recert(p,pl,cache);assert k==z["own_plan"] and membership(p,base,pl,r,g)
            assert max(abs(a-b) for a,b in zip(m["E_bounds"],z["own"]["E_bounds"]))<1e-9
            avail.append((k,"P"+str(g)+" independent"))
            nested=min(avail,key=lambda a:cache[a[0]]["E_bounds"][1])
            candidates=avail+([ (hist[0],"v1.1 witness") ] if hist and history_groups[g] else [])
            pick=min(candidates,key=lambda a:cache[a[0]]["E_bounds"][1]);best.append(pick)
            bounded=cache[pick[0]];assert LB[g]<=bounded["E_bounds"][1]
            row=dict(region=name,case=p.case,group="P"+str(g),stages=len(r["ids"]),independent_SAFE_J=m["E_J"],
                own_L=z["LB"],true_L_J=LB[g],true_U_J=bounded["E_bounds"][1],upper_source=pick[1],upper_plan=pick[0],
                independent_plan=k,nested_new_U_J=cache[nested[0]]["E_bounds"][1],historical_member=history_groups[g] if hist else "",
                own_gain_lower_J=(bm["E_bounds"][0]-m["E_bounds"][1]) if k!=basek else 0.,
                own_gain_upper_J=(bm["E_bounds"][1]-m["E_bounds"][0]) if k!=basek else 0.,
                peak_upper_C=max(m["peak_hi"]),activity_J=m["activity_J"],base_J=m["base_J"],temperature_J=m["temperature_J"],
                switch_J=m["switch_J"],external_J=m["external_J"],switches=m["switch_count"],evaluated=z["independent_candidates"],
                termination=z["termination"],reference_best_J=z["E35_best_visited"],reference_optimum_J=z["E35_exact_optimum"],
                true_proven_optimizer=z["true_optimum_identity"] or "",unresolved=z["unresolved"])
            results.append(row)
            if name=="D2":d2.append(("P"+str(g)+" 独立搜索",pl,m))
        for g in range(1,4):
            ka,kb=best[g-1][0],best[g][0];a,b=cache[ka],cache[kb]
            lower=max(0.,math.nextafter(LB[g-1]-b["E_bounds"][1],-math.inf));upper=max(0.,math.nextafter(a["E_bounds"][1]-LB[g],math.inf))
            known_equal=rr[g]["true_optimum_identity"] and rr[g]["true_optimum_identity"]==rr[g-1]["true_optimum_identity"]
            if known_equal:lower=upper=0.;state="已证无改善"
            elif lower>0:state="已证严格额外节能"
            elif upper<=TOL:state="已证改善不超过容差"
            elif b["E_bounds"][1]<a["E_bounds"][0]:state="观察到额外节能"
            elif rr[g]["unresolved"] or rr[g-1]["unresolved"]:state="证据未决"
            else:state="有限搜索未发现改善"
            observed=0. if ka==kb else a["E_J"]-b["E_J"]
            values.append(dict(region=name,change=f"P{g-1}→P{g}",lower_J=lower,upper_J=upper,status=state,
                 observed_best_known_J=observed,larger_upper_source=best[g][1],
                 independent_difference_J=rr[g-1]["own"]["E_J"]-rr[g]["own"]["E_J"]))
    table("e1/results.csv",results);table("e1/conditional_values.csv",values)
    if d2:gantt(Problem("D2"),d2,[289,295,296,310,311])
    save("e1/audit.json",dict(unique_final_plans=len(cache),all_final_SAFE=True,regions=len(results)//4,certificate_layout="npz events: original 14 state columns + 17 continuous certificate columns"))
    report(results,values,regions)

def report(res,vals,regions):
    lines=["# P1 紧凑频域联合优化 E0/E1 诊断","",
       "## 紧凑模型一致性",""]
    e0=read("e0/gate.json");lines+=[f"门控通过。{e0['fixtures']} 个预先限定的小域中，两种独立生成方式得到相同物理排程集合，共 {e0['unique_test_schedules']} 个。五份实际时间表均能编码，切换、功率事件、精确参考分项、连续安全能耗与峰温证书通过复核。逐夹具数据见 e0/equivalence.csv，一般对应说明见 e0/model.md。","",
       "## 四级权限的真实安全能耗","",
       "|区域|权限|独立搜索/J|真实最优可靠区间/J|独立解较 G3 至少节能/mJ|切换次数|上界来源|","|---|---|---:|---:|---:|---:|---|"]
    for r in res:
        lines.append(f"|{r['region']}|{r['group']}|{r['independent_SAFE_J']:.8f}|[{math.floor(r['true_L_J']*1e6)/1e6:.6f}, {math.ceil(r['true_U_J']*1e6)/1e6:.6f}]|{math.floor(r['own_gain_lower_J']*1e6)/1000:.3f}|{r['switches']}|{r['upper_source']}|")
    lines+=["","每行独立从原 G3 开始。数学上界另可继承较小权限的安全计划，或使用属于该域的既有见证。参考目标、停止状态、能耗分项与原始独立上界见 e1/results.csv。","",
       "## 条件节能价值","",
       "|区域|权限变化|最佳已知解差/mJ|条件最优价值可靠区间/mJ|证据|","|---|---|---:|---:|---|"]
    for v in vals:lines.append(f"|{v['region']}|{v['change']}|{v['observed_best_known_J']*1000:.3f}|[{math.floor(v['lower_J']*1e6)/1000:.3f}, {math.ceil(v['upper_J']*1e6)/1000:.3f}]|{v['status']}|")
    lines+=["","## 历史见证与 D2 跨场景结构",""]
    for t in read("e0/replay.json"):
        if t["historical"]:lines.append(f"- {t['case']} 历史改善排程属于 "+ "、".join("P"+str(g) for g,b in enumerate(t["membership"]) if b)+"，统一作为归档见证。")
    lines+=["","D2 的 Stage 289、295 从第一场景释放，Stage 310 从第二场景释放，三者在原 G3 中共享 NPU。两个 post 是 296、311。各权限组的 OPP、起止、单元和重排结果见 D2_changes.csv 与 D2_timeline.csv。","",
      "![D2 跨场景甘特图](e1/D2_gantt.png)","","## 场景转换与内部区域",""]
    for name in ("R1","R2","R3","R4"):
        r=regions["regions"][name];group=[x for x in res if x["region"]==name]
        if not group:lines.append(f"- {name} 未取得预定请求数。");continue
        lines.append(f"- {name}，中心 {r['center_tick']/10:g} ms，选中的主 Stage 为 {r['selected_mains']}。P0–P3 各自相较 G3 的安全节能下界依次为 "+ "、".join(f"{x['own_gain_lower_J']*1000:.3f}" for x in group)+" mJ。")
    lines+=["","D3 不同中心的请求负载和局部结构不同。重叠 Stage 见 regions.json，区域间差异不作场景转换的因果估计。","",
       "## 立项判断",""]
    for g,label in [(1,"固定映射与次序的调频、移时"),(2,"开放次序"),(3,"开放映射")]:
        vv=[x for x in vals if x["change"].endswith("P"+str(g))]
        strict=[x["region"] for x in vv if x["status"]=="已证严格额外节能"]
        obs=[x["region"] for x in vv if x["status"]=="观察到额外节能"]
        lines.append(f"- {label}的严格条件收益已证实于 {('、'.join(strict) or '无')}；另观察到安全上界下降的区域为 {('、'.join(obs) or '无')}。")
    lines+=["","本轮止于有限权限诊断。优先考虑有严格证据并能解释具体生效决策的权限。仅有独立搜索上界差异时，复杂联合机制的必要性仍未决。"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
