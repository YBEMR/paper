"""Create a disarmed K172 proposal using archive/source reads only.

There is deliberately no scientific dispatch, solver import, or run command.
Recipes name existing entries for a separately authorized controlled launcher.
"""
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCIENCE = REPO/'research/chapter3_experiments'
CASES = ('base__R1','base__R3')
METHOD_SECONDS = 300
POST_SECONDS = 60


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def recipe(variant, common):
    if variant not in ('A','B','C'):
        raise ValueError('Only A/B/C in the predeclared domain')
    kwargs = {'seconds':METHOD_SECONDS,'shared_deployment':deepcopy(common['shared_deployment']),
        'builder_options':deepcopy(common['builder_options']),
        'opened_by_scene':deepcopy(common['first_opened_by_scene']),
        'scene_slice_s':150 if variant=='A' else 60}
    if variant != 'A':
        kwargs.update(linked_opened_by_scene=deepcopy(common['second_opened_by_scene']),
            preeliminate_closed_anchors=variant=='C')
    return {'variant':variant,'entry_module':'neighborhood_method' if variant=='A' else 'linked_method',
        'entry_function':'execute_n1_neighborhood' if variant=='A' else 'execute_linked_fixed_unit_opp_start',
        'kwargs':kwargs,'runtime_arguments':{
            'input_loader':'p0_batch.run_p0.fresh_input(case_id, budget), called once inside root',
            'workdir':'new per-slot directory, no historical results loaded',
            'budget':'one caller-owned MethodBudget(300), created before arm-entry import and all case work, passed unchanged',
            'clock':'same budget.clock',
            'session_factory':'partial(MatlabSession, cut_max_iterations=10), exactly one owned worker',
            'on_global_update':'same immutable-evidence observer, fully billed'},
        'second_phase':variant!='A','new_bound_filter':False,
        'scientific_execution_authorized':False}


