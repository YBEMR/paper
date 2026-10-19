"""Finite Q1 joint enumeration, independent of the MILP candidate generator.

Only exact mode costs and the input's explicit starts generate assignments.
Scene evaluations are memoized inside one invocation; every improving global
upper bound is rechecked by the original full-input continuous evaluator.
No history, fixed-deployment receipt or solver answer is read.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import itertools
import json
from pathlib import Path
import time
import uuid

from schedules import validate_schedule
from thermal import Exhausted, I, _accuracy, evaluate_candidate
from timing import MethodBudget

PROTOCOL = 'q1-independent-joint-enumeration-v1'
HERE = Path(__file__).resolve().parent


def _json_default(value):
    if isinstance(value, (F, Decimal)):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False, default=_json_default).encode()).hexdigest()


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=_json_default)+'\n', encoding='utf-8')


def source_identity():
    names = ['q1_reference.py', 'q1_case.py', 'inputs.py', 'schedules.py',
             'thermal.py', 'timing.py', 'start_domain.py',
             '../v1_evaluator/interval.py']
    return {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            for name in names if (HERE/name).is_file()}


def assignment_domain(instance, *, budget=None):
    """Build individual exact options, not complete schedules or a heat library.

    The global cartesian product is deliberately independent of expand_options.
    Original scene/Stage/mode order is preserved; exact starts are ascending.
    """
    from start_domain import explicit_start_sets
    starts = explicit_start_sets(instance, budget=budget)
    if starts is None:
        raise ValueError('Q1 enumeration requires an explicit start domain')
    dimensions, identities = [], []
    window = F(instance['window_ms'])
    counts_by_shared = defaultdict(list)
    unfiltered = []
    for scene in instance['scenarios']:
        requests = {r['id']: r for r in scene['requests']}
        for stage in scene['stage_instances']:
            if budget is not None:
                budget.check()
            sid, iid = scene['id'], stage['id']
            request = requests[stage['request_id']]
            release, deadline = F(request['release_ms']), F(request['deadline_ms'])
            options, raw_count = [], 0
            for mode in instance['stage_modes'][stage['shared_stage_id']]:
                duration = F(mode['duration_ms'])
                if duration <= 0:
                    raise ValueError('nonpositive mode duration')
                for start in sorted(starts[sid][iid]):
                    raw_count += 1
                    start = F(start)
                    if start >= release and start+duration <= min(window, deadline):
                        options.append({'stage_id': iid, 'unit': mode['unit_id'],
                                        'opp': mode['opp_id'], 'start_ms': str(start)})
            dimensions.append(options)
            identities.append((sid, stage['shared_stage_id']))
            counts_by_shared[stage['shared_stage_id']].append(Counter(o['unit'] for o in options))
            unfiltered.append(raw_count)
    def shared_count(counts):
        units = set().union(*(set(c) for c in counts))
        return sum(_product(c.get(unit, 0) for c in counts) for unit in units)
    return dimensions, identities, {
        'individual_option_counts': [len(d) for d in dimensions],
        'individual_option_counts_before_time_filter': unfiltered,
        'raw_cartesian_assignments_before_time_filter': _product(unfiltered),
        'cartesian_assignments_after_time_filter_before_shared_filter': _product(map(len, dimensions)),
        'joint_assignments_total': _product(shared_count(c) for c in counts_by_shared.values())}


def _product(values):
    result = 1
    for value in values:
        result *= value
    return result


def _candidate(rows, identities, scene_ids):
    shared, result = {}, {'scenes': {sid: [] for sid in scene_ids}}
    for row, (sid, key) in zip(rows, identities):
        if key in shared and shared[key] != row['unit']:
            return None
        shared[key] = row['unit']
        result['scenes'][sid].append(deepcopy(row))
    return result


def _scene_view(instance, scene):
    out = deepcopy(instance)
    out['scenarios'] = [deepcopy(scene)]
    out['scenarios'][0]['weight'] = '1'
    used = {s['shared_stage_id'] for s in scene['stage_instances']}
    out['stage_modes'] = {k: deepcopy(v) for k, v in instance['stage_modes'].items() if k in used}
    domain = out.get('start_domain')
    if domain is not None:
        domain['by_scene_stage_ms'] = {scene['id']: deepcopy(domain['by_scene_stage_ms'][scene['id']])}
    return out


def _committed_violations(result, seconds):
    # Evaluator commits genuine witnesses before returning; reject absent or
    # post-deadline timestamps rather than guessing from its exit state.
    return [deepcopy(v) for v in result.get('violations', [])
            if isinstance(v.get('formed_at_elapsed_s'), (float, int))
            and v['formed_at_elapsed_s'] < seconds]


def _safe_energy(result, budget, field='weighted_energy_J'):
    formed = result.get('completed_at_elapsed_s')
    if (result.get('state') != 'SAFE' or not result.get('rankable_energy')
        or result.get(field) is None or not isinstance(formed, (float, int))
        or formed >= budget.seconds or budget.elapsed >= budget.seconds):
        return None
    energy = I(*result[field])
    if energy.lo < 0:
        raise ValueError('negative SAFE energy')
    return energy


def execute_reference(input_loader, workdir, *, seconds=300, clock=time.monotonic,
                      evaluator=evaluate_candidate, lower_bound=None):
    """One fresh bounded call. Dependency injection is for correctness tests.

    input_loader(budget) returns (config, instance); lower_bound(instance)
    returns a dictionary with exact ``lower_bound_J``. Existing workdirs are
    refused. Serialization after the stop only archives committed evidence.
    """
    budget = MethodBudget(float(seconds), clock=clock)
    workdir = Path(workdir)
    if workdir.exists():
        raise FileExistsError(str(workdir))
    workdir.mkdir(parents=True)
    out = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'safe_candidate': None, 'safe_upper_bound_J': None, 'evaluation': None,
        'first_safe_at_s': None, 'first_legal_candidate_at_s': None,
        'certified_lower_bound_J': None, 'independent_lower_bound': None,
        'coverage_complete': False, 'numerical_unresolved': False,
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'finite_domain_optimal_value_enclosure_J': None,
        'remaining_domain': 'UNSTARTED', 'current_candidate': None,
        'solver_reported': None, 'candidate_and_cache_shared_between_calls': False,
        'formal_comparison': False, 'violations': [], 'unresolved_candidates': [],
        'events': [], 'counters': dict(joint_started=0, joint_committed=0,
            invalid_schedules=0, thermal_excluded=0, locally_safe=0,
            numerical_unresolved=0, local_evaluations=0, local_cache_hits=0,
            full_evaluations=0, upper_bound_updates=0)}
    config = instance = None
    cache, safe_values = {}, []
    best = None
    cursor = 0
    active = 'input'
    try:
        with budget.phase('input_read_and_expansion'):
            config, instance = input_loader(budget)
        budget.check()
        accuracy = _accuracy(config.get('accuracy_targets'))
        source = source_identity()
        identity = {'protocol': PROTOCOL, 'input': canonical_hash(instance),
            'accuracy': canonical_hash(accuracy), 'source': source,
            'budget': {'token': uuid.uuid4().hex, 'start': repr(budget.start),
                'seconds': repr(budget.seconds)}}
        out.update(problem_id=instance['id'], identity=identity)
        active = 'independent_lower_bound'
        if lower_bound is None:
            from q1_case import independent_lower_bound
            lower_bound = independent_lower_bound
        bound = lower_bound(instance)
        value = F(bound['lower_bound_J'])
        budget.check()
        out.update(independent_lower_bound=deepcopy(bound), certified_lower_bound_J=str(value))
        with budget.phase('assignment_domain'):
            dimensions, identities, counts = assignment_domain(instance, budget=budget)
        out['domain_counts'] = counts
        scenes = instance['scenarios']
        views = {scene['id']: _scene_view(instance, scene) for scene in scenes}
        scene_ids = [scene['id'] for scene in scenes]
        weights = [F(scene['weight']) for scene in scenes]
        if any(w < 0 for w in weights) or sum(weights) != 1:
            raise ValueError('invalid original weights')
        active = 'joint_enumeration'
        for cursor, rows in enumerate(itertools.product(*dimensions), 1):
            budget.check()
            candidate = _candidate(rows, identities, scene_ids)
            if candidate is None:
                continue
            counters = out['counters']
            counters['joint_started'] += 1
            index = counters['joint_started']
            out.update(current_candidate=deepcopy(candidate),
                current_joint_index=index, current_raw_cartesian_index=cursor,
                remaining_domain='CURRENT_AND_UNVISITED_CARTESIAN_ASSIGNMENTS')
            checked = validate_schedule(instance, candidate)
            budget.mark('after_q1_reference_legality')
            if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
                if checked.get('reason') == 'MALFORMED_INPUT_OR_CANDIDATE':
                    raise ValueError('input/validator mismatch: '+str(checked))
                counters['invalid_schedules'] += 1
                counters['joint_committed'] += 1
                out['current_candidate'] = None
                continue
            if out['first_legal_candidate_at_s'] is None:
                out['first_legal_candidate_at_s'] = budget.elapsed
            local, violations = [], []
            for scene in scenes:
                sid = scene['id']
                local_candidate = {'scenes': {sid: candidate['scenes'][sid]}}
                key = canonical_hash({'invocation': identity, 'scene': scene,
                    'view': views[sid], 'candidate': local_candidate})
                if key in cache:
                    counters['local_cache_hits'] += 1
                    receipt = cache[key]
                else:
                    budget.check()
                    counters['local_evaluations'] += 1
                    with budget.phase('local_continuous_evaluation'):
                        evaluated = evaluator(views[sid], local_candidate, accuracy, budget)
                    witnessed = _committed_violations(evaluated, budget.seconds)
                    # Copy a pre-deadline violation before checking outer time.
                    out['violations'].extend(witnessed)
                    energy = _safe_energy(evaluated, budget)
                    receipt = {'identity_sha256': key, 'scene_id': sid,
                        'candidate': local_candidate, 'evaluation': deepcopy(evaluated),
                        'state': 'THERMAL_VIOLATION' if witnessed else 'SAFE' if energy is not None else 'UNRESOLVED',
                        'energy_J': energy.data() if energy is not None else None,
                        'violations': witnessed}
                    cache[key] = receipt
                    out['events'].append({'kind': 'local_evaluation', 'at_s': budget.elapsed,
                        'scene': sid, 'state': receipt['state'], 'identity_sha256': key})
                local.append(receipt)
                violations.extend(receipt['violations'])
                if violations:
                    break
                budget.check()
            if violations:
                counters['thermal_excluded'] += 1
                # The current assignment has a committed counterexample even
                # if the evaluator returned after expiry; no global U added.
                counters['joint_committed'] += 1
                out['current_candidate'] = None
                budget.check()
                continue
            budget.check()
            if len(local) != len(scenes) or any(r['state'] != 'SAFE' for r in local):
                counters['numerical_unresolved'] += 1
                out['unresolved_candidates'].append({'joint_index': index,
                    'candidate': deepcopy(candidate), 'reason': 'LOCAL_EVALUATION_UNRESOLVED'})
            else:
                total = sum((I(*r['energy_J'])*I.rational(w)
                             for r, w in zip(local, weights)), I(0))
                safe_values.append(total)
                counters['locally_safe'] += 1
                if best is None or total.hi < best.hi:
                    counters['full_evaluations'] += 1
                    with budget.phase('independent_full_candidate_recheck'):
                        full = evaluator(instance, candidate, accuracy, budget)
                    witnessed = _committed_violations(full, budget.seconds)
                    out['violations'].extend(witnessed)
                    energy = _safe_energy(full, budget)
                    if witnessed:
                        raise ValueError('local SAFE/full violation inconsistency')
                    if energy is None:
                        counters['numerical_unresolved'] += 1
                        out['unresolved_candidates'].append({'joint_index': index,
                            'candidate': deepcopy(candidate), 'reason': 'FULL_RECHECK_UNRESOLVED'})
                    elif max(total.lo, energy.lo) > min(total.hi, energy.hi):
                        raise ValueError('local/global energy enclosures disagree')
                    elif best is None or energy.hi < best.hi:
                        budget.mark('before_q1_reference_upper_bound_commit')
                        at = budget.elapsed
                        if at >= budget.seconds:
                            raise Exhausted('wall_time_limit')
                        best = energy
                        if out['first_safe_at_s'] is None:
                            out['first_safe_at_s'] = at
                        out.update(state='SAFE', safe_candidate=deepcopy(candidate),
                            safe_upper_bound_J=str(energy.hi), evaluation=deepcopy(full))
                        counters['upper_bound_updates'] += 1
                        out['events'].append({'kind': 'safe_upper_bound', 'at_s': at,
                            'energy_J': energy.data(), 'candidate': deepcopy(candidate),
                            'joint_index': index})
            budget.check()
            counters['joint_committed'] += 1
            out['current_candidate'] = None
        budget.check()
        if out['counters']['joint_committed'] != counts['joint_assignments_total']:
            raise ValueError('joint enumeration count did not match exact domain count')
        completion = dict(coverage_complete=True, remaining_domain='NONE_UNVISITED',
                          current_candidate=None,
                          numerical_unresolved=bool(out['unresolved_candidates']))
        if not completion['numerical_unresolved']:
            if safe_values and best is not None:
                lower = min(v.lo for v in safe_values)
                lower = max(I.rational(value).lo, lower)
                if lower > best.hi:
                    raise ValueError('certified lower exceeds safe upper')
                completion['certified_lower_bound_J'] = str(lower)
                completion['finite_domain_optimal_value_enclosure_J'] = [str(lower), str(best.hi)]
                completion['independently_proven_optimal'] = lower == best.hi
                completion['reason'] = 'COMPLETE_COVERAGE_OPTIMAL_VALUE_ENCLOSURE'
            elif not safe_values:
                completion.update(state='INFEASIBLE', reason='ALL_JOINT_ASSIGNMENTS_RELIABLY_EXCLUDED',
                                  independently_proven_infeasible=True)
        else:
            completion['reason'] = 'COMPLETE_VISIT_WITH_NUMERICAL_UNRESOLVED'
        # Even the coverage/proof commit must finish inside the same deadline;
        # visiting the last leaf in time does not authorize a later upgrade.
        budget.mark('before_q1_reference_coverage_commit')
        completion['coverage_completed_at_s'] = budget.elapsed
        if completion['coverage_completed_at_s'] >= budget.seconds:
            raise Exhausted('wall_time_limit')
        out.update(completion)
    except Exhausted as error:
        out['reason'] = str(error)
        out['budget_exhausted'] = True
    except MemoryError:
        out['reason'] = 'RESOURCE_LIMIT'
    except Exception as error:
        out.update(reason='INTERFACE_OR_CONSISTENCY_ERROR',
                   error=f'{type(error).__name__}: {error}')
    finally:
        stopped = budget.elapsed
        out['numerical_unresolved'] = bool(out['unresolved_candidates'])
        # A local UNKNOWN may be paired with a strict violation in another
        # scene, which reliably excludes that complete assignment. Keep the
        # local diagnostic separate from genuinely unresolved joint leaves.
        out['local_unresolved_evaluations'] = sum(
            r['state'] == 'UNRESOLVED' for r in cache.values())
        out.update(stop_stage=active, last_raw_cartesian_index=cursor,
            budget_exhausted=out.get('budget_exhausted', False) or stopped >= budget.seconds,
            timing=budget.summary(stopped), source_sha256=source_identity(),
            local_cache_size=len(cache), panels=budget.panels, refinements=budget.refinements)
        archive_start = clock()
        if config is not None:
            _save(workdir/'input_config.json', config)
        if instance is not None:
            _save(workdir/'input_instance.json', instance)
        _save(workdir/'local_evaluations.json', cache)
        _save(workdir/'events.json', out['events'])
        out['archive_wall_s'] = clock()-archive_start
        _save(workdir/'result.json', out)
    return out
