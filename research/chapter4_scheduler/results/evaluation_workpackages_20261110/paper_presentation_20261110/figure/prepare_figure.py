"""Freeze ten bounded same-model calls for paper figure samples."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from fractions import Fraction as F

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];C=ROOT/'workpackage_C';REPO=ROOT.parents[3]
sys.path.insert(0,str(OUT))
from figure_core import repeat_history,split_history,signature
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')

def main():
    frozen=OUT/'frozen';frozen.mkdir(exist_ok=False);cplan=read(C/'plan.json');cases=[];data={};checks=[]
    assert sha(C/'plan.json')==read(C/'plan_identity.json')['sha256']
    c_manifest=read(C/'C_final_manifest.json')['files_sha256']
    for name,value in c_manifest.items():assert sha(C/name)==value,'C_SOURCE_MANIFEST_DRIFT:'+name
    sources={str((C/'plan.json').relative_to(REPO)):sha(C/'plan.json'),str((C/'C_final_manifest.json').relative_to(REPO)):sha(C/'C_final_manifest.json')}
    config=read(C/'frozen/input_config.json');instance=read(C/'frozen/input_instance.json');save(frozen/'input_config.json',config);save(frozen/'input_instance.json',instance)
    for period in ['75','80','85','90']:
        slot=next(v for v in cplan['slots'] if v['template']=='All-H initial' and v['scene_id']=='AB_offset_0ms' and v['period_ms']==period);spec_path=C/'frozen'/(slot['id']+'.json');spec=read(spec_path);coarse,origin=repeat_history(spec['segments'],period,'3000');fine,parent=split_history(coarse)
        assert len(fine)+1<=2000
        for row,mapping in zip(coarse,origin):assert signature(row)==signature(spec['segments'][mapping['source_segment_index']])
        key='startup_P'+period;save(frozen/(key+'_power.json'),{'coarse_segments':coarse,'fine_segments':fine,'fine_parent_indices':parent,'coarse_period_origin':origin,'source_C_slot':slot})
        cases.append({'id':key,'panel':'startup','template':'All-H initial','period_ms':period,'window_ms':'3000','scene_id':'AB_offset_0ms','entry_degC':['50']*4,'limits_degC':['80']*4,'power_file':key+'_power.json','seconds':180,'maximum_trace_points_including_initial':2000,'candidate_sha256':slot['candidate_sha256'],'source_C_slot':slot['id']})
        sources[str(spec_path.relative_to(REPO))]=sha(spec_path)
        result_path=C/'real_run01'/slot['id']/'result.json';result=read(result_path);sources[str(result_path.relative_to(REPO))]=sha(result_path);data[key]={'C_classification':result['classification'],'C_result':result['result']}
    for template in ['All-H initial','Enhanced HEFT final','MILP final']:
        slot=next(v for v in cplan['slots'] if v['template']==template and v['scene_id']=='AB_offset_0ms' and v['period_ms']=='90');spec_path=C/'frozen'/(slot['id']+'.json');spec=read(spec_path);result_path=C/'real_run01'/slot['id']/'result.json';r=read(result_path)['result'];coarse=spec['segments'];fine,parent=split_history(coarse)
        assert len(fine)+1<=100
        key='steady_'+template.replace(' ','_');save(frozen/(key+'_power.json'),{'coarse_segments':coarse,'fine_segments':fine,'fine_parent_indices':parent,'source_C_slot':slot});box=r['periodic_entry_box_degC']
        for side,index in [('lower',0),('upper',1)]:cases.append({'id':key+'_'+side,'panel':'steady','side':side,'template':template,'period_ms':'90','window_ms':'90','scene_id':'AB_offset_0ms','entry_degC':[v[index] for v in box],'limits_degC':['80']*4,'power_file':key+'_power.json','seconds':60,'maximum_trace_points_including_initial':100,'candidate_sha256':slot['candidate_sha256'],'source_C_slot':slot['id']})
        sources[str(spec_path.relative_to(REPO))]=sha(spec_path);sources[str(result_path.relative_to(REPO))]=sha(result_path);data[key]={'C_result':r}
    # Synthetic boundary tests: no model/heat calls.
    fake=[{'start_ms':'0','end_ms':'3','duration_ms':'3','power':['7','8'],'active_stage_ids':['x']},{'start_ms':'3','end_ms':'5','duration_ms':'2','power':['1','2'],'active_stage_ids':[]}]
    repeated,mapping=repeat_history(fake,'5','12');fine,parent=split_history(repeated);assert len(repeated)==5 and repeated[-1]['end_ms']=='12' and repeated[-1]['duration_ms']=='2';checks.append('repeat exact busy/idle and truncate last observation')
    assert sum(F(v['duration_ms']) for v in fine)==12 and all(F(v['duration_ms'])<=2 for v in fine);checks.append('split duration/area and maximum step')
    assert fake[0]['end_ms']=='3' and all(signature(v)==signature(repeated[p]) for v,p in zip(fine,parent));checks.append('source immutable and all vectors preserved')
    save(OUT/'artificial_checks.json',{'utc':datetime.now(timezone.utc).isoformat(),'passed':True,'checks':checks,'real_heat_calls':0,'scheduling_search_calls':0})
    save(frozen/'C_reference_data.json',data)
    for name in ['thermal.py','schedules.py','control_policy.py','start_domain.py']:
        p=REPO/'research/chapter3_experiments'/name;sources[str(p.relative_to(REPO))]=sha(p)
    interval=REPO/'research/v1_evaluator/interval.py';sources[str(interval.relative_to(REPO))]=sha(interval)
    code={p.name:sha(p) for p in OUT.glob('*.py')}
    import importlib.metadata,platform
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'purpose':'TWO_PANEL_PAPER_TEMPERATURE_FIGURE_FIXED_AB_NPU0','cases':cases,'limits':{'max_original_kernel_calls':10,'startup_seconds_each':180,'steady_seconds_each':60,'total_seconds':1200,'maximum_step_ms':'2','maximum_left_vector_points_each':2000,'maximum_right_vector_points_each':100,'panels_each':100000,'refinements_each':20000},
        'environment':{'python':sys.version,'platform':platform.platform(),'numpy':importlib.metadata.version('numpy'),'scipy':importlib.metadata.version('scipy'),'matplotlib':importlib.metadata.version('matplotlib')},
        'scope':'Only the existing frozen C templates/configurations. Left repeats same All-H AB power histories continuously to3s, no temperature resets; right original C proved periodic-entry box lower/upper paths at90ms. Original400ms schedule identities/deadlines and model unchanged.',
        'display':'AB/NPU0 explicitly. Lines connect<=2ms sampled interval midpoints; no continuous safety or first-crossing claim from interpolation. Old C witness points are already-certified points, not exact first crossings. Unsafe continuations show fixed-model diagnostic with no thermal shutdown; only within20..100 model range. Right initial state is periodic, not50C. HEFT/MILP not offset to separate curves.',
        'safety_evidence':'Original C certificates retained separately. New sample values do not replace C continuous claims. Four-node model fully propagated even though only NPU0 drawn.',
        'source_sha256':sources,'code_sha256':code,'frozen_sha256':{p.name:sha(p) for p in frozen.iterdir()},'artificial_checks_passed':True,'real_calls_during_preparation':0,'no_retries_search_or_scans':True}
    save(OUT/'plan.json',plan);save(OUT/'plan_identity.json',{'sha256':sha(OUT/'plan.json'),'utc':datetime.now(timezone.utc).isoformat()});print({'plan_sha256':sha(OUT/'plan.json'),'calls':len(cases),'real_heat_calls':0},flush=True)

if __name__=='__main__':main()
