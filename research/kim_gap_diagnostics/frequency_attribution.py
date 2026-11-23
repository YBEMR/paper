"""Recover independent proxy energies algebraically from ALREADY archived scene traces.

No dispatch, thermal integration, new policy evaluation or optimizer call. For fixed
OPP and duration, the leakage energy slope w depends only on the frozen RC model:
E(T_ref) = E(T_entry) - w @ (T_entry-T_ref). Compare original SetFreq against
the already certified optimal policy in its own proxy objective.
"""
import sys
from time import perf_counter
import numpy as np
from analyze_gap import ROOT,HERE,read,lines,csv_out
sys.path.insert(0,str(ROOT/"research/kim_synthetic_platform_v1"))
from profiles import thermal_kwargs
from thermal import modes

def reset_energy(physical,ambient,platform):
    parts=[]
    for scene in physical["scene_rows"]:
        kw=thermal_kwargs(platform,scene["opp"],ambient,True,"base")
        lam,u,inv=modes(tuple(kw["capacity_J_K"]),tuple(map(tuple,kw["conductance_W_K"])),tuple(kw["slope_W_K"]))
        duration=(scene["end_ns"]-scene["start_ns"])*1e-9
        w=((np.asarray(kw["slope_W_K"])@u)*(np.expm1(lam*duration)/lam))@inv
        delta=np.asarray(scene["entry_c"])-np.asarray(kw["initial_C"])
        parts.append(float(scene["energy_j"]-delta@w))
    return sum(parts),parts

def main():
    begin=perf_counter();s=read(HERE/"summary.json")
    platform=read(ROOT/"research/kim_synthetic_platform_v1/platform.json")
    cases={r["case_id"]:r for r in s["cases"]};physical={};rows=[];maxerror=0.
    for c in s["cases"]:
        for phase in ["fixed_frequency","deployment_probe"]:
            for r in lines(HERE/"raw"/c["case_id"]/phase/"physical.jsonl.gz"):
                physical[c["case_id"],phase,r["dep"],tuple(r["indices"])]=r["physical"]
    for row in s["candidates"]:
        if row["setfreq_status"]!="SAFE" or row["best_safe_j"] is None:continue
        case=cases[row["case_id"]];prefix=row["case_id"],row["phase"],row["dep"]
        sf=physical[*prefix,tuple(row["setfreq_indices"])]
        best=physical[*prefix,tuple(row["optimal_indices"])]
        sfproxy,sfparts=reset_energy(sf,case["ambient_c"],platform)
        optproxy,optparts=reset_energy(best,case["ambient_c"],platform)
        error=abs(sfproxy-row["setfreq_proxy_j"]);maxerror=max(error,maxerror);assert error<=1e-7
        loss=row["setfreq_continuous_j"]-row["best_safe_j"]
        label="no_observed_frequency_loss"
        if loss>1e-7:
            label="SetFreq_missed_a_lower_proxy_policy" if optproxy<sfproxy-1e-7 else (
                  "proxy_continuous_reversal" if optproxy>sfproxy+1e-7 else "proxy_tie_continuous_difference")
        rows.append(dict(case_id=row["case_id"],phase=row["phase"],dep=row["dep"],certificate=row["certificate"],
            setfreq_indices=row["setfreq_indices"],optimal_indices=row["optimal_indices"],
            setfreq_j=row["setfreq_continuous_j"],joint_optimum_j=row["best_safe_j"],
            within_deployment_saving_pct=100*loss/row["setfreq_continuous_j"],
            versus_best_kim_saving_pct=100*(case["kim_energy_j"]-row["best_safe_j"])/case["kim_energy_j"],
            setfreq_proxy_j=sfproxy,optimal_policy_proxy_j=optproxy,proxy_difference_j=sfproxy-optproxy,
            setfreq_proxy_by_scene=sfparts,optimal_proxy_by_scene=optparts,classification=label))
    csv_out("frequency_attribution.csv",rows)
    from collections import Counter
    import json
    report=dict(method="algebraic reset-energy reconstruction from archived scene entries/energies; no new physical evaluation",
        rows=rows,counts=dict(Counter(r["classification"] for r in rows)),max_proxy_reconstruction_error_j=maxerror,
        elapsed_s=perf_counter()-begin)
    (HERE/"frequency_attribution.json").write_bytes((json.dumps(report,indent=2)+"\n").encode())
    print(report["counts"],"maximum validation error J",maxerror)
if __name__=="__main__":main()
