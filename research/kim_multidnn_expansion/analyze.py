"""Read saved arrays and results only; never schedule or integrate a new policy."""
import csv
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw' / 'expanded'


def put_csv(path, rows):
    if rows:
        with path.open('w', encoding='utf8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)


def main():
    catalog = json.loads((HERE/'expanded_input.json').read_text(encoding='utf8'))
    results = json.loads((RAW/'results.json').read_text(encoding='utf8'))
    selections, summaries, witnesses, costs = [], [], [], []
    for result in results:
        case = result['case']['id']
        folder = RAW/case
        deployments = json.loads((folder/'deployments.json').read_text(encoding='utf8'))
        resources = list(csv.DictReader((folder/'sc2_resources.csv').open(encoding='utf8')))
        resource_lookup = {(r['deployment'],r['opp']): r for r in resources}
        reference = result['historical_ac']['joint']
        best = result['decisions']['joint']
        independent = result['decisions']['independent']
        summaries.append(dict(case=case, covered=len(result['completed_deployments']),
            catalog_size=81, coverage_complete=result['coverage_complete'],
            global_optimality_proven=result['global_optimality_proven'],
            baseline_ac_j=reference['physical']['energy_j'] if reference else None,
            best_found_j=best['physical']['energy_j'] if best else None,
            best_deployment=best['deployment'] if best else None,
            independent_deployment=independent['deployment'] if independent else None,
            independent_continuous_j=independent['physical']['energy_j'] if independent else None,
            independent_status=independent['physical']['thermal_status'] if independent else None,
            lower_bound_j=result['energy_lower_bound_j'],
            lower_bound_gap_pct=result['lower_bound_gap_pct'],
            classifications=json.dumps(result['summed_classifications'],separators=(',',':')),
            elapsed_s=result['elapsed_s'],overrun_s=result['budget_overrun_s'],
            compile_integrations=result['compilation_original_integrations'],
            prefix_evaluations=result['joint_prefix_evaluations'],
            fallback_integrations=result['fallback_integrations'],
            full_replays=result['full_policy_replays']))
        a = np.load(folder/'space_A.npz',allow_pickle=False)['status']
        c = np.load(folder/'space_C.npz',allow_pickle=False)['status']
        for d in deployments:
            dep = d['deployment']
            specs = catalog['deployments'][dep]['per_app_candidate_ids']
            x = d['joint']
            opp = x['opps'][result['case']['order'].index('sc2')] if x else None
            sc2 = resource_lookup.get((dep,opp))
            selections.append(dict(case=case,deployment=dep,structures='|'.join(specs),
                resident_dla=catalog['deployments'][dep]['resident_dla_stages'],
                deadline_legal=d['logical_sequences']-d['deadline_failed'],safe=d['safe'],
                overtemp=d['overtemp'],unresolved=d['unresolved'],
                best_j=x['physical']['energy_j'] if x else None,
                opps='|'.join(x['opps']) if x else None,
                peak_c=max(x['physical']['peak_upper_c']) if x else None,
                gpu_peak_c=x['physical']['peak_upper_c'][1] if x else None,
                min_slack_ms=x['physical']['min_slack_ms'] if x else None,
                sc2_opp=opp,sc2_gpu_busy_ms=sc2['gpu_busy_ms'] if sc2 else None,
                sc2_dla0_busy_ms=sc2['dla0_busy_ms'] if sc2 else None,
                sc2_dla1_busy_ms=sc2['dla1_busy_ms'] if sc2 else None,
                sc2_gpu_wait_max_ms=sc2['gpu_wait_max_ms'] if sc2 else None))
            costs.append(dict(case=case,deployment=dep,scheduling_s=d['scheduling_s'],
                compile_s=d['compile_s'],joint_search_s=d['joint_search_s'],
                fallback_integrations=d['joint_fallback_integrations'],
                prefixes=d['joint_prefix_evaluations'],elapsed_s=d['elapsed_s']))
            if dep in ('A','C'):
                continue
            with np.load(folder/f'space_{dep}.npz',allow_pickle=False) as archive:
                state, energy = archive['status'],archive['energy_j']
            newly_safe = np.flatnonzero((state==1)&(a!=1)&(c!=1))
            thermal_only = np.flatnonzero((state==1)&(a==2)&(c==2))
            for kind, ids in [('same_clocks_unavailable_in_AC',newly_safe),
                              ('same_clocks_both_AC_overheat',thermal_only)]:
                if not len(ids):
                    continue
                code = int(ids[np.argmin(energy[ids])])
                witnesses.append(dict(case=case,deployment=dep,kind=kind,count=len(ids),code=code,
                    energy_j=float(energy[code]),A_status=int(a[code]),C_status=int(c[code]),
                    evidence='stored complete-domain classification; not a new physical replay'))
    put_csv(HERE/'summary.csv',summaries)
    put_csv(HERE/'deployment_outcomes.csv',selections)
    put_csv(HERE/'search_costs.csv',costs)
    put_csv(HERE/'new_feasibility_witnesses.csv',witnesses)
    summary=dict(cases=summaries,new_feasibility_witness_groups=witnesses,
                 scientific_calls=0,scope='Read-only post-analysis of preregistered saved arrays')
    (HERE/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
