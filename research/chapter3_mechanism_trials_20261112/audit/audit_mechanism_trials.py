"""Read saved mechanism-trial evidence only; never import/execute scientific routines.

Run only after the batch is closed. Missing/unstarted evidence remains UNKNOWN.
Creates two new audit files and never edits experiment evidence or prior audits.
"""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import math
import time
import numpy as np
from scipy import sparse
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / 'work/mechanism_trials_v1'
RUN = ROOT / 'work/mechanism_trials_execution_v1'
HISTORY = ROOT / 'work/formal_abc_execution_v1'
KEYS = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon', 'x0')
TRIALS = {'C_repeat': {'model_arm': 'C', 'Heuristics': 'basic'},
          'B_repeat': {'model_arm': 'B', 'Heuristics': 'basic'},
          'C_noheur': {'model_arm': 'C', 'Heuristics': 'none'}}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def maybe(path):
    return read(path) if Path(path).exists() else None


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), default=str).encode()).hexdigest()


def clean(v):
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, np.ndarray):
        return clean(v.tolist())
    if isinstance(v, np.generic):
        return clean(v.item())
    if isinstance(v, float) and not math.isfinite(v):
        return repr(v)
    return v


def payload(path, native=False):
    d = loadmat(path, variable_names=list(KEYS))
    p = {k: d[k].tocsc() if k in ('A', 'Aeq') else d[k].reshape(-1) for k in KEYS}
    if native:
        p['intcon'] = p['intcon'].astype(np.int64) - 1
    return p


def array_digest(p):
    """Independent copy of frozen byte-level hash format, no scientific import."""
    out = {}
    for key in KEYS:
        value = p[key]
        h = hashlib.sha256()
        if sparse.issparse(value):
            h.update((str(value.shape) + str(value.dtype) + value.format).encode())
            for part in (value.data, value.indices, value.indptr):
                h.update((str(part.shape) + str(part.dtype)).encode())
                h.update(part.tobytes())
        else:
            value = np.asarray(value)
            h.update((str(value.shape) + str(value.dtype)).encode())
            h.update(value.tobytes())
        out[key] = h.hexdigest()
    return out


def schedule_key(candidate):
    return {s: sorted((r['stage_id'], r['unit'], r['opp'], F(r['start_ms'])) for r in rows)
            for s, rows in candidate['scenes'].items()}


def reconstruct_selection(options, vector, scene_ids):
    # Identity reconstruction only, not legality validation or thermal evaluation.
    candidate = {'scenes': {s: [] for s in scene_ids}}
    y = vector[:len(options)]
    if len(y) != len(options) or not np.isfinite(y).all():
        raise ValueError('Malformed option prefix')
    if np.any(np.abs(y - np.rint(y)) > 1e-6) or np.any(y < -1e-6) or np.any(y > 1 + 1e-6):
        raise ValueError('Prefix is not numerically binary')
    for o, v in zip(options, y):
        if round(float(v)) == 1:
            candidate['scenes'][o['scenario_id']].append(dict(stage_id=o['stage_instance_id'],
                unit=o['unit_id'], opp=o['opp_id'], start_ms=o['start_ms']))
    return candidate


def is_full_safe(e):
    return bool(e and e.get('state') == 'SAFE' and e.get('rankable_energy') is True
                and isinstance(e.get('completed_at_elapsed_s'), (int, float))
                and not isinstance(e.get('completed_at_elapsed_s'), bool)
                and 0 <= e['completed_at_elapsed_s'] < 600
                and len(e.get('scenes', {})) == 2
                and all(s.get('complete') is True and s.get('state') == 'SAFE'
                        for s in e['scenes'].values()))


