"""Shared-deployment SA adaptation, using the common complete evaluator.

Huang/Xu DATE 2010, section 3.2, supplies the simulated-annealing search
organisation.  Its mapping-only representation, reliability cost and voltage
stretching are not reused.  This adaptation searches shared mappings, per-scene
OPPs, ready-list priorities and explicit grid waits.  The common list decoder
restricts its searched schedules; this is not exhaustive finite-domain search.

All annealing constants below are predeclared, dimensionless algorithm choices.
They are neither measured hardware parameters nor chip temperatures.  Search
and every candidate evaluation use the caller's single method deadline.
"""
from collections import Counter
from copy import deepcopy
from control_policy import require_legacy_control
from fractions import Fraction as F
import math
import random

from thermal import Exhausted


PROTOCOL = 'shared-deployment-safe-sa-v1'
INITIAL_TEMPERATURE = 0.05
MINIMUM_TEMPERATURE = 0.0001
COOLING_FACTOR = 0.95
SAFE_TRIALS_PER_LEVEL = 20
INITIAL_RANDOM_BATCH = 32
INITIAL_RANDOM_MAX_DELAY_STEPS = 4
INITIAL_RANDOM_ZERO_WAIT_PROBABILITY = 0.5
MOVE_KINDS = ('mapping', 'opp', 'priority', 'delay')


def algorithm_parameters():
    """Return the immutable, pre-run interpretation of the algorithm choices."""
    return {
        'initial_temperature_dimensionless': INITIAL_TEMPERATURE,
        'minimum_temperature_dimensionless': MINIMUM_TEMPERATURE,
        'cooling_factor': COOLING_FACTOR,
        'safe_trials_per_temperature_level': SAFE_TRIALS_PER_LEVEL,
        'initial_random_batch': INITIAL_RANDOM_BATCH,
        'initial_random_max_delay_steps': INITIAL_RANDOM_MAX_DELAY_STEPS,
        'initial_random_zero_wait_probability': INITIAL_RANDOM_ZERO_WAIT_PROBABILITY,
        'move_kinds': list(MOVE_KINDS),
        'acceptance': 'exp(-relative_complete_energy_increase / dimensionless_temperature)',
        'score': 'midpoint of complete SAFE weighted-energy interval',
        'best_output': 'smallest independently accepted SAFE energy upper endpoint',
        'unsafe_policy': 'reject; no penalty or prefix energy enters annealing',
        'initialisation': 'HEFT construction; uniform-domain H/M/L constructions; random restarts',
        'uninitialised_after_batch': 'continue random restarts until SAFE or method deadline',
        'scope': 'heuristic decoded subset; no optimality or infeasibility certificate',
        'parameter_source': 'algorithmic self-set values, frozen before comparison; no empirical tuning',
    }


def _indexes(instance):
    copies, units = {}, {}
    for scene in instance['scenarios']:
        for stage in scene['stage_instances']:
            shared = stage['shared_stage_id']
            copies.setdefault(shared, []).append((scene['id'], stage['id']))
    for shared in copies:
        units[shared] = list(dict.fromkeys(m['unit_id'] for m in instance['stage_modes'][shared]))
        if not units[shared]:
            raise ValueError('SA cannot initialise a Stage without a legal mode')
    return copies, units


def _opp_ids(instance, shared, unit):
    return list(dict.fromkeys(m['opp_id'] for m in instance['stage_modes'][shared]
                              if m['unit_id'] == unit))


