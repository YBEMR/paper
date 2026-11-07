"""K162 beta=1.0 input and stored-evidence adapters; no scientific search changes."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[1]
sys.path[:0] = [str(HERE), str(ROOT/'p0_batch'), str(ROOT)]
import run_p0 as p0
from run_four_method_comparison import read, sha, canonical

PROBLEMS = tuple('beta_1.0__R'+str(i) for i in range(1, 6))
NORMAL = p0.NORMAL
SECONDS = 300
METHODS = p0.METHODS


def jobs(problem_id):
    if problem_id not in PROBLEMS:
        raise ValueError('Deadline preparation permits beta_1.0 R1..R5 only')
    blocks = [[deepcopy(j)] for j in METHODS] + [[
        {'id': 'sa'+str(seed), 'method': 'sa', 'seed': seed} for seed in range(101, 106)]]
    k = PROBLEMS.index(problem_id) % 4
    return [j for block in blocks[k:]+blocks[:k] for j in block]


def slots():
    return [dict(job, problem_id=pid, slot_id=pid+'__'+job['id'], seconds=SECONDS,
                 ordinal=i*8+n+1)
            for i, pid in enumerate(PROBLEMS) for n, job in enumerate(jobs(pid))]


def fresh_input(problem_id, budget=None):
    if problem_id not in PROBLEMS:
        raise ValueError('Undeclared deadline condition')
    from inputs import build_instance, load_config
    from control_policy import with_auto_low_idle, resolve_idle_policy
    from run_neighborhood_diagnostic import opened_stages
    from run_four_method_comparison import masks
    raw = load_config()
    instance = build_instance(raw, problem_id, budget=budget)
    config, instance = with_auto_low_idle(raw), with_auto_low_idle(instance)
    if (instance['id'] != problem_id or instance['response_variant'] != 'H'
            or F(instance['settings']['deadline_beta']) != 1
            or F(instance['window_ms']) != 400 or F(instance['start_grid_ms']) != 5
            or resolve_idle_policy(instance) != 'auto_low_immediate_v1'
            or any(any(F(t) != 50 for t in s['entry']['temperature_degC'])
                   or any(F(t) != 80 for t in s['maximum_temperature_degC'])
                   for s in instance['scenarios'])):
        raise ValueError('Deadline response/time/temperature/control contract changed')
    for scene in instance['scenarios']:
        for request in scene['requests']:
            length = F(request['reference_CPU_H_chain_ms'])
            if (F(request['relative_deadline_ms']) != length
                    or F(request['deadline_ms']) != F(request['release_ms'])+length):
                raise ValueError('Deadline must use the unchanged CPU-H reference chain')
    opened_stages(instance)
    masks(instance, 4)
    return raw, config, instance


def input_declaration(problem_id):
    from run_four_method_comparison import scene_spec, masks
    from run_neighborhood_diagnostic import opened_stages
    raw, config, instance = fresh_input(problem_id)
    ids = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                   map(canonical, (raw, config, instance))))
    return {'problem_id': problem_id, **ids, 'input_identities': ids,
            'scene_spec': scene_spec(instance),
            'first_opened_by_scene': opened_stages(instance),
            'linked_opened_by_job': {'anchor_linked4': masks(instance, 4)}}, (raw, config, instance)


def bind_current_legality(record, result, declaration):
    """Check saved complete SAFE schedules against this input, without heat or a new U.

    A SAFE label and a changed problem id cannot substitute for the current
    per-request deadline. Original numerical/thermal/technical evidence is kept.
    """
    from schedules import validate_schedule
    from execution_status import classify_execution
    checked = deepcopy(record)
    r = result if isinstance(result, dict) else {}
    context = checked.setdefault('context', {})
    checks, errors = [], []
    root_bad = False
    candidates = []
    has_u = checked.get('usable_U_J') is not None or r.get('safe_upper_bound_J') is not None
    if has_u:
        candidates.append(('final_safe_candidate', r.get('safe_candidate'), True))
    for index, row in enumerate(r.get('evaluations') or []):
        if isinstance(row, dict) and row.get('accepted_safe') is True:
            candidates.append(('evaluations:'+str(index), row.get('candidate'), False))
    witness = (r.get('initialisation') or {}).get('witness')
    if isinstance(witness, dict) and (witness.get('evaluation') or {}).get('state') == 'SAFE':
        candidates.append(('initialisation.witness', witness.get('candidate'), False))
    for name in ('diagnostic', 'solver_diagnostic'):
        diag = r.get(name) or {}
        if isinstance(diag, dict):
            diag = diag.get('diagnostic', diag)
            for index, row in enumerate(diag.get('evaluations') or []):
                if isinstance(row, dict) and row.get('accepted_safe') is True:
                    candidates.append((name+':'+str(index), row.get('candidate'), False))
    if candidates:
        try:
            _, config, instance = fresh_input(declaration['problem_id'])
            if (canonical(instance) != declaration['input_sha256']
                    or canonical(config) != declaration['config_sha256']):
                raise ValueError('Current input/config identity differs from declaration')
            identity_error = None
        except (KeyError, TypeError, ValueError) as error:
            instance = None
            identity_error = str(error)
        for source, candidate, is_root in candidates:
            if identity_error:
                detail = {'state': 'SCHEDULE_INVALID', 'reason': 'CURRENT_INPUT_IDENTITY_MISMATCH',
                          'details': identity_error}
            else:
                detail = validate_schedule(instance, candidate)
            valid = detail.get('state') == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
            checks.append({'source': source, 'valid': valid,
                           'reason': detail.get('reason'), 'details': detail.get('details')})
            if not valid:
                errors.append('CURRENT_DEADLINE_LEGALITY:'+source+':'+str(detail.get('reason')))
                root_bad = root_bad or is_root
    audit = {'passed': not errors, 'checks': checks,
             'new_thermal_evaluation': False, 'new_candidate_or_U': False,
             'scope': 'exact current-input scheduling checks on saved complete SAFE candidates only'}
    checked['current_schedule_audit'] = audit
    if errors:
        context['hard_errors'] = list(context.get('hard_errors') or [])+errors
        if root_bad:
            context['safe_receipt'] = None
        checked['execution'] = classify_execution(result, context)
        checked['usable_U_J'] = checked['execution']['usable_U_J']
    return checked


def result_records(job, result, declaration, folder, **kw):
    if job not in jobs(declaration['problem_id']):
        raise ValueError('Unbound method identity')
    if job['method'] == 'milp':
        from audit_whole import result_records as audit
        record = audit(result, declaration, folder, **kw)
    elif job['method'] == 'linked_fixed_unit_opp_start':
        import audit_cutoff as adapter
        from execution_status import classify_execution
        record = adapter.correct_records(job, result, declaration, folder, **kw)
        if record.get('cutoff_audit', {}).get('applied'):
            _, python, _, _ = adapter._last_mapping(result, folder)
            cancel = Path(folder)/'matlab'/f"request_{python['request_number']:06d}.cancel"
            valid = cancel.is_file() and cancel.read_text(encoding='ascii').strip() == 'budget'
            record['cutoff_audit']['cancel_file_verified'] = valid
            if not valid:
                record['context']['hard_errors'].append('MISSING_MATCHING_ROOT_CANCEL_FILE')
                record['execution'] = classify_execution(result, record['context'])
        from terminal_adapter import adapt_no_safe_seed
        record = adapt_no_safe_seed(record, result, declaration, folder)
    else:
        from audit_heuristic import result_records as audit
        record = audit(result, declaration, **kw)
    return bind_current_legality(record, result, declaration)
