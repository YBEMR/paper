"""Read-only long-budget adapters; no model, decoder or evaluator is called.

The launcher must bind its frozen science and p0_batch paths before calling
``audit_result``.  This module deliberately does not add a live-source path.
Checkpoint data describe existing receipts only, not new safety certificates.
"""
from copy import deepcopy
from fractions import Fraction
import importlib
import json
import math
from pathlib import Path
import threading


SECONDS = 3600
_AUDIT_LOCK = threading.RLock()


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def audit_result(result, declaration, folder, *, input_valid, source_valid,
                 errors=None, seconds=SECONDS):
    """Reuse the frozen original audit, changing only its method cutoff.

    Both modules need the new cutoff: audit_whole imported receipt_issues from
    audit_heuristic, and that function uses its defining module's globals.
    The changes are in memory, serialized, and restored even on an exception.
    """
    if not _finite(seconds) or seconds != SECONDS:
        raise ValueError('This diagnostic permits exactly one 3600-second cutoff')
    whole = importlib.import_module('audit_whole')
    heuristic = importlib.import_module('audit_heuristic')
    with _AUDIT_LOCK:
        old_whole, old_heuristic = whole.SECONDS, heuristic.SECONDS
        try:
            whole.SECONDS = heuristic.SECONDS = seconds
            return whole.result_records(result, declaration, Path(folder),
                input_valid=input_valid, source_valid=source_valid, errors=errors)
        finally:
            whole.SECONDS, heuristic.SECONDS = old_whole, old_heuristic


def _read_json(path, diagnostics):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError) as exc:
        diagnostics.append({'file': path.name, 'error': type(exc).__name__})
        return None


def _read_rows(path, diagnostics):
    try:
        data = path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return [], 0
    except (OSError, UnicodeError) as exc:
        diagnostics.append({'file': path.name, 'error': type(exc).__name__})
        return [], 0
    lines = data.splitlines(keepends=True)
    partial = bool(lines and not lines[-1].endswith(('\n', '\r')))
    if partial:
        lines.pop()  # A writer may still be publishing the last JSONL record.
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('JSONL record is not an object')
            rows.append(row)
        except (ValueError, TypeError) as exc:
            diagnostics.append({'file': path.name, 'line': number,
                                'error': type(exc).__name__})
    return rows, int(partial)


def _record_time(row):
    if _finite(row.get('method_elapsed_s')):
        return row['method_elapsed_s']
    if _finite(row.get('evaluation_returned_at_s')):
        return row['evaluation_returned_at_s']
    return (row.get('decode') or {}).get('completed_at_s')


def _safe_record(candidate, evaluation, source, eligible):
    if not isinstance(candidate, dict) or not isinstance(evaluation, dict):
        return None
    if (evaluation.get('state') != 'SAFE' or evaluation.get('rankable_energy') is not True
            or not eligible(evaluation.get('completed_at_elapsed_s'))):
        return None
    try:
        low, high = map(Fraction, evaluation['weighted_energy_J'])
        upper = Fraction(evaluation['safe_upper_bound_J'])
        if low < 0 or high < low or upper != high:
            return None
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return None
    return {'source': source, 'candidate': deepcopy(candidate),
            'evaluation': deepcopy(evaluation),
            'safe_upper_bound_J': str(evaluation['safe_upper_bound_J']),
            'formed_at_s': evaluation['completed_at_elapsed_s'],
            'independently_validated_by_reader': False}


