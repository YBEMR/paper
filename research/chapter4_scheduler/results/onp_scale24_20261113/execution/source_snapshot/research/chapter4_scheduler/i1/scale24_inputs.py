"""Preserve saved U03/U04 roots and extend12 to24; no scientific screening."""
from pathlib import Path
import json
import time
import traceback

from research.chapter4_scheduler.scaling import input as original
from .new_inputs import ROOTS,NAMESPACE

SCALE=24
PARENTS=original.REPO/'research/chapter4_scheduler/results/unseen_i1_20261113/input_generation'


def fixed_plan():
    plan=original.fixed_plan()
    plan.update(schema='chapter4-frozen-I1-scale12-to24-inputs-v1',namespace=NAMESPACE,
        roots=[{'root_id':r,'seed':s} for r,s in ROOTS],scales=[SCALE],
        scale_rule='Original build_base(scale=24,parent=saved12); preserve existing physical/time profiles and edges. Recompute original beta1.3 deadlines/window. Work is not held constant.',
        algorithm_frozen_before_extension='d7ecc1b4ed86d2d8aabece01337c6167c6291f43',
        parent_manifest_sha256=original._sha(PARENTS/'inputs_manifest.json'),
        parent_plan_sha256=original._sha(PARENTS/'input_plan.json'),
        selection='Exactly saved U03/U04 roots. No replacement, tuning, scheduler or thermal screening, or12-stage rerun.',
        scope='Scale extension of observed roots in the same synthetic profile/topology family; not two additional unseen roots.')
    return plan


def load_parent(root_id,seed,plan):
    for name,key in (('inputs_manifest.json','parent_manifest_sha256'),('input_plan.json','parent_plan_sha256')):
        if original._sha(PARENTS/name)!=plan[key]:raise ValueError('PARENT_IDENTITY_DRIFT')
    manifest=json.loads((PARENTS/'inputs_manifest.json').read_text(encoding='utf-8'))
    case=next(c for c in manifest['cases'] if c['root_id']==root_id and c['seed']==seed)
    for k in ('config','instance','generation_evidence'):
        if original._sha(PARENTS/case[k+'_path'])!=case[k+'_sha256']:raise ValueError('PARENT_FILE_DRIFT')
    return json.loads((PARENTS/case['generation_evidence_path']).read_text(encoding='utf-8')),case


def construct(catalog,config,root_id,seed,plan,parent):
    from research.chapter3_workload_calibration.generator import build_base,validate_transform
    from research.chapter3_calibration_adjustment.window_policy import make_window_receipt
    from research.chapter3_formal_input_adapter.core import adapt_bundle
    raw_parent=parent['unprojected_eight_scene_bundle']
    selected_parent=parent['two_scene_evidence']['workload']
    p=raw_parent['provenance']
    if (p['namespace'],p['root_id'],p['seed'],p['scale'])!=(plan['namespace'],root_id,seed,12):
        raise ValueError('PARENT_LINEAGE_MISMATCH')
    case_id=f'{root_id}__n24'
    raw=build_base(catalog,root_id=root_id,namespace=plan['namespace'],seed=seed,
        scene_pool='A',compatibility_pool='heterogeneous',scale=24,settings=plan['settings'],parent=raw_parent)
    bundle=original._project_base(raw,selected_parent)
    validate_transform(raw_parent,raw);validate_transform(selected_parent,bundle)
    evidence=original._time_evidence(bundle)
    window=make_window_receipt(case_id,'S2',{'base':evidence},beta=original.BETA,baseline=evidence)
    adapted=adapt_bundle(bundle,evidence['deadlines'][original.BETA],window,
        member_key='base',config=config,instance_id=case_id)
    check=original._static_check(adapted,evidence);metrics=original._metrics(adapted,evidence)
    if metrics['stages_per_scene']!=[24,24]:raise ValueError('TWENTYFOUR_STAGES_PER_SCENE_REQUIRED')
    lineage={'parent_raw_bundle_hash':raw_parent['bundle_hash'],
        'parent_two_scene_bundle_hash':selected_parent['bundle_hash'],
        'parent_raw_contract_hash':raw_parent['contract_hash'],
        'parent_two_scene_contract_hash':selected_parent['contract_hash'],
        'existing_profiles_and_edges_preserved':True,'parent_scale':12,'child_scale':24,
        'parent_metrics':parent['metrics'],'new_reference_injected_into_initializer':False}
    return adapted,{'unprojected_eight_scene_bundle':raw,'two_scene_evidence':evidence,
        'window_receipt':window,'adaptation_receipt':adapted['receipt'],'static_check':check,
        'metrics':metrics,'lineage':lineage}


def build_inputs(out):
    from research.chapter3_workload_calibration.profiles import load_catalog
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    plan=fixed_plan();original._save(out/'input_plan.json',plan)
    cases=[];started=time.perf_counter();current=None
    try:
        catalog=load_catalog(original.SOURCE_CONFIG)
        config=json.loads(original.SOURCE_CONFIG.read_text(encoding='utf-8'))
        for root,seed in ROOTS:
            current=f'{root}__n24';directory=out/current;directory.mkdir()
            parent,parent_case=load_parent(root,seed,plan)
            original._save(directory/'generation_started.json',{'root_id':root,'seed':seed,
                'plan_sha256':original._sha(out/'input_plan.json'),'parent_case':parent_case,'no_retry':True})
            began=time.perf_counter()
            adapted,evidence=construct(catalog,config,root,seed,plan,parent)
            evidence['generation_seconds']=time.perf_counter()-began
            evidence['parent_generation_evidence_sha256']=parent_case['generation_evidence_sha256']
            original._save(directory/'config.json',adapted['config'])
            original._save(directory/'instance.json',adapted['instance'])
            original._save(directory/'generation_evidence.json',evidence)
            cases.append({'case_id':current,'root_id':root,'seed':seed,'stages_per_scene':24,'scenes':2,
                **{k+'_path':f'{current}/{k}.json' for k in ('config','instance','generation_evidence')},
                **{k+'_sha256':original._sha(directory/(k+'.json')) for k in ('config','instance','generation_evidence')},
                'metrics':evidence['metrics']})
    except BaseException as error:
        original._save(out/'generation_failure.json',{'case_id':current,'completed_cases':cases,
            'error':repr(error),'traceback':traceback.format_exc(),'retry_count':0,'replacement_count':0,
            'thermal_evaluations':0,'method_calls':0})
        raise
    manifest={'schema':'chapter4-preserved-roots-scale24-inputs-v1','plan_sha256':original._sha(out/'input_plan.json'),
        'cases':cases,'input_construction_seconds':time.perf_counter()-started,
        'counters':{'existing_parameter_roots':2,'new_parameter_roots':0,'scale_extensions':2,
            'mapping_constructions':2,'H_timetable_constructions':2,'scene_schedules':4,
            'thermal_evaluations':0,'HEFT_ON_OFF_SA_calls':0,'retries':0,'replacements':0}}
    original._save(out/'inputs_manifest.json',manifest)
    return manifest
