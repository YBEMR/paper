"""Offline completion of partial-run evidence. No solver or optimization calls."""
import collections,csv,gzip,json,time
from design_d import ROOT,INITIAL,read,write,sha
from evidence_d import check_jobs
from report_d import stage,table
def rows(name):
    with (ROOT/name).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))

def main():
    import c1r_assets,bounded
    from base import Problem,decode,key,raw,evaluate,np,obj
    from flow_run import apply_delta
    from audit import thermal
    tag="NoCore_101";folder=ROOT/"runs"/tag
    ledger=read(ROOT/"execution.json");assert ledger["status"]=="FORMAL_INTERRUPTION" and len(ledger["runs"])==3
    with gzip.open(folder/"events.jsonl.gz","rb") as f:events=[json.loads(l) for l in f]
    with (folder/"accepted.jsonl").open("rb") as f:hist=[json.loads(l) for l in f]
    p=Problem("D3");plan=None;prev=None;prior=None;deltas=[]
    for v in hist:
        assert v["before"]==prev and v["metrics"]["status"]=="SAFE"
        plan=decode(v["full"]) if plan is None else apply_delta(plan,v)
        assert key(p,plan)==v["after"] and (prior is None or v["metrics"]["E_bounds"][1]<prior["E_bounds"][0])
        if v["phase"]=="joint":
            rr=dict(method="NoCore",seed=101,cycle=v["cycle"],iteration=v["it"],origin=v["origin"],config=len(v["cfg"]),
                shifted=len(v["moved"]),support=len(set(v["cfg"])|set(v["moved"])),shifted_devices=v["moved_devices"],
                cross_resource=int(len(v["moved_devices"])>=2),cross_scene=int(len(v["scenes"])>1),before=prev,after=v["after"],
                gain_lower_mJ=1000*(prior["E_bounds"][0]-v["metrics"]["E_bounds"][1]),scope="interrupted_prefix")
            assert rr["config"]<=12 and rr["support"]<=24;deltas.append(rr)
        prev=v["after"];prior=v["metrics"]
    assert hist[0]["after"]==INITIAL
    true=evaluate(p,plan,cert=True,trace=True);ev=np.asarray(true.pop("events"))
    assert raw(true)==raw(prior)
    cert=thermal(p,plan,ev,true,{})
    write(folder/"partial_certificate.json",dict(sha=prev,accepted_at=hist[-1]["t"],metrics=true,independent=cert,ranked=False))
    np.savez_compressed(folder/"partial_trace.npz",events=ev)
    (folder/"partial_plan.json.gz").write_bytes(gzip.compress(raw(obj("D3",plan)),mtime=0))
    subs=[v for v in events if v["event"]=="subproblem"];failed=len(subs)
    tail=[v for v in events if v["it"]==failed]
    assert len([v for v in tail if v["event"]=="initialization_timeout"])==2 and not any(v["event"]=="certificate" for v in tail)
    lifecycle=("worker_start","worker_boot","worker_ready","worker_exit","initialization_timeout")
    prefix=[v for v in events if v["it"]!=failed]+[dict(v,it=None) for v in tail if v["event"] in lifecycle]
    verified=check_jobs(folder,prefix,"NoCore");mod_calls=verified.pop("modules")
    interrupted=ledger["runs"][-1]
    verified.update(status="INTERRUPTED",exit_s=interrupted["exit_s"],open_iteration=failed,
         open_iteration_events=tail,open_iteration_wall_upper_s=interrupted["exit_s"]-780,
         lifecycle=[v for v in events if v["event"] in lifecycle],last_safe=prev,last_safe_time=hist[-1]["t"],ranked=False)
    for name in ("timing.json","results.csv","phase_results.csv","module_results.csv","accepted_changes.csv","curves.csv.gz"):
        assert (ROOT/name).is_file()
    ts=read(ROOT/"timing.json");assert tag not in ts["formal"]
    ts["formal"][tag]=verified;ts["complete_endpoints"]=2;ts["interrupted_runs"]=1
    write(ROOT/"timing.json",ts)
    def at(t):return next((v for v in reversed(hist) if v["t"]<=t),hist[0])
    gset={i for v in events if v["event"]=="move" for i in v["st"]}
    cset={i for v in events if v["event"] in ("selection","core_region") for i in v.get("ids",v.get("st",[]))}
    result=rows("results.csv");r=next(r for r in result if r["method"]=="NoCore" and r["seed"]=="101")
    assert r["status"]=="INTERRUPTED" and not r["E900"]
    for t in (180,300,600):
        h=at(t)["metrics"];r.update({f"E{t}":h["E_J"],f"lo{t}":h["E_bounds"][0],f"hi{t}":h["E_bounds"][1]})
    r.update(restarts=verified["restarts"],init_timeouts=2,exit_s=interrupted["exit_s"],iterations=failed,
        stages=len(gset|cset),coverage=len(gset|cset)/2400,cp_stages=len(cset),accepted=len(hist)-1,
        steps=sum(v["event"]=="move" for v in events),multi=sum(v["config"]>=2 for v in deltas),
        max_support=max(v["support"] for v in deltas),partial_safe_J=true["E_J"],partial_safe_lo=true["E_bounds"][0],
        partial_safe_hi=true["E_bounds"][1],partial_safe_at=hist[-1]["t"],partial_sha=prev)
    table("results.csv",result,["method","seed","status"])
    change=rows("accepted_changes.csv");table("accepted_changes.csv",change+deltas,["method","seed","cycle","iteration","config","support"])
    mods=rows("module_results.csv");ph=rows("phase_results.csv")
    en={v["after"]:v["metrics"]["E_J"] for v in hist}
    for cycle in (1,2,3):
        broad=(cycle-1)*300+180;end=min(cycle*300,interrupted["exit_s"])
        before=at((cycle-1)*300);mid=at(broad);last=at(end)
        gains=collections.Counter();improves=collections.Counter()
        for s in (v for v in subs if v["cycle"]==cycle):
            e=en[s["source"]]
            for origin,h,v,b in s["improvements"]:
                k=stage(origin);gains[k]+=e-v;improves[k]+=1;e=v
        assert abs(sum(gains.values())-(mid["metrics"]["E_J"]-last["metrics"]["E_J"]))<1e-7
        for phase,x,y,cut in (("G3",before,mid,broad),("joint",mid,last,cycle*300)):
            ph.append(dict(method="NoCore",seed=101,cycle=cycle,phase=phase,before=x["after"],after=y["after"],
                net_J=en[x["after"]]-en[y["after"]],scheduled_end=cut,status="INTERRUPTED_PREFIX" if cycle==3 and phase=="joint" else "completed_phase_in_interrupted_run",
                hint_J=gains["hint"] if phase=="joint" else 0,aux_cp_J=gains["aux_cp"] if phase=="joint" else 0,
                core_J=0,fallback_J=gains["fallback"] if phase=="joint" else 0,ordinary_full_J=gains["ordinary_full"] if phase=="joint" else 0))
        for mod in ("hint","aux_cp","compact_core","ordinary_full","fallback"):
            c=[v for v in mod_calls if v["cycle"]==cycle and v["module"]==mod]
            a=[v for v in deltas if v["cycle"]==cycle and stage(v["origin"])==mod]
            mods.append(dict(method="NoCore",seed=101,cycle=cycle,module=mod,calls=len(c),wall_s=sum(v["seconds"] for v in c),
                censored=sum(v["censored"] for v in c),accepted=len(a),ordered_improvements=improves[mod],ordered_gain_J=gains[mod],
                certified_candidates=sum(v["event"]=="certificate" and v["cycle"]==cycle and v["on_time"] and stage(v["stage"])==mod for v in events),
                multi=sum(v["config"]>=2 for v in a),changed_configs=sum(v["config"] for v in a),max_support=max([0]+[v["support"] for v in a]),scope="interrupted_prefix"))
        g=[v for v in hist if v["cycle"]==cycle and v["phase"]=="G3"]
        mods.append(dict(method="NoCore",seed=101,cycle=cycle,module="g3",calls=1,accepted=len(g),ordered_improvements=len(g),
              ordered_gain_J=en[before["after"]]-en[mid["after"]],scope="interrupted_prefix; exact earlier G3 end stamps unavailable"))
    table("module_results.csv",mods,["method","seed","cycle","module","calls","wall_s","accepted","ordered_gain_J"])
    table("phase_results.csv",ph,["method","seed","cycle","phase","net_J"])
    with gzip.open(ROOT/"curves.csv.gz","at",encoding="utf8",newline="") as f:
        cw=csv.writer(f,lineterminator="\n")
        for v in hist:cw.writerow(["NoCore",101,v["t"],v["metrics"]["E_J"],*v["metrics"]["E_bounds"],v["after"]])
    print("independently verified partial incumbent; recovered",len(hist),"states and",failed,"completed subproblems")
