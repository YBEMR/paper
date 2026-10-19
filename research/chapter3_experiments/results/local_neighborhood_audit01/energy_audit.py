from fractions import Fraction as F
from pathlib import Path
import hashlib,json
P=Path('research/chapter3_experiments/results/cumulative_pair_diagnostic01/call_off/invocation')
instance=json.loads((P/'input_instance.json').read_text(encoding='utf8'))
platform=instance['platform']; W=F(instance['window_ms'])/1000
nodes=platform['node_order']; domains=platform['domains']
def iv(x): return [F(x[0]),F(x[1])]
def ser(x):
 if isinstance(x,F): return str(x)
 if isinstance(x,dict): return {k:ser(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)): return [ser(v) for v in x]
 return x
out={'protocol':'K123_READ_ONLY_ARCHIVED_ENERGY_AUDIT_V1','source_root':str(P),'source_sha256':{},'computed_scope':'Exact rational sums/products of archived input, legal segments and node-injected energies. No new schedule, model, LP/MILP, thermal propagation or production evaluator import.','temperature_tail_status':'Not separately archived; not reconstructed. Full-scene temperature correction by node can be recovered from archived node-injected energy less exact baseline/activity.','scenes':{}}
for name in ['result.json','initial_scene_000.json','initial_scene_001.json','input_instance.json','input_config.json']:
 out['source_sha256'][name]=hashlib.sha256((P/name).read_bytes()).hexdigest()
weighted={k:[F(0),F(0)] for k in ['baseline','activity','external_common','temperature_correction','total']}
for j,scene in enumerate(instance['scenarios']):
 sid=scene['id']; a=json.loads((P/f'initial_scene_{j:03d}.json').read_text(encoding='utf8')); e=a['witness']['evaluation']['scenes'][sid]; leg=a['witness']['evaluation']['legality']['scenes'][sid]
 assert e['state']=='SAFE' and e['complete'] and e['covered_until_s']=='2/5'
 rows=leg['rows']; segs=leg['segments']; last=max(F(x['end_ms']) for x in rows); tail=[x for x in segs if F(x['start_ms'])>=last]
 domain_info={}; node_info={}
 for node in nodes:
  base=sum(F(s['baseline_by_node_W'][node])*F(s['duration_ms'])/1000 for s in segs)
  act=sum(F(s['activity_by_node_W'][node])*F(s['duration_ms'])/1000 for s in segs)
  inj=iv(e['node_injected_energy_J'][node]);corr=[z-base-act for z in inj]
  node_info[node]={'baseline_J':base,'activity_J':act,'temperature_correction_J':corr,'node_injected_energy_J':inj}
 for dom,d in domains.items():
  opp_durations={o:sum(F(s['duration_ms']) for s in segs if s['domain_opps'][dom]==o) for o in d['opps']}
  base=sum(F(s['baseline_by_power_group_W'][dom])*F(s['duration_ms'])/1000 for s in segs)
  floor=F(d['baseline_W']['L'])*W
  domain_info[dom]={'opp_duration_ms':opp_durations,'full_window_L_baseline_J':floor,'archived_opp_baseline_J':base,'opp_excess_over_L_J':base-floor}
 tail_base=sum(sum(F(v) for v in s['baseline_by_power_group_W'].values())*F(s['duration_ms'])/1000 for s in tail)
 tail_common=sum(F(s['external_common_power_W'])*F(s['duration_ms'])/1000 for s in tail)
 stage=[]
 for row in rows:
  ss=row['shared_stage_id'];current=F(row['activity_power_W'])*F(row['duration_ms'])/1000
  choices=[]
  for m in instance['stage_modes'][ss]:
   if m['unit_id']!=row['unit']:continue
   choices.append({'opp':m['opp_id'],'duration_ms':m['duration_ms'],'activity_power_W':m['activity_power_W'],'activity_energy_J':m['activity_energy_J'],'activity_reduction_vs_current_J':current-F(m['activity_energy_J'])})
  stage.append({'stage_id':ss,'unit':row['unit'],'opp':row['opp'],'start_ms':row['start_ms'],'end_ms':row['end_ms'],'activity_J':current,'same_device_options':choices})
 parts={k:iv(v) for k,v in e['energy_components_J'].items()};parts['total']=iv(e['energy_J'])
 for k,v in parts.items():
  for endpoint in range(2):weighted[k][endpoint]+=F(scene['weight'])*v[endpoint]
 assert parts['baseline'][0] <= sum(x['baseline_J'] for x in node_info.values()) <= parts['baseline'][1]
 assert parts['activity'][0] <= sum(x['activity_J'] for x in node_info.values()) <= parts['activity'][1]
 corr=[sum(x['temperature_correction_J'][k] for x in node_info.values()) for k in range(2)]
 assert max(corr[0],parts['temperature_correction'][0])<=min(corr[1],parts['temperature_correction'][1])
 out['scenes'][sid]={'weight':scene['weight'],'archived_energy_components_J':parts,'domain_baseline':domain_info,'node_energy':node_info,'stages':stage,'all_work_complete_ms':last,'all_idle_tail':{'start_ms':last,'end_ms':F(instance['window_ms']),'duration_ms':F(instance['window_ms'])-last,'baseline_J':tail_base,'external_common_J':tail_common,'temperature_independent_energy_J':tail_base+tail_common,'temperature_correction_J':None,'reason':'No separate tail energy integral in saved trace; not reconstructed.'},'request_completion_ms':leg['request_completion_ms'],'source_pointer':f'initial_scene_{j:03d}.json#/witness/evaluation'}
