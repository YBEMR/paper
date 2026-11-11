"""Exact physical energy bounds for the original and shared-condition domains.

No model, solver, schedule or trajectory is constructed. These algebraic
bounds apply only to complete arrangements accepted by the common evaluator:
in particular every local temperature must stay within the declared power
model range. A bound is neither a feasible witness nor an infeasibility proof.
"""
from fractions import Fraction as F

from control_policy import resolve_idle_policy
from scene_adapter import canonical_hash, shared_deployment_ids, validate_shared_deployment
from schedules import _check_platform


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError('Bound scalars must be exact strings/integers/rationals')
    return F(value)


def _check(budget):
    if budget is not None:
        budget.check()


def _thermal_declaration(instance, nodes):
    """Check the structural physical premises, without integrating dynamics."""
    platform = instance['platform']; n = len(nodes)
    capacities = list(map(_q, platform['heat_capacity_J_per_K']))
    conductance = [list(map(_q, row)) for row in platform['conductance_W_per_K']]
    if (len(capacities) != n or any(c <= 0 for c in capacities)
            or len(conductance) != n or any(len(row) != n for row in conductance)):
        raise ValueError('Invalid thermal dimensions or capacities')
    for i,row in enumerate(conductance):
        if row[i] <= 0 or sum(row) <= 0:
            raise ValueError('Non-passive grounded conductance')
        if any(row[j] != conductance[j][i] or (j != i and row[j] > 0) for j in range(n)):
            raise ValueError('Non-passive conductance coupling')
    valid = list(map(_q, platform['power_model_temperature_range_degC']))
    if len(valid) != 2 or valid[0] >= valid[1]:
        raise ValueError('Invalid power-model temperature range')
    _q(platform['ambient_temperature_degC'])
    reference = _q(platform['reference_temperature_degC'])
    return valid, reference


def _mode_energies(instance, stages, units, domains, budget):
    costs = {}
    for shared in sorted(stages):
        _check(budget)
        modes = instance['stage_modes'][shared]
        if not isinstance(modes, list) or not modes:
            raise ValueError('Used Stage must have legal modes')
        seen, values = set(), []
        for mode in modes:
            _check(budget)
            unit_id, opp_id = mode['unit_id'], mode['opp_id']
            if unit_id not in units or (unit_id,opp_id) in seen:
                raise ValueError('Unknown unit or duplicate Stage/unit/OPP mode')
            seen.add((unit_id,opp_id))
            unit = units[unit_id]; domain_id = unit['domain_id']
            if (mode['shared_stage_id'] != shared or mode['domain_id'] != domain_id
                    or mode['power_group_id'] != domain_id
                    or mode['thermal_node_id'] != unit['thermal_node_id']
                    or opp_id not in domains[domain_id]['opps']):
                raise ValueError('Mode does not use its declared local power/thermal unit')
            opp = domains[domain_id]['opps'][opp_id]
            if (_q(mode['frequency_GHz']) != _q(opp['frequency_GHz'])
                    or _q(mode['voltage_V']) != _q(opp['voltage_V'])):
                raise ValueError('Mode working point differs from its domain')
            power, duration = _q(mode['activity_power_W']), _q(mode['duration_ms'])
            if power < 0 or duration <= 0:
                raise ValueError('Bound requires nonnegative activity and positive duration')
            # activity_energy_J is deliberately not read: q and d are the
            # primary quantities used by schedule and continuous evaluation.
            values.append((unit_id,power*duration/1000))
        costs[shared] = values
    return costs


