"""Read archived data only. No builder, evaluator, solver, or experiment runner imports.

Usage: python audit_saved.py WORKSPACE NEW_OUTPUT_DIRECTORY
The output directory must not already exist. Requires scipy for MAT inspection.
"""
import hashlib
import json
from pathlib import Path
import sys
from scipy.io import loadmat
from scipy.sparse import issparse


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, data):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def inspect_mat(path):
    keys = ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon', 'x0')
    data = loadmat(path, variable_names=keys)
    sparse_bytes = lambda a: a.data.nbytes + a.indices.nbytes + a.indptr.nbytes
    return dict(variables=int(data['c'].size), inequalities=int(data['A'].shape[0]),
                equalities=int(data['Aeq'].shape[0]), integer_variables=int(data['intcon'].size),
                A_nnz=int(data['A'].nnz), Aeq_nnz=int(data['Aeq'].nnz),
                stored_array_buffer_bytes=int(sum(sparse_bytes(data[k]) if issparse(data[k]) else data[k].nbytes for k in keys)),
                mat_file_bytes=path.stat().st_size, sha256=sha(path))


def main():
    workspace = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = workspace / 'work/stable_expression'
    oldplan = read(base / 'entry_plan.json')
    receipt = read(base / 'entry_runs/off1/receipt.json')
    native = read(base / 'entry_runs/off1/native_receipt.json')
    closed = read(base / 'entry_runs/off1/matlab/closed.json')
    full = read(base / 'full/summary.json')
    stage = read(base / 'stage_summary.json')
    post = read(base / 'post_entry_audit.json')
    bindings = {}
    for name, expected in oldplan['frozen_files'].items():
        path = Path(name)
        actual = sha(path)
        if actual != expected:
            raise ValueError('Historical frozen file drift: ' + name)
        bindings[path.relative_to(workspace).as_posix()] = actual
    if sha(base / 'entry_plan.json') != '8d908013e9f6ef2cb87ae2ba31b4e0b7a68818218805e7858ed9fd785e4eb0c4':
        raise ValueError('Historical plan drift')
    if native['options'] != oldplan['native_options']:
        raise ValueError('Native options mismatch')
    for name, expected in full['files'].items():
        if sha(base / 'full' / name) != expected:
            raise ValueError('Saved full input drift: ' + name)
    archive = workspace / 'work/publish_repo/research/chapter3_stable_expression_20261112/R1_stable_expression_evidence.zip'
    expected_archive = 'd332bfb34c7a40e92cb4328a655c60ec88be0f377f0a8623820eb1f71e29557f'
    if sha(archive) != expected_archive:
        raise ValueError('Published evidence archive drift')
    evidence_names = ['entry_plan.json', 'entry_runs/off1/receipt.json', 'entry_runs/off1/native_receipt.json',
                      'entry_runs/off1/controller.json', 'entry_runs/off1/matlab/closed.json',
                      'stage_summary.json', 'post_entry_audit.json', 'full/summary.json', 'small_run/results.json']
    for name in evidence_names:
        path = base / name
        bindings[path.relative_to(workspace).as_posix()] = sha(path)
    bindings[archive.relative_to(workspace).as_posix()] = sha(archive)
    save(out / 'source_bindings.json', bindings)
    matrices = {arm: {rep: inspect_mat(base / 'full' / (arm + suffix))
                      for rep, suffix in [('original', '.original.mat'), ('complement', '.mat')]}
                for arm in ['off', 'on']}
    for arm, pair in matrices.items():
        pair['delta'] = {k: pair['complement'][k] - pair['original'][k]
                         for k in ['variables', 'inequalities', 'equalities', 'integer_variables', 'A_nnz', 'Aeq_nnz', 'stored_array_buffer_bytes']}
    audit = dict(
        subject_commit='12bd7bdf507d9c5f2ccb0aac0f41efad702bdd3a',
        historical_frozen_files_verified=len(oldplan['frozen_files']),
        archived_full_files_verified=len(full['files']), archived_zip_sha256=expected_archive,
        matrices=matrices,
        cost=dict(full_OFF_ON_static_preparation_combined_s=full['elapsed_s'],
                  per_arm_preparation_s=None, preparation_proof_recheck_s=None,
                  small_validation_s=read(base / 'small_run/results.json')['elapsed_s'],
                  method_elapsed_s=receipt['method_elapsed_s'], worker_total_s=receipt['total_elapsed_s'],
                  controller_total_s=read(base / 'entry_runs/off1/controller.json')['wall_s'],
                  named_exclusive_phases_s=receipt['timing']['phases_exclusive_s'],
                  unattributed_method_s=receipt['timing']['unattributed_s'],
                  native_nested_phases_s=native['phase_seconds'],
                  cleanup_observed_s=closed['cleanup_wall_seconds'],
                  post_method_worker_overhead_s=receipt['total_elapsed_s']-receipt['method_elapsed_s'],
                  peak_process_memory_bytes=None,
                  accounting='Nested native phases must not be added to solver_wait_and_response_read. Static preparation was outside this saved-matrix diagnostic. Buffer sizes are SciPy loaded-array storage, not peak RAM; differently compressed MAT file sizes do not measure model memory.'),
        failure=dict(classification='ORDINARY_NATIVE_TIME_LIMIT_WITH_NO_RETURNED_VECTOR',
                     raw_status=native['status'], exitflag=native['exitflag'], message=native['output']['message'],
                     returned_vector_present=bool(native['x']), final_numfeaspoints=native['output']['numfeaspoints'],
                     callback_numfeaspoints=[dict(state=c['state'], count=c['values']['numfeaspoints'], vector_present=bool(c['x'])) for c in native['callbacks']],
                     callback_counter_discrepancy_source='UNKNOWN',
                     finite_bound_observed=receipt['last_reported_bound'] is not None,
                     root_or_later_observed=receipt['root_or_later_first'] is not None,
                     root_LP_actual_completion='UNKNOWN',
                     initial_SAFE=receipt['checks']['initial_complete_SAFE'],
                     solver_returned_SAFE=None,
                     exact_native_options_match=True, actual_transport_match=post['rows'][0]['actual_sent_arrays_match'],
                     process_cleanup_verified=closed['observed_tree_verified_terminated'],
                     wrapper_error=receipt['error']['message'],
                     wrapper_error_is_native_exception=False,
                     skipped_checks_are_not_observed_violations=True,
                     omitted_slots=stage['omitted_slots']),
        conclusion=dict(exact_projection_equivalence='VERIFIED_WITH_ARCHIVED_CERTIFICATES',
                        physical_small_fixture='VERIFIED_IN_DECLARED_ENUMERABLE_DOMAIN',
                        numerical_solver_benefit='UNVERIFIED', formal_default_representation=False,
                        numerical_instability_cause='UNKNOWN', same_OFF_retry_permitted=False),
        current_work=dict(native_solver_calls=0, thermal_evaluations=0, model_builds=0, expression_changes=0),
        source_bindings_sha256=sha(out / 'source_bindings.json'))
    save(out / 'cost_failure_audit.json', audit)
    proposal = dict(
        protocol='R1-ON-only-saved-matrix-diagnostic-proposal-v1', status='PREPARED_NOT_AUTHORIZED_NOT_EXECUTED',
        execution_authorized=False, executable_entrypoint=None,
        implementation_status='Protocol and saved inputs bound; a separate one-shot adapter must be frozen and pure-tested before execution approval. The historical OFF-first runner must not be invoked or edited.',
        subject_commit=audit['subject_commit'], representation='complement_gate_split_constant_v1', arm='ON',
        slots=1, maximum_native_calls=1, retries=0, fallback_calls=0, model_builds=0,
        total_window_s=300, native_MaxTime_s=240, watchdog_s=380,
        prior_unused_slots_reused=False, OFF_precondition=False, formal_performance_comparison=False,
        native_options=oldplan['native_options'], native_options_null_encoding='MaxFeasiblePoints and ObjectiveCutOff null preserve the archived Inf serialization; do not assign MATLAB [] or change the setting.',
        native_option_identity_rule='Compare the entire actual option receipt, including defaults, to the archived OFF receipt. Preserve the original solve_model.m/worker and MATLAB R2023b.',
        input_identity=oldplan['input_sha256'], initial_candidate_identity=oldplan['initial_candidate_sha256'],
        source_bindings_sha256=sha(out / 'source_bindings.json'),
        ON_mat_sha256=matrices['on']['complement']['sha256'], original_ON_mat_sha256=matrices['on']['original']['sha256'],
        initial_policy='Saved x0 and saved common schedule. Refresh complete physical SAFE once inside the window; no repaired x0, fixed integer schedule, new initialization search, or model reconstruction.',
        candidate_policy='Callbacks are recorded unchanged, including vectors and receipt times. At most one final returned candidate gets new/original row admission, independent decode, and complete physical evaluation inside the same deadline. Do not discard all other progress just because exitflag is 0 or a final vector is absent.',
        physical_evaluation_limit=2,
        metrics=['root LP entry/explicit completion evidence separately', 'available native integer vectors and identities',
                 'returned vector admitted by transformed and original rows', 'full physical SAFE',
                 'same initial / different schedule', 'strict energy interval improvement',
                 'finite solver-reported lower bound with timestamp and units', 'native status and both counter values',
                 'all elapsed times and cleanup integrity'],
        bound_policy='Check finite value, source/timestamp/objective identity and consistency with a verified feasible objective; conflicting bounds are invalid. Native-only bounds are solver-reported, not exact certificates. Do not use the full physical energy interval as a MILP objective certificate without accounting for their relationship.',
        root_policy='A rootlp phase label only proves stage entry; require an explicit completion receipt or a later solver phase before claiming root LP completed. Missing callbacks mean unobserved, not proof that no internal work occurred.',
        stop_rule='After the single call, terminate whether there is progress or not; no retry, retuning, replacement sample, OFF repeat, or automatic A/B/C launch.',
        deadline_policy='300 seconds starts in the parent before imports/input reads and ends scientific evidence credit. Cleanup may continue to the watchdog but adds no evidence. Insufficient time to honor the fixed native cap causes a no-call stop; do not shorten MaxTime. Validate source and transport before outcome classification, even on timeout.',
        gate_policy='Input/source drift, invalid transport, unresolved process ownership, or validation correctness errors invalidate the affected evidence. Ordinary timeout is a reportable diagnostic outcome. Every dimension may remain UNKNOWN; no all-or-nothing progress gate.',
        interpretation='A successful ON diagnostic neither demonstrates pruning speedup against the earlier OFF nor proves end-to-end affordability or general numerical stability.')
    save(out / 'ON_diagnostic_proposal.json', proposal)
    print(json.dumps(dict(audit_passed=True, matrices=matrices,
                         historical_frozen_files_verified=len(oldplan['frozen_files']),
                         native_calls=0, proposal_sha256=sha(out / 'ON_diagnostic_proposal.json')), ensure_ascii=False))


if __name__ == '__main__':
    main()
