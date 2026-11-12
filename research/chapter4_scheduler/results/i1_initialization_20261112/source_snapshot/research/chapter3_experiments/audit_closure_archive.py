"""Finite read-only checks of one terminal closure archive, without replay.

Reads saved JSON, Git blobs and local MATLAB payload arrays. It never imports
an execution entry or calls a solver, model builder, trajectory evaluator or
candidate repair. PASS concerns archive consistency, not method success or
mathematical optimality. Ignored MAT files stay local; their hashes are saved.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import subprocess

from research.chapter3_experiments.completion_metrics import build_completion_metrics
from research.chapter3_experiments.thermal_limit_ablation import planning_instance, summarize_post
from research.chapter3_method_entry_executor.common import inspect_safe_receipt, cleanup_receipt_complete


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT/'research/chapter3_experiments/results'
EXPECTED_JOBS = [
    ('t50_milp', 'whole_milp', None, 't50_full'), ('t50_heft', 'heft', None, 't50_full'),
    ('t50_sa101', 'sa', 101, 't50_full'), ('t50_milp_no_limit', 'whole_milp', None, 't50_no_limit'),
    *[(f't50_sa{s}', 'sa', s, 't50_full') for s in range(102, 106)],
    ('t78_milp', 'whole_milp', None, 't78_full'),
    ('t78_milp_no_limit', 'whole_milp', None, 't78_no_limit')]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_blob_hashes(subject, paths):
    """One read-only cat-file process; avoid a separate Git process per source."""
    names = list(paths)
    payload = ''.join(subject+':'+name+'\n' for name in names).encode('utf-8')
    output = subprocess.run(['git', 'cat-file', '--batch'], cwd=ROOT,
                            input=payload, capture_output=True, check=True).stdout
    hashes, position = {}, 0
    for name in names:
        end = output.index(b'\n', position)
        header = output[position:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise ValueError('Subject blob missing: '+name)
        size = int(header[2]); position = end+1
        hashes[name] = hashlib.sha256(output[position:position+size]).hexdigest()
        position += size+1
    if position != len(output):
        raise ValueError('Unexpected Git batch framing')
    return hashes


def mat_certificate_hashes(path, x0_supplied):
    """Hash actual transport arrays in the certificate's Python conventions."""
    import numpy as np
    from scipy.io import loadmat
    from research.chapter3_experiments.numeric_case_diagnostic.exact_equalities import KEYS, _digest
    values = loadmat(path, variable_names=list(KEYS))
    payload = {key: values[key] if key in ('A', 'Aeq') else values[key].reshape(-1)
               for key in KEYS if key in values}
    if ('x0' in payload) != x0_supplied:
        raise ValueError('Actual MAT x0 presence mismatch')
    payload['intcon'] = payload['intcon'].astype(np.int64)-1
    if not x0_supplied:
        payload['x0'] = np.zeros(len(payload['c']), dtype=np.float64)
    return _digest(payload)