def independent_lower_bound(instance, shared_deployment=None, budget=None):
    """Return L0, or L_a when an exact H mapping is explicitly supplied.

    The input must be the original unprojected instance. None selects its
    full legal domain. A dict (including {} when H
    is empty) selects one shared condition; its bound must not be presented as
    a bound on all other conditions. Use the same caller-owned method Budget.
    No internal solver bound or exported MILP row is consulted or generated.
    """
    try:
        _check(budget)
        policy = resolve_idle_policy(instance)
        nodes,units,domains = _check_platform(instance['platform'])
        valid,reference = _thermal_declaration(instance,nodes)
        window = _q(instance['window_ms'])
        if window <= 0:
            raise ValueError('Positive complete window required')
        shared_ids = shared_deployment_ids(instance)
        fixed = (None if shared_deployment is None else
                 validate_shared_deployment(instance,shared_deployment))
        floor_by_domain = {}
        for domain_id,domain in domains.items():
            _check(budget)
            # The baseline is charged once per domain; the local slope is
            # charged once for each of its distinct unit/local-node members.
            floor_by_domain[domain_id] = min(
                _q(domain['baseline_W'][opp]) + len(domain['unit_ids']) *
                _q(domain['local_temperature_slope_W_per_K'][opp]) * (valid[0]-reference)
                for opp in domain['opps'])
        external = _q(instance['platform']['external_common_power_W'])
        baseline = (external+sum(floor_by_domain.values(),F(0)))*window/1000
        scenes = instance['scenarios']
        weights = [_q(scene['weight']) for scene in scenes]
        if any(w < 0 for w in weights) or sum(weights) != 1:
            raise ValueError('Expected nonnegative normalized scene weights')
        used = {stage['shared_stage_id'] for scene in scenes for stage in scene['stage_instances']}
        costs = _mode_energies(instance,used,units,domains,budget)
        scene_activity,copy_costs = {},{}
        for scene in scenes:
            _check(budget)
            sid = scene['id']; stages = scene['stage_instances']
            ids = [stage['id'] for stage in stages]
            if not stages or len(set(ids)) != len(ids):
                raise ValueError('Empty scene or duplicate Stage instance')
            entry = scene['entry']
            if entry['unfinished_work'] != []:
                raise ValueError('Unsupported unfinished entry work')
            initial = list(map(_q,entry['temperature_degC']))
            limits = list(map(_q,scene['maximum_temperature_degC']))
            if (len(initial) != len(nodes) or len(limits) != len(nodes)
                    or any(t < valid[0] or t > valid[1] for t in initial)):
                raise ValueError('Invalid entry temperatures or node dimensions')
            per_copy = {}
            for stage in stages:
                _check(budget)
                shared = stage['shared_stage_id']
                values = [cost for unit,cost in costs[shared]
                          if fixed is None or shared not in fixed or unit == fixed[shared]]
                if not values:
                    raise ValueError('No compatible mode; no bound/feasibility certificate produced')
                per_copy[stage['id']] = min(values)
            copy_costs[sid] = per_copy
            scene_activity[sid] = sum(per_copy.values(),F(0))
        activity = sum((weight*scene_activity[scene['id']]
                        for weight,scene in zip(weights,scenes)),F(0))
        out = {'lower_bound_J':str(baseline+activity),
            'baseline_lower_bound_J':str(baseline),
            'activity_lower_bound_J':str(activity),
            'domain_power_floors_W':{key:str(value) for key,value in floor_by_domain.items()},
            'external_common_power_W':str(external),
            'scene_activity_lower_bounds_J':{key:str(value) for key,value in scene_activity.items()},
            'stage_instance_activity_minima_J':{
                sid:{key:str(value) for key,value in per_copy.items()} for sid,per_copy in copy_costs.items()},
            'scope':'original_full_domain' if fixed is None else 'fixed_shared_deployment',
            'is_global_lower_bound':fixed is None,
            'shared_stage_ids':shared_ids,'shared_deployment':fixed,
            'input_sha256':canonical_hash(instance),
            'shared_deployment_sha256':None if fixed is None else canonical_hash(fixed),
            'control_policy':policy,'formed_at_s':None,
            'source':'independent exact domain-power floor plus Stage-copy q*d minima',
            'assumptions':[
                'all accepted local temperatures remain in the declared power-model range',
                'domain baseline counted once; nonnegative per-local-node temperature slopes',
                'every declared Stage copy executes once with its mode q and positive duration',
                'zero declared transfer/switch/handoff costs; no omitted negative energy terms'],
            'solver_reported':False,'used_as_new_MILP_row':False,
            'independently_proven_optimal':False,'independently_proven_infeasible':False}
        # Identity construction is part of the same caller-owned budget.
        # Only a completely formed algebraic receipt can cross this cutoff.
        _check(budget)
        if budget is not None:
            formed = budget.elapsed
            if formed >= budget.seconds:
                budget.check()
            out['formed_at_s'] = formed
        return out
    except (KeyError,TypeError,ZeroDivisionError) as error:
        raise ValueError('Malformed input for independent partial energy bound') from error


def get_deployment_bounds(instance, shared_deployment, budget=None):
    """Convenience wrapper; neither invocation receives a fresh budget.

    Call separately when an already committed L0 must be retained even if
    computing the conditional receipt subsequently exhausts the budget.
    """
    return {'L0':independent_lower_bound(instance,None,budget),
            'L_a':independent_lower_bound(instance,shared_deployment,budget)}
