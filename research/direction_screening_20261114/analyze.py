import json, pathlib, collections, math
root=pathlib.Path(__file__).parent
rows=[json.loads(x) for x in (root/'results/all_candidates.jsonl').read_text().splitlines()]
full={(r['id'],r['state']):r for r in rows if r['variant']=='full'}
summary=json.loads((root/'results/summary.json').read_text())
ans={}
for direction in ['A','B']:
    states=['cool','warm']
    ids=sorted({r['id'] for r in full.values() if r['direction']==direction})
    bests={s:min((full[i,s] for i in ids if full[i,s]['feasible']),key=lambda r:r['energy_J']) for s in states}
    valid=[i for i in ids if all(full[i,s]['feasible'] for s in states)]
    fixed=min(valid,key=lambda i:sum(full[i,s]['energy_J'] for s in states))
    fixedsum=sum(full[fixed,s]['energy_J'] for s in states)
    adapsum=sum(bests[s]['energy_J'] for s in states)
    ans[direction]=dict(best_ids={s:r['id'] for s,r in bests.items()},fixed_id=fixed,
        fixed_sum_J=fixedsum,adaptive_sum_J=adapsum,adaptive_gain_J=fixedsum-adapsum,
        adaptive_gain_percent=100*(fixedsum-adapsum)/fixedsum)
    for s in states:
        ids_show=['A-10-0-0','A-10-0-2','A-10-0-3','A-10-0-6','A-10-1-6'] if direction=='A' else ['B-1111-0000','B-22-00','B-211-100','B-22-11','B-4-0']
        ans[direction][s]=[{k:full[i,s][k] for k in ['id','energy_J','dynamic_J','leakage_J','base_J','switching_J','completion_s','peak_C','feasible','extended_energy_J','structure','terminal_C']} for i in ids_show]
ans['B']['frozen_temperature_threshold_C']=40+math.log((.006/.014-.17)/(.85*.2))/.035
ans['B']['threshold_expression']='0.006 - 0.014*(0.17 + 0.85*0.2*exp(0.035*(T-40))) = 0'
ans['all_temperature_max_C']=max(r['peak_C'] for r in rows if r['variant']=='full')
ans['all_temperature_minimum_margin_C']=80-ans['all_temperature_max_C']
ans['unique_A_schedules']=None
# Count actual event schedules separately from action aliases.
import screen
ans['unique_A_schedules']=len({json.dumps(screen.a_schedule(a,'full')[0],sort_keys=True) for a in screen.a_actions()})
(root/'results/analysis.json').write_text(json.dumps(ans,indent=2),encoding='utf-8')
print(json.dumps(ans,indent=2))