def audit(folder, plan_path):
    folder, plan_path = Path(folder).resolve(), Path(plan_path).resolve()
    evidence, checks, observations = {}, {}, []

    def read(path):
        path = Path(path)
        evidence[path.relative_to(ROOT).as_posix()] = digest(path)
        return json.loads(path.read_bytes())

    def check(name, condition):
        checks[name] = bool(condition)

    plan = read(plan_path); batch = read(folder/'batch.json')
    if batch.get('state') not in ('COMPLETED', 'STOPPED'):
        raise ValueError('A saved terminal batch is required; no live result is certified')
    approval = read(plan_path.parent/'user_approval.json')
    claim = read(RESULTS/'natural_full_claims'/(digest(plan_path)+'.json'))
    subject = approval['subject_commit']
    expected = [dict(id=i, method=m, seed=s, case=c) for i, m, s, c in EXPECTED_JOBS]
    check('predeclared_ten_jobs', plan['jobs'] == expected)
    check('budgets_and_no_precheck_calls', plan['scope'] == {
        'method_calls': 10, 'method_seconds_each': 600, 'method_seconds_total': 6000,
        'post_calls_at_most': 10, 'post_seconds_each': 60, 'post_seconds_total_at_most': 600,
        'job_calendar_seconds': 780, 'batch_calendar_seconds': 7860, 'retries': 0}
        and plan['precheck_thermal_calls'] == 0)
    check('user_subject_plan_scope_binding', approval['approved_by_user'] is True
        and approval['approval_source'] == 'USER_CURRENT_CONVERSATION'
        and bool(approval['human_authorization_text'])
        and approval['not_an_external_agent_loop_review'] is True
        and approval['plan_sha256'] == digest(plan_path) == batch['plan_sha256']
        and approval['scope'] == plan['scope'] and Path(approval['output_directory']).resolve() == folder)
    check('one_time_claim_binding', claim['scope'] == plan['scope']
        and claim['approval_sha256'] == digest(plan_path.parent/'user_approval.json')
        and Path(claim['output']).resolve() == folder and claim['no_resume_or_retry'] is True)
    paths = dict(plan['source_sha256']); paths[plan_path.relative_to(ROOT).as_posix()] = digest(plan_path)
    check('subject_sources_and_plan', git_blob_hashes(subject, paths) == paths)
    check('current_frozen_sources', all(digest(ROOT/path) == sha for path, sha in paths.items()))
    science = read(RESULTS/'small_whole_preparation01/plan.json')['source_sha256']
    check('original_197_scientific_sources', len(science) == 197 and plan['science_source_count'] == 197
        and all(plan['source_sha256'].get(path) == sha and digest(ROOT/path) == sha for path, sha in science.items()))
    check('native_executable_unchanged', digest(plan['native_executable']) == plan['native_executable_sha256'])
    manifest = read(plan_path.parent/'inputs.json')
    check('case_manifest_and_no_hidden_prechecks', manifest['cases'] == plan['cases']
        and manifest['optimization_calls'] == manifest['thermal_calls'] == manifest['matrix_builds'] == 0)
    cases = {}
    for name, case in plan['cases'].items():
        check(name+'/frozen_files', all(digest(ROOT/case[field]) == sha for field, sha in case['sha256'].items()))
        instance, original = read(ROOT/case['input_file']), read(ROOT/case['posterior_file'])
        declaration = read(ROOT/case['declaration_file']); size = read(ROOT/case['static_size_file'])
        view, expected_declaration = planning_instance(original, not name.endswith('_no_limit'))
        check(name+'/only_declared_limit_view', view == instance and declaration == expected_declaration)
        deadlines = {r['application']: F(r['deadline_ms']) for s in original['scenarios'] for r in s['requests']}
        check(name+'/beta1_temperature_domain', deadlines == {'A': F(90), 'B': F(100), 'C': F(90)}
            and F(original['settings']['deadline_beta']) == 1
            and all(F(t) == (78 if name.startswith('t78') else 50)
                for s in original['scenarios'] for t in s['entry']['temperature_degC'])
            and original['window_ms'] == '400' and original['start_grid_ms'] == '5'
            and original.get('start_domain') is None)
        cases[name] = (instance, original, read(ROOT/case['config_file']), size)
    methods = {r['job']: r for r in batch['methods']}; posts = {r['job']: r for r in batch['posts']}
    planned = {j['id'] for j in expected}
    check('call_inventory_no_retry_or_extra_slot', len(methods) == len(batch['methods']) == batch['method_attempts'] <= 10
        and len(posts) == len(batch['posts']) == batch['post_attempts'] <= len(methods)
        and set(methods) <= planned and set(posts) <= set(methods)
        and set(batch['not_run']) == planned-set(methods)
        and {p.name for p in (folder/'slots').iterdir() if p.is_dir()} ==
            {j+'__method' for j in methods} | {j+'__post' for j in posts})
    check('completed_batch_covers_all_ten', batch['state'] != 'COMPLETED'
        or (len(methods) == 10 and not batch['not_run']))
    outcomes, local_mats = [], {}
    for job in expected:
        jid = job['id']
        if jid not in methods:
            outcomes.append(dict(job=jid, execution_status='NOT_RUN', energy_J=None)); continue
        instance, original, config, size = cases[job['case']]
        slot = folder/'slots'/(jid+'__method')
        meta = read(slot/'slot_result.json'); ticket = read(slot/'ticket.json')
        worker_path = slot/'worker/worker_result.json'
        worker = read(worker_path) if worker_path.exists() else {}
        check(jid+'/method_slot_identity', meta == methods[jid] and ticket['job'] == job
            and ticket['scientific_deadline'] == ticket['origin']+600
            and ticket['plan_sha256'] == digest(plan_path))
        check(jid+'/method_cleanup', meta.get('monitor', {}).get('cleanup_verified_observed_tree') is True)
        rawpath = slot/'worker/raw_result.json'
        if not rawpath.exists():
            observations.append(jid+': no raw method result; failure state retained, no energy inferred')
            outcomes.append(dict(job=jid, execution_status=meta['status'], energy_J=None)); continue
        raw = read(rawpath)
        check(jid+'/archived_input_identity', read(slot/'worker/method/input_instance.json') == instance
            and read(slot/'worker/method/input_config.json') == config)
        check(jid+'/600_root_and_cleanup_separation', raw['timing']['limit_s'] == 600
            and meta['total_wall_s'] >= raw['timing']['method_elapsed_s']+raw['timing'].get('cleanup_s', 0))
        safe = inspect_safe_receipt(instance, raw, 600)
        check(jid+'/final_planning_receipt_identity', safe['preserved'] == worker.get('safe', {}).get('preserved', False)
            and (not safe['preserved'] or (safe['candidate'] == worker['safe']['candidate']
                and F(safe['U_J']) == F(worker['safe']['U_J']))))
        metrics = build_completion_metrics(raw, uses_matlab=job['method'] == 'whole_milp', seconds=600)
        check(jid+'/accepted_initial_and_final_times', not metrics['rejected_SAFE_record_sources']
            and all(0 <= r['completed_at_s'] < 600 for r in metrics['complete_SAFE_receipts'])
            and (not safe['preserved'] or any(F(r['safe_upper_bound_J']) == F(safe['U_J'])
                for r in metrics['complete_SAFE_receipts'])))
        check(jid+'/no_claimed_exact_optimum', raw.get('independently_proven_optimal') is False)
        if job['method'] == 'whole_milp':
            directory = slot/'worker/method/matlab'
            if raw.get('model_complete'):
                admission = read(slot/'worker/method/full_domain_model_admission.json')
                check(jid+'/actual_model_matches_static_size', admission['state'] == 'PASS'
                    and admission['variables'] == size['predicted_total_variables']
                    and admission['rows'] == size['predicted_total_rows']
                    and admission['stage_integer_options'] == size['deadline_legal_options'])
            if (directory/'closed.json').exists():
                check(jid+'/native_cleanup', cleanup_receipt_complete(read(directory/'closed.json')))
            request_files = sorted(directory.glob('request_*.request.json'))
            check(jid+'/native_request_count', len(request_files) == raw['solver_request_attempts'])
            round_by_number = {r['request_number']: r for r in raw.get('rounds', [])}
            for request_path in request_files:
                prefix = str(request_path)[:-len('.request.json')]
                req = read(request_path); reserve = read(prefix+'.delivery_reserve.json')
                certificate = read(prefix+'.equality_certificate.json')
                identity = read(prefix+'.input.json'); admission = read(prefix+'.equality_admission.json')
                label = jid+'/'+Path(prefix).name
                check(label+'/original_root_and_fixed_30_reserve', reserve['root_method_seconds'] == 600
                    and reserve['nominal_reserve_seconds'] == 30
                    and reserve['root_absolute_deadline'] == ticket['scientific_deadline']
                    and identity['absolute_deadline'] == ticket['scientific_deadline']
                    and reserve['response_deadline_changed'] is False
                    and math.isclose(reserve['native_duration_cap_s'],
                        reserve['available_at_allocation_s']-30, rel_tol=0, abs_tol=1e-8)
                    and req['solver_max_time_s'] == req['solver_max_time_s_declared'] == reserve['native_duration_cap_s'])
                actual = Path(prefix+'.mat'); local_mats[actual.relative_to(ROOT).as_posix()] = digest(actual)
                check(label+'/actual_sent_arrays_match_exact_certificate',
                    mat_certificate_hashes(actual, admission['x0_supplied_to_native']) == certificate['derived_array_sha256'])
                check(label+'/saved_exact_representation_checks', bool(certificate['checks'])
                    and all(certificate['checks'].values())
                    and admission['certificate_checks'] == certificate['checks']
                    and all(certificate['source_array_sha256'][k] == certificate['derived_array_sha256'][k]
                        for k in ('c', 'lb', 'ub', 'intcon', 'x0')))
                response_path = Path(prefix+'.response.json'); python_path = Path(prefix+'.python.json')
                if response_path.exists():
                    response = read(response_path); options = response.get('options', {})
                    check(label+'/unchanged_native_search_settings',
                        {k: v for k, v in options.items() if k != 'MaxTime'} == plan['native_options']
                        and 0 < options['MaxTime'] <= req['solver_max_time_s'] <= req['remaining_s'] <= 600
                        and response['solver_max_time_s_allocated'] == req['solver_max_time_s']
                        and response['solver_max_time_s_used'] == options['MaxTime'])
                if python_path.exists():
                    returned = read(python_path)
                    check(label+'/unchanged_returned_round', round_by_number.get(returned['request_number']) == returned)
                    if returned.get('accepted_for_evaluation'):
                        check(label+'/accepted_return_before_deadline', returned.get('budget_valid') is True
                            and returned['solver_response_complete_at_monotonic'] < ticket['scientific_deadline'])
        post_state = None
        if jid in posts:
            postslot = folder/'slots'/(jid+'__post'); postmeta = read(postslot/'slot_result.json')
            postticket = read(postslot/'ticket.json')
            check(jid+'/one_post_60s_identity', postmeta == posts[jid] and postticket['job'] == job
                and postticket['scientific_deadline'] == postticket['origin']+60
                and postticket['method_receipt_sha256'] == digest(rawpath) and safe['preserved'])
            check(jid+'/post_cleanup', postmeta.get('monitor', {}).get('cleanup_verified_observed_tree') is True)
            postpath = postslot/'worker/post_result.json'
            if postpath.exists():
                post = read(postpath); post_state = post['state']
                pure = summarize_post(original, safe['candidate'], post['evaluation'], cutoff_s=60)
                check(jid+'/same_candidate_original80_post', post['same_candidate'] == safe['candidate']
                    and post['method_receipt_sha256'] == digest(rawpath) and post['diagnostic'] == pure
                    and post['new_method_result_accepted'] is False)
                if pure['complete_physical_evaluation']:
                    a, z = map(F, raw['evaluation']['weighted_energy_J'])
                    c, d = map(F, pure['diagnostic_weighted_energy_J'])
                    check(jid+'/full_energy_interval_overlap', max(a, c) <= min(z, d))
                check(jid+'/posterior_state_not_promoted', post_state == pure['state']
                    and (post_state != 'SAFE' or inspect_safe_receipt(original,
                        dict(safe_candidate=safe['candidate'], evaluation=post['evaluation'],
                             safe_upper_bound_J=post['evaluation'].get('safe_upper_bound_J')), 60)['preserved']))
            else:
                observations.append(jid+': no complete posterior file; retain post status '+postmeta['status'])
        outcomes.append(dict(job=jid, execution_status=meta['status'], planning_SAFE=safe['preserved'],
            energy_J=safe.get('U_J'), post_state=post_state,
            method_root_s=raw['timing']['method_elapsed_s'], cleanup_s=raw['timing'].get('cleanup_s'),
            method_process_s=meta['total_wall_s']))
    failures = [name for name, passed in checks.items() if not passed]
    return dict(state='PASS' if not failures else 'FAIL', scope='Saved archive consistency; not an external approval or mathematical optimum certificate',
        subject_commit=subject, batch_state=batch['state'], batch_error=batch.get('error'),
        check_count=len(checks), checks=checks, failures=failures, observations=observations,
        methods=outcomes, method_status_counts=dict(Counter(r['execution_status'] for r in outcomes)),
        method_attempts=batch['method_attempts'], post_attempts=batch['post_attempts'], not_run=batch['not_run'],
        source_count=len(plan['source_sha256']), original_science_source_count=len(science),
        evidence_sha256=evidence, local_only_MAT_sha256=local_mats,
        limitations=['Exact equality checks were formed during the method; archive reader checks the actually sent arrays against that certificate, without reconstructing an unarchived original matrix.',
                    'Zero prechecks refers to this declared batch ledger; no claim about unrelated machine activity.',
                    'Normal timeout, lack of improvement, and original-limit posterior overheating are research outcomes, not archive failures.'],
        new_optimization_calls=0, new_model_builds=0, new_thermal_evaluations=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit('Refusing to overwrite an existing archive review')
    result = audit(args.folder, args.plan)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('state', 'check_count', 'failures', 'method_attempts', 'post_attempts')}, ensure_ascii=False))