def read_checkpoint(folder, cutoff, observed_monotonic):
    """Observe one call without solving, decoding, evaluating, or writing.

    Event records are included only when their recorded receipt/return time is
    strictly before cutoff and no later than this observation.  Initialization
    SAFE evidence is extracted separately by its completed receipt time; later
    x0-completion or publication metadata are never backfilled into the cut.
    Native time is request-relative; root time always uses Python receipts.
    """
    if not _finite(cutoff) or not 0 < cutoff <= SECONDS:
        raise ValueError('Checkpoint cutoff must be in (0, 3600] seconds')
    if not _finite(observed_monotonic):
        raise ValueError('Observation must use a finite monotonic timestamp')
    folder = Path(folder)
    diagnostics = []
    out = {'cutoff_s': cutoff, 'observed_monotonic': observed_monotonic,
           'state': 'ROOT_IDENTITY_NOT_AVAILABLE', 'read_diagnostics': diagnostics,
           'research_calls': 0, 'new_evaluations': 0, 'new_candidates': 0,
           'scope': 'existing evidence observation; one 3600-second trajectory, not an independent run',
           'independently_proven_optimal': False, 'independently_proven_infeasible': False}
    root = _read_json(folder/'method_budget_identity.json', diagnostics)
    if not isinstance(root, dict):
        return out
    if (root.get('clock') != 'monotonic' or root.get('limit_s') != SECONDS
            or not _finite(root.get('start')) or not _finite(root.get('deadline'))
            or root['deadline'] != root['start'] + SECONDS):
        out['state'] = 'INVALID_ROOT_IDENTITY'
        return out
    elapsed = observed_monotonic - root['start']
    out.update(root_identity=deepcopy(root), observed_method_elapsed_s=elapsed,
               checkpoint_reached=elapsed >= cutoff)
    if elapsed < 0:
        out['state'] = 'OBSERVATION_PRECEDES_METHOD'
        return out

    def eligible(stamp):
        return _finite(stamp) and 0 <= stamp < cutoff and stamp <= elapsed

    raw, partial = _read_rows(folder/'diagnostic_events.jsonl', diagnostics)
    events = [r for r in raw if eligible(_record_time(r))]
    builds, build_partial = _read_rows(folder/'build_progress.jsonl', diagnostics)
    builds = [r for r in builds if eligible(r.get('method_elapsed_seconds'))]
    checkpoint = _read_json(folder/'initial_receipt_checkpoint.json', diagnostics)
    initialization = (checkpoint or {}).get('initialisation') or {}
    witness = initialization.get('witness') or {}
    initial = _safe_record(witness.get('candidate'), witness.get('evaluation'),
                           'initial_constructor', eligible)
    initial_attempts = [r for r in initialization.get('attempts', [])
        if isinstance(r, dict) and eligible(r.get('schedule_completed_at_s'))]
    solver_safe = []
    for row in events:
        if row.get('event') == 'candidate_evaluated' and row.get('accepted_safe') is True:
            receipt = _safe_record(row.get('candidate'), row.get('evaluation'),
                                   row.get('source'), eligible)
            if receipt is not None:
                solver_safe.append(receipt)
    safe = ([initial] if initial else []) + solver_safe
    best = min(safe, key=lambda r: Fraction(r['safe_upper_bound_J'])) if safe else None
    worker = [r for r in events if r.get('event') == 'worker_event_received']
    bound_rows = [r for r in worker if _finite((r.get('values') or {}).get('lowerbound'))]
    latest_bound = bound_rows[-1] if bound_rows else None
    counts = {'raw_worker_events': len(worker),
        'solver_candidate_receipts': sum(r.get('event') == 'candidate_received' for r in events),
        'legal_decodes': sum(r.get('event') == 'candidate_decoded'
                            and (r.get('decode') or {}).get('state') == 'LEGAL' for r in events),
        'invalid_decodes': sum(r.get('event') == 'invalid_candidate' for r in events),
        'duplicate_receipts': sum(r.get('event') == 'duplicate_receipt_reused' for r in events),
        'solver_candidate_evaluations': sum(r.get('event') == 'candidate_evaluated' for r in events),
        'solver_safe_receipts': len(solver_safe),
        'initial_schedule_attempts': len(initial_attempts),
        'initial_safe_receipts': int(initial is not None)}
    solver_entered = next((r for r in worker if r.get('kind') == 'solver_entered'), None)
    out.update(state='OBSERVED', raw_events=events, counts=counts,
        raw_events_excluded=len(raw)-len(events), ignored_partial_lines=partial+build_partial,
        latest_build_progress=builds[-1] if builds else None,
        initial_safe_receipt=initial, solver_safe_receipts=solver_safe,
        best_safe_receipt_as_reported=best,
        solver_entered_received_s=None if solver_entered is None else solver_entered['method_elapsed_s'],
        latest_solver_reported_bound=None if latest_bound is None else {
            'lowerbound': latest_bound['values']['lowerbound'],
            'relativegap': latest_bound['values'].get('relativegap'),
            'method_elapsed_s': latest_bound['method_elapsed_s'],
            'request': latest_bound.get('request'), 'independently_certified': False},
        time_semantics='receipt/commit time in the same Python root clock; no future response backfill')
    return out
