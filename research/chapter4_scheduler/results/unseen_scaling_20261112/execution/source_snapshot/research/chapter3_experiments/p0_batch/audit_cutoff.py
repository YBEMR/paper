from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from run_four_method_comparison import read, canonical, finite
from completion_metrics import build_completion_metrics
from execution_status import classify_execution, DEADLINE_REASONS
SECONDS = 300

import audit_linked as runner
PROTOCOL = 'K154-P0-stored-cutoff-audit-v1'

def _complete(request):
    return (request.get('latched_unresolved') is False
        and request.get('within_budget') is True
        and not request.get('failure_reasons')
        and request.get('callback_publications_complete') is True
        and request.get('expected_callback_numbers') == request.get('checked_callback_numbers'))

def _last_mapping(r, folder):
    """Map a single unfinished final augmented request to its exact scene round."""
    requests = (r.get('augmented_transport') or {}).get('requests', [])
    if not requests or _complete(requests[-1]):
        raise ValueError('No unfinished final augmented request')
    request = requests[-1]
    phases = r.get('phases')
    if not isinstance(phases, list) or not phases:
        raise ValueError('Missing phases')
    phase = phases[-1]
    scenes = phase.get('scenes')
    if not isinstance(scenes, dict) or not scenes:
        raise ValueError('Missing last phase scenes')
    sid, scene = list(scenes.items())[-1]
    rounds = (scene.get('solver_result') or {}).get('rounds')
    if not isinstance(rounds, list) or not rounds:
        raise ValueError('Missing last scene round')
    last_round = rounds[-1]
    if last_round.get('augmented_admission') != request:
        raise ValueError('Final scene and transport request identities differ')
    number = last_round.get('request_number')
    if type(number) is not int or number <= 0:
        raise ValueError('Missing final native request number')
    pyfile = Path(folder)/'matlab'/f'request_{number:06d}.python.json'
    if sorted((Path(folder)/'matlab').glob('request_*.python.json'))[-1] != pyfile:
        raise ValueError('A later native result exists')
    python = read(pyfile)
    metadata = read(pyfile.with_name(f'request_{number:06d}.input.json'))
    if python.get('request_number') != number or metadata.get('request_number') != number:
        raise ValueError('Native request numbers differ')
    scope = f'{sid}:round:{len(rounds)}'
    scopes = {scope, f"phase:{phase['phase_index']}:{scope}"}
    return request, python, metadata, scopes

def correct_records(job, r, declaration, folder, *, input_valid, source_valid, errors=None):
    """Pure saved-evidence classification; preserve every unrelated error and U.

    The only relaxation is that a cancel publication may occur after 300 s but
    no later than the recorded method stop.  It grants no candidate admission.
    """
    original = runner.result_records(job, r, declaration, folder,
        input_valid=input_valid, source_valid=source_valid, errors=errors)
    context = deepcopy(original['context'])
    audit = {'protocol': PROTOCOL, 'applied': False, 'removed_hard_records': [],
        'original_execution_status': original['execution']['execution_status'],
        'new_safe_evaluation': False, 'late_candidate_accepted': False}
    try:
        timing = r.get('timing') or {}
        elapsed = timing.get('method_elapsed_s')
        if not (r.get('budget_exhausted') is True and r.get('reason') == 'wall_time_limit'
            and timing.get('limit_s') == runner.SECONDS and runner.finite(elapsed)
            and elapsed >= runner.SECONDS
            and all(context.get(k) is True for k in ('input_identity_valid',
                'source_identity_valid', 'current_request_identity_valid'))
            and context.get('observed_numerical_rejection') is False
            and context.get('prior_requests_complete') is True
            and context.get('worker_isolation') == 'VERIFIED'):
            raise ValueError('Root cutoff, identities, prior completion, numeric or isolation not verified')
        request, python, metadata, scopes = _last_mapping(r, folder)
        cancel = request.get('cancel_published_at_s')
        reasons = request.get('failure_reasons')
        transient = set((python.get('publication_read') or {}).get('transient_read_errors') or {})
        start = (r.get('condition') or {}).get('budget_identity', {}).get('start')
        if not (request.get('cancel_requested') is True and runner.finite(cancel)
            and runner.SECONDS <= cancel <= elapsed
            and request.get('native_status') == 'BUDGET_EXHAUSTED'
            and request.get('within_budget') is False
            and python.get('status') == 'BUDGET_EXHAUSTED'
            and python.get('response_may_arrive_later') is True
            and python.get('budget_valid') is False
            and python.get('accepted_for_evaluation') is False and python.get('x') == []
            and transient <= {'FileNotFoundError'}
            and isinstance(reasons, list) and bool(reasons)
            and all(isinstance(v, str) and v in DEADLINE_REASONS for v in reasons)
            and metadata.get('method_deadline_bound') is True
            and F(str(metadata['absolute_deadline'])) == F(start)+runner.SECONDS):
            raise ValueError('Final request has no complete matching root-cutoff rejection chain')
        hard = context['hard_errors']
        keep, removed = [], []
        fields = {'scope', 'reason', 'status', 'technical_state', 'error'}
        for item in hard:
            blank_cutoff = (isinstance(item, dict) and set(item) == fields
                and item['scope'] in scopes and item['status'] == 'BUDGET_EXHAUSTED'
                and all(item[k] is None for k in ('reason', 'technical_state', 'error')))
            (removed if blank_cutoff else keep).append(item)
        context['hard_errors'] = keep
        context['root_deadline_confirmed'] = True
        context['deadline_causal_trace'] = True
        context['completion_verified'] = False
        context['last_request'] = {'state': 'PENDING', 'pending_at_cutoff': True,
            'refuses_late_candidate': True, 'deadline_causal_trace': True,
            'deadline_reasons': reasons}
        execution = classify_execution(r, context)
        if execution.get('usable_U_J') != original.get('usable_U_J'):
            raise ValueError('Post-audit would change already formed safe U')
        audit.update(applied=True, removed_hard_records=removed,
            exact_request_scopes=sorted(scopes), cancel_published_at_s=cancel,
            method_stop_s=elapsed, method_deadline_bound=True,
            absolute_deadline=metadata['absolute_deadline'])
        return {**original, 'execution': execution, 'context': context,
                'usable_U_J': execution['usable_U_J'], 'cutoff_audit': audit}
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
        audit['not_applied_reason'] = str(exc)
        return {**original, 'cutoff_audit': audit}
