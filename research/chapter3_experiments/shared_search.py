"""K114 first-pass shared-deployment search; one budget and one worker.

Only complete, original-input partial-adapter aggregates can update U. Search
order and cooperative scene slices are heuristics, never domain exclusions.
No old candidates, reference energies, or another invocation's caches enter.
"""
from copy import deepcopy
from itertools import product, zip_longest
import math
from pathlib import Path
import platform
import sys
import time

from control_policy import resolve_idle_policy
from matlab_bridge import MatlabSession
from partial_bounds import independent_lower_bound
from partial_method import execute_shared_deployment, _change
from scene_adapter import (PARTIAL_PROTOCOL, _partial_identity, _receipt_hash,
    canonical_hash, shared_deployment_ids, validate_shared_deployment)
from scene_method import _save
from thermal import Exhausted, _accuracy, _q
from timing import MethodBudget


PROTOCOL = 'shared-deployment-first-pass-global-budget-v1'
RECORDS = {}


def ordered_conditions(instance, budget, bound_provider=independent_lower_bound):
    """Small unit-support product, not a library of complete schedules."""
    shared = shared_deployment_ids(instance)
    key_order = [h for h in ('A.pre', 'A.main', 'A.post') if h in shared]
    key_order += [h for h in shared if h not in key_order]
    supports = {h: sorted({m['unit_id'] for m in instance['stage_modes'][h]}) for h in shared}
    group_stage = ('A.main' if 'A.main' in shared else
                   min(shared, key=lambda h: (-len(supports[h]), h)) if shared else None)
    groups = {}
    for units in product(*(supports[h] for h in shared)):
        budget.check()
        fixed = validate_shared_deployment(instance, dict(zip(shared, units)))
        bound = bound_provider(instance, fixed, budget)
        if (bound.get('scope') != 'fixed_shared_deployment'
                or bound.get('input_sha256') != canonical_hash(instance)
                or bound.get('shared_deployment') != fixed
                or bound.get('solver_reported') is not False):
            raise ValueError('Conditional bound identity/scope mismatch')
        row = {'shared_deployment': fixed, 'L_a': bound, 'group': fixed.get(group_stage)}
        groups.setdefault(row['group'], []).append(row)
    for rows in groups.values():
        rows.sort(key=lambda r: (_q(r['L_a']['lower_bound_J']),
                                 tuple(r['shared_deployment'][h] for h in key_order)))
    keys = sorted(groups, key=lambda k: (_q(groups[k][0]['L_a']['lower_bound_J']), k or ''))
    ordered = [row for bundle in zip_longest(*(groups[k] for k in keys)) for row in bundle if row is not None]
    for index, row in enumerate(ordered):
        row.update(index=index, state='UNVISITED', reason='NOT_VISITED', visited=False,
                   result_file=None, initial_upper_bound_J=None, initial_energy_J=None,
                   safe_upper_bound_J=None, weighted_energy_J=None)
    budget.check()
    return ordered, {'group_stage_id': group_stage, 'group_order': keys,
                     'shared_stage_ids': shared, 'canonical_key_order': key_order,
                     'nominal_condition_count': len(ordered),
                     'domain_pruning': False, 'symmetry_deletion': False}


def _technical_issues(result):
    bad = {'INTERFACE_ERROR', 'RESOURCE_LIMIT', 'SOLVER_INTERFACE_ERROR',
           'INVALID_INPUT_OR_INTERFACE', 'SOLVER_NUMERICAL_CONSISTENCY_UNRESOLVED',
           'NUMERICAL_CANDIDATE_ANOMALY', 'INITIALISATION_ERROR'}
    issues = []
    def inspect(record, scope):
        if record.get('reason') in bad or record.get('error') or record.get('cleanup_error'):
            issues.append({'scope': scope, 'reason': record.get('reason'),
                           'error': record.get('error') or record.get('cleanup_error')})
        if (record.get('numerical_consistency') or {}).get('state') == 'NUMERICAL_ADMISSION_STATUS_CONFLICT':
            issues.append({'scope': scope, 'reason': 'NUMERICAL_ADMISSION_STATUS_CONFLICT'})
    inspect(result, 'condition')
    for sid, scene in result.get('scenes', {}).items():
        inspect(scene, sid)
        solved = scene.get('solver_result') or {}
        inspect(solved, sid+':solver')
        for returned in solved.get('rounds', []):
            inspect(returned, sid+':native')
            if returned.get('status') in ('ERROR', 'WORKER_EXITED'):
                issues.append({'scope': sid, 'reason': returned['status']})
    return issues