def main():
    start = time.monotonic()
    if not (RUN / 'batch.json').is_file():
        raise SystemExit('Audit refused: batch.json is absent; wait for the finite batch to close.')
    checks, artifact_checks, records, artifacts, owned = [], [], {}, {}, []

    def check(name, value, detail=None, artifact=False):
        target = artifact_checks if artifact else checks
        target.append(dict(name=name, passed=None if value is None else bool(value),
                           state='UNKNOWN' if value is None else ('PASS' if value else 'FAIL'), detail=detail))

    plan = read(PACKAGE / 'plan.json')
    plan_sha = sha(PACKAGE / 'plan.json')
    check('plan_digest', read(PACKAGE / 'plan.identity.json')['sha256'] == plan_sha)
    check('fixed_trials_and_order', plan['trials'] == TRIALS and plan['arms'] == list(TRIALS))
    check('new_subject_commit', plan['base_commit'] == '3baeae859d0370da183c108cd4f6de869db09fec')
    for label, root in [('workspace_files', ROOT), ('package_files', PACKAGE)]:
        bad = [name for name, expected in plan[label].items()
               if not (root / name).is_file() or sha(root / name) != expected]
        check(label + '_unchanged', not bad, bad)
    original_script = ROOT / 'work/equality_pair_source/research/chapter3_experiments/solve_model.m'
    variant_script = PACKAGE / 'native_none/solve_model.m'
    insertion = b"        opts.Heuristics = 'none'; % Predeclared mechanism trial; sole native option intervention.\n"
    check('native_script_single_intervention', variant_script.read_bytes().count(insertion) == 1
          and variant_script.read_bytes().replace(insertion, b'') == original_script.read_bytes())
    approval = maybe(RUN / 'approval_consumed.json')
    expected_approval = dict(approved=True, plan_sha256=plan_sha, protocol=plan['protocol'],
        arms=plan['arms'], maximum_native_calls_per_arm=1, total_window_s=600, retries=0)
    check('new_approval_bound_to_plan', None if approval is None else
          all(approval.get(k) == v for k, v in expected_approval.items())
          and bool(approval.get('user_decision_reference')))
    batch = maybe(RUN / 'batch.json')
    completed = (batch or {}).get('completed', [])
    check('batch_closed', None if batch is None else True)
    check('no_duplicate_trials', len(completed) == len(set(completed)))
    check('predeclared_order_subsequence', completed == [a for a in plan['arms'] if a in completed])
    check('no_batch_retry', None if batch is None else batch.get('retries') == 0)
    expected_pending = list(plan['arms'])
    cumulative_affected = set()
    cumulative_stop_all = False
    used_pids, observed_calls, published_total, build_total, evaluation_total = [], 0, 0, 0, 0

    for trial in plan['arms']:
        folder = RUN / trial
        cfg = TRIALS[trial]
        if not folder.exists():
            records[trial] = dict(state='NOT_STARTED', scientific_outcome='UNKNOWN')
            artifacts[trial] = dict(state='NOT_STARTED')
            continue
        controller, receipt = maybe(folder / 'controller.json'), maybe(folder / 'receipt.json')
        claim, worker = maybe(folder / 'claim.json'), maybe(folder / 'worker_claim.json')
        monitor = maybe(folder / 'process_monitor.json') or {}
        owned += monitor.get('observed_identities', [])
        if worker:
            used_pids.append(worker['pid'])
        check(trial + '.claim_identity', None if claim is None else
              claim.get('arm') == trial and claim.get('plan_sha256') == plan_sha)
        check(trial + '.one_request_file', len(list((folder / 'matlab').glob('*.request.json'))) <= 1)
        check(trial + '.one_session', len(list(folder.glob('**/session.json'))) <= 1)
        if trial in completed:
            check(trial + '.permitted_next_trial', bool(expected_pending) and expected_pending[0] == trial)
        if receipt is None:
            records[trial] = dict(state='NO_COMPLETE_RECEIPT', controller=controller, scientific_outcome='UNKNOWN')
            artifacts[trial] = dict(state='NO_COMPLETE_RECEIPT')
            cumulative_stop_all = True
            expected_pending = []
            continue
        r = receipt
        check(trial + '.receipt_trial_identity', r.get('arm') == trial and r.get('model_arm') == cfg['model_arm']
              and r.get('predeclared_Heuristics') == cfg['Heuristics'])
        check(trial + '.single_request_build_eval_caps', r['native_request_attempts'] <= 1
              and r['native_requests_published'] <= 1 and r['model_builds'] <= 1
              and r['physical_evaluations_observed'] <= 4 and r['retries'] == 0
              and r['native_calls_observed'] in (None, 0, 1))
        if r['native_calls_observed'] is not None:
            observed_calls += r['native_calls_observed']
        published_total += r['native_requests_published']
        build_total += r['model_builds']
        evaluation_total += r['physical_evaluations_observed']
        native = r.get('native') or {}
        validation = r.get('returned_vector_validation') or {}
        progress = r['progress']
        event_log = folder / 'progress.jsonl'
        events = [json.loads(s) for s in event_log.read_text(encoding='utf-8').splitlines()] if event_log.exists() else []
        check(trial + '.timely_monotonic_events', all(0 <= e['received_elapsed_s'] < 550 for e in events)
              and all(a['received_elapsed_s'] <= b['received_elapsed_s'] for a, b in zip(events, events[1:])))
        check(trial + '.unique_event_numbers', len({e['event_number'] for e in events}) == len(events))
        entries = [e for e in events if e.get('kind') == 'solver_entered']
        roots = [e for e in events if e.get('values', {}).get('phase') == 'rootlp']
        later = [e for e in events if e.get('values', {}).get('phase') in ('heuristics', 'cutgen', 'branching')]
        check(trial + '.single_entry', len(entries) <= 1 and r['actual_native_entry_events'] == len(entries))
        check(trial + '.root_callback_completion_semantics',
              progress['root_lp_completion_observed'] == bool(roots or later)
              and progress['root_lp_entry_observed'] == bool(roots)
              and progress['root_lp_completion_via_later_phase'] == bool(later))
        admission = maybe(folder / 'initial_admission.json') or {}
        reference = admission.get('objective_reference_exact')
        returned_reference = validation.get('objective_exact_binary64') if validation.get('state') == 'ADMITTED' else None
        references = [F(v) for v in (reference, returned_reference) if v is not None]
        reference = min(references) if references else None
        finite_bounds = []
        for e in events:
            value = e.get('values', {}).get('lowerbound')
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                q = F.from_float(float(value))
                finite_bounds.append(dict(value=value, event_number=e['event_number'],
                    value_exact_binary64=str(q), consistency='UNKNOWN' if reference is None else
                    ('CONSISTENT_WITH_NUMERICAL_REFERENCE' if q <= F(reference) else 'CONFLICT')))
        check(trial + '.finite_bound_provenance_recomputed',
              [{k: b.get(k) for k in ('value', 'event_number', 'value_exact_binary64', 'consistency')}
               for b in progress['finite_bounds']] == finite_bounds)
        has_conflict = any(b['consistency'] == 'CONFLICT' for b in finite_bounds)
        check(trial + '.native_bound_conflict_recomputed', r['native_bound_conflict'] == has_conflict)
        if has_conflict:
            check(trial + '.bound_conflict_stopped_trial',
                  r.get('fault_scope') in ('ARM', 'ALL', 'FEATURE') and trial in r.get('affected_arms', []))
        for e in events:
            event_path = folder / 'matlab' / ('request_000001.event_%06d.json' % e['event_number'])
            check(trial + '.immutable_event_' + str(e['event_number']),
                  event_path.exists() and read(event_path) == {k: v for k, v in e.items() if k != 'received_elapsed_s'})
        allocation = maybe(folder / 'publication_allocation.json')
        request = maybe(folder / 'matlab/request_000001.request.json')
        if allocation:
            cap = math.floor(min(540, max(0, 600 - allocation['measured_elapsed_s'] - 10 - 50)))
            check(trial + '.dynamic_cap', allocation['native_seconds'] == cap
                  and allocation['can_submit'] == (cap >= 30))
        if request:
            check(trial + '.published_cap', allocation is not None and
                  request['solver_max_time_s'] == request['solver_max_time_s_declared'] == allocation['native_seconds'])
        if native.get('accepted_for_evaluation'):
            check(trial + '.response_before_cutoff', native.get('budget_valid') is True
                  and 0 <= native['received_by_adapter_elapsed_s'] < 550)
        init = maybe(folder / 'initialization.json')
        witnesses = [a for a in (init or {}).get('attempts', []) if is_full_safe(a.get('evaluation'))]
        seed = witnesses[0]['candidate'] if witnesses else None
        initial, returned = r.get('initial_evaluation'), r.get('returned_evaluation')
        if init:
            check(trial + '.initial_attempt_limit', len(init['attempts']) <= 3)
        if seed:
            check(trial + '.common_initial_identity', digest(seed) == plan['initial_candidate_identity'])
            check(trial + '.initial_evaluation_identity', initial['evidence_identity'] ==
                  dict(input_sha256=plan['input_identity'], candidate_sha256=digest(seed)))
        if returned:
            check(trial + '.returned_evaluation_identity', r.get('candidate') is not None and
                  returned['evidence_identity'] == dict(input_sha256=plan['input_identity'], candidate_sha256=digest(r['candidate'])))
        safe = is_full_safe(returned)
        check(trial + '.full_SAFE_claim_recomputed', r['returned_complete_SAFE'] == safe)
        check(trial + '.no_improvement_without_SAFE', safe or r.get('strict_energy_improvement') is not True)
        if validation.get('state') == 'ADMITTED':
            same = schedule_key(seed) == schedule_key(r['candidate'])
            check(trial + '.schedule_identity_recomputed', r['same_initial'] == same)
            check(trial + '.admission_before_method_cutoff', 0 <= validation['completed_at_elapsed_s'] < 600)
        if safe:
            same = schedule_key(seed) == schedule_key(r['candidate'])
            strict = F(returned['weighted_energy_J'][1]) < F(initial['weighted_energy_J'][0]) and not same
            disjoint = F(returned['weighted_energy_J'][1]) < F(initial['weighted_energy_J'][0]) or F(initial['weighted_energy_J'][1]) < F(returned['weighted_energy_J'][0])
            check(trial + '.strict_improvement_recomputed', r['strict_energy_improvement'] == strict)
            check(trial + '.energy_identity_conflict_recomputed', r['energy_identity_conflict'] == bool(disjoint and same))
        check(trial + '.new_SAFE_claim_recomputed', r['new_complete_SAFE'] == bool(safe and r['same_initial'] is False))
        check(trial + '.no_independent_optimality_overclaim', r['independent_optimality_proof'] is False)
        check(trial + '.cleanup_not_overclaimed', not r['lifecycle_integrity'] or
              bool(r['cleanup'].get('complete') and monitor.get('complete') and not monitor.get('forced_pids')))
        check(trial + '.clock_order', 0 <= r['method_elapsed_s'] <= r['total_elapsed_s']
              <= (controller or {}).get('actual_total_wall_s', float('inf')))
        timing = maybe(folder / 'timing_after_cleanup.json') or {}
        if timing:
            check(trial + '.exclusive_clock_accounting', abs(sum(timing['phases_exclusive_s'].values())
                  + timing['unattributed_s'] - timing['method_elapsed_s']) < 0.01)
        model = maybe(folder / 'model_summary.json')
        if model:
            check(trial + '.model_identity', model['problem_id'] == 'base__R1'
                  and model['preprocessing']['source_input_sha256'] == plan['input_identity'])
            check(trial + '.reduction_switches', bool(model['formulation'].get('propagate_support'))
                  and bool(model['formulation'].get('prune_joint_states')) == (cfg['model_arm'] == 'C'))

        # Independent native source/option/array evidence; no trust in receipt VERIFIED alone.
        art = dict(state='PARTIAL', model_arm=cfg['model_arm'])
        identity_parts = []
        raw_response = maybe(folder / 'matlab/request_000001.response.json')
        ready = maybe(folder / 'matlab/ready.json')
        session = maybe(folder / 'matlab/session.json')
        if raw_response and allocation:
            expected = dict(plan['native_options'], Heuristics=cfg['Heuristics'], MaxTime=allocation['native_seconds'])
            options_ok = raw_response.get('options') == expected
            identity_parts.append(options_ok)
            check(trial + '.sole_native_option_intervention', options_ok, artifact=True)
        else:
            identity_parts.append(None)
        if session and ready:
            script = variant_script if cfg['Heuristics'] == 'none' else original_script
            sources = {'solve_model.m': sha(script), 'matlab_bridge.py': sha(original_script.parent / 'matlab_bridge.py')}
            source_ok = session.get('source_sha256') == sources and ready.get('release') == '2023b'
            identity_parts.append(source_ok)
            check(trial + '.independent_native_source_identity', source_ok, artifact=True)
        else:
            identity_parts.append(None)
        cert_path = folder / 'representation_certificate.json'
        input_path = folder / 'matlab/request_000001.mat'
        old_path = folder / 'original_zero_based.mat'
        cert = read(cert_path) if cert_path.exists() else None
        original = payload(old_path) if old_path.exists() else None
        submitted = payload(input_path, True) if input_path.exists() else None
        if cert:
            check(trial + '.saved_exact_projection_flags', all(cert['checks'].values()), artifact=True)
            art['certificate_sha256'] = sha(cert_path)
        if original is not None and cert:
            old_hash = array_digest(original)
            check(trial + '.original_bound_to_certificate', old_hash == cert['source_array_sha256'], artifact=True)
            historical = payload(HISTORY / cfg['model_arm'] / 'original_zero_based.mat')
            historical_same = old_hash == array_digest(historical)
            check(trial + '.historical_same_model_original_arrays', historical_same, artifact=True)
            art['original_arrays'] = old_hash
        if submitted is not None and cert:
            new_hash = array_digest(submitted)
            array_ok = new_hash == cert['derived_array_sha256']
            identity_parts.append(array_ok)
            check(trial + '.submitted_bound_to_certificate', array_ok, artifact=True)
            historical = payload(HISTORY / cfg['model_arm'] / 'matlab/request_000001.mat', True)
            check(trial + '.historical_same_model_submitted_arrays', new_hash == array_digest(historical), artifact=True)
            art['submitted_arrays'] = new_hash
        else:
            identity_parts.append(None)
        raw_path = folder / 'matlab/request_000001.native.mat'
        if raw_path.exists():
            raw = loadmat(raw_path, variable_names=['x', 'fval', 'exitflag', 'output', 'initialPoint'], simplify_cells=True)
            vector = np.asarray(raw['x'], dtype=float).reshape(-1)
            check(trial + '.raw_vector_equals_receipt', np.array_equal(vector, np.asarray(native.get('x', []))), artifact=True)
            check(trial + '.raw_exitflag_matches_receipt', int(raw['exitflag']) == native.get('exitflag'), artifact=True)
            check(trial + '.raw_fval_matches_receipt', np.array_equal(np.asarray(raw['fval']).reshape(-1),
                  np.asarray(native.get('fval', [])).reshape(-1)), artifact=True)
            if raw_response:
                check(trial + '.raw_response_vector_state_matches_receipt',
                      raw_response.get('x') == native.get('x') and raw_response.get('exitflag') == native.get('exitflag')
                      and raw_response.get('output') == native.get('output'), artifact=True)
            art.update(raw_vector_length=len(vector), raw_vector_sha256=digest(vector.tolist()) if len(vector) else None,
                raw_native_output=raw['output'], raw_fval=raw['fval'], state='NATIVE_ARTIFACT_PRESENT')
            if submitted is not None:
                check(trial + '.native_initialPoint_equals_submitted',
                      np.array_equal(np.asarray(raw['initialPoint']).reshape(-1), submitted['x0']), artifact=True)
            if len(vector) and original is not None and cert:
                check(trial + '.returned_dimension', len(vector) == cert['derived_variables'], artifact=True)
                projected = vector[:cert['original_variables']]
                idx = original['intcon'].astype(int)
                art['same_integer_values_as_initial'] = np.array_equal(projected[idx], original['x0'][idx])
                art['same_full_vector_as_initial'] = np.array_equal(projected, original['x0'])
                if r.get('candidate'):
                    reconstructed = reconstruct_selection(read(folder / 'options.json'), projected,
                                                          list(r['candidate']['scenes']))
                    check(trial + '.receipt_candidate_reconstructed_from_native',
                          digest(reconstructed) == digest(r['candidate']), artifact=True)
                    check(trial + '.receipt_same_initial_from_native_selection',
                          r['same_initial'] == (schedule_key(reconstructed) == schedule_key(seed)), artifact=True)
                    art['reconstructed_candidate_identity'] = digest(reconstructed)
        else:
            art['native_result_status'] = 'UNKNOWN_NO_RAW_RESULT'
        independent_identity = False if False in identity_parts else (True if all(x is True for x in identity_parts) else None)
        art['independently_recomputed_native_identity'] = independent_identity
        check(trial + '.receipt_native_identity_not_overclaimed', not r['evidence_integrity'] or independent_identity is True)
        records[trial] = {k: r.get(k) for k in ['terminal_state', 'model_arm', 'predeclared_Heuristics', 'error',
            'fault_scope', 'affected_arms', 'native_calls_observed', 'native_requests_published', 'model_builds',
            'physical_evaluations_observed', 'allocated_native_MaxTime_s', 'returned_complete_SAFE', 'same_initial',
            'new_complete_SAFE', 'strict_energy_improvement', 'evidence_integrity', 'method_elapsed_s', 'total_elapsed_s']}
        records[trial].update(root_events=[{k: e.get(k) for k in ['event_number', 'received_elapsed_s', 'values']} for e in roots],
            native_output=native.get('output'), native_exitflag=native.get('exitflag'), progress=progress,
            initial_energy_J=initial.get('weighted_energy_J') if initial else None,
            returned_energy_J=returned.get('weighted_energy_J') if returned else None,
            native_response_elapsed_s=native.get('received_by_adapter_elapsed_s'), controller=controller,
            timing=timing, cleanup=r['cleanup'], missing_scientific_results_remain_unknown=True)
        artifacts[trial] = art
        # Independently apply scope to all future trials; ordinary outcomes do not block.
        remaining = [a for a in plan['arms'] if a not in completed[:completed.index(trial) + 1]] if trial in completed else []
        cumulative_affected.update(r.get('affected_arms', []))
        if not (controller or {}).get('completed') or not r['cleanup'].get('complete') \
                or r['identity_after'].get('state') != 'VERIFIED' or r.get('fault_scope') == 'ALL':
            cumulative_stop_all = True
        if cumulative_stop_all:
            expected_pending = []
        else:
            expected_pending = [a for a in remaining if a not in cumulative_affected
                                and TRIALS[a]['model_arm'] not in cumulative_affected]
        records[trial]['independent_cumulative_stop_audit'] = dict(
            stop_all=cumulative_stop_all, affected=sorted(cumulative_affected),
            permitted_pending_trials=expected_pending)

    check('batch_native_call_cap', observed_calls <= 3 and published_total <= 3)
    check('batch_build_evaluation_caps', build_total <= 3 and evaluation_total <= 12)
    check('independent_worker_pids', len(used_pids) == len(set(used_pids)))
    identities = [(p['pid'], p['create_time']) for p in owned]
    check('independent_owned_process_identities', len(identities) == len(set(identities)))
    import psutil
    process_states = []
    for pid, created in identities:
        try:
            p = psutil.Process(pid)
            alive = p.create_time() == created and p.is_running()
        except psutil.NoSuchProcess:
            alive = False
        except psutil.Error:
            alive = None
        process_states.append(dict(pid=pid, create_time=created, original_process_alive=alive))
    check('owned_processes_gone', None if any(p['original_process_alive'] is None for p in process_states)
          else all(p['original_process_alive'] is False for p in process_states))
    if batch:
        check('not_started_accounting', batch['not_started'] == [a for a in plan['arms'] if a not in completed])
        check('no_unexplained_early_batch_stop', not expected_pending,
              'Any remaining permitted trial needs a recorded correctness/lifecycle stop, not an ordinary timeout')
        check('batch_wall_accounting', abs(sum(c['actual_total_wall_s'] for c in batch['controllers'])
              - batch['per_arm_wall_sum_s']) < 1e-6 and batch['actual_batch_wall_s'] >= batch['per_arm_wall_sum_s'])
    base = dict(plan_sha256=plan_sha, subject_commit=plan['base_commit'], new_native_calls=0, new_builds=0,
                new_physical_evaluations=0, scope='Post-run saved-evidence audit only; no late scientific credit',
                independent_optimality_or_physical_bound_certificate=False)
    output = ROOT / 'work/mechanism_trials_audit'
    output.mkdir(exist_ok=False)
    results = [dict(base, checks=checks, trials=records, batch=batch, postrun_process_check=process_states),
               dict(base, checks=artifact_checks, trials=artifacts)]
    for name, result in zip(('audit.json', 'native_artifact_audit.json'), results):
        result.update(passed=not any(c['passed'] is False for c in result['checks']),
                      unknown_checks=[c['name'] for c in result['checks'] if c['passed'] is None],
                      audit_wall_s=time.monotonic() - start)
        with (output / name).open('x', encoding='utf-8', newline='\n') as f:
            json.dump(clean(result), f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
    print(json.dumps({name: dict(passed=r['passed'], checks=len(r['checks']), unknown=r['unknown_checks'],
          failed=[c for c in r['checks'] if c['passed'] is False])
          for name, r in zip(('audit', 'native_artifacts'), results)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
