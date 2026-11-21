"""Read frozen Git blobs and archived results only. All paths are repository-relative."""
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

BASE = "b8187776fdf2c995cbec410032b34a5a76fa774b"
HERE = Path(__file__).resolve().parent
S = "research/kim_synthetic_platform_v1/"
A = "research/kim_scene_dvfs_admission/"
H = "research/kim_safety_repair_audit/"
X = "research/kim_multidnn_expansion/"
T = "research/kim_multidnn_search_trial/"
P = "research/kim_pressure_feasibility/"
N = 27**4
STATIC = np.arange(27)*sum(27**k for k in range(4))
FOUR = ("A", "C", "D001", "D015")
NODES = ("cpu","gpu","dla0","dla1")
PENDING = "待补数据"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source_root", type=Path)
parser.add_argument("--git-dir", type=Path)
args = parser.parse_args()
root = args.source_root.resolve()
git = ["git","--git-dir="+str(args.git_dir.resolve())] if args.git_dir else ["git","-C",str(root)]
tree = subprocess.check_output(git+["ls-tree","-rz",BASE,"--","research","papers/2023_Kim_Energy_Aware_Mapping.pdf"])
expected = {}
for record in tree.split(b"\0"):
    if record:
        meta, name = record.split(b"\t",1)
        expected[name.decode()] = meta.split()[-1].decode()
sources = {}
def source(path):
    file = root/path
    if path not in sources:
        b=file.read_bytes()
        blob=hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
        assert blob==expected[path],path
        sources[path]=dict(path=path,commit=BASE,git_blob=blob,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
    return file
def js(p): return json.loads(source(p).read_bytes())
def rows(p):
    with source(p).open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def save(name,data):
    cols=list(dict.fromkeys(k for row in data for k in row))
    with (HERE/"derived"/(name+".csv")).open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols,lineterminator="\n"); w.writeheader(); w.writerows(data)
