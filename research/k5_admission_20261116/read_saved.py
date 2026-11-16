"""Post-run descriptive counts only; no physical evaluation or search."""
from pathlib import Path
from collections import Counter
import csv,json,time,hashlib

root=Path(__file__).resolve().parent
start=time.perf_counter()
rows=list(csv.DictReader((root/'run01/cases.csv').open(encoding='utf-8')))
methods=list(csv.DictReader((root/'run01/methods.csv').open(encoding='utf-8')))
feasible={r['case_id'] for r in rows if r['E_J']}
filtered=sum(int(r['deadline_thermal_violations'])>0 for r in rows)
noheat_lookup={r['case_id']:r for r in methods if r['method']=='E0_no_thermal_constraint'}
noheat_safe=sum(noheat_lookup[c]['status']=='SAFE' for c in feasible)
d_fail=Counter(r['status'] for r in methods if r['method']=='D' and r['case_id'] in feasible and r['status']!='SAFE')
map_reduction=sum(len(json.loads(r['all_optimal_maps']))<len(json.loads(r['all_noheat_optimal_maps'])) for r in rows if r['E_J'])
cap_count=sum(json.loads(r['note'])['step_cap_reached'] for r in methods if r['method']=='D')
by_thermal=[]
for tau in [1,10,100]:
    for gain in [.5,2]:
        rr=[r for r in rows if float(r['tau_over_time_unit'])==tau and float(r['single_power_steady_theta_gain'])==gain]
        by_thermal.append(dict(tau_over_L=tau,kappa=gain,cases=len(rr),feasible=sum(bool(r['E_J']) for r in rr),
                               thermal_infeasible=sum(int(r['deadline_feasible'])>0 and not r['E_J'] for r in rr),
                               any_deadline_feasible_schedule_rejected_by_heat=sum(int(r['deadline_thermal_violations'])>0 for r in rr)))
method_pairs={m:{r['case_id']:r for r in methods if r['method']==m} for m in ['A','B','D','E']}
gain_vs={}
for m in ['A','B']:
    pp=[(method_pairs[m][c],method_pairs['E'][c]) for c in feasible if method_pairs[m][c]['status']=='SAFE']
    gain_vs[m]=dict(safe_pairs=len(pp),positive_energy_difference_pairs=sum(float(a['energy_J'])-float(e['energy_J'])>1e-10 for a,e in pp),
                    max_safe_energy_difference_J=max((float(a['energy_J'])-float(e['energy_J']) for a,e in pp),default=None))
result=dict(posthoc=True,new_physical_evaluations=0,new_searches=0,
    cases_with_any_ontime_schedule_rejected_by_heat=filtered,
    feasible_cases_with_unchanged_safe_noheat_winner=noheat_safe,
    feasible_cases_with_reduced_optimal_mapping_set=map_reduction,
    D_failed_feasible_statuses=dict(d_fail),D_step_caps=cap_count,
    comparison_to_fixed_width= gain_vs,thermal_parameter_groups=by_thermal,
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),wall_s=time.perf_counter()-start)
(root/'run01/posthoc_summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
