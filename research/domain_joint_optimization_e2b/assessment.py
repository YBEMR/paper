"""Offline audit of all run receipts. No results are made available to another search."""
import itertools,math,statistics
from scipy.linalg import expm
from base import *
from model import independent_events
from validation import common_grid
METH=["G3","CP-FO","CP-LNS","Proposed","Proposed-Single","Proposed-NoOrder"]
def stream(path):
    with gzip.open(path,"rt",encoding="utf8") as f:
        for line in f:yield json.loads(line)
def audit_final(p,plan,stored,where):
    m=evaluate(p,plan,cert=True,trace=True);events=np.asarray(m.pop("events"))
    assert m["status"]=="SAFE" and m["E_bounds"]==stored["E_bounds"] and m["peak_hi"]==stored["peak_hi"]
    lay=Layout(p,plan[0]);a,b=common_grid(lay.events(plan[1]),events[:,:14]);assert np.array_equal(a,b)
    x=np.r_[p.initial,0.,1.];memo={};err=0.
    for row in events:
        t,e=row[:2];q=row[2:6];beta=row[6:10];k=(e-t,*q,*beta)
        if k not in memo:
            A=np.zeros((6,6));A[:4,:4]=(-p.G+np.diag(beta))/p.cap[:,None]
            A[:4,5]=(p.G@np.full(4,p.ta)+q-35*beta)/p.cap;A[4,:4]=beta;A[4,5]=q.sum()-35*beta.sum()+.3
            memo[k]=expm(A*(e-t)/10000)
        x=memo[k]@x;err=max(err,max(abs(x[:4]-row[18:22])))
    assert m["E_bounds"][0]<=x[4]<=m["E_bounds"][1] and err<1e-7 and m["min_deadline_slack_ms"]>=-1e-9
    save(where/"final_certificate.json",dict(plan=key(p,plan),metrics=m,expm_J=x[4],max_endpoint_error_K=err))
    np.savez_compressed(where/"final_certificate.npz",events=events)
    (where/"final_plan.json.gz").write_bytes(gzip.compress(raw(obj(p.case,plan)),compresslevel=6,mtime=0))
    return m