out['weighted_components_J']=weighted
out['full_window_L_baseline_J']=sum(F(d['baseline_W']['L'])*W for d in domains.values())
out['external_common_full_window_J']=F(platform['external_common_power_W'])*W
out['weighted_OPP_excess_J']=sum(F(scene['weight'])*sum(F(v['opp_excess_over_L_J']) for v in out['scenes'][scene['id']]['domain_baseline'].values()) for scene in instance['scenarios'])
out['weighted_same_device_catalog_activity_floor_J']=sum(F(scene['weight'])*sum(min(F(v['activity_energy_J']) for v in stage['same_device_options']) for stage in out['scenes'][scene['id']]['stages']) for scene in instance['scenarios'])
out['nominal_activity_reduction_if_each_chose_its_minimum_J']=weighted['activity'][0]-out['weighted_same_device_catalog_activity_floor_J']
out['main_stage_weighted_activity_J']=sum(F(scene['weight'])*sum(stage['activity_J'] for stage in out['scenes'][scene['id']]['stages'] if stage['stage_id'].endswith('.main')) for scene in instance['scenarios'])
out['limitations']=['All saved Stage choices are H. Catalog lower q*d values identify activity-energy opportunities only; no replacement was constructed/evaluated.', 'Shared CPU-domain baselines are counted once, so Stage-local baseline energy cannot generally be added without accounting for overlap.', 'Temperature correction is state/history/OPP dependent and can only be re-evaluated for a new complete schedule; archived node attribution is not a marginal saving.', 'N2: all CPU options of B.main have activity energy greater than its current NPU-H; C.main CPU-L has lower activity than current GPU-H but higher activity than GPU-L. A mapping change cannot be justified from activity energy alone; resources, durations and thermal histories may differ.', 'Long idle tail baseline/external energy is unavoidable under fixed W and powered devices, except the temp correction can depend on preceding work.']
Path('.runtime').mkdir(exist_ok=True)
Path('.runtime/k123_energy_audit.json').write_text(json.dumps(ser(out),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('WEIGHTED', {k:float(v[1]) for k,v in weighted.items()})
for sid,e in out['scenes'].items():
 print(sid,'domains', {k:{'baseline':float(v['archived_opp_baseline_J']),'excess':float(v['opp_excess_over_L_J'])} for k,v in e['domain_baseline'].items()})
 print('nodes', {k:{'baseline':float(v['baseline_J']),'activity':float(v['activity_J']),'temperature':float(v['temperature_correction_J'][1])} for k,v in e['node_energy'].items()})
 print('tail',ser(e['all_idle_tail']))
 print('mode_activity_reductions',[(s['stage_id'],[(x['opp'],round(float(x['activity_reduction_vs_current_J']),9)) for x in s['same_device_options']]) for s in e['stages']])
