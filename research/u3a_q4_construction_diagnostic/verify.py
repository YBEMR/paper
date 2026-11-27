"""Read-only numerical audit of the recorded runs; --tables also writes the derived CSVs."""
import argparse
import csv
import gzip
from collections import Counter
from runtime import *
from construct_once import ranked

def emit(name,rows):
    target=HERE/"tables"/(name+".csv")
    target.parent.mkdir(exist_ok=True)
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with target.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,keys,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def main(write=False):
    stack=u.stack()
    counts=Counter()
    cases=[]
    candidates=[]
    policies=[]
    coverage=[]
    clocks=[]
    for obj in u.CASES:
        code,dest,flow,eng,_=case_context(obj,stack)
        case=obj["case"]
        assert (HERE/"registration/inputs"/obj["input"]).read_bytes()==u.table(eng.p.req)
        hist=read(dest/"history.json")
        con=read(dest/"construction.json")
        pol=read(dest/"policies.json")
        layers=json.loads(gzip.decompress((dest/"raw_pool.json.gz").read_bytes()))
        prev=[""]
        for j,(l,m) in enumerate(zip(layers,con["meta"]["scenes"],strict=True)):
            tries=l["attempts"]
            assert len(tries)==len(prev)*30 and all(a["parent"] in prev for a in tries)
            assert all(len(bytes.fromhex(a["extension"]))==len(eng.groups[j]) for a in tries)
            assert sum(a["score"] is not None for a in tries)==m["feasible_candidates"]
            assert ranked(l)[:4]==l["retained"]
            prev=l["retained"]
        assert con["meta"]==hist["construction"] and con["retained"]==prev
        for folder in (dest/"evidence"/case).iterdir():
            payload=read(folder/"plan.json")
            assert sha(raw(payload))==folder.name and payload["case"]==case
            rows,low=u.decode(payload)
            cfg=tuple(r[:2] for r in rows[1::3])
            r=eng.replay(cfg)
            assert r is not None and len(cfg)==eng.n
            expected=[part for i,(unit,k) in enumerate(cfg) for part in ((0,0,eng.ps[i]),(unit,k,r["starts"][i]),(1,0,r["posts"][i]))]
            assert rows==expected
            ev,sw,_=stack[1].event_arrays(eng.p,rows,low)
            other,sw2=stack[1].independent_events(eng.p,rows,low)
            assert sw==sw2 and np.array_equal(ev,other)
            cert=folder/"certificate.json"
            if cert.exists():
                cert=read(cert)
                assert cert["plan_sha256"]==folder.name and raw(cert["switches"])==raw(sw)
                check_trace(folder,dict(ev=ev),eng.p.horizon)
                m=cert["metrics"]
                assert m["E_bounds"][0]<=m["E_J"]<=m["E_bounds"][1]
                assert (m["status"]=="SAFE" and max(m["peak_hi"])<=80 or m["status"]=="HOT" and max(m["peak_lo"])>80)
                counts["physical_certificates"]+=1
            else:
                assert not (folder/"trace.npz").exists()
                counts["native_plan_only"]+=1
        selected=[read(p) for p in sorted(dest.glob("retained_*.json"))]
        for h,r in zip(prev,selected,strict=True):assert sha(bytes.fromhex(h))==r["config_sha256"]
        assert len(prev)==pol["count"]
        first=next((r["rank"] for r in selected if r["status"]=="SAFE"),None)
        assert first==pol["first_safe"]
        for method,subset in (("original",selected[:1]),("all",selected),("sequential",selected[:first])):
            best=None
            for r in subset:
                if r["status"]=="SAFE" and (best is None or r["bounds"][1]<best["bounds"][0]):best=r
            v=pol[method]
            assert v["selected_plan"]==(best["plan"] if best else None)
            assert v["considered"]==len(subset) and v["additional"]==max(0,len(subset)-1)
            policies.append(dict(case=code,method=method,**v))
        allrows=selected.copy()
        audit=read(dest/"audit.json") if (dest/"audit.json").exists() else {}
        allrows+=audit.get("terminal",[])
        allrows += [v["certificate"] for v in audit.get("prefix_attempts",[]) if "certificate" in v]
        for w in audit.get("nt_path",{}).get("windows",[]):
            j=w["window"]-1
            actual=ranked(layers[j]) if w["actual_layer"] else []
            actual_rank=next((i for i,k in enumerate(actual,1) if sha(bytes.fromhex(k))==w["nt_prefix_sha256"]),None)
            assert bool(actual_rank)==w["generated_on_actual_path"] and bool(actual_rank and actual_rank<=4)==w["retained_on_actual_path"]
            coverage.append(dict(case=code,window=j+1,nt_prefix=w["nt_prefix_sha256"],nt_quota=w["nt_quota"],
                pairs_matching=len(w["matched_pairs"]),actual_pool_rank=actual_rank,actual_layer=w["actual_layer"]))
        for r in allrows:
            cert=read(dest/"evidence"/case/r["plan"]/"certificate.json")
            assert all(row(cert)[k]==r[k] for k in ("status","J","bounds","peak_hi","peak_lo"))
            v=r["native_metrics"] or {}
            candidates.append(dict(case=code,phase=r["phase"],rank=r["rank"],status=r["status"],
                causal_plan=r["plan"],native_plan=r["native_plan"],native_status=v.get("status"),
                native_J=v.get("J"),native_peak_hi=v.get("peak_hi"),changed_idle=r["changed_idle"],causal_J=r["J"],
                causal_peak_hi=r["peak_hi"],causal_peak_lo=r["peak_lo"],ref_native_J=r["native_reference_J"],
                ref_causal_J=r["reference_J"],slack_ms=r["slack_ms"],reused=r["reuse"],config_sha256=r["config_sha256"],
                trace_sha256=r["trace_sha256"],kernel_s=r["kernel_s"],causal_replay_build_s=r["causal_build"]["wall_s"],
                cert_or_load_s=r["cert_or_load"]["wall_s"]))
        last=layers[-1]
        first_row=selected[0] if selected else {}
        cases.append(dict(case=code,input_sha256=obj["input_sha256"],requests=obj["requests"],
            actual_windows=len(layers),planned_windows=obj["windows"],last_attempts=len(last["attempts"]),
            last_legal=sum(x["score"] is not None for x in last["attempts"]),last_distinct=len(ranked(last)),
            retained=len(prev),first_safe=first,rank1_status=first_row.get("status","EMPTY"),
            rank1_peak_hi=first_row.get("peak_hi"),rank1_J=first_row.get("J"),best_J=pol["all"]["J"],
            best_peak_hi=pol["all"]["peak_hi"],best_rank=pol["all"]["winner_rank"]))
        hfirst=hist.get("first",{})
        clocks.append(dict(case=code,construct_with_observer_wall_s=con["timing"]["wall_s"],
            construct_with_observer_cpu_s=con["timing"]["cpu_s"],observer_callbacks_wall_s=con["timing"]["observers_wall_s"],
            historical_native_first_return_s=hfirst.get("t"),historical_native_first_cert_archive_s=(
            hfirst["t"]-hfirst["began"] if hfirst else None),historical_causal_first_kernel_s=hist.get("causal",{}).get("source_kernel_s"),
            reused_first_load_wall_s=selected[0]["cert_or_load"]["wall_s"] if selected else None,
            reuse_first_causal_build_wall_s=selected[0]["causal_build"]["wall_s"] if selected else None,
            all_extra_wall_s=pol["all"]["extra_wall_s"],sequential_extra_wall_s=pol["sequential"]["extra_wall_s"]))
    assert len(cases)==12 and len(policies)==36
    budget=read(OUTPUT/"offline_budget.json")
    assert all(v["status"]=="complete" for v in budget["cases"]) and sum(v["charged_cpu_s"] for v in budget["cases"])<budget["limit_cpu_s"]
    if write:
        for name,rows in (("cases",cases),("policies",policies),("candidates",candidates),("costs",clocks),("nt_path",coverage)):
            emit(name,rows)
        save(HERE/"tables/verification.json",dict(counts,flows=len(cases),policy_rows=len(policies),candidate_records=len(candidates)))
    print(dict(counts),len(cases),len(candidates),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tables",action="store_true")
    main(parser.parse_args().tables)