def inspect_run(case,method,seed,p,initial,base_metrics,lb):
    tag=f"{case}_{method}_{seed}";folder=ROOT/"runs"/tag;s=read(folder/"summary.json")
    hist=list(stream(folder/"history.jsonl.gz"));assert hist and hist[0]["after"]==initial and hist[-1]["after"]==s["final"]
    assert len(hist)-1==s["accepted"] and 0<len(s["windows"])<=s["total_windows"]
    active={};last=None;actual=Counter();mechanisms=[];origin=initial
    iterations=folder/"iterations.jsonl.gz"
    if iterations.exists():
        for z in stream(iterations):
            assert z["source"]==origin
            if z.get("status")=="TIME_LIMIT":continue
            assert z["cp_seed"]==seed and all(a["seed"]==seed for a in z["solves"])
            assert set(z["Sf"])<=set(z["St"]) and len(z["St"])<=24 and len(z["Sf"])<=12
            if "adopted" in z:
                active[z["adopted"]]=z;origin=z["adopted"]
        assert origin==s["final"]
    gain_points=[];inc0=None;prev_time=-1.
    for h,packed in itertools.zip_longest(hist,stream(folder/"plans.jsonl.gz")):
        ident,body=packed;plan=decode(body);assert key(p,plan)==ident==h["after"]
        assert h["t"]>=prev_time and h["t"]<=1800 and h["metrics"]["status"]=="SAFE"
        assert abs(sum(h["metrics"][k] for k in ("activity_J","base_J","temperature_J","switch_J","external_J"))-h["metrics"]["E_J"])<1e-8
        gain_points.append((h["t"],h["metrics"]["E_J"],h["metrics"]["E_bounds"],ident));prev_time=h["t"]
        if last:
            assert h["before"]==last[0] and h["metrics"]["E_bounds"][1]<last[2]["E_bounds"][0]
            delta=h["actual"];a=changes(p,last[1],plan)
            assert raw(a)==raw(delta)
            cfg=delta["config"];moved=delta["moved"];inv=delta["inversions"]
            actual["multi"]+=len(cfg)>=2;actual["shifted"]+=len(moved);actual["order"]+=bool(inv)
            actual["config"]+=len(cfg);actual["cross_scene"]+=len(delta["scenes"])>=2
            z=active.get(ident);op=z["operator"] if z else {};opname=op.get("operator","G3")
            trace=op.get("conditional",[]);last_try=trace[-1] if trace else {}
            planned={int(i):tuple(v) for i,v in op.get("targets",[])}
            adopted=[i for i in cfg if i in planned and plan[0][i][:2]==planned[i]]
            support=set(last_try.get("final",{}).get("support",[]))
            real_support=[i for i in delta["only_timing"] if i in support and any(plan[0][i][0]!=plan[0][j][0] for j in adopted)]
            previous_rows=last[1][0]
            paid=[i for i in op.get("compensation",[]) if i in cfg and p.dur(i,*plan[0][i][:2])<p.dur(i,*previous_rows[i][:2])]
            released={tuple(x) for x in op.get("released",[])}
            used_edges=[v for v in inv if (v[0],min(v[1:]),max(v[1:])) in released]
            special=opname=="configuration_support"
            if method=="Proposed-Single":assert len(cfg)<=1
            if method=="CP-FO":assert not inv and all(plan[0][i][0]==previous_rows[i][0] for i in cfg)
            row=dict(run=tag,case=case,method=method,seed=seed,t=h["t"],before=last[0],after=ident,
                operator=opname,config_n=len(cfg),moved_n=len(moved),timing_only_n=len(delta["only_timing"]),inversions=len(inv),
                target_combo_real=int(special and len(adopted)>=2),cross_resource_support=int(special and bool(real_support)),
                compensation_used=int(special and bool(paid)),special_order_used=int(special and bool(used_edges)),
                scenes=delta["scenes"],cross_scene=int(len(delta["scenes"])>1),gain_lower_mJ=1000*(last[2]["E_bounds"][0]-h["metrics"]["E_bounds"][1]))
            mechanisms.append(row)
        last=(ident,plan,h["metrics"])
    cert=audit_final(p,last[1],s["metrics"],folder)
    def at(t):return next((v for v in reversed(gain_points) if v[0]<=t),gain_points[0])
    E=cert["E_J"];e0=base_metrics["E_J"];lo,hi=cert["E_bounds"]
    r=dict(run=tag,case=case,method=method,seed=seed,initial=initial,final=s["final"],SAFE_J=E,lower_cert_J=lo,upper_cert_J=hi,
           initial_J=e0,net_gain_pct=(e0-E)/e0*100,gain_lower_mJ=1000*(base_metrics["E_bounds"][0]-hi),
           E180_J=at(180)[1],E900_J=at(900)[1],E1800_J=at(1800)[1],last_180s_gain_lower_mJ=max(0,1000*(at(1620)[2][0]-hi)),
           last_improvement_s=gain_points[-1][0],global_L_exact=str(lb),global_L_J=math.nextafter(float(lb),-math.inf),
           open_gap_J=math.nextafter(hi-math.nextafter(float(lb),-math.inf),math.inf),peak_upper_C=max(cert["peak_hi"]),
           min_slack_ms=cert["min_deadline_slack_ms"],activity_J=cert["activity_J"],residency_J=cert["base_J"],
           thermal_J=cert["temperature_J"],switch_J=cert["switch_J"],external_J=cert["external_J"],switch_count=cert["switch_count"],
           accepted=s["accepted"],multi_config_updates=actual["multi"],shifted_stages_sum=actual["shifted"],order_updates=actual["order"],
           cross_scene_updates=actual["cross_scene"],windows_covered=len(s["windows"]),total_windows=s["total_windows"],stages_visited=s["stages"],
           stages_total=s["reach_n"],elapsed_s=s["elapsed_s"],cpu_s=s["cpu_s"])
    assert r["open_gap_J"]>=0 and r["E1800_J"]==E
    return r,mechanisms,gain_points