def obj(name,data): (HERE/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
for folder in ["audit","derived"]: (HERE/folder).mkdir(exist_ok=True)
def grid(path):
    with np.load(source(path),allow_pickle=False) as a:
        st,en=a["status"],a["energy_j"]
    assert len(st)==len(en)==N and np.all(st<=3) and np.array_equal(st!=0,np.isfinite(en))
    return st,en
def phys(choice):
    p=(choice or {}).get("physical")
    if not p:return {}
    return dict(mapping_id=choice.get("deployment"),frequency_code=choice["code"],peak_upper_c=max(p["peak_upper_c"]),
                min_slack_ms=p["min_slack_ms"],on_time_fraction=1 if p["deadline_ok"] and p["completed"]==p["required"] else None,
                thermal_margin_c=80-max(p["peak_upper_c"]),best_safe_energy_j=p["energy_j"] if p["feasible"] else None)
def outcome(choice):
    p=(choice or {}).get("physical")
    if not p:return "NO_SELECTION"
    return "SAFE" if p["feasible"] else "UNSAFE_THERMAL" if p["deadline_ok"] else "MISS_DEADLINE"
models=js(X+"expanded_input.json")
catalog=js(X+"catalog.json")
levels=["".join(x) for x in models["clock_policy"]["constant_opp_levels"]]
def opps(code): return "/".join(levels[(int(code)//27**i)%27] for i in (3,2,1,0))
histpath=H+"raw/new/results.json"
hist=js(histpath)
def digest(case):
    frames=dict(zip(sorted(case["order"]),case["dwell_frames"]))
    offset=0; offsets={}
    for sc in sorted(frames):
        offsets[sc]=offset;offset+=frames[sc]
    records=[];frame=0
    for sc in case["order"]:
        for j in range(frames[sc]):
            for app in models["fsm"]["active_apps"][sc]:
                records.append([f"f{offsets[sc]+j:04d}-a{app}",app,frame*40000000,(frame+1)*40000000])
            frame+=1
    assert frame==250 and len(records)==500
    return hashlib.sha256(json.dumps(records,separators=(",",":")).encode()).hexdigest()
case_hash={x["case"]["id"]:digest(x["case"]) for x in hist}
pressure=js(P+"manifest.json")
for c in pressure["cases"]:assert case_hash[c["id"]]==c["request_stream_sha256"]
metrics=rows(T+"results/run_metrics.csv")
m2={x["case"]:x for x in metrics if x["stage"]=="dev" and x["method"]=="M2"}
assert len(m2)==4 and all(r["scope"]=="catalog" and r["completed"]=="81" and r["status"]=="PASS" for r in m2.values())
expfile=X+"raw/expanded/results.json"
exp={x["case"]["id"]:x for x in js(expfile)}
closure={x["case"]:x for x in js(X+"raw/ac_closure/summary.json")["cases"]}
methods=[]; instances=[]; coverage=[]; diagnoses=[]; abl=[]; traces=[]; peaks=[]; press=[]; cells=[]; classifications=[]
def add(case,method,scope,status,path,**fields):
    methods.append(dict(run_id=f"{case}|{method}|{scope}",instance_id=case,method_id=method,domain=scope,status=status,
          seed=None,cap_s=None,best_safe_energy_j=None,peak_upper_c=None,min_slack_ms=None,mapping_id=None,frequency_code=None,
          first_safe_s=None,certificate_s=None,cert_scope="",source_path=path) | fields)
def best(states,energy,ids):
    valid=ids[states[ids]==1]
    if not len(valid):return None
    floor=float(np.min(energy[valid]))
    code=int(valid[energy[valid]<=floor+1e-9][0])
    return floor,code
def score_grid(case,dep,path,record=None):
    st,en=grid(path)
    counts=np.bincount(st,minlength=4)
    classifications.append(dict(instance_id=case,deployment=dep,logical=N,deadline_failed=int(counts[0]),safe=int(counts[1]),overtemp=int(counts[2]),unresolved=int(counts[3]),source_path=path))
    if record:
        assert counts.tolist()==[record[k] for k in ("deadline_failed","safe","overtemp","unresolved")]
        assert record["array_archive"]["sha256"]==sources[path]["sha256"]
    for policy,ids in [("Static-DVFS",STATIC),("Max-Freq",STATIC[-1:]),("Scene-DVFS",np.arange(N))]:
        found=best(st,en,ids); floor,code=found if found else (None,None)
        cells.append(dict(instance_id=case,deployment=dep,policy=policy,strict_min_j=floor,code=code,source_path=path,
                          n_codes=len(ids),safe=int(np.sum(st[ids]==1)),unresolved=int(np.sum(st[ids]==3))))
    return st,en
for c,x in exp.items():
    for dep in x["completed_deployments"]:
        folder=X+"raw/expanded/"+c+"/"
        detail=js(folder+"deployment_"+dep+".json")
        score_grid(c,dep,folder+detail["array_archive"]["path"],detail)
for dep in ("A","C"):
    score_grid("forward_flat_27p5C",dep,X+"raw/ac_closure/forward_flat_27p5C/space_"+dep+".npz")
    score_grid("forward_flat_30C",dep,A+"raw/space_30_"+dep+".npz")
for n,job in enumerate(pressure["execution_order"]):
    folder=P+f"raw_execution/{n:02d}/";path=folder+"result.json";r=js(path);c=r["case_id"];dep=r["deployment"]
    assert r["subject"]=="c73b6c6728794d68db33395f78c7dc94e4634e5a" and r["request_sha256"]==case_hash[c]
    st,en=score_grid(c,dep,folder+"space.npz")
    co=r["counts"];assert list(np.bincount(st,minlength=4))==[co[k] for k in ["deadline_failed","safe","overtemp","unresolved"]]
    cert=r["certificate"];p=r["physical"];pr=dict(r["selection"],physical=p,deployment=dep)
    assert outcome(pr)==("SAFE" if cert=="MIN_SAFE" else "UNSAFE_THERMAL")
    add(c,"CT-Joint",dep,"SAFE" if cert=="MIN_SAFE" else "NO_SAFE_PROVED",path,
        cert_scope=cert+" / "+dep,**(phys(pr) if cert=="MIN_SAFE" else {}))
    press.append(dict(instance_id=c,deployment=dep,domain="A/C/D001/D015",deadline_legal=N-co["deadline_failed"],**co,certificate=cert,
        best_safe_energy_j=r["strict_minimum_known_safe_j"],diagnostic_or_safe_peak_c=max(p["peak_upper_c"]),selection_role=r["selection_role"],source_path=path))
for case,rr in m2.items():
    choice=exp[case]["decisions"]["joint"]
    # An incomplete older run can have a different incumbent than the final catalogue winner.
    fields={}
    path=T+"results/run_metrics.csv"
    if choice["deployment"]==rr["winner"] and choice["code"]==int(rr["code"]):
        fields=phys(choice);path+=";"+expfile
    fields.update(best_safe_energy_j=float(rr["best_safe_j"]),mapping_id=rr["winner"],frequency_code=int(rr["code"]),
          peak_upper_c=float(rr["peak_upper_c"]),thermal_margin_c=80-float(rr["peak_upper_c"]),cap_s=rr["cap_s"],first_safe_s=rr["first_safe_s"],
          certificate_s=rr["certificate_s"],optimality_gap_pct=0,coverage_deployments=81,cert_scope="MIN_SAFE / 81 representatives")
    add(case,"CT-Joint","81","SAFE",path,**fields)
for item in hist:
    c=item["case"];case=c["id"];temp=c["ambient"];deps=exp[case]["completed_deployments"] if case in exp else []
    named=[x for x in press if x["instance_id"]==case]
    scope="81" if case in exp else "4" if named else "A/C"
    known="81部署能耗最优；完整分类 "+str(len(deps))+"/81" if case in exp else "四部署完整分类" if named else "A/C 最低SAFE" if case in closure else "A/C 无解；81部署待补"
    frames=dict(zip(sorted(c["order"]),c["dwell_frames"]))
    instances.append(dict(instance_id=case,scene_order="/".join(c["order"]),dwell_profile=c["dwell_id"],frames_execution_order="/".join(str(frames[s]) for s in c["order"]),
        ambient_c=temp,request_sha=case_hash[case],request_hash_format="compact JSON [ID,app,release_ns,deadline_ns]",deployment_scope=scope,known_certificate_scope=known,
        source_commit=BASE,source_path=histpath,classification_deployments=len(deps) if deps else 4 if named else "",request_count=500))
    instances[-1]["classification_deployments"]=sum(x["instance_id"]==case for x in classifications)
    if case in exp:
        four=[x for x in cells if x["instance_id"]==case and x["policy"]=="Scene-DVFS" and x["deployment"] in FOUR]
        assert len(four)==4 and not sum(x["unresolved"] for x in four)
        w=min((x for x in four if x["strict_min_j"] is not None),key=lambda x:x["strict_min_j"])
        fp=X+"raw/expanded/"+case+"/deployment_"+w["deployment"]+".json"
        chosen=js(fp)["joint"];assert chosen["code"]==w["code"]
        add(case,"CT-Joint","4","SAFE","derived/grid_minima.csv;"+fp,cert_scope="MIN_SAFE / A,C,D001,D015",**phys(chosen))
    for method in ["Kim-Adapt","Kim-Adapt+SAFE","Thermal-GA"]:
        add(case,method,"81","NOT_RUN","",note="待补数据：未运行")
    choice=item["independent"]
    add(case,"Reset","A/C",outcome(choice),histpath,**phys(choice))
    if temp==30:
        assert item["oracle"]["status"]=="NO_SAFE"
        add(case,"CT-Joint","A/C","NO_SAFE_PROVED",histpath,cert_scope=item["oracle"]["method"]+" / A/C")
    elif case in closure:
        r=closure[case];add(case,"CT-Joint","A/C","SAFE",X+"raw/ac_closure/summary.json",best_safe_energy_j=r["optimal_safe_j"],cert_scope="MIN_SAFE / A/C")
    if named:
        win=min((x for x in named if x["best_safe_energy_j"] is not None),key=lambda x:x["best_safe_energy_j"])
        row=next(x for x in methods if x["instance_id"]==case and x["domain"]==win["deployment"] and x["method_id"]=="CT-Joint")
        add(case,"CT-Joint","4","SAFE",P+"raw_execution/summary.json",**{k:row.get(k) for k in ["best_safe_energy_j","mapping_id","frequency_code","peak_upper_c","min_slack_ms","thermal_margin_c","on_time_fraction"]},cert_scope="MIN_SAFE / 4, minimum of 4 certified units")
    if case in exp:
        dom=str(len(deps))+"/81 classified"
        for key,method in [("independent","Reset"),("no_thermal_constraint","No-Thermal")]:
            ch=exp[case]["decisions"][key]
            add(case,method,dom,outcome(ch),expfile,**phys(ch))
    # Summarise only observed subdomains. No partial optimum is promoted to a catalogue optimum.
    for method in ["Max-Freq","Static-DVFS","Scene-DVFS"]:
        subset=[r for r in cells if r["instance_id"]==case and r["policy"]==method]
        if not subset:continue
        for fixed in [False,True]:
            subset2=[r for r in subset if not fixed or r["deployment"]=="A"]
            ds="A" if fixed else "81" if len(subset2)==81 else "4" if named else "A/C" if len(subset2)==2 else f"{len(subset2)}/81 classified"
            legal=[r for r in subset2 if r["strict_min_j"] is not None]
            unresolved=sum(r["unresolved"] for r in subset2)
            chosen=min(legal,key=lambda r:r["strict_min_j"]) if legal else None
            status="SAFE_WITNESS_ONLY" if chosen and unresolved else "SAFE" if chosen else "UNRESOLVED" if unresolved else "NO_SAFE_PROVED"
            f=dict(mapping_id=chosen["deployment"],frequency_code=chosen["code"],best_safe_energy_j=chosen["strict_min_j"]) if chosen else {}
            if chosen and case in exp:
                path=X+"raw/expanded/"+case+"/deployment_"+chosen["deployment"]+".json"
                for k in ["joint","independent"]:
                    z=js(path)[k]
                    if z and z["code"]==chosen["code"] and outcome(z)=="SAFE": f.update(phys(z));break
            add(case,method,ds,status,"derived/grid_minima.csv",cert_scope=("MIN_SAFE" if chosen and not unresolved else status)+" / "+ds+" / "+method,**f)
            if case=="reverse_flat_25C" and method in ["Scene-DVFS","Static-DVFS"]:
                abl.append(dict(instance_id=case,ablation_id=("FixA" if fixed else "Select81")+"-"+method,fixed_mapping_id="A" if fixed else "",
                    permitted_mapping_set=ds,frequency_policy=method,status=status,best_safe_j=chosen["strict_min_j"],winner=chosen["deployment"],
                    code=chosen["code"],opps=opps(chosen["code"]),peak_upper_c=f.get("peak_upper_c"),min_slack_ms=f.get("min_slack_ms"),
                    thermal_margin_c=f.get("thermal_margin_c"),logical_domain=sum(r["n_codes"] for r in subset2),winner_array=chosen["source_path"],
                    metrics_status="完整回放已归档" if f.get("peak_upper_c") is not None else "温度与期限裕量待补数据"))
for r in abl:
    if r["ablation_id"]=="FixA-Static-DVFS":
        lp=H+"raw/new/reverse_flat_25C/local.csv"
        local=[x for x in rows(lp) if x["deployment"]=="A" and x["opp"]==r["opps"].split("/")[0]]
        assert len(local)==4 and sum(int(x["required"]) for x in local)==500 and all(x["deadline_ok"]=="True" for x in local)
        r["min_slack_ms"]=min(float(x["min_slack_ms"]) for x in local)
        r["metrics_status"]="期限裕量来自四场景原调度记录；连续峰温待补数据"
        r["deadline_source"]=lp
        for row in methods:
            if (row["instance_id"],row["domain"],row["method_id"])==("reverse_flat_25C","A","Static-DVFS"):
                row.update(min_slack_ms=r["min_slack_ms"],on_time_fraction=1,source_path=row["source_path"]+";"+lp)
baseline=next(x["best_safe_j"] for x in abl if x["ablation_id"]=="FixA-Static-DVFS")
for r in abl:r.update(reference_j=baseline,delta_pct=(baseline-r["best_safe_j"])/baseline*100)
assert len(abl)==4 and abs(min(r["best_safe_j"] for r in abl)-float(m2["reverse_flat_25C"]["best_safe_j"]))<1e-7
# Reuse the original four-node sample stream; keep paired reset boundary points in file order.
case="forward_flat_25C"; archived="10s_25fps_25C_on_base"
tracefile=S+"raw/traces.csv"; candfile=S+"raw/candidates.csv"
safechoice=hist[0]["independent"]; assert hist[0]["case"]["id"]==case and safechoice["deployment"]=="C"
import base64
import zlib
ledger_path=S+"raw/ledger/events-000.jsonl"
packet=next(x for x in map(json.loads,source(ledger_path).read_bytes().splitlines()) if x[0]=="10s_25_C_HHH")
plain=zlib.decompress(base64.b64decode(packet[2]));assert hashlib.sha256(plain).hexdigest()==packet[1]
jobs=json.loads(plain)[3]
assert hashlib.sha256(json.dumps([j[:4] for j in jobs],separators=(",",":")).encode()).hexdigest()==case_hash[case]
assert all(j[2]<=j[4]<=j[3] for j in jobs) and len(jobs)==500
scenes=safechoice["physical"]["scene_rows"]
bounds=[s["start_ns"]/1e9 for s in scenes]+[scenes[-1]["service_end_ns"]/1e9,scenes[-1]["end_ns"]/1e9]
def marker(t):
    return next((f"{b:g}" for b in bounds if abs(t-b)<1e-7),"")
for record in rows(tracefile):
    if (record["case_id"],record["deployment"],record["opp"])!=(archived,"C","HHH"):continue
    t=float(record["t_s"])
    for n in NODES:
        traces.append(dict(instance_id=case,solution_id="C / HHH×4",eval_mode=record["mode"],node=n,t_s=t,temperature_c=float(record[n+"_c"]),
            scene_marker=marker(t),sample_type="archived_sample",source_path=tracefile))
for s in scenes:
    points=[(s["start_ns"],s["entry_c"]),(s["end_ns"],s["final_c"])]
    for ns,temperature in points:
        for j,n in enumerate(NODES):
            traces.append(dict(instance_id=case,solution_id="C / "+opps(safechoice["code"]),eval_mode="continuous",node=n,t_s=ns/1e9,
                temperature_c=temperature[j],scene_marker=marker(ns/1e9),sample_type="scene_endpoint",source_path=histpath))
for r in rows(candfile):
    if (r["case_id"],r["deployment"],r["opp"])==(archived,"C","HHH"):
        peaks.append(dict(instance_id=case,solution_id="C / HHH×4",eval_mode=r["mode"],peak_upper_c=max(float(r["peak_"+n+"_c"]) for n in NODES),
            status=r["thermal_status"],request_digest_source_format=r["request_sha256"],source_path=candfile))
peaks.append(dict(instance_id=case,solution_id="C / "+opps(safechoice["code"]),eval_mode="continuous",peak_upper_c=max(safechoice["physical"]["peak_upper_c"]),
                  status="SAFE",request_digest_source_format=case_hash[case],source_path=histpath))
comp=A+"raw/comparison_sets.json"; grouped=[]
rawpeak=H+"raw/historical_peaks.csv"
prior=rows(rawpeak)
for r in js(comp):
    if r["ambient"]!=25:continue
    d=r["deployment"];p=A+"raw/space_25_"+d+".npz";st,en=grid(p);selected=[a for a in prior if a["deployment"]==d]
    ids=np.array([int(a["code"]) for a in selected]);assert len(set(ids))==len(ids)==r["reset_only"] and np.all(st[ids]==2)
    assert np.sum(st!=0)==r["reset_feasible"] and np.sum(st==1)==r["both_feasible"]
    for a in selected:
        diagnoses.append(dict(instance_id=case,solution_id=d+"-"+a["code"],deployment=d,frequency_code=a["code"],independent_status="SAFE",continuous_status="UNSAFE_THERMAL",
            peak_upper_c=max(float(a["peak_"+n+"_hi_c"]) for n in NODES),energy_j=float(a["continuous_energy_j"]),candidate_scope="A/C; reset-accepted false positives",source_path=rawpeak))
    grouped.append(dict(instance_id=case,deployment=d,candidate_scope=d+" × 27^4",assumed_safe=r["reset_feasible"],continuous_safe=r["both_feasible"],
        false_accept=r["reset_only"],false_accept_pct=100*r["reset_only"]/r["reset_feasible"],source_path=comp+";"+p))
num=sum(x["false_accept"] for x in grouped);den=sum(x["assumed_safe"] for x in grouped)
assert num==len(diagnoses) and den==118098
grouped.append(dict(instance_id=case,deployment="A+C",candidate_scope="2 × 27^4",assumed_safe=den,continuous_safe=den-num,false_accept=num,false_accept_pct=num/den*100,source_path=comp))
# Rectangular 12 x method matrix, with separate scoped records so that gaps stay visible.
method_ids=["CT-Joint","Kim-Adapt","Kim-Adapt+SAFE","Thermal-GA","Reset","No-Thermal","Max-Freq","Static-DVFS","Scene-DVFS"]
for ins in instances:
    for method in method_ids:
        match=[r for r in methods if r["instance_id"]==ins["instance_id"] and r["method_id"]==method and r["status"]!="NOT_RUN"]
        def availability(key):
            return " | ".join(str(r["domain"]) for r in match if r.get(key) not in (None,"")) or PENDING
        coverage.append(dict(instance_id=ins["instance_id"],method_id=method,status_and_domain=" | ".join(f"{r['domain']}:{r['status']}" for r in match) or PENDING,
            safe_energy_scope=availability("best_safe_energy_j"),peak_scope=availability("peak_upper_c"),slack_scope=availability("min_slack_ms"),
            deadline_ratio_scope=availability("on_time_fraction"),certificate_scope=availability("cert_scope"),first_safe_time_scope=availability("first_safe_s"),
            certificate_time_scope=availability("certificate_s"),gap_to_81_optimum_scope=availability("optimality_gap_pct"),source_paths=";".join(dict.fromkeys(r["source_path"] for r in match))))
for name,data in [("instances",instances),("method_results",methods),("coverage_matrix",coverage),("classification",classifications),("grid_minima",cells),
        ("temperature_traces",traces),("peak_certificates",peaks),("candidate_diagnostics",diagnoses),("reset_confusion",grouped),("pressure_classification",press),("ablation_results",abl)]:
    save(name,data)
parameters=[dict(parameter=k,value=json.dumps(v,ensure_ascii=False),source_path=p) for k,v,p in [
    ("network_and_affinity",models["applications"],X+"expanded_input.json"),("frequency_MHz",models["frequency_mhz"],X+"expanded_input.json"),
    ("active_apps",models["fsm"]["active_apps"],X+"expanded_input.json"),("catalog_counts",catalog["counts"],X+"catalog.json"),
    ("four_deployment_layer_ranges",pressure["stages"],P+"manifest.json"),("pressure_runtime",js(P+"raw_execution/00/result.json")["runtime"],P+"raw_execution/00/result.json"),
    ("historical_packages",js(S+"raw/run.json")["packages"],S+"raw/run.json"),("initial_c",js(P+"raw_execution/00/result.json")["initial_c"],P+"raw_execution/00/result.json"),
    ("thermal_model",js(S+"platform.json").get("thermal"),S+"platform.json")]]
save("parameters",parameters)
# Common data interfaces for future A/B/F/G; preserve absent measurements as empty fields.
main=["CT-Joint","Kim-Adapt","Kim-Adapt+SAFE","Thermal-GA"]
ab=[];fg=[]
for ins in instances:
    case=ins["instance_id"]
    for method in main:
        full=next((x for x in methods if x["instance_id"]==case and x["method_id"]==method and x["domain"]=="81" and x["status"]!="NOT_RUN"),None)
        ab.append(dict(instance_id=case,ambient_c=ins["ambient_c"],method_id=method,domain="81",seed=None,outcome_status=full["status"] if full else PENDING,
            energy_j=full["best_safe_energy_j"] if full else None,optimal_j=float(m2[case]["best_safe_j"]) if case in m2 else None,
            optimality_gap_pct=full.get("optimality_gap_pct") if full else None,cert_scope=full["cert_scope"] if full else "",source_path=full["source_path"] if full else ""))
        sub=next((x for x in methods if x["instance_id"]==case and x["method_id"]==method and x["domain"]=="4"),None)
        fg.append(dict(instance_id=case,scene_id=case.rsplit("_",1)[0],ambient_c=ins["ambient_c"],method_id=method,domain="A/C/D001/D015",
            request_sha=case_hash[case],status=sub["status"] if sub else PENDING,energy_j=sub["best_safe_energy_j"] if sub else None,
            margin_c=sub.get("thermal_margin_c") if sub else None,min_slack_ms=sub.get("min_slack_ms") if sub else None,n_instances=1,source_path=sub["source_path"] if sub else ""))
save("figAB_method_comparison",ab);save("figFG_matched_pressure",fg)
registry=[
 ("A","figAB_method_comparison","method_id","instance_id","energy_j","J","统一81部署，四个25°C参照可用；外部方法待补"),
 ("B","figAB_method_comparison","method_id","instance_id","outcome_status","状态","缺测保持待补"),
 ("C","temperature_traces;peak_certificates","eval_mode/node","t_s","temperature_c","s / °C","同方案GPU两条采样；安全代表仅端点"),
 ("D","reset_confusion;pressure_classification","deployment","instance_id","false_accept_pct;safe/deadline_legal","% / 个","25°C重置接纳；27.5°C四部署期限合法域"),
 ("E","ablation_results","ablation_id","ablation_id","best_safe_j;delta_pct","J / %","逆序原驻留25°C；固定A或81代表"),
 ("F","figFG_matched_pressure","method_id","ambient_c/scene_id","status","状态","四部署共同域；外部方法待补"),
 ("G","figFG_matched_pressure","method_id","ambient_c/scene_id","energy_j;margin_c","J / °C","同实例同四部署域；安全点")]
save("figure_registry",[dict(figure_id=i,source_table=t,series=s,x_field=x,y_field=y,unit=u,filter_scope=f,
    status="已绘" if i in "CDE" else "部分数据／待方法对照",generated_files=";".join("figures/fig"+i+"."+ext for ext in ("svg","pdf","png")) if i in "CDE" else "") for i,t,s,x,y,u,f in registry])
for p in [P+"execution_freeze.json",P+"raw_execution/sha256.json",P+"audit_27p5/audit.json",T+"freeze.json",T+"PROTOCOL.md",
          T+"results/RECOVERY_REPORT.md",T+"holdout_receipt.json",X+"freeze_manifest.json",X+"protocol.md",S+"experiments.json","papers/2023_Kim_Energy_Aware_Mapping.pdf"]:
    source(p)
audit=js(P+"audit_27p5/audit.json");assert audit["status"]=="PASS"
for rel,sha in js(P+"raw_execution/sha256.json").items():
    path=P+"raw_execution/"+rel;source(path);assert sources[path]["sha256"]==sha
stages=[("热继承平台","6bad679a","301b06e5",S),("逐场景调频","9b261166","2d352e71",A),
    ("修复审计","8ccc51e5","02f3f621",H),("多部署扩展","033cf345","babfc5ed",X),
    ("正式搜索协议及原件恢复","0347bf99","19dc53fb",T),("H2 单次补跑","e69b7b8f","55517e28",T),
    ("压力实验","c73b6c67","b8187776",P)]
def resolve(rev): return subprocess.check_output(git+["rev-parse","--verify",rev+"^{commit}"]).decode().strip()
save("versions",[dict(stage=s,directory=d,freeze_commit=resolve(a),archive_commit=resolve(b),read_snapshot=BASE) for s,a,b,d in stages])
save("evidence_inventory",sorted(sources.values(),key=lambda r:r["path"]))
obj("audit/sources.json",dict(repository="YBEMR/paper",result_commit=BASE,taskbook_sha256="ad4c947eb9687063ac563e7fb7ec1020cf396634394fea7971a051a963af7984",
    pressure_execution_commit=audit["subject"],pressure_freeze_sha256=audit["execution_freeze_sha256"],input_files=list(sorted(sources.values(),key=lambda r:r["path"]))))
print("Verified input blobs:",len(sources),"| Matrix rows:",len(coverage),"| grid files:",len(classifications),"| plotted ablations:",len(abl))
