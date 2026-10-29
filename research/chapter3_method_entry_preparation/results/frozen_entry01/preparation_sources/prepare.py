"""Freeze a candidate-free input and a pending small method-entry protocol.

No production algorithm import, model construction, solver or thermal call.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT/'research/chapter3_formal_input_adapter/results/frozen_semantic02/payload.json'
SOURCE_SHA = '6dc0b254d412f6a103d22c8b7bf3c8375d1d7a026a0224213e03e4447c11bc74'
METHODS = ('whole_milp', 'heft', 'sa101')
FLAGS = {'fix_late_options': True, 'aggregate_opp_locks': True,
         'relax_auxiliary_integrality': True, 'strengthen_energy_lower_bounds': True,
         'prefilter_deadlines': True, 'cumulative_precedence': False}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def validate_common_input(value):
    require(set(value) == {'schema', 'config', 'instance', 'provenance'}, 'COMMON_INPUT_FIELDS')
    require(value['schema'] == 'ch3-method-entry-common-input-v1', 'COMMON_INPUT_SCHEMA')
    i = value['instance']
    require(i['window_ms'] == '230' and i['start_grid_ms'] == '5'
            and i['response_variant'] == 'H', 'SCIENTIFIC_TIME_OR_RESPONSE_DRIFT')
    require([s['id'] for s in i['scenarios']] == ['C1', 'C2']
            and all(len(s['stage_instances']) == 6 and len(s['requests']) == 2
                    and F(s['weight']) == F(1, 2) for s in i['scenarios']), 'SCENARIO_OR_REQUEST_DRIFT')
    require(all(s['entry']['temperature_degC'] == ['50']*4
                and s['maximum_temperature_degC'] == ['80']*4 for s in i['scenarios']), 'THERMAL_CONDITION_DRIFT')
    require(i['platform'] == value['config']['platform']
            and i['execution_rules'] == value['config']['execution_rules']
            and i['execution_rules']['idle_policy'] == 'auto_low_immediate_v1', 'PLATFORM_CONTROL_DRIFT')
    forbidden = {'candidate', 'safe_candidate', 'reference', 'timetables', 'mapping_record',
                 'safe_upper_bound_J', 'evaluation', 'fixed_deployment', 'fixed_shared_deployment',
                 'formal_initial_solution', 'neighborhood_condition', 'explicit_start_sets'}
    def walk(node):
        if isinstance(node, dict):
            require(not forbidden.intersection(node), 'REFERENCE_OR_SEARCH_RESTRICTION_LEAK')
            for v in node.values(): walk(v)
        elif isinstance(node, list):
            for v in node: walk(v)
    walk(value)
    require(canonical(i) == value['provenance']['instance_sha256']
            and canonical(value['config']) == value['provenance']['config_sha256'], 'COMMON_INPUT_CONTENT_DRIFT')
    return True


def validate_plan(plan):
    require(plan['schema'] == 'ch3-small-method-entry-proposal-v1'
            and plan['execution_authorized'] is False
            and plan['real_execution_entry_present'] is False, 'NOT_AN_EXECUTION_AUTHORIZATION')
    require(plan['methods_order'] == list(METHODS) and len(plan['jobs']) == 3, 'JOB_SCOPE_DRIFT')
    for job, mid in zip(plan['jobs'], METHODS):
        require(job['id'] == mid and job['method_seconds'] == 300
                and job['process_wall_seconds'] == 480 and job['independent_post_seconds'] == 60,
                'JOB_BUDGET_DRIFT')
        require(job['input_sha256'] == plan['common_input_sha256'], 'DIFFERENT_METHOD_INPUT')
        require(job['seed'] == (101 if mid == 'sa101' else None), 'SEED_DRIFT')
        if mid == 'whole_milp':
            require(job['builder_flags'] == FLAGS and job['feedback_kind'] == 'conditional'
                    and job['cut_max_iterations'] == 10 and job['maximum_feedback_rounds'] == 50,
                    'WHOLE_FORMULATION_DRIFT')
        else:
            require(job['allow_auto_low'] is True, 'HEURISTIC_CONTROL_DRIFT')
    require(plan['method_calls_max'] == 3 and plan['method_seconds_max'] == 900
            and plan['post_calls_max'] == 3 and plan['post_seconds_max'] == 180
            and plan['batch_wall_seconds'] == 1800 and plan['retries'] == 0,
            'TOTAL_BUDGET_DRIFT')
    return True


def mock_dispatch(plan, job, callback):
    """Contract-level routing only. callback must be a caller-supplied mock."""
    validate_plan(plan)
    require(job in plan['jobs'], 'UNDECLARED_JOB')
    return callback(deepcopy(job), {'input_sha256': plan['common_input_sha256'],
                                   'initial_solution_imported': False,
                                   'cache_shared_between_methods': False,
                                   'simulation_only': True})


def static_case(instance):
    # Reuse archived scalar counts; never generate options/events/models here.
    path = ROOT/'research/chapter3_formal_input_audit/static_scale01/static_scale_counts.json'
    data = load(path)
    sample = next(s for r in data['all_24_roots_base_ranges']
                  if r['stage_count_per_scenario'] == 6 for s in r['samples']
                  if s['condition'] == 'C01__base_6')
    scenes = sample['per_scene'][:2]
    require([s['scenario_id'] for s in scenes] == ['C1', 'C2'], 'STATIC_SCENE_MISMATCH')
    y = sum(s['deadline_retained_y_count'] for s in scenes)
    k = sum(s['exact_interval_count'] for s in scenes)
    t = sum(s['stage_instances'] for s in scenes)
    u = sum(s['local_unit_mapping_equalities'] for s in scenes)
    edges = sum(s['dependencies'] for s in scenes)
    j = len(instance['stage_modes']); x = sum(len({m['unit_id'] for m in modes}) for modes in instance['stage_modes'].values())
    r0 = 2*j+3*t+2*u+edges+8*len(scenes)
    return {'source': path.relative_to(ROOT).as_posix(), 'source_sha256': sha(path),
            'per_scene': scenes, 'initial_options': sum(s['initial_option_expansion_count'] for s in scenes),
            'Y': y, 'K': k, 'shared_ids': j, 'X': x,
            'variables_bounds': [y+x+8+22*k, y+x+8+48*k],
            'rows_bounds': [r0+y+58*k, r0+y+330*k],
            'scope': 'exact archived catalog counts and structural bounds, not measured construction/memory/time'}


def prepare(out):
    require(not out.exists() and out.is_relative_to((HERE/'results').resolve()), 'NEW_OUTPUT_REQUIRED')
    require(sha(SOURCE) == SOURCE_SHA, 'ADAPTER_PAYLOAD_SOURCE_DRIFT')
    original = load(SOURCE)['adapted']
    value = {'schema': 'ch3-method-entry-common-input-v1',
             'config': deepcopy(original['config']), 'instance': deepcopy(original['instance']),
             'provenance': {'root_id': 'C01', 'scenario_subset': ['C1', 'C2'], 'beta': '13/10',
                'source_payload_sha256': SOURCE_SHA, 'adapter_receipt_sha256': original['receipt']['receipt_hash'],
                'instance_sha256': canonical(original['instance']), 'config_sha256': canonical(original['config']),
                'input_role': 'same scientific data as prior semantic precheck; no prior schedule or energy'}}
    validate_common_input(value)
    out.mkdir(parents=True)
    save(out/'common_input.json', value)
    common_sha = sha(out/'common_input.json')
    jobs = [{'id': mid, 'method_seconds': 300, 'process_wall_seconds': 480,
             'independent_post_seconds': 60, 'input_sha256': common_sha,
             'seed': 101 if mid == 'sa101' else None} for mid in METHODS]
    jobs[0].update(entry='formal_milp.execute_formal_milp', builder_flags=FLAGS,
                   feedback_kind='conditional', cut_max_iterations=10, maximum_feedback_rounds=50,
                   independent_L0='billed inside own loader, as in P0')
    for job in jobs[1:]:
        job.update(entry='heuristic_runner.execute_heuristic', allow_auto_low=True,
                   independent_L0='billed once inside original heuristic lifecycle')
    sources = {}
    for folder in ('chapter3_experiments', 'chapter3_formal_input_adapter'):
        for p in sorted((HERE.parent/folder).iterdir()):
            if p.is_file() and p.suffix in ('.py', '.m', '.json'):
                sources[p.relative_to(ROOT).as_posix()] = sha(p)
    snapshot = out/'preparation_sources'; snapshot.mkdir()
    for p in sorted(HERE.glob('*.py')):
        shutil.copyfile(p, snapshot/p.name)
        sources[p.relative_to(ROOT).as_posix()] = sha(p)
    plan = {'schema': 'ch3-small-method-entry-proposal-v1',
            'state': 'FROZEN_SCIENTIFIC_AND_BUDGET_PROPOSAL_PENDING_APPROVAL',
            'execution_authorized': False, 'real_execution_entry_present': False,
            'common_input_file': 'common_input.json', 'common_input_sha256': common_sha,
            'instance_sha256': canonical(value['instance']), 'config_sha256': canonical(value['config']),
            'methods_order': list(METHODS), 'jobs': jobs,
            'method_calls_max': 3, 'method_seconds_max': 900,
            'post_calls_max': 3, 'post_seconds_max': 180,
            'batch_wall_seconds': 1800, 'retries': 0,
            'source_sha256': sources, 'static_case': static_case(value['instance']),
            'initialization': 'each original method constructs independently in its own root budget; no reference/prior SAFE/cache',
            'timing': {'method_clock': 'original MethodBudget begins before input loader; 300 seconds includes initialization, construction, MATLAB, search, internal checks/feedback',
                       'process_clock': 'supervisor before fresh Python launch through process exit; includes interpreter/imports/cleanup/archive; report separately',
                       'post_clock': 'at most one independent full-window recheck per valid final SAFE; not used for method improvement'},
            'resource_prelaunch': {'available_physical_bytes_min': 2*1024**3,
                                  'available_commit_bytes_min': 4*1024**3,
                                  'free_disk_bytes_min': 2*1024**3,
                                  'existing_matlab_processes_allowed': 0,
                                  'appcontainer_allowed': False},
            'stop_rules': ['no rerun, input replacement or parameter change',
                           'normal deadline or no SAFE may continue to next declared method',
                           'input/source drift, numerical conflict, technical fault or unverified process cleanup stops batch',
                           'post proves illegal/unsafe stops batch; post timeout remains unresolved, never repairs'],
            'before_any_real_call': ['separate explicit user approval of this proposal budget',
                                     'freeze one-shot launcher, per-process monitoring and actual source manifest',
                                     'pass dry-run/identity/resource checks; no automatic fallback to one scene'],
            'formal_50_roots': False, 'linked_C_included': False}
    validate_plan(plan)
    save(out/'plan.json', plan)
    print(json.dumps({'state': plan['state'], 'plan_sha256': sha(out/'plan.json'),
                      'common_input_sha256': common_sha, 'static_case': plan['static_case']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare(Path(args.output).resolve())