def _random_plan(instance, rng, indexes=None):
    """Random genes are individually legal, not promised schedulable or safe."""
    copies, units = indexes if indexes is not None else _indexes(instance)
    plan = {'mapping': {}, 'opps': {}, 'priorities': {}, 'delays': {}}
    for shared in sorted(copies):
        plan['mapping'][shared] = rng.choice(units[shared])
    max_wait = min(INITIAL_RANDOM_MAX_DELAY_STEPS,
                   int(F(instance['window_ms']) // F(instance['start_grid_ms'])))
    zero_wait = rng.random() < INITIAL_RANDOM_ZERO_WAIT_PROBABILITY
    for scene in instance['scenarios']:
        sid = scene['id']
        ids = [st['id'] for st in scene['stage_instances']]
        plan['priorities'][sid] = rng.sample(ids, len(ids))
        plan['opps'][sid], plan['delays'][sid] = {}, {}
        for st in scene['stage_instances']:
            key, iid = st['shared_stage_id'], st['id']
            plan['opps'][sid][iid] = rng.choice(_opp_ids(instance, key, plan['mapping'][key]))
            plan['delays'][sid][iid] = 0 if zero_wait else rng.randint(0, max_wait)
    return plan


def _move_catalog(instance, plan, indexes=None):
    """Nonempty move types have equal probability, then select their operands."""
    copies, units = indexes if indexes is not None else _indexes(instance)
    moves = {kind: [] for kind in MOVE_KINDS}
    for shared in sorted(copies):
        alternatives = [u for u in units[shared] if u != plan['mapping'][shared]]
        if alternatives:
            moves['mapping'].append((shared, alternatives))
        for sid, iid in copies[shared]:
            alternatives = [o for o in _opp_ids(instance, shared, plan['mapping'][shared])
                            if o != plan['opps'][sid][iid]]
            if alternatives:
                moves['opp'].append((sid, iid, alternatives))
    max_wait = int(F(instance['window_ms']) // F(instance['start_grid_ms']))
    for scene in instance['scenarios']:
        sid = scene['id']
        if len(plan['priorities'][sid]) > 1:
            moves['priority'].append(sid)
        for st in scene['stage_instances']:
            iid, current = st['id'], plan['delays'][sid][st['id']]
            alternatives = [k for k in (current-1, current+1) if 0 <= k <= max_wait]
            if alternatives:
                moves['delay'].append((sid, iid, alternatives))
    return {kind: values for kind, values in moves.items() if values}


def _mutate(instance, plan, rng, indexes=None):
    indexes = indexes if indexes is not None else _indexes(instance)
    moves = _move_catalog(instance, plan, indexes)
    if not moves:
        return None, None
    kind = rng.choice(list(moves))
    new = deepcopy(plan)
    operand = rng.choice(moves[kind])
    if kind == 'mapping':
        shared, choices = operand
        unit = rng.choice(choices)
        new['mapping'][shared] = unit
        for sid, iid in indexes[0][shared]:
            # A shared mapping move changes every replica.  OPPs are chosen
            # together so no stale device-specific OPP survives the move.
            new['opps'][sid][iid] = rng.choice(_opp_ids(instance, shared, unit))
    elif kind == 'opp':
        sid, iid, choices = operand
        new['opps'][sid][iid] = rng.choice(choices)
    elif kind == 'priority':
        sid = operand
        left, right = rng.sample(range(len(new['priorities'][sid])), 2)
        items = new['priorities'][sid]
        items[left], items[right] = items[right], items[left]
    else:
        sid, iid, choices = operand
        new['delays'][sid][iid] = rng.choice(choices)
    return new, kind


def _safe_energy(evaluation):
    """No unsafe, incomplete, unknown or malformed objective can guide SA."""
    if (evaluation.get('state') != 'SAFE' or not evaluation.get('rankable_energy')
            or not evaluation.get('weighted_energy_J')):
        return None
    bounds = evaluation['weighted_energy_J']
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
        return None
    try:
        lo, hi = map(F, bounds)
        upper = F(evaluation['safe_upper_bound_J'])
    except (TypeError, ValueError, ZeroDivisionError, KeyError):
        return None
    if lo < 0 or hi < lo or upper != hi:
        return None
    return lo, hi


def _temperature(safe_trials):
    level = safe_trials // SAFE_TRIALS_PER_LEVEL
    # Avoid pointless underflow for cheap fixtures or long method budgets.
    return max(MINIMUM_TEMPERATURE,
               INITIAL_TEMPERATURE * COOLING_FACTOR**min(level, 100000))


def _accept(old, new, safe_trials, rng):
    old_mid, new_mid = sum(old)/2, sum(new)/2
    if new_mid <= old_mid:
        return True
    relative = float((new_mid-old_mid)/max(abs(old_mid), F(1, 10**12)))
    exponent = relative/_temperature(safe_trials)
    return exponent < 745 and rng.random() < math.exp(-exponent)


def run_sa(instance, config, budget, assess, seed):
    """Run one independent SA invocation.  The caller owns SAFE/cache records.

    ``assess(candidate, source)`` performs the common full evaluation under the
    very same budget, commits timely safe bounds, and returns its receipt.
    Imported HEFT is only a constructor: its energy-improvement loop is not
    called and no answer from another method invocation is read.
    """
    require_legacy_control(instance, 'SA search')
    require_legacy_control(config, 'SA configuration')
    from heft_method import build_heft_candidate
    from heuristic_common import decode_plan, plan_from_candidate

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('SA seed must be an integer')
    rng = random.Random(seed)
    counts, by_move = Counter(), Counter()
    meta = {'method': 'SA', 'protocol': PROTOCOL, 'seed': seed,
            'parameters': algorithm_parameters(), 'state': 'UNRESOLVED',
            'reason': 'NO_SAFE_CANDIDATE', 'counters': counts,
            'moves_proposed': by_move, 'best_evaluated_upper_J': None,
            'initialisation_source': None,
            'coverage': 'HEURISTIC_DECODED_SUBSET; unvisited schedules remain unresolved'}
    current, current_energy = None, None
    best_upper = None

    def evaluate(candidate, source):
        nonlocal best_upper
        budget.check()
        counts['complete_candidate_requests'] += 1
        result = assess(candidate, source)
        counts['receipt_'+result.get('state', 'UNRESOLVED')] += 1
        energy = _safe_energy(result)
        if energy is not None:
            counts['safe_receipts'] += 1
            if best_upper is None or energy[1] < best_upper:
                best_upper = energy[1]
                meta['best_evaluated_upper_J'] = str(best_upper)
                counts['upper_bound_improvements'] += 1
            meta['state'], meta['reason'] = 'SAFE', 'SAFE_HEURISTIC_WITNESS'
        return energy

    try:
        budget.check()
        indexes = _indexes(instance)
        # Finite, deterministic constructions precede random initialisation.
        for label, rank in (('heft', None), ('template_H', 0),
                            ('template_M', 1), ('template_L', 2)):
            budget.check()
            counts['initial_constructions'] += 1
            built = build_heft_candidate(instance, budget=budget, opp_rank=rank)
            candidate = built.get('candidate')
            if candidate is None:
                counts['construction_failure'] += 1
                continue
            energy = evaluate(candidate, 'sa_initial_'+label)
            if energy is not None:
                current = plan_from_candidate(instance, candidate, budget=budget)
                current_energy = energy
                meta['initialisation_source'] = label
                break
        while True:
            budget.check()
            if current is None:
                counts['random_initialisation_attempts'] += 1
                ordinal = counts['random_initialisation_attempts']
                if ordinal > INITIAL_RANDOM_BATCH:
                    counts['post_batch_random_restarts'] += 1
                proposed = _random_plan(instance, rng, indexes)
                source, move = 'sa_random_initialisation', None
            else:
                proposed, move = _mutate(instance, current, rng, indexes)
                if proposed is None:
                    meta['reason'] = 'SAFE_NO_MUTABLE_GENES'
                    break
                by_move[move] += 1
                source = 'sa_neighbour_'+move
            counts['decode_attempts'] += 1
            candidate = decode_plan(instance, proposed, budget=budget)
            if candidate is None:
                counts['decode_failure'] += 1
                continue
            energy = evaluate(candidate, source)
            if energy is None:
                counts['rejected_without_safe_objective'] += 1
                continue
            if current is None:
                current, current_energy = proposed, energy
                meta['initialisation_source'] = 'random_restart'
                continue
            trial = counts['safe_neighbour_trials']
            counts['safe_neighbour_trials'] += 1
            if _accept(current_energy, energy, trial, rng):
                if energy[1] < current_energy[0]:
                    counts['certified_strict_energy_decreases'] += 1
                elif sum(energy) > sum(current_energy):
                    counts['accepted_uphill_midpoint'] += 1
                else:
                    counts['accepted_nonuphill_midpoint'] += 1
                counts['accepted_neighbours'] += 1
                current, current_energy = proposed, energy
            else:
                counts['rejected_uphill_midpoint'] += 1
    except Exhausted:
        meta['stop_reason'] = 'METHOD_BUDGET_EXHAUSTED'
    meta.setdefault('stop_reason', 'NO_MUTABLE_GENES')
    meta['counters'], meta['moves_proposed'] = dict(counts), dict(by_move)
    meta['final_temperature_dimensionless'] = _temperature(counts['safe_neighbour_trials'])
    meta['current_safe_energy_J'] = (list(map(str, current_energy))
                                       if current_energy is not None else None)
    return meta
