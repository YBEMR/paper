"""Q1 main-only quality case derived from the unchanged physical input.

No historical witness, solver result or energy answer is read. The explicit
start restriction is specific to this quality reference, not the main study.
"""
from copy import deepcopy
from control_policy import require_legacy_control
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from inputs import build_instance, load_config
from start_domain import explicit_start_sets

HERE = Path(__file__).resolve().parent
CONFIG_SHA = '615be096bfbcb3e7c53ba9b0810d888264d48adbc428f1f7d2f94a5c6a29a4fe'
PROBLEM_ID = 'quality_Q1__R1'
SECONDS = 300


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_q1(budget=None):
    if budget is not None:
        budget.check()
    raw = (HERE/'config_v01.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONFIG_SHA:
        raise ValueError('Frozen physical/configuration input changed')
    config = load_config()
    base = build_instance(config, 'base__R1', budget=budget)
    instance = deepcopy(base)
    instance.update(id=PROBLEM_ID, condition_id='quality_Q1',
                    experiment_group='quality_reference_Q1', ablation_input=False)
    used = {'A.main', 'B.main', 'C.main'}
    instance['stage_modes'] = {key: value for key, value in instance['stage_modes'].items()
                               if key in used}
    # Derived from the same reference modes, not from a measured/best schedule.
    fastest = [min(F(m['duration_ms']) for m in instance['stage_modes'][key]
                   if m['opp_id'] == 'H') for key in sorted(used)]
    grid = F(instance['start_grid_ms'])
    later = -((-max(fastest))//grid)*grid
    if later != 45:
        raise ValueError('Q1 declared start derivation changed')
    domains = {}
    for scene in instance['scenarios']:
        scene['stage_instances'] = [s for s in scene['stage_instances']
                                     if s['shared_stage_id'] in used]
        ids = {s['id'] for s in scene['stage_instances']}
        for request in scene['requests']:
            request['stage_instance_ids'] = [key for key in request['stage_instance_ids']
                                               if key in ids]
        scene['requests'] = [r for r in scene['requests'] if r['stage_instance_ids']]
        scene['dependencies'] = [[a, b] for a, b in scene['dependencies']
                                   if a in ids and b in ids]
        domains[scene['id']] = {s['id']: ['0', str(later)] for s in scene['stage_instances']}
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': domains}
    instance['quality_reference'] = {
        'source_problem_id': base['id'], 'source_instance_sha256': canonical_hash(base),
        'source_config_sha256': CONFIG_SHA,
        'scope': 'main-only quality reference; original full three-Stage main study unchanged',
        'deadline_scope': 'inherited original budgets after deleting pre/post; not full-chain validation',
        'start_derivation': '5 ms aligned maximum of fastest H main durations 30/35/45 ms',
        'historical_answers_or_candidates_used': False}
    explicit_start_sets(instance, budget=budget)
    if budget is not None:
        budget.check()
    return config, instance


def independent_lower_bound(instance):
    """Physical bound, exact algebra; not a solver-reported integer bound."""
    require_legacy_control(instance, 'Method energy lower-bound interface')
    p = instance['platform']
    floor = F(p['external_common_power_W'])
    minimum, _ = map(F, p['power_model_temperature_range_degC'])
    reference = F(p['reference_temperature_degC'])
    for domain in p['domains'].values():
        slopes = domain['local_temperature_slope_W_per_K']
        if any(F(v) < 0 for v in slopes.values()):
            raise ValueError('Lower bound requires nonnegative local slopes')
        floor += min(F(domain['baseline_W'][opp]) + len(domain['unit_ids']) *
                     F(slopes[opp]) * (minimum-reference) for opp in domain['opps'])
    weights = [F(scene['weight']) for scene in instance['scenarios']]
    if sum(weights) != 1 or any(w < 0 for w in weights):
        raise ValueError('Expected nonnegative normalized scenario weights')
    activity = sum(F(scene['weight']) * sum(min(F(m['activity_energy_J'])
        for m in instance['stage_modes'][s['shared_stage_id']])
        for s in scene['stage_instances']) for scene in instance['scenarios'])
    if any(F(m['activity_power_W']) < 0 or F(m['duration_ms']) <= 0
           for modes in instance['stage_modes'].values() for m in modes):
        raise ValueError('Lower bound requires nonnegative activity and positive duration')
    baseline = floor*F(instance['window_ms'])/1000
    return {'lower_bound_J': str(baseline+activity),
        'baseline_lower_bound_J': str(baseline), 'activity_lower_bound_J': str(activity),
        'source': 'independent exact domain-baseline floor plus Stage activity minima',
        'assumptions': 'nonnegative local slopes; valid trajectories in declared temperature range',
        'solver_reported': False, 'used_as_new_MILP_row': False}