def plot(curves):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13.2,4.3));grid=np.arange(0,1801,10)
    for ax,case in zip(axes,("D1","D2","D3")):
        for method in METH:
            ys=[]
            for seed in (101,102,103):
                arr=curves.get((case,method,seed))
                if arr is None:continue
                ts=np.array([v[0] for v in arr]);energy=np.array([v[1] for v in arr])
                ys.append(energy[np.maximum(0,np.searchsorted(ts,grid,side="right")-1)])
            if ys:ax.step(grid,np.median(ys,axis=0),where="post",label=method,lw=2 if method=="Proposed" else 1.2)
        ax.set_title(case);ax.set_xlabel("Search time (s)");ax.grid(alpha=.2);ax.set_xlim(0,1800)
    axes[0].set_ylabel("Best certified energy (J)");fig.legend(*axes[-1].get_legend_handles_labels(),loc="lower center",ncol=6)
    fig.tight_layout(rect=[0,.10,1,1]);fig.savefig(ROOT/"energy_time.png",dpi=145);plt.close(fig)
def main():
    man=read(ROOT/"manifest.json");rows=[];mech=[];curves={};cases={}
    for c,m,s in man["design"]:
        if c not in cases:
            p=Problem(c);k,plan=archived(c);cases[c]=(p,k,evaluate(p,plan,cert=True),Q(p.lower()["total"]))
        r,actions,pts=inspect_run(c,m,s,*cases[c]);rows.append(r);mech.extend(actions);curves[c,m,s]=pts
    table(ROOT/"results.csv",rows);table(ROOT/"accepted_mechanisms.csv",mech)
    table(ROOT/"cross_scene.csv",[m for m in mech if m["cross_scene"]] or [dict(status="none")])
    lookup={(r["case"],r["method"],r["seed"]):r for r in rows};paired=[]
    for (c,m,s),r in lookup.items():
        if m=="Proposed":continue
        target=lookup[c,"Proposed",s];a=r["lower_cert_J"]-target["upper_cert_J"];b=r["upper_cert_J"]-target["lower_cert_J"]
        paired.append(dict(case=c,seed=s,baseline=m,difference_mJ=(r["SAFE_J"]-target["SAFE_J"])*1000,
            lower_mJ=math.nextafter(a*1000,-math.inf),upper_mJ=math.nextafter(b*1000,math.inf),
            result="win" if a>0 else "loss" if b<0 else "overlap",
            difference_180_mJ=(r["E180_J"]-target["E180_J"])*1000,difference_900_mJ=(r["E900_J"]-target["E900_J"])*1000))
    table(ROOT/"paired.csv",paired)
    with gzip.open(ROOT/"curves.csv.gz","wt",encoding="utf8",newline="") as f:
        w=csv.writer(f,lineterminator="\n");w.writerow(["case","method","seed","seconds","SAFE_J","lower_J","upper_J","sha"])
        for (c,m,s),pts in curves.items():
            for t,e,b,k in pts:w.writerow([c,m,s,t,e,*b,k])
    plot(curves);stats=[]
    for c in cases:
        for m in METH:
            ms=sorted((r for r in rows if r["case"]==c and r["method"]==m),key=lambda r:r["seed"])
            if not ms:continue
            v=[r["SAFE_J"] for r in ms];stats.append(dict(case=c,method=m,seed101_J=v[0],seed102_J=v[1],seed103_J=v[2],
                median_J=statistics.median(v),min_J=min(v),max_J=max(v),median_gain_pct=statistics.median(r["net_gain_pct"] for r in ms)))
    table(ROOT/"summary.csv",stats)
    outcome=lambda method:Counter(z["result"] for z in paired if z["baseline"]==method)
    direct=outcome("CP-LNS");single=outcome("Proposed-Single");noorder=outcome("Proposed-NoOrder")
    acts=[a for a in mech if a["method"]=="Proposed"];co=sum(a["cross_resource_support"] for a in acts)
    positive=direct["win"]==9 and single["win"]==9 and co>0 and any(a["target_combo_real"] for a in acts)
    title="支持在三个已测工况上继续研究该联合机制" if positive else "本轮未建立满足预设条件的跨工况核心算法优势"
    lines=["# E2-b 完整任务流联合节能优化","",f"**{title}。** 普通 CP-LNS 的九个同工况、同种子配对中，Proposed 严格胜 {direct['win']}、负 {direct['loss']}、认证区间重叠 {direct['overlap']}。相对 Single 的对应计数为 {single['win']}、{single['loss']}、{single['overlap']}。D3 上相对 NoOrder 为 {noorder['win']}、{noorder['loss']}、{noorder['overlap']}。","",
        "## 1800 秒末完整安全能耗","",
        "|工况|方法|种子 101 / J|种子 102 / J|种子 103 / J|中位数 / J|中位净节能率|","|---|---|---:|---:|---:|---:|---:|"]
    for z in stats:lines.append(f"|{z['case']}|{z['method']}|{z['seed101_J']:.7f}|{z['seed102_J']:.7f}|{z['seed103_J']:.7f}|{z['median_J']:.7f}|{z['median_gain_pct']:.3f}%|")
    lines+=["","## Proposed 相对各基线的配对差额","","正值表示 Proposed 的最终全窗能耗更低。每行依次为种子 101、102、103，单位 mJ。完整认证上下端及三个时点见 paired.csv。","",
           "|工况|基线|101|102|103|","|---|---|---:|---:|---:|"]
    for c in cases:
        for m in METH:
            z=sorted((x for x in paired if x["case"]==c and x["baseline"]==m),key=lambda x:x["seed"])
            if z:lines.append("|"+c+"|"+m+"|"+"|".join(f"{x['difference_mJ']:.3f}" for x in z)+"|")
    lines+=["","![三个种子的安全能耗中位轨迹](energy_time.png)","","## 已采用的机制","",
         f"Proposed 共接受 {len(acts)} 次严格改善，其中 {sum(a['config_n']>=2 for a in acts)} 次实际同时改变至少两项配置。{sum(a['target_combo_real'] for a in acts)} 次采用至少两个暂定目标配置，{co} 次实际采用跨资源移时支撑，{sum(a['compensation_used'] for a in acts)} 次实际采用加速补偿，{sum(a['special_order_used'] for a in acts)} 次用了专门释放的次序对。这些事件可以重叠。"]
    cross=[a for a in acts if a["cross_scene"]]
    if cross:
        a=max(cross,key=lambda z:z["gain_lower_mJ"])
        lines+=["",f"跨场景接受 {len(cross)} 次。最大单次安全节能下限为 {a['gain_lower_mJ']:.3f} mJ，来自 {a['run']} 的 {a['t']:.2f} s。涉及 {a['config_n']} 项配置变化、{a['moved_n']} 项移时、{a['inversions']} 个同设备相对次序反转。对应前后排程为 {a['before']} 与 {a['after']}。场景按请求释放记录划分。"]
    else:lines+=["","Proposed 本轮无跨场景的严格接受记录。"]
    lines+=["","## 解质量与覆盖","",f"48 个终点全部通过独立事件和矩阵指数复核。{sum(r['windows_covered']==r['total_windows'] for r in rows)} 个运行访问了全部释放窗口，逐 Stage 覆盖与全局下界在 results.csv。48 个运行中 {sum(r['last_180s_gain_lower_mJ']>0 for r in rows)} 个在最后 180 s 仍有可认证改善。原全局下界来自原模型有效温区功率下界，未闭合差距逐运行列出。三个种子的比较仅用于初步稳定性判断。","",
        "每个运行的 plans.jsonl.gz 保存全部接受状态的完整物理排程，history.jsonl.gz 给出前后身份、分项及真实变化。CP 的 iterations.jsonl.gz 保存候选、当前排程绑定的边界、时序路径、缺口与释放次序。G3 的 moves.jsonl.gz 保存冻结随机重构的选点。","",
        "本轮结束于 D1–D3 的固定预算验证，H1–H3 和第四章未启动。"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
    save(ROOT/"audit.json",dict(terminal_certificates=len(rows),paired=len(paired),accepted=len(mech),
        certified_comparison_to_CPLNS=direct,certified_comparison_to_Single=single,certified_comparison_to_NoOrder=noorder,decision=title))
if __name__=="__main__":main()
