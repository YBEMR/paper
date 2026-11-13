"""Two prospectively fixed parameter roots; no scheduler or heat screening."""
from pathlib import Path
import json
import time
import traceback

from research.chapter4_scheduler.scaling import input as original

ROOTS=(('U03',2026111303),('U04',2026111304))
NAMESPACE='ch4-independent-i1-v1'
SCALE=12


def fixed_plan():
    plan=original.fixed_plan()
    plan.update(schema='chapter4-frozen-I1-new-parameter-roots-v1',namespace=NAMESPACE,
        roots=[{'root_id':r,'seed':s} for r,s in ROOTS],scales=[SCALE],
        scale_rule='Direct original build_base(scale=12,parent=None); no 6/24 Stage construction.',
        algorithm_frozen_before_generation='6d67cf2538280c3fee4ab5b7879570b204bb6224',
        selection='Exactly these two named random streams, declared before generation. No replacement, tuning, ranking, scheduler or thermal screening.',
        scope='New parameters drawn from the existing prototype/workload/topology family after I1/ON freeze; not new topology families or external blind tasks.')
    return plan


def construct(catalog,config,root_id,seed,plan):
    from research.chapter3_workload_calibration.generator import build_base
    from research.chapter3_calibration_adjustment.window_policy import make_window_receipt
    from research.chapter3_formal_input_adapter.core import adapt_bundle
    case_id=f'{root_id}__n12'
    raw=build_base(catalog,root_id=root_id,namespace=plan['namespace'],seed=seed,
        scene_pool='A',compatibility_pool='heterogeneous',scale=12,settings=plan['settings'],parent=None)
    bundle=original._project_base(raw)
    evidence=original._time_evidence(bundle)
    window=make_window_receipt(case_id,'S2',{'base':evidence},beta=original.BETA,baseline=evidence)
    adapted=adapt_bundle(bundle,evidence['deadlines'][original.BETA],window,
        member_key='base',config=config,instance_id=case_id)
    check=original._static_check(adapted,evidence)
    metrics=original._metrics(adapted,evidence)
    if metrics['stages_per_scene']!=[12,12]:raise ValueError('TWELVE_STAGES_PER_SCENE_REQUIRED')
    return adapted,{'unprojected_eight_scene_bundle':raw,'two_scene_evidence':evidence,
        'window_receipt':window,'adaptation_receipt':adapted['receipt'],'static_check':check,'metrics':metrics}


def build_inputs(out):
    from research.chapter3_workload_calibration.profiles import load_catalog
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    plan=fixed_plan();original._save(out/'input_plan.json',plan)
    cases=[];started=time.perf_counter();current=None
    try:
        catalog=load_catalog(original.SOURCE_CONFIG)
        config=json.loads(original.SOURCE_CONFIG.read_text(encoding='utf-8'))
        for root,seed in ROOTS:
            current=f'{root}__n12';directory=out/current;directory.mkdir()
            original._save(directory/'generation_started.json',{'root_id':root,'seed':seed,
                'plan_sha256':original._sha(out/'input_plan.json'),'no_retry':True})
            began=time.perf_counter()
            adapted,evidence=construct(catalog,config,root,seed,plan)
            evidence['generation_seconds']=time.perf_counter()-began
            original._save(directory/'config.json',adapted['config'])
            original._save(directory/'instance.json',adapted['instance'])
            original._save(directory/'generation_evidence.json',evidence)
            cases.append({'case_id':current,'root_id':root,'seed':seed,'stages_per_scene':12,'scenes':2,
                **{k+'_path':f'{current}/{k}.json' for k in ('config','instance','generation_evidence')},
                **{k+'_sha256':original._sha(directory/(k+'.json')) for k in ('config','instance','generation_evidence')},
                'metrics':evidence['metrics']})
    except BaseException as error:
        original._save(out/'generation_failure.json',{'case_id':current,'completed_cases':cases,
            'error':repr(error),'traceback':traceback.format_exc(),'retry_count':0,'replacement_count':0,
            'thermal_evaluations':0,'method_calls':0})
        raise
    manifest={'schema':'chapter4-two-new-I1-roots-inputs-v1','plan_sha256':original._sha(out/'input_plan.json'),
        'cases':cases,'input_construction_seconds':time.perf_counter()-started,
        'counters':{'parameter_roots':2,'mapping_constructions':2,'H_timetable_constructions':2,
            'scene_schedules':4,'thermal_evaluations':0,'HEFT_ON_OFF_SA_calls':0,'retries':0,'replacements':0}}
    original._save(out/'inputs_manifest.json',manifest)
    return manifest