def entry_accepts(spec):
    """Check keyword reachability from source AST; never import the entry."""
    tree=ast.parse((SCIENCE/(spec['entry_module']+'.py')).read_text('utf-8-sig'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==spec['entry_function'])
    accepted={a.arg for a in function.args.args+function.args.kwonlyargs}
    keys=set(spec['kwargs'])|{'budget','clock','session_factory','on_global_update'}
    return bool(function.args.kwarg) or keys<=accepted


def build_proposal():
    baseline=read(SCIENCE/'results/bound_build_replay01/review/before_manifest.json')
    sources=baseline['groups']['source_sha256']
    if any(sha(REPO/name)!=value for name,value in sources.items()):
        raise ValueError('A frozen original scientific source changed')
    source_files=dict(sources)
    source_files['research/chapter3_experiments/conditional_energy_bound/bounds.py']=sha(
        SCIENCE/'conditional_energy_bound/bounds.py')
    cases=[]
    input_files={}
    for case_id in CASES:
        campaign='p0_execution01' if case_id=='base__R1' else 'p0_resume01'
        folder=SCIENCE/'results'/campaign/'calls'/case_id/'anchor_linked4'
        result, instance, config=[read(folder/name) for name in
            ('result.json','input_instance.json','input_config.json')]
        for name in ('result.json','input_instance.json','input_config.json','wrapper_raw_result.json'):
            path=folder/name
            input_files[path.relative_to(REPO).as_posix()]=sha(path)
        first, second=result['phases']
        common={'case_id':case_id,'input_sha256':canonical(instance),
            'config_sha256':canonical(config),'scene_order':[s['id'] for s in instance['scenarios']],
            'scene_weights':{s['id']:s['weight'] for s in instance['scenarios']},
            'shared_deployment':result['shared_deployment'],'builder_options':result['builder_options'],
            'first_opened_by_scene':first['condition']['opened_by_scene'],
            'second_opened_by_scene':second['condition']['opened_by_scene'],
            'window_ms':instance['window_ms'],'start_grid_ms':instance['start_grid_ms'],
            'control_policy':result['control_policy'],'accuracy_targets':config['accuracy_targets'],
            'model_source':'P0 H response, independent 50C entries, 80C limit, original four nodes',
            'archived_input_used_for':'read-only identity anchor; every future call reloads/expands input under its root clock',
            'historical_seed_reference':{
                'candidate_sha256':first['condition']['seed_candidate_sha256'],
                'use':'diagnostic label identity only; never inject the old candidate, receipt, U or cache'}}
        if (canonical(instance)!=result['identity']['full_input_sha256'] or
                canonical(config)!=result['identity']['config_sha256']):
            raise ValueError('Archived P0 identities disagree')
        recipes={v:recipe(v,common) for v in ('A','B','C')}
        if not all(entry_accepts(spec) for spec in recipes.values()):
            raise ValueError('Proposed keywords do not reach an existing entry')
        cases.append({'common':common,'recipes':recipes,
            'purpose':'public mechanism development, not a representative test sample'})
    slots=[]
    for case_id,order in [('base__R1',('A','B','C')),('base__R3',('C','B','A'))]:
        for variant in order:
            slots.append({'ordinal':len(slots)+1,'slot_id':case_id+'__'+variant,
                'case_id':case_id,'variant':variant,'method_seconds':300,'post_seconds_max':60,
                'run_once':True,'state':'PENDING_USER_CONFIRMATION'})
    return {'protocol':'K172-two-stage-and-closed-anchor-ablation-proposal-v1',
        'authorized':False,'preparation_only':True,'scientific_execution_enabled':False,
        'research_calls_consumed':0,'research_seconds_reserved':0,'native_requests_consumed':0,
        'real_launcher_implemented':False,'post_calls_consumed':0,'claim':None,
        'source_subject':'2a2ab35ab31e33b51f0b84335ae85d7e5356e816',
        'clock_start_policy':{
            'outside_root':'fresh child interpreter and identical common MethodBudget support imports only; separately timed',
            'inside_root':'selected arm-entry imports, settings/adapter/context, input loading/expansion and all physical/search work',
            'no_arm_specific_free_import':True,'no_precomputed_case_or_candidate':True},
        'cases':cases,'slots':slots,
        'budget_proposal':{'recommended_full_development':{
            'research_calls_max':6,'method_seconds_per_call':300,'method_seconds_total_max':1800,
            'unique_final_safe_post_calls_max':6,'post_seconds_per_call_max':60,
            'post_seconds_total_max':360,'method_plus_post_seconds_max':2160,
            'method_return_watchdog_s':420,'slot_watchdog_s':480,'slot_wall_sum_max_s':2880,
            'overall_wall_proposal_s':3600},
            'reduced_B_C_only':{'research_calls_max':4,'method_seconds_total_max':1200,
                'post_calls_max':4,'post_seconds_total_max':240,'method_plus_post_seconds_max':1440,
                'slot_wall_sum_max_s':1920,'overall_wall_proposal_s':2400},
            'watchdog_is_not_evidence_extension':True,'all_budget_fields_pending':True},
        'solver_options':{'AbsoluteGapTolerance':0,'RelativeGapTolerance':0,
            'ConstraintTolerance':'1e-9','IntegerTolerance':'1e-6',
            'IntegerPreprocess':'none','LPPreprocess':'none','CutMaxIterations':10,
            'Display':'off','OutputFcn':'same original callback',
            'MaxTime':'min(root remaining, scene-slice remaining, worker guard) after export/option preparation',
            'other_options':'R2023b effective defaults; archive all values; no tuning'},
        'source_sha256':source_files,'archive_readonly_sha256':input_files,
        'K170_use':'quality evidence only; no candidate/combination filter',
        'K168':'separate pending 1x300 native diagnostic; zero consumption here',
        'deadline_batch':'16 consumed / 24 unstarted, not resumed',
        'scope_limits':['A has two 150s soft scene caps versus four 60s in B/C; equal root limits, not equal actual solver time.',
            'If a scene returns early, do not sleep, restart or add passes to fill time.',
            'B/C close choices use their own final complete phase-1 SAFE generation; different anchors limit causal attribution.',
            'Common initialization means independent same-rule fresh generation; hashes/labels must be audited before comparison.',
            'Existing entry recipes are checked; a new once-only supervised launcher/source freeze requires separate approval.']}


def main(output):
    if output.exists():
        raise FileExistsError('Preparation records are append-only')
    output.mkdir(parents=True)
    proposal=build_proposal()
    proposal['preparation_source_sha256']=sha(Path(__file__))
    (output/'proposal.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'prepared':True,'authorized':False,'slots':len(proposal['slots']),
        'research_calls_consumed':0,'output':str(output)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
