"""Read-only extraction of existing audited results; no scientific calls."""
import csv
from datetime import datetime, timezone
from fractions import Fraction as F
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
def save(p,value):
    with p.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')

summary=read(OUT/'execution/summary.json');audit=read(OUT/'audit.json')
assert audit['passed'] and summary['batch']['completed']
rows=[];detail=[]
for row in summary['rows']:
    slot=row['slot'];r=row['result'];post=row['post'];folder=OUT/'execution/calls'/slot['id']
    raw=read(folder/'method/result.json');worker=read(folder/'worker_command_return.json')
    item={'id':slot['id'],'arm':slot['arm'],'seed':slot['seed'],'terminal':r['terminal'],
        'success':row['success'],'energy_lower_J':r['energy_interval_J'][0],
        'energy_upper_J':r['energy_interval_J'][1],'energy_upper_J_rounded':float(F(r['energy_interval_J'][1])),
        'started_utc':worker['started_utc'],'ended_utc':worker['ended_utc'],
        'method_root_s':r['timing']['method_elapsed_s'],'method_process_s':worker['wall_s'],
        'post_root_s':post['timing']['method_elapsed_s'],
        'post_process_s':read(folder/'post_command_return.json')['wall_s'],
        'first_SAFE_s':r['first_SAFE_at_s'],
        'first_strict_improvement_over_first_SAFE_s':r['first_strict_improvement_over_first_SAFE_at_s'],
        'own_final_quality_s':r['first_own_final_quality_at_s'],
        'HEFT_quality_s':row['time_to_reference_upper_s']['HEFT'],
        'ON_quality_s':row['time_to_reference_upper_s']['ON'],
        'maximum_peak_upper_degC':float(max(F(interval[1]) for scene in raw['evaluation']['scenes'].values()
            for interval in scene['peaks_degC'].values())),**r['counts']}
    rows.append(item)
    detail.append({'slot':slot,'initialization':r['initialization_phase_records'],
        'first_neighbour_assessment_at_s':r['first_neighbour_assessment_at_s'],
        'clock_origin':r['timing']['clock_origin'],
        'root_deadline_overshoot_s':r['timing']['deadline_overshoot_s'],
        'native_search_metadata':r['native_search_metadata'],'coverage':r['coverage'],
        'final_candidate_sha256':raw['evaluation']['evidence_identity']['candidate_sha256'],
        'scene_energy_and_thermal':{s:{k:v[k] for k in ('energy_J','energy_components_J','peaks_degC','violations','covered_until_s')}
            for s,v in raw['evaluation']['scenes'].items()},
        'initial_safe_snapshot_sha256':r['initial_safe_snapshot_sha256'],
        'ON_proposal_observations':[{k:q.get(k) for k in ('candidate_sha256','base_candidate_sha256',
            'scene_id','selected_stages','orientation','additional_reversed_edges','energy_target',
            'strict_accepted','proposed_at_s')} for q in raw.get('graph_proposals',[])]})
heft=next(F(r['energy_upper_J']) for r in rows if r['arm']=='HEFT')
on=next(F(r['energy_upper_J']) for r in rows if r['arm']=='ON')
median=F(summary['SA']['energy_upper_J_median_among_successes'])
sa=[r for r in rows if r['arm']=='SA']
statistics={'SA':summary['SA'],'ON_energy_reduction_vs_HEFT_percent':float(100*(heft-on)/heft),
    'ON_energy_reduction_vs_SA_median_percent':float(100*(median-on)/median),
    'SA_seeds_reached_ON_quality':[r['seed'] for r in sa if r['ON_quality_s'] is not None],
    'SA_seeds_reached_HEFT_quality':[r['seed'] for r in sa if r['HEFT_quality_s'] is not None],
    'SA_seeds_reached_HEFT_quality_before_HEFT_itself':[r['seed'] for r in sa if r['HEFT_quality_s'] is not None and r['HEFT_quality_s']<next(x['HEFT_quality_s'] for x in rows if x['arm']=='HEFT')],
    'counts_total':audit['counts_total'],'all_seven_SAFE_and_post':all(r['success'] for r in rows),
    'maximum_final_peak_upper_degC':max(r['maximum_peak_upper_degC'] for r in rows)}
with (OUT/'metrics.csv').open('x',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
save(OUT/'metrics.json',{'created_utc':datetime.now(timezone.utc).isoformat(),
    'plan_sha256':summary['plan_sha256'],'batch':summary['batch'],'rows':rows,'detail':detail,
    'statistics':statistics,'nature':'Existing-record extraction only; energy upper comparisons are observations, post uses same evaluator'})
print(json.dumps({'rows':len(rows),'statistics':statistics},ensure_ascii=False),flush=True)
