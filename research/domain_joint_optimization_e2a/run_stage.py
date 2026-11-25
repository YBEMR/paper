import math,platform
from assets_e2 import *
from reference_objective import Core,PJ,error_bound
from verify_core import check
from master import solver,cp

def inputs():
    lock=read("inputs.lock.json");head=git("rev-parse","HEAD").decode().strip()
    assert git("rev-parse","HEAD^").decode().strip()==BASE
    hist=read(E1/"manifest.json");snapshot=read(E1/"snapshot.json");verified={}
    def verify(path,sig):
        data=path.read_bytes();val=sha(data);assert val==sig,path
        verified[path.relative_to(REPO).as_posix()]=val
    for rel,key in lock["blobs"].items():
        b=(REPO/rel).read_bytes()
        assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==key,rel
        verify(REPO/rel,sha(b))
    for name,h in snapshot["files"].items():verify(E1/name,h)
    for name,h in hist["identities"].items():verify(REPO/name,h["sha256"])
    sources={}
    for p in [*HERE.glob("*.py"),HERE/"model.md",HERE/"taskbook.md",HERE/"inputs.lock.json"]:
        blob=git("rev-parse",head+":"+p.relative_to(REPO).as_posix()).decode().strip()
        b=p.read_bytes();assert hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()==blob
        sources[p.name]=dict(git_blob=blob,sha256=sha(b))
    for name in ["D1","D2","D3"]:
        k,plan=archived(name);assert k==hist["plans"][name]["g3"]
    write("manifest.json",dict(freeze=head,base=BASE,inputs=verified,sources=sources,environment=dict(
          python=sys.version,platform=platform.platform(),packages={n:version(n) for n in ("ortools","protobuf","numpy","scipy","numba")}),
          workers=1,seed=101,windows_tick_ms="1/10",reference_unit="pJ",budgets=[300,1200,900,18*60,600,4080,4500]))

def smoke(name,group,end):
    start=time.perf_counter();p,seed,r=region(name);seed=(seed[0],Layout(p,seed[0]).normalize(seed[1]))
    k0,bm=certify(p,seed);best=(k0,bm);receipts={};runs=[]
    core=Core(p,seed,r["ids"],group,region=r);built=time.perf_counter()-start
    old=core.master
    # The master proto now also contains E2-a. Count the inherited master on a fresh identical domain.
    from master import Master
    old=Master(p,seed[0],r["ids"],group)
    warm=core.m.clone()
    for var,val in core.assignment(seed):warm.add(var==val)
    sl=solver(min(4,max(.05,end-time.perf_counter()-10)));status=sl.solve(warm)
    assert status in (cp.OPTIMAL,cp.FEASIBLE),("G3 fixed hint",sl.status_name(status))
    assert core.plan(sl)==seed
    core.m.clear_hints()
    for j in range(len(core.m.proto.variables)):
        var=core.m.get_int_var_from_proto_index(j)
        core.m.add_hint(var,sl.value(var))
    def keep(plan,parts,switches):
        nonlocal best
        k=sha(raw(obj(p.case,plan)))
        if k in receipts:return
        exact,err=check(p,plan,parts,switches)
        key,m=certify(p,plan);assert key==k
        receipts[k]=dict(sha=k,CP_pJ=sum(parts.values()),parts_pJ=parts,E35_J=str(sum(exact.values())),error_J=str(err),
                         status=m["status"],true_E=m["E_bounds"],peak_upper=max(m["peak_hi"]),
                         stage_changes=sum(a!=b for a,b in zip(plan[0],seed[0])),control_changes=len(plan[1]^seed[1]))
        if m["status"]=="SAFE" and m["E_bounds"][1]<best[1]["E_bounds"][0]:best=(k,m)
    keep(seed,{k:sl.value(v) for k,v in core.parts.items()},core.switches(sl))
    for j in range(2):
        remaining=end-time.perf_counter()
        if remaining<=4:break
        budget=min(22.,remaining-4) if j==0 else remaining-4
        out,log=core.candidates(budget,limit=8,exclude=[seed] if j else [],presolve=(j!=0));runs.append(log)
        for plan,parts,sw in out:keep(plan,parts,sw)
    row=dict(region=name,group="P"+str(group),seed=k0,best=best[0],seed_J=bm["E_J"],best_SAFE_J=best[1]["E_J"],
             best_bounds=best[1]["E_bounds"],best_peak_upper_C=max(best[1]["peak_hi"]),physical_candidates=len(receipts),
             nonseed_rows=sum(z["stage_changes"]>0 for z in receipts.values()),build_s=built,
             variables=len(core.m.proto.variables),constraints=len(core.m.proto.constraints),
             master_vars=len(old.m.proto.variables),master_constraints=len(old.m.proto.constraints),arcs=core.arcs,
             maximum_int_envelope=core.int_bound,objective_error_bound_J=float(error_bound(p)),
             statuses="/".join(z["status"] for z in runs),local_elapsed_s=time.perf_counter()-start)
    write("smoke/"+name+"_P"+str(group)+".json",dict(summary=row,solves=runs,candidates=list(receipts.values()),blocks=core.blocks))
    print(name,group,len(receipts),row["statuses"],flush=True)

