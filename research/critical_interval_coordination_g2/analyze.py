"""Read-only paired analysis; distinguish actual configuration gains, timing gains and interval overlap."""
import csv,gzip,hashlib,json
from fractions import Fraction
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
RUNS=ROOT/"runs"
def read(p):return json.loads(p.read_bytes())
def lines(p):return [json.loads(l) for l in p.read_bytes().splitlines()] if p.exists() else []
def save(name,items):
    if not items:return
    columns=list(dict.fromkeys(k for r in items for k in r))
    with (ROOT/name).open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,columns,lineterminator="\n");writer.writeheader();writer.writerows(items)
def plan_rows(folder,h):
    data=gzip.decompress((folder/"evidence/plans"/(h+".json.gz")).read_bytes())
    assert hashlib.sha256(data).hexdigest()==h
    return json.loads(data)["rows"]
def certify(folder):
    checked=0
    for file in (folder/"evidence/certificates").glob("*.json"):
        c=read(file);h=file.stem;assert c["plan"]==h
        plan_rows(folder,h)
        m=c["metrics"]
        assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
        with np.load(file.with_suffix(".npz"),allow_pickle=False) as z:tr=z["events"]
        assert tr[0,0]==0 and np.all(tr[:,1]>tr[:,0]) and np.array_equal(tr[:-1,1],tr[1:,0])
        assert np.allclose(tr[:,26:30].sum(axis=0),m["energy_by_node_J"],atol=1e-10,rtol=1e-11)
        assert abs(sum(m[k] for k in ("base_J","switch_J","temperature_J","external_J","activity_J"))-m["E_J"])<1e-8
        if m["status"]=="SAFE":assert max(m["peak_hi"])<=80 and m["min_deadline_slack_ms"]>=0
        checked+=1
    return checked
def compare(ab,pro):
    if pro["bounds"][1]<ab["bounds"][0]:return "Proposed严格更低"
    if ab["bounds"][1]<pro["bounds"][0]:return "AB严格更低"
    return "同一排程" if ab["plan"]==pro["plan"] else "认证区间重叠"
def changes(folder,a,b):
    x=plan_rows(folder,a["plan"]);y=plan_rows(folder,b["plan"])
    return sum(r[:2]!=s[:2] for r,s in zip(x[1::3],y[1::3]))