def finish_report():
    r=rows("results.csv");ms=rows("module_results.csv");timing=read(ROOT/"timing.json")["formal"]
    ledger=read(ROOT/"execution.json");ref=timing["NoCore_101"]
    q=next(z for z in rows("paired.csv") if z["result"]=="win")
    lines=["# E2-d 模块消融与工程停止报告","","**暂时保留 Full。** 九项正式运行完成两项，一项在第 809.391 秒按重复初始化故障规则停止，其余六项未启动。只有一项同种子终点配对可判定，无法计算三种子中位数和范围，也无法判断专门 Core 的独立保留价值。","","## 种子 101 的完整系统安全能耗","","|方法|180 s / J|300 s / J|600 s / J|900 s / J|已完成联合迭代|多配置接纳|","|---|---:|---:|---:|---:|---:|---:|"]
    for z in r:
        if z["seed"]=="101":
            vals=[f"{float(z[k]):.6f}" if z[k] else "未到达" for k in ("E180","E300","E600","E900")]
            lines.append("|"+z["method"]+"|"+"|".join(vals)+f"|{z['iterations']}|{z['multi']}|")
    lines+=["",f"NoAux 较 Full 节省 {float(q['full_minus_ablation_J']):.9f} J，区间差为 [{float(q['difference_lo_J']):.9f}, {float(q['difference_hi_J']):.9f}] J。两项 900 秒终点均通过原连续认证器和独立矩阵指数复核，峰温上界分别为 62.3514°C、62.5219°C，最小期限余量均为 0 ms。两方法末 180 秒的可靠改善分别为 1.634318 J、0.806516 J。三个已启动运行均触及全部 2400 个 Stage。","","NoCore 的最后一次接纳在 774.581 秒，能耗 58.145077176 J。其排程、连续证书及独立热轨迹已保存为 partial_plan.json.gz、partial_certificate.json 和 partial_trace.npz。该值只描述中断前状态，900 秒终点和对应配对保持空缺。","","## 各模块已观察到的贡献","","以下为种子 101。NoCore 只统计中断前已观测的工作。顺序增量以同一固定前态的逐阶段累计最佳计算；接纳次数按最终更新下一轮前态的来源计。","","|方法|模块|调用|墙钟秒|实际接纳|顺序节能 / J|","|---|---|---:|---:|---:|---:|"]
    for method in METHODS_LOCAL:
        for mod in ("hint","aux_cp","compact_core","fallback","ordinary_full"):
            sel=[x for x in ms if x["method"]==method and x["module"]==mod]
            sums=[sum(float(x[k]) for x in sel) for k in ("calls","wall_s","accepted","ordered_gain_J")]
            lines.append(f"|{method}|{mod}|{sums[0]:.0f}|{sums[1]:.3f}|{sums[2]:.0f}|{sums[3]:.6f}|")
    lines+=["","Full 中紧凑辅助 CP 提供了 0.906798 J 顺序节能；专门 Core 调用 29 次，合计 121.649 秒，顺序节能 0.006336 J。NoAux 将节省的时间用于更多迭代，完成 58 次，Full 为 42 次。一次配对无法满足预设的至少两次严格胜出及中位数更低的条件，也无法推出同时删除两个模块的效果。","","## 初始化故障与停止依据","","种子 103 的三个 120 秒短运行均通过。E2-a 回归、46 项紧凑等价验证、48 次 G3 随机续接及模块开关检查通过。预检期间 NoAux 曾跨阶段重启一次，成功就绪。E2-c2 种子 103 前两阶段原有的 14 次启动、7.55 毫秒越界和退出观测延迟保留在历史记录。","","NoCore／101 的初次工作进程在 3.550 秒内就绪，其中导入 3.075 秒、加载资产 0.030 秒。第 2 周期末，第 38 个子问题只剩约 1.37 秒执行提示，截止清理在第 598.107 秒终止了原进程。第 3 周期 G3 完成后，第 39 个子问题尝试重新创建工作进程。两次均已进入解释器，分别等待 9.610 和 18.639 秒仍未收到 ready，清理用时分别为 0.031 和 0.080 秒。该子问题没有进入数值模块，也没有接纳候选。失败启动的导入和资产加载细分只会随 ready 一起发出，因此底层阻塞位置未决。","","两个完整运行均无重启、无初始化超时。中断的 NoCore 有 2 次重启尝试、2 次初始化超时。修正后的 timing.json 包含三项运行。已完成子问题的模块数据均经交接日志核对；被终止的模块在 module_results.csv 标注 censored。中断运行第 39 个子问题的墙钟上界为 29.391 秒。","","## 预算与数据","","预检计费 443.442 秒。三个已启动的 900 秒窗口均按满额保守计费，正式预算使用 2700/8100 秒。独立核验与归档合并计入 900 秒辅助额度。最终总计见归档回执。本轮已停止，未补跑或打开 1800 秒确认。","","[逐次运行与分项能耗](results.csv) · [配对区间](paired.csv) · [模块](module_results.csv) · [周期](phase_results.csv) · [计时与故障](timing.json)"]
    (ROOT/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
    write(ROOT/"decision.json",dict(decision="暂时保留 Full；两种模组的独立保留价值未决",eligible=[],verified=2,partial_certified=1,interrupted=1,not_started=6,next_runs=0))
METHODS_LOCAL=("Full","NoAux","NoCore")
if __name__=="__main__":
    main()
    finish_report()