def initial_baseline_comparison(final_energy, baselines):
    """A certificate against the entire initial pool, including overlaps.

    Selecting the initial interval with the smallest upper endpoint does not
    identify which initialization has the smallest true energy. To beat all
    of them, the final upper must be below every initial lower endpoint.
    """
    lower = min((_q(row['energy_J'][0]) for row in baselines), default=None)
    return {'best_initial_true_energy_lower_bound_J': None if lower is None else str(lower),
            'strict_improvement_over_best_initial_certified':
                lower is not None and final_energy is not None and _q(final_energy[1]) < lower}


def execute_shared_search(input_loader, workdir, *, seconds=900, scene_slice_s=60,
        clock=time.monotonic, session_factory=MatlabSession,
        condition_executor=execute_shared_deployment,
        bound_provider=independent_lower_bound, condition_options=None):
    """Lazy first visit of every nominal condition, until one absolute cutoff.

    The factory is called only after the first condition's initialization. It
    supplies the same worker to subsequent conditions and never renews time.
    ``condition_options`` injects correctness-fixture dependencies only.
    """
    budget = MethodBudget(seconds, clock=clock)
    folder = Path(workdir)
    if folder.exists():
        raise FileExistsError(f'Invocation directory already exists: {folder}')
    folder.mkdir(parents=True, exist_ok=False)
    if isinstance(scene_slice_s, bool) or not isinstance(scene_slice_s, (int, float)) or not math.isfinite(scene_slice_s) or scene_slice_s <= 0:
        raise ValueError('scene_slice_s must be positive and finite')
    opts = dict(condition_options or {})
    protected = {'budget', 'close_session', 'scene_slice_s', 'session_factory',
                 'on_global_update', 'bounds_receipt', 'seconds', 'clock', 'shared_deployment'}
    if protected.intersection(opts):
        raise ValueError('Fixture options cannot replace shared timing/session/condition contracts')
    result = {'protocol': PROTOCOL, 'state': 'UNRESOLVED', 'reason': None,
        'safe_upper_bound_J': None, 'weighted_energy_J': None, 'safe_candidate': None,
        'aggregation': None, 'rankable_energy': False, 'best_shared_deployment': None,
        'global_updates': [], 'initial_baselines': [], 'best_initial_upper_bound_J': None,
        'best_initial_energy_J': None, 'best_initial_shared_deployment': None,
        'conditions': [], 'condition_result_files': [], 'violations': [],
        'scene_slice_s': float(scene_slice_s), 'global_budget_s': float(seconds),
        'independently_proven_optimal': False, 'independently_proven_infeasible': False,
        'remaining_domain': 'retained', 'formal_comparison': False, 'condition_revisits': 0,
        'matlab_worker_ready': False, 'shared_cache_between_method_calls': False}
    config = instance = session = None
    active_index = None
    input_digest = accuracy = None

    def get_session(_folder, **kwargs):
        nonlocal session
        if kwargs.get('budget') is not budget:
            raise ValueError('Condition tried to create another method budget')
        budget.check()
        if session is None:
            session = session_factory(folder/'matlab', total_budget_s=budget.remaining, budget=budget)
            result['matlab_worker_ready'] = True
        if getattr(session, 'request_blocked', False):
            raise RuntimeError('Previous native request has not safely unwound')
        return session

    def accept_update(partial, update):
        """Transfer already formed all-scene evidence; no heat/solver work."""
        item = result['conditions'][active_index]
        fixed = item['shared_deployment']
        aggregation = partial.get('aggregation') or {}
        candidate = aggregation.get('safe_candidate')
        expected = _partial_identity(instance, fixed, accuracy, budget, candidate=candidate,
                                     local_deployment=aggregation.get('merged_deployment'))
        formed = aggregation.get('completed_at_elapsed_s')
        if (partial.get('shared_deployment') != fixed
                or aggregation.get('protocol') != PARTIAL_PROTOCOL
                or aggregation.get('state') != 'SAFE' or not aggregation.get('rankable_energy')
                or aggregation.get('identity') != expected
                or aggregation.get('receipt_sha256') != _receipt_hash(aggregation)
                or aggregation.get('shared_deployment') != fixed
                or set(aggregation.get('scenes', {})) != {s['id'] for s in instance['scenarios']}
                or isinstance(formed, bool) or not isinstance(formed, (float, int))
                or not 0 <= formed < budget.seconds
                or aggregation.get('weighted_energy_J') != update.get('weighted_energy_J')
                or aggregation.get('safe_upper_bound_J') != update.get('safe_upper_bound_J')):
            raise ValueError('Outer aggregate identity/energy/timing mismatch')
        energy = deepcopy(aggregation['weighted_energy_J'])
        upper = aggregation['safe_upper_bound_J']
        if _q(energy[0]) > _q(energy[1]) or _q(upper) != _q(energy[1]):
            raise ValueError('Invalid aggregate energy interval')
        scene_sources = update.get('scene_sources') or {}
        if set(scene_sources) != {s['id'] for s in instance['scenarios']}:
            raise ValueError('Source attribution must cover all original scenes')
        initial = all(v == 'initial_constructor' for v in scene_sources.values())
        # These are retained already-formed receipts, not a newly synthesized U.
        if initial:
            baseline = {'shared_deployment': deepcopy(fixed), 'energy_J': energy,
                        'upper_bound_J': upper, 'formed_at_s': formed,
                        'transferred_at_s': budget.elapsed}
            result['initial_baselines'].append(baseline)
            item.update(initial_upper_bound_J=upper, initial_energy_J=deepcopy(energy))
            if result['best_initial_upper_bound_J'] is None or _q(upper) < _q(result['best_initial_upper_bound_J']):
                result.update(best_initial_upper_bound_J=upper, best_initial_energy_J=deepcopy(energy),
                              best_initial_shared_deployment=deepcopy(fixed))
        if budget.elapsed >= budget.seconds:
            result.setdefault('late_existing_aggregate_transfers', []).append({
                'condition_index': active_index, 'formed_at_s': formed, 'transferred_at_s': budget.elapsed})
            return
        item.update(safe_upper_bound_J=upper, weighted_energy_J=deepcopy(energy))
        if result['safe_upper_bound_J'] is not None and _q(upper) >= _q(result['safe_upper_bound_J']):
            return
        previous = result['weighted_energy_J']
        old_fixed = result['best_shared_deployment']
        prepared = {'condition_index': active_index, 'shared_deployment': deepcopy(fixed),
            'source': 'initial_constructor' if initial else 'inner_MILP',
            'scene_sources': deepcopy(scene_sources), 'condition_changed': old_fixed is not None and old_fixed != fixed,
            'energy_J': deepcopy(energy), 'safe_upper_bound_J': upper, 'aggregate_formed_at_s': formed,
            **_change(previous, energy)}
        saved = deepcopy(aggregation)
        budget.check()
        prepared['committed_at_s'] = budget.elapsed
        result['global_updates'].append(prepared)
        result.update(state='SAFE', rankable_energy=True, safe_upper_bound_J=upper,
            weighted_energy_J=deepcopy(energy), safe_candidate=deepcopy(candidate),
            aggregation=saved, best_shared_deployment=deepcopy(fixed))
        result.setdefault('first_safe_at_s', prepared['committed_at_s'])

    try:
        with budget.phase('input_read_and_expansion'):
            config, instance = input_loader(budget)
            config, instance = deepcopy(config), deepcopy(instance)
        budget.check()
        if resolve_idle_policy(config) != resolve_idle_policy(instance):
            raise ValueError('Input/config policy mismatch')
        accuracy = _accuracy(config['accuracy_targets'])
        input_digest = canonical_hash(instance)
        result['identity'] = {'full_input_sha256': input_digest, 'config_sha256': canonical_hash(config),
                              'control_policy': resolve_idle_policy(instance)}
        result['problem_id'] = instance['id']
        with budget.phase('global_independent_bound'):
            result['L0'] = bound_provider(instance, None, budget)
        if (result['L0'].get('scope') != 'original_full_domain'
                or result['L0'].get('input_sha256') != input_digest
                or result['L0'].get('solver_reported') is not False):
            raise ValueError('Global lower bound scope/identity mismatch')
        with budget.phase('condition_bounds_and_order'):
            result['conditions'], result['ordering'] = ordered_conditions(instance, budget, bound_provider)
        def same_input(given):
            if given is not budget:
                raise ValueError('A condition must receive the outer budget')
            return config, instance
        for item in result['conditions']:
            budget.check()
            active_index = item['index']
            fixed = item['shared_deployment']
            item.update(visited=True, state='PROCESSING', visit_started_at_s=budget.elapsed)
            subfolder = folder/('condition_%03d' % active_index)
            item['result_file'] = (subfolder/'result.json').relative_to(folder).as_posix()
            with budget.phase('condition_execution_including_reports'):
                partial = condition_executor(same_input, subfolder, shared_deployment=fixed,
                    budget=budget, close_session=False, scene_slice_s=float(scene_slice_s),
                    session_factory=get_session, on_global_update=accept_update,
                    bounds_receipt={'L0': result['L0'], 'L_a': item['L_a']}, **opts)
            # Retain returned evidence first, even if the common deadline passed.
            item.update(state=partial['state'], reason=partial.get('reason'),
                        visit_returned_at_s=budget.elapsed,
                        scenes={sid: {'state': rec.get('state'), 'reason': rec.get('reason'),
                            'model_complete': rec.get('model_complete'),
                            'search_started_at_s': rec.get('search_started_at_s'),
                            'search_returned_at_s': rec.get('search_returned_at_s'),
                            'x0_injected': rec.get('x0_injected'),
                            'slice': (rec.get('solver_result') or {}).get('slice')}
                            for sid, rec in partial.get('scenes', {}).items()})
            result['condition_result_files'].append(item['result_file'])
            result['violations'].extend(deepcopy(partial.get('violations', [])))
            issues = _technical_issues(partial)
            if issues:
                result.update(reason='CONDITION_TECHNICAL_FAILURE', technical_issues=issues)
                break
            if partial.get('worker_reusable') is False and budget.remaining > 0:
                result['reason'] = 'NATIVE_REQUEST_NOT_UNWOUND'
                break
            if session is not None and getattr(session, 'request_blocked', False):
                result['reason'] = 'NATIVE_REQUEST_NOT_UNWOUND'
                break
            del partial  # Large matrices belong only to the finished condition.
            budget.check()
        else:
            result['reason'] = 'FIRST_PASS_COMPLETED_REMAINING_DOMAIN_UNRESOLVED'
    except Exhausted:
        result['reason'] = 'GLOBAL_BUDGET_EXHAUSTED'
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except Exception as error:
        result.update(reason='INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
    finally:
        stopped = budget.elapsed
        result['timing'] = budget.summary(stopped)
        result['timing']['cleanup_s'] = 0.0
        cleanup_start = clock()
        if session is not None:
            session.event_consumer = None
            try:
                session.close()
            except Exception as error:
                result['cleanup_error'] = f'{type(error).__name__}: {error}'
        result['timing']['cleanup_s'] = clock()-cleanup_start
        result['solver_request_attempts'] = getattr(session, 'counter', 0)
    # Read-only reporting over previously formed receipts; no late new U.
    result['visited_condition_count'] = sum(r['visited'] for r in result['conditions'])
    result['best_initial_baseline_scope'] = 'min of this invocation complete initial receipts formed before cutoff; not a new search U'
    result.update(initial_baseline_comparison(result['weighted_energy_J'], result['initial_baselines']))
    if result.get('L0') and result['safe_upper_bound_J'] is not None:
        lower = _q(result['L0']['lower_bound_J'])
        upper = _q(result['safe_upper_bound_J'])
        gap = upper-lower
        result['independent_gaps'] = {'L0': {'lower_bound_J': str(lower),
            'safe_upper_bound_J': str(upper), 'absolute_gap_J': str(gap),
            'relative_gap': str(gap/upper) if upper > 0 else None,
            'scope': 'original_full_domain', 'consistent': gap >= 0,
            'solver_reported': False, 'independently_proven_optimal': False}}
    result['environment'] = {'python': sys.version, 'platform': platform.platform(),
                             'scope': 'first-pass bounded search, not a formal comparison'}
    _save(folder/'input_config.json', config)
    _save(folder/'input_instance.json', instance)
    _save(folder/'result.json', result)
    return result