def audit():
    finite=read("validation/finite_gate.json");replay=read("validation/replay_gate.json")
    assert finite["original"]==109 and replay["passed"]
    rows=[];keys=set()
    for path in sorted((HERE/"smoke").glob("*_P?.json")):
        z=read(path);r=z["summary"];rows.append(r);keys.update(w["sha"] for w in z["candidates"])
        assert r["seed"]==archived("D3" if r["region"][0]=="R" else r["region"])[0]
    assert len(rows)==len({(r["region"],r["group"]) for r in rows})==18
    table("smoke/results.csv",rows)
    # Compare the stored certified traces to fresh independent events and a separate dense matrix exponential.
    from scipy.linalg import expm
    audit_rows=[];problems={};memo={}
    for path in sorted((HERE/"certificates").glob("*.json")):
        z=read(path);key=z["sha"];data=gzip.decompress((HERE/"plans"/(key+".json.gz")).read_bytes());assert sha(data)==key
        if z["case"] not in problems:problems[z["case"]]=Problem(z["case"])
        p=problems[z["case"]];pl=decode(json.loads(data));ev,sw=independent_events(p,*pl)
        with np.load(path.with_suffix(".npz")) as tr:trace=tr["events"]
        assert np.array_equal(ev,trace[:,:14])
        x=np.r_[p.initial,0.,1.];maxerr=0
        for row in trace:
            s,e=row[:2];q=row[2:6];b=row[6:10];ident=(p.case,e-s,*q,*b)
            if ident not in memo:
                A=np.zeros((6,6));A[:4,:4]=(-p.G+np.diag(b))/p.cap[:,None]
                A[:4,5]=(p.G@np.full(4,p.ta)+q-35*b)/p.cap;A[4,:4]=b;A[4,5]=q.sum()-35*b.sum()+.3
                memo[ident]=expm(A*(e-s)/10000)
            x=memo[ident]@x;maxerr=max(maxerr,max(abs(x[:4]-row[18:22])))
        met=z["metrics"];assert met["E_bounds"][0]<=x[4]<=met["E_bounds"][1] and maxerr<1e-7
        audit_rows.append(dict(sha=key,status=met["status"],expm_J=x[4],max_endpoint_err_K=maxerr))
    table("validation/independent_audit.csv",audit_rows)
    useful=sum(r["nonseed_rows"]>0 for r in rows)
    verdict=("核心通过基本规模可用性检查" if useful==18 else "部分区域的联合候选生成受限")
    write("validation/acceptance.json",dict(correct=True,engineering=verdict,groups_with_task_changes=useful,
          groups_with_alternatives=sum(r["physical_candidates"]>1 for r in rows),smoke_unique=len(keys),audited=len(audit_rows)))
    f=csv_rows(HERE/"validation/finite.csv")
    lines=["# E2-a 完整频域能耗联合求解核心","",f"**正确性验证通过。{verdict}。** 18 个区域权限组合中，{useful} 个返回了改变任务配置或时刻的候选。","",
       "## 正确性证据","",
       "|小域|理论编码数|规范化物理解|CP 所选解达到有理数最优|最大绝对误差 / µJ|","|---|---:|---:|---|---:|"]
    for z in f:lines.append(f"|{z['fixture']}|{z['theory']}|{z['CP']}|{z['same_optimum']}|{1e6*float(z['max_abs_error_J']):.6f}|")
    lines+=["",f"原四域的 109 个物理排程集合摘要与 E0 一致。新增四域共有 {finite['additional']} 个物理排程。逐排程核对了 CP 切换、前沿、忙区间并集、参考目标四项及有理数目标。D3 整数化最坏误差界为 0.155715 µJ。", "",
       f"历史回放覆盖 {replay['unique']} 个不同排程和 {replay['memberships']} 项区域权限归属，包含归档中的全部允许与禁止赋值。另核验 {replay['permissions']} 个独立权限测试。共 {len(audit_rows)} 份轨迹通过独立事件与矩阵指数复核。","",
       "## 实际规模","",
       "|区域|权限|旧→新变量|旧→新约束|候选弧|搜索状态（两次）|物理解数（含 G3）|安全能耗 / J|","|---|---|---:|---:|---:|---|---:|---:|"]
    for r in rows:
        lines.append(f"|{r['region']}|{r['group']}|{r['master_vars']}→{r['variables']}|{r['master_constraints']}→{r['constraints']}|{r['arcs']}|{r['statuses']}|{r['physical_candidates']}|{r['best_SAFE_J']:.9f}|")
    lines+=["","第一轮使用全模型与完整 G3 提示，第二轮使用同一物理域并排除已返回的 G3。第二轮的参考目标界仅适用于该剩余集合。每次求解的整数目标、求解器下界和耗时见 smoke 下逐组 JSON。整数组合最优与有理能耗最优在有限域内分别验算，真实能耗使用冻结的全窗连续评价器排序。","",
      "## 研究决定","","本轮提供的是第三章方法与强基线可共用的参考能耗核心。候选数和限时状态衡量工程可用性。若某组仅保留 G3，应先从等价的弧消除和更紧的变量界处理该组瓶颈。当前结果不支持算法间独立节能优势判断。E2-b 与 H1–H3 均未启动。"]
    (HERE/"decision.md").write_bytes(("\n".join(lines)+"\n").encode())
