"""Read existing JSON only. This is not attachment-defined A/B/C execution."""
from datetime import datetime,timezone
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[3]
started=datetime.now(timezone.utc).isoformat();began=time.monotonic();sources={}
def read(relative):
    path=REPO/relative;data=path.read_bytes();sources[str(relative)]=hashlib.sha256(data).hexdigest();return json.loads(data)
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
prefix='research/chapter3_experiments/results/'
summary=read(prefix+'chapter3_closure_analysis01/summary.json')
ids=['t50_milp','t50_heft',*[f't50_sa{seed}' for seed in range(101,106)]]
rows=[];detail=[];first_instance=first_config=None
for identifier in ids:
    slot=f'{prefix}chapter3_closure_execution01/slots/{identifier}'
    method=slot+'__method/worker/method/';post_path=slot+'__post/worker/post_result.json'
    raw=read(method+'result.json');instance=read(method+'input_instance.json');config=read(method+'input_config.json');post=read(post_path)
    record=next(r for r in summary['methods'] if r['id']==identifier)
    if first_instance is None:first_instance,first_config=instance,config
    assert instance==first_instance and config==first_config
    assert instance['window_ms']=='400'
    assert record['case']=='t50_full' and record['enforce_80C_in_planning']
    final=raw['safe_candidate'];assert final==record['final_candidate']
    evaluation=post['evaluation'];availability=[]
    for sid,scene in evaluation['scenes'].items():
        assert scene['complete'] and F(scene['covered_until_s'])==F(2,5)
        availability.append({'scene':sid,'state':scene['state'],'covered_until_s':scene['covered_until_s'],
            'trace_points':len(scene['trace']),'node_integrals_present':set(scene['temperature_rise_integrals_Ks'])==set(instance['platform']['node_order'])})
    assert len(availability)==2 and all(s['node_integrals_present'] for s in availability)
    row={'selection_status':'CANDIDATE_FAMILY_ONLY_ATTACHMENT_TARGETS_UNKNOWN','id':identifier,'method':record['method'],'seed':record['seed'],
        'case':record['case'],'window_ms':instance['window_ms'],'input_file':method+'input_instance.json',
        'input_canonical_sha256':canonical(instance),'config_canonical_sha256':canonical(config),
        'final_candidate_canonical_sha256':canonical(final),'method_result':method+'result.json','post_result':post_path,
        'post_state':evaluation['state'],'final_energy_upper_J':evaluation['weighted_energy_J'][1],
        'summary_input_file_byte_sha256':record['input_sha256'],'both_scene_traces_and_integrals_present':True}
    rows.append(row);detail.append({'id':identifier,'availability':availability,'post_receipt_identity':evaluation.get('evidence_identity'),
        'initial_candidate_canonical_sha256':canonical(record['initial_candidate']) if record.get('initial_candidate') else None})
prepared=read(prefix+'chapter3_closure_preparation01/t50_full/input_instance.json');assert prepared==first_instance
result={'created_utc':datetime.now(timezone.utc).isoformat(),'status':'PRELIMINARY_PROVENANCE_ONLY_NOT_A_COMPLETE',
    'attachments_read':False,'exact_seven_targets_confirmed':False,'C_nine_configurations_confirmed':False,
    'candidate_family':'Existing closure_beta1_t50__R1 MILP/HEFT/SA101..105; not asserted to be attachment selection',
    'rows':rows,'detail':detail,'all_seven_inputs_and_configs_semantically_equal':True,
    'prepared_input_file_byte_sha256':sources[prefix+'chapter3_closure_preparation01/t50_full/input_instance.json'],
    'prepared_input_canonical_sha256':canonical(prepared),
    'average_temperature_possible_from_existing_integral':'Ta + integral(T-Ta)dt /0.4s; not computed pending attachment metric definitions',
    'trace_limit':'Panel-end interval samples, not a continuous safety proof or periodic stationary orbit',
    'new_search_calls':0,'new_thermal_integrations':0,'new_periodic_solves':0,'existing_sources_sha256':sources,
    'execution':{'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-began,
        'cwd':str(REPO),'python':platform.python_version(),'platform':platform.platform(),
        'subject_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()}}
with (OUT/'candidate_source_index.json').open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
with (OUT/'candidate_family_closure_t50.csv').open('x',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
print(json.dumps({'preliminary_only':True,'candidate_rows':len(rows),'same_inputs':True,'trace_scenes_with_saved_integrals':sum(len(r['availability']) for r in detail),
    'new_search':0,'new_physics':0,'new_periodic_solves':0,'wall_s':result['execution']['wall_s']},ensure_ascii=False),flush=True)
