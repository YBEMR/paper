"""Pure extraction of complete-receipt timing; never creates physical evidence.

The caller supplies one invocation's already saved result. This module does not
read archives, run the evaluator, validate a schedule or import method code.
SAFE below means a structurally consistent *stored* full-scene SAFE receipt;
independent physical verification remains a separate responsibility.
"""
from fractions import Fraction
import math


PROTOCOL = 'complete-receipt-completion-metrics-v1'


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _q(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not an energy')
    return Fraction(str(value))


def _interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('a complete two-sided energy interval is required')
    low, high = map(_q, value)
    if low < 0 or high < low:
        raise ValueError('invalid energy interval')
    return low, high


def _complete_scene(scene):
    if (not isinstance(scene, dict) or scene.get('state') != 'SAFE'
            or scene.get('rankable_energy') is not True):
        return False
    # Partial-scene aggregation wraps the original physical receipt in
    # ``result``; direct full evaluation stores that receipt as the scene.
    physical = scene.get('result') if isinstance(scene.get('result'), dict) else scene
    return (physical.get('state') == 'SAFE'
            and physical.get('rankable_energy') is True
            and physical.get('complete') is True)


def _safe_row(evaluation, candidate, source, cutoff, *, accepted=True,
              phase_index=None):
    if not accepted or not isinstance(evaluation, dict):
        return None
    stamp = _number(evaluation.get('completed_at_elapsed_s'))
    if not (evaluation.get('state') == 'SAFE'
            and evaluation.get('rankable_energy') is True
            and stamp is not None and 0 <= stamp < cutoff):
        return None
    scenes = evaluation.get('scenes')
    candidate_scenes = candidate.get('scenes') if isinstance(candidate, dict) else None
    if (not isinstance(scenes, dict) or not scenes
            or not isinstance(candidate_scenes, dict)
            or set(scenes) != set(candidate_scenes)
            or any(not _complete_scene(scene) for scene in scenes.values())):
        return None
    try:
        low, high = _interval(evaluation.get('weighted_energy_J'))
        if _q(evaluation.get('safe_upper_bound_J')) != high:
            return None
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    return dict(source=source, completed_at_s=stamp,
                energy_interval_J=[str(low), str(high)],
                safe_upper_bound_J=str(high), phase_index=phase_index)


def _collect_safe_rows(result, cutoff):
    rows, rejected, initial = [], [], None

    def collect(evaluation, candidate, source, accepted=True, phase_index=None):
        row = _safe_row(evaluation, candidate, source, cutoff,
                        accepted=accepted, phase_index=phase_index)
        if row is not None:
            rows.append(row)
        elif isinstance(evaluation, dict) and evaluation.get('state') == 'SAFE':
            rejected.append(source)
        return row

    witness = (result.get('initialisation') or {}).get('witness')
    if isinstance(witness, dict):
        initial = collect(witness.get('evaluation'), witness.get('candidate'),
                          'initialisation.witness')

    # A linked update is matched to its full aggregate receipt, not a scene's
    # local SAFE or an unverified energy event. Complete generations may survive
    # a later method error; the method's final state need not still be SAFE.
    aggregates = [r for r in result.get('aggregation_attempts', [])
                  if isinstance(r, dict)]
    if isinstance(result.get('aggregation'), dict):
        aggregates.append(result['aggregation'])
    for index, update in enumerate(result.get('global_updates', [])):
        if not isinstance(update, dict):
            continue
        match = next((r for r in aggregates
                      if r.get('completed_at_elapsed_s') == update.get('committed_at_s')
                      and r.get('weighted_energy_J') == update.get('weighted_energy_J')
                      and r.get('safe_upper_bound_J') == update.get('safe_upper_bound_J')), None)
        row = collect(match, (match or {}).get('safe_candidate'),
                      'global_updates[' + str(index) + ']',
                      phase_index=update.get('phase_index'))
        if initial is None and index == 0 and row is not None:
            # Only the explicit initial full aggregate establishes the linked
            # baseline; a later local/global improvement cannot replace it.
            if update.get('weighted_energy_J') == result.get('initial_global_weighted_energy_J'):
                initial = row

    # The existing heuristic entry archives every full-candidate evaluation.
    for index, item in enumerate(result.get('evaluations', [])):
        if not isinstance(item, dict):
            continue
        collect(item.get('evaluation'), item.get('candidate'),
                'evaluations[' + str(index) + ']',
                accepted=item.get('accepted_safe') is True)

    # Formal whole-MILP diagnostic may be top-level, nested, or both. It never
    # treats integer callback times or partial scene receipts as complete SAFE.
    diagnostics = [result.get('diagnostic'),
                   (result.get('solver_diagnostic') or {}).get('diagnostic')]
    for d_index, diagnostic in enumerate(diagnostics):
        if not isinstance(diagnostic, dict):
            continue
        for index, item in enumerate(diagnostic.get('evaluations', [])):
            if isinstance(item, dict):
                collect(item.get('evaluation'), item.get('candidate'),
                        'diagnostic' + str(d_index) + '.evaluations[' + str(index) + ']',
                        accepted=item.get('accepted_safe') is True)
    unique = {}
    for row in rows:
        key = (row['completed_at_s'], tuple(row['energy_interval_J']), row['phase_index'])
        unique.setdefault(key, row)
    rows = sorted(unique.values(), key=lambda row: row['completed_at_s'])
    if (initial is None and rows and isinstance(result.get('evaluations'), list)
            and not result.get('global_updates') and witness is None):
        initial = rows[0]
    return rows, initial, rejected


def _strict_metrics(rows, baseline, *, origin=None):
    if baseline is None:
        return dict(first_strict_improvement_at_s=None,
                    first_strict_improvement_after_entry_s=None,
                    strict_improvement_status='NO_INITIAL_COMPLETE_SAFE',
                    strict_improvements=[])
    base_low, base_high = _interval(baseline['energy_interval_J'])
    strict = [row for row in rows
              if row['completed_at_s'] > baseline['completed_at_s']
              and _interval(row['energy_interval_J'])[1] < base_low]
    first = strict[0]['completed_at_s'] if strict else None
    overlap = any(_interval(row['energy_interval_J'])[1] < base_high
                  and _interval(row['energy_interval_J'])[1] >= base_low
                  for row in rows if row['completed_at_s'] > baseline['completed_at_s'])
    return dict(first_strict_improvement_at_s=first,
                first_strict_improvement_after_entry_s=(None if first is None or origin is None
                                                        else first-origin),
                strict_improvement_status=('OBSERVED_INTERVAL_STRICT' if strict else
                                           'UPPER_DECREASE_WITHOUT_INTERVAL_SEPARATION' if overlap else
                                           'NOT_OBSERVED_BEFORE_CUTOFF'),
                strict_improvements=strict)


def _phase_record(raw, rows, cutoff, previous_end=None, *, kind='method_phase'):
    start = _number(raw.get('started_at_s', raw.get('start_s')))
    end = _number(raw.get('completed_at_s', raw.get('end_s')))
    valid = start is not None and end is not None and 0 <= start <= end
    before = [row for row in rows if start is not None and row['completed_at_s'] <= start]
    baseline = before[-1] if before else None
    during = [row for row in rows if valid and start <= row['completed_at_s'] <= end]
    cap = _number(raw.get('planned_total_cap_s'))
    gap = (start-previous_end if start is not None and previous_end is not None
           and start >= previous_end else None)
    improvement = (_strict_metrics(during, baseline, origin=start)
                   if kind == 'method_phase' else
                   dict(first_strict_improvement_at_s=None,
                        first_strict_improvement_after_entry_s=None,
                        strict_improvement_status='NOT_APPLICABLE_ACCOUNTING_OR_LOCAL_SLICE',
                        strict_improvements=[]))
    return dict(kind=kind, phase_index=raw.get('phase_index'),
                name=raw.get('name', raw.get('phase')), depth=raw.get('depth'),
                start_s=start, end_s=end,
                actual_interval_s=end-start if valid else None,
                actual_interval_status='TIMESTAMP_DERIVED' if valid else 'UNKNOWN',
                planned_total_cap_s=cap,
                planned_cap_status='EXPLICIT_RECORDED_CAP' if cap is not None else
                                   'NOT_SEPARATELY_ALLOCATED_RECORDED_ROOT_BUDGET',
                root_remaining_at_entry_s=max(0.0, cutoff-start) if start is not None else None,
                root_remaining_at_end_s=max(0.0, cutoff-end) if end is not None else None,
                pre_record_transition_s=gap,
                transition_status='TIMESTAMP_GAP_NOT_CAUSAL_OVERHEAD' if gap is not None else 'UNKNOWN',
                baseline_complete_energy_interval_J=(None if baseline is None else baseline['energy_interval_J']),
                **improvement)


def build_completion_metrics(result, *, uses_matlab=False, seconds=300):
    """Summarize one saved result without I/O, imports or new SAFE evidence.

    ``None`` or explicit NOT_RUN is unexecuted; absent fields in an executed
    result remain UNKNOWN. A missing MATLAB phase is never a measured zero.
    Every improvement requires a full-scene accepted receipt formed strictly
    before the single method deadline and U_new < L_baseline.
    """
    limit = _number(seconds)
    if limit is None or limit <= 0 or type(uses_matlab) is not bool:
        raise ValueError('positive finite seconds and boolean uses_matlab required')
    if result is not None and not isinstance(result, dict):
        raise TypeError('saved result must be a dictionary or None')
    not_run = result is None or result.get('state') == 'NOT_RUN'
    if not_run:
        return dict(protocol=PROTOCOL, status='NOT_RUN', root_budget_s=limit,
                    matlab_startup=dict(status='NOT_RUN', wall_s=None, records=[]),
                    first_complete_SAFE_at_s=None, first_complete_SAFE_status='NOT_RUN',
                    initial_complete_SAFE_energy_interval_J=None,
                    first_strict_improvement_at_s=None,
                    strict_improvement_status='NOT_RUN', complete_SAFE_receipts=[],
                    phases=[], scene_slices=[], native_requests=[],
                    scope='stored-result extraction only; no new proof')
    timing = result.get('timing') or {}
    recorded_limit = _number(timing.get('limit_s'))
    cutoff = min(limit, recorded_limit) if recorded_limit is not None and recorded_limit > 0 else limit
    rows, baseline, rejected = _collect_safe_rows(result, cutoff)
    frames = [r for r in timing.get('phase_records', []) if isinstance(r, dict)]
    startup = [r for r in frames if r.get('phase') == 'solver_startup']
    measured = all(_number(r.get('wall_s')) is not None and r['wall_s'] >= 0
                   and _number(r.get('start_s')) is not None
                   and _number(r.get('end_s')) is not None
                   and 0 <= r['start_s'] <= r['end_s']
                   and abs(r['wall_s']-(r['end_s']-r['start_s'])) <= 1e-8
                   for r in startup)
    startup_status = ('NOT_APPLICABLE' if not uses_matlab else
                      'MEASURED' if startup and measured else 'UNKNOWN')
    matlab = dict(status=startup_status,
                  wall_s=sum(r['wall_s'] for r in startup) if startup_status == 'MEASURED' else None,
                  records=[dict(r) for r in startup],
                  applicability_conflict=bool(startup and not uses_matlab))
    phases, slices, previous_end = [], [], None
    phase_input = result.get('phases') or []
    if phase_input:
        for raw in phase_input:
            if not isinstance(raw, dict):
                continue
            record = _phase_record(raw, rows, cutoff, previous_end)
            phases.append(record)
            previous_end = record['end_s']
            for scene, saved_scene in (raw.get('scenes') or {}).items():
                solver = (saved_scene or {}).get('solver_result') or {}
                scene_raw = dict(start_s=solver.get('slice_started_at_s'),
                                 end_s=(saved_scene or {}).get('search_returned_at_s'))
                slice_record = _phase_record(scene_raw, [], cutoff, kind='local_scene_slice')
                slice_record.update(phase_index=raw.get('phase_index'), scene=scene,
                                    planned_cooperative_cap_s=solver.get('scene_slice_s'),
                                    local_scene_first_SAFE_at_s=(solver.get('diagnostic') or {}).get('first_safe_receipt_s'),
                                    local_SAFE_is_complete_system_SAFE=False,
                                    request_settled=solver.get('request_settled'))
                slices.append(slice_record)
    else:
        # Keep nested phase depth; do not sum overlapping inclusive intervals.
        phases = [_phase_record(frame, rows, cutoff, kind='accounting_frame') for frame in frames]
    natives = []
    round_sets = [result.get('rounds') or []]
    for phase in phase_input:
        if isinstance(phase, dict):
            round_sets.extend(((scene or {}).get('solver_result') or {}).get('rounds') or []
                              for scene in (phase.get('scenes') or {}).values())
    for sequence in round_sets:
        for raw in sequence:
            if not isinstance(raw, dict):
                continue
            response = raw.get('response') if isinstance(raw.get('response'), dict) else raw
            effective = _number((response.get('options') or {}).get('MaxTime'))
            actual = _number((response.get('phase_seconds') or {}).get('intlinprog_call'))
            natives.append(dict(request_number=raw.get('request_number'),
                                request_root_remaining_s=raw.get('remaining_s'),
                                request_solver_MaxTime_upper_s=raw.get('solver_max_time_s'),
                                native_effective_MaxTime_s=effective,
                                native_effective_MaxTime_status='SAVED_NATIVE_DIAGNOSTIC' if effective is not None else 'UNKNOWN',
                                actual_native_call_s=actual,
                                actual_native_call_status='SAVED_NATIVE_DIAGNOSTIC' if actual is not None else 'UNKNOWN',
                                budget_valid=raw.get('budget_valid'),
                                accepted_for_evaluation=raw.get('accepted_for_evaluation'),
                                diagnostic_only_not_new_U=True))
    answer = dict(protocol=PROTOCOL, status='EXECUTED_RESULT', root_budget_s=limit,
                  recorded_root_budget_s=recorded_limit, evidence_cutoff_s=cutoff,
                  budget_identity_status='MATCH' if recorded_limit == limit else 'UNKNOWN' if recorded_limit is None else 'MISMATCH',
                  root_stop_at_s=timing.get('method_elapsed_s'),
                  deadline_overshoot_s=timing.get('deadline_overshoot_s'),
                  cleanup_s=timing.get('cleanup_s'), clock_origin=timing.get('clock_origin'),
                  matlab_startup=matlab,
                  first_complete_SAFE_at_s=rows[0]['completed_at_s'] if rows else None,
                  first_complete_SAFE_status='OBSERVED_FULL_RECEIPT' if rows else 'NOT_OBSERVED_IN_SAVED_FULL_RECEIPTS',
                  initial_complete_SAFE_energy_interval_J=None if baseline is None else baseline['energy_interval_J'],
                  complete_SAFE_receipts=rows, rejected_SAFE_record_sources=rejected,
                  phases=phases, scene_slices=slices, native_requests=natives,
                  scope='stored-result extraction only; no new candidate, physical verification or proof',
                  **_strict_metrics(rows, baseline))
    return answer