def analyze(checkpoint=False):
    outcome=read(RUNS/"end.json") if not checkpoint else {"incomplete":read(RUNS/"continuation.json")["interrupted"]}
    if not checkpoint:assert outcome["outcome"] in ("COMPLETED","CLOSED_WITH_INTERRUPTION")
    assert all(read(ROOT/p)["status"]=="PASS" for p in ("witness_gate.json","model_gate.json","finite_gate.json","engineering/gate.json"))
    runs=[];pairs=[];initial=[];mechanism=[];budgets=[];stored={}
    for folder in sorted(d for d in RUNS.iterdir() if d.is_dir()):
        if checkpoint and not (folder/"receipt.json").exists():continue
        r=read(folder/"receipt.json");result=read(folder/"result.json");budgets.append(r)
        interrupted=r["status"]=="INTERRUPTED"
        if interrupted:
            assert folder.name in outcome["incomplete"] and result["final"] is None
            assert r["elapsed_s"] is None
        else:
            assert r["status"]=="OK" and r["elapsed_s"]<=r["limit_s"]+.25
        checked=certify(folder)
        if r["action"]=="init":
            data=result["initial"] or {};initial.append(dict(case=r["case"],status=result["status"],**{k:data.get(k) for k in ("J","plan")},seconds=r["elapsed_s"],certificates=checked))
            continue
        key=(r["action"],r["case"],r["seed"],r["method"]);stored[key]=result
        line=dict(batch=r["action"],case=r["case"],seed=r["seed"],method=r["method"],status=result["status"],
                  budget_s=r["limit_s"]+r["prior_charge_s"],charged_s=None if interrupted else r["elapsed_s"]+r["prior_charge_s"],certificates=checked)
        if interrupted:line["last_observed_charged_s"]=r["last_observed_charged_s"]
        if result["status"] not in ("COMPLETE","INTERRUPTED"):runs.append(line);continue
        a,b,c=(result[k] for k in ("initial","configuration","final"))
        for part,obj in zip(("initial","config","final"),(a,b,c)):
            if obj is None:continue
            line.update({part+"_J":obj["J"],part+"_lo":obj["bounds"][0],part+"_hi":obj["bounds"][1],part+"_plan":obj["plan"]})
            assert obj["status"]=="SAFE" and obj["bounds"]==read(folder/"evidence/certificates"/(obj["plan"]+".json"))["metrics"]["E_bounds"]
        chain_hits=0;late_rounds=0;attributed=0;rounds=lines(folder/"rounds.jsonl")
        for rd in rounds:
            prev=rd["before"];chosen=[];accepted=[]
            for candidate in rd["candidates"]:
                cert=read(folder/"evidence/certificates"/(candidate["plan"]+".json"))
                assert candidate["bounds"]==cert["metrics"]["E_bounds"]
                if candidate["accepted"]:
                    assert candidate["in_time"] and candidate["status"]=="SAFE" and candidate["bounds"][1]<prev["bounds"][0]
                    assert candidate["elapsed_s"]<=line["budget_s"]
                    prev=candidate;accepted.append(candidate["plan"])
            assert prev["plan"]==rd["after"]["plan"]
            if rd["phase"]!="configuration":continue
            feedback=rd["feedback"];late_rounds+=bool(feedback)
            chosen={t["selected"] for t in feedback if t["selected"] is not None}
            changed={j for j,old,new in rd["real_changes"] if old!=new}
            hit=bool(changed&chosen)
            chain_hits+=hit
            if hit:attributed+=rd["before"]["J"]-rd["after"]["J"]
            mechanism.append(dict(batch=key[0],case=key[1],seed=key[2],method=key[3],round=rd["turn"],target=rd["target_type"],
                  target_ids=json.dumps(rd["target"]),scope=len(rd["scope"]),chains=len(feedback),compensators=json.dumps(sorted(chosen)),
                  realized_compensators=json.dumps(sorted(changed&chosen)),actual_main_changes=len(changed),round_gain_J=rd["before"]["J"]-rd["after"]["J"],
                  delta_activity_J=rd["before"]["activity_J"]-rd["after"]["activity_J"],delta_residency_J=rd["before"]["residency_J"]-rd["after"]["residency_J"],
                  delta_switch_J=rd["before"]["switch_J"]-rd["after"]["switch_J"],duration=rd["round_s"],solver_status=rd["solver"]["status"]))
        line.update(config_gain_J=a["J"]-b["J"],post_gain_J=b["J"]-c["J"] if c else None,total_gain_J=a["J"]-c["J"] if c else None,lower_J=float(Fraction(result["lower_J"])) if result.get("lower_J") else None,
              final_peak_C=c["peak_upper_C"] if c else None,final_slack_ms=c["deadline_slack_ms"] if c else None,config_main_changes=changes(folder,a,b),
              final_main_changes=changes(folder,a,c) if c else None,config_rounds=result["configuration_rounds"],post_rounds=result["post_rounds"],
              chain_rounds=late_rounds,realized_compensation_rounds=chain_hits,realized_round_gain_J=attributed)
        runs.append(line)
    assert (checkpoint or len(runs)==40) and len(initial)==5
    for (kind,case,seed,method),pro in sorted(stored.items()):
        if method!="Proposed":continue
        if checkpoint and ((kind,case,seed,"AB") not in stored or (kind=="main" and (kind,case,seed,"Compact") not in stored)):continue
        ab=stored[kind,case,seed,"AB"];line=dict(batch=kind,case=case,seed=seed)
        if not all(x["status"] in ("COMPLETE","INTERRUPTED") for x in (ab,pro)):line.update(final_verdict="未决",config_verdict="未决")
        else:
            assert ab["initial"]["plan"]==pro["initial"]["plan"]
            if kind=="main":
                compact=stored[kind,case,seed,"Compact"];assert compact["initial"]["plan"]==ab["initial"]["plan"]
                line["compact_final_J"]=compact["final"]["J"] if compact["final"] else None
            line.update(common=ab["initial"]["plan"])
            for phase,label in (("configuration","config"),("final","final")):
                a,b=ab[phase],pro[phase]
                if a is None or b is None:
                    line[label+"_AB_J"]=a["J"] if a else None
                    line[label+"_Proposed_J"]=b["J"] if b else None
                    line[label+"_verdict"]="未决"
                    continue
                line.update({label+"_AB_J":a["J"],label+"_Proposed_J":b["J"],label+"_AB_minus_Proposed_J":a["J"]-b["J"],
                            label+"_verdict":compare(a,b),label+"_diff_lo":a["bounds"][0]-b["bounds"][1],
                            label+"_diff_hi":a["bounds"][1]-b["bounds"][0]})
        pairs.append(line)
    assert checkpoint or len(pairs)==14
    save("summary.csv",runs);save("paired.csv",pairs);save("mechanism.csv",mechanism);save("construction.csv",initial);save("budget_receipts.csv",budgets)
    print(json.dumps({"runs":len(runs),"pairs":len(pairs),"unique_inside_arms":sum(x["certificates"] for x in runs),"rounds":len(mechanism)}))
if __name__=="__main__":
    import sys
    assert sys.argv[1:] in ([],["--checkpoint"])
    analyze(checkpoint=bool(sys.argv[1:]))
