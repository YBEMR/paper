"""Archive-only checks for the single auxiliary-relaxed 900 s diagnostic.

Reads existing JSON, source snapshots and exported MAT files. Never imports
the planner, constructs a model, decodes a candidate or evaluates temperature.
Writes verification.json containing evidence-consistency checks only.
"""
import argparse
import ast
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.sparse import issparse


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORMULATION = {'fix_late_options': True, 'aggregate_opp_locks': True,
               'relax_auxiliary_integrality': True}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolved(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (ROOT/path).resolve()


def construction_ast(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    # These two routines are numerical candidate acceptance/observation only.
    tree.body = [node for node in tree.body if not (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
        node.name in {'decode', 'logical_candidate_diagnostics'})]
    return ast.dump(tree, include_attributes=False)


def matrix_equal(a, b):
    if issparse(a) or issparse(b):
        if not issparse(a) or not issparse(b) or a.shape != b.shape:
            return False
        # Compare the saved sparse representation without recomputing rows.
        a, b = a.tocsc(), b.tocsc()
        return (np.array_equal(a.indptr, b.indptr) and
                np.array_equal(a.indices, b.indices) and
                np.array_equal(a.data, b.data))
    return np.array_equal(a, b)


def first_event(result, phase):
    return next((e['method_elapsed_s'] for e in result['diagnostic']['solver_progress']
                 if e.get('values', {}).get('phase') == phase), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', required=True, type=Path)
    parser.add_argument('--prior-dir', type=Path)
    args = parser.parse_args()
    folder = args.result_dir.resolve()
    old_folder = (args.prior_dir or folder.parent/'base_long_diagnostic02').resolve()
    result, old = read(folder/'result.json'), read(old_folder/'result.json')
    integrity = read(folder/'source_integrity.json')
    diagnostic, checks = result['diagnostic'], []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})

    check('one_absolute_900_second_budget', result['timing']['limit_s'] == 900)
    check('original_case_and_nonformal_scope', result['problem_id'] == 'base__R1'
          and not result['formal_comparison'] and not result['construct_only'])
    check('source_integrity', integrity['match'] and integrity['before'] == integrity['after'])
    for name, sha in integrity['after'].items():
        check('archived_source/'+name, digest(folder/'source_snapshot'/name) == sha)
    check('source_hash_manifest', read(folder/'source_hashes.json') == integrity['after'])
    check('original_config_identical', read(folder/'input_config.json') == read(old_folder/'input_config.json'))
    check('original_instance_identical', read(folder/'input_instance.json') == read(old_folder/'input_instance.json'))
    unchanged = ['inputs.py', 'schedules.py', 'thermal.py', 'milp_coefficients.py',
                 'interval.py', 'config_v01.json', 'solve_model.m', 'matlab_bridge.py', 'timing.py']
    for name in unchanged:
        check('unchanged_physics_and_solver/'+name,
              digest(folder/'source_snapshot'/name) == digest(old_folder/'source_snapshot'/name))
    check('milp_construction_and_physical_feedback_ast_unchanged',
          construction_ast(folder/'source_snapshot/milp.py') ==
          construction_ast(old_folder/'source_snapshot/milp.py'))

    claims = [(path, read(path)) for path in folder.parent.glob('*/original_run_claim.json')]
    claims = [(path, claim) for path, claim in claims if resolved(claim['out']) == folder]
    check('exactly_one_claim_for_this_invocation', len(claims) == 1)
    if len(claims) == 1:
        path, claim = claims[0]
        check('claim_protocol', claim['seconds'] == 900 and claim['retries'] == 0
              and claim['problem_id'] == 'base__R1' and not claim['formal_comparison'])
        check('claim_sources_and_formulation', claim['source_hashes'] == integrity['before']
              and claim['formulation'] == FORMULATION)
        for label, record_path, script in (
            ('live', path.parent/'checks.json', 'precheck_diagnostic.py'),
            ('auxiliary', resolved(claim['auxiliary_precheck']), 'run_auxiliary_precheck.py')):
            record = read(record_path)
            check('precheck_passed/'+label, record['all_passed'])
            check('precheck_matches/'+label, record['formulation'] == FORMULATION and
                  record['source_hashes'] == integrity['before'])
            check('precheck_script_current/'+label,
                  record['precheck_source_sha256'] == digest(HERE/script))
        prerequisites = path.parent/'original_prerequisites.json'
        if prerequisites.exists():
            prereq = read(prerequisites)
            check('prerequisites_passed', prereq['all_prerequisites_passed'])
            check('prerequisite_sources', prereq['source_hashes'] == integrity['before'])
            for name, record in prereq['records'].items():
                check('prerequisite_archive/'+name, digest(resolved(record['path'])) == record['sha256'])

    summary = result['model_summary']
    check('requested_formulation', summary['formulation'] == FORMULATION)
    expected = {'options': 6422, 'variables': 91844, 'binary_variables': 6422,
                'logical_binary_variables': 75825, 'deadline_fixed_options': 4741}
    for key, value in expected.items():
        check('model_count/'+key, summary[key] == value)
    check('initial_model_row_count', result['construction']['rows'] == 613164)
    check('initial_model_nonzeros', result['construction']['nonzeros_in_rows'] == 7771874)
    check('events_and_coefficients_unchanged', summary['events_per_scene'] == old['model_summary']['events_per_scene']
          and summary['coefficient_sets'] == old['model_summary']['coefficient_sets'])

    first_mat = folder/'matlab/request_000001.mat'
    old_mat = old_folder/'matlab/request_000001.mat'
    current, previous = loadmat(first_mat), loadmat(old_mat)
    check('saved_matrix_shape', current['A'].shape == (613164, 91844))
    check('saved_matrix_nonzeros', current['A'].nnz == 7771874)
    for key in ('A', 'b', 'Aeq', 'beq', 'c', 'lb', 'ub'):
        check('saved_export_identical_except_intcon/'+key, matrix_equal(current[key], previous[key]))
    check('saved_integer_indices_exactly_all_options',
          np.array_equal(current['intcon'].reshape(-1), np.arange(1, 6423)))
    check('prior_integer_count', previous['intcon'].size == 75825)
    del current, previous

    request_paths = sorted((folder/'matlab').glob('*.request.json'))
    check('requests_accounted', len(request_paths) == result['solver_request_attempts'])
    deadlines, available, raw_outputs = [], [], []
    old_response = read(old_folder/'matlab/request_000001.response.json')
    for path in request_paths:
        prefix = path.name.removesuffix('.request.json')
        req = read(path)
        info = read(path.with_name(prefix+'.input.json'))
        deadlines.append(info['absolute_deadline'])
        available.append(req['remaining_s'])
        check('remaining_budget/'+prefix, info['method_deadline_bound'] and
              0 < req['remaining_s'] <= info['case_budget_at_entry_s'] <= 900)
        response = path.with_name(prefix+'.response.json')
        if response.exists():
            raw = read(response)
            options = raw.get('options', {})
            if options:
                check('solver_options/'+prefix,
                      {k: v for k, v in options.items() if k != 'MaxTime'} ==
                      {k: v for k, v in old_response['options'].items() if k != 'MaxTime'})
                check('solver_max_time_uses_remainder/'+prefix,
                      0 <= options['MaxTime'] <= req['remaining_s'])
            raw_outputs.append({'request': prefix, 'status': raw.get('status'),
                'exitflag': raw.get('exitflag'), 'output': raw.get('output'),
                'returned_vector_length': len(raw.get('x') or []),
                'scope': 'native archive only; no post-budget candidate acceptance'})
    check('one_deadline_across_rounds', len(set(deadlines)) == 1)
    check('remaining_budget_never_replenished', all(b <= a for a, b in zip(available, available[1:])))
    check('late_rounds_not_accepted', all(not r.get('accepted_for_evaluation') or r.get('budget_valid')
          for r in result['rounds']))
    check('received_events_in_budget', all(0 <= e['method_elapsed_s'] < 900
          for e in diagnostic['solver_progress']))

    records = diagnostic['decode_records']
    legal = [r for r in records if r['state'] == 'LEGAL' and r['within_budget']]
    check('decode_receipts_accounted', len(records) == diagnostic['candidate_receipts'])
    check('decode_timestamps_and_labels', all(
        r['within_budget'] == (r['completed_at_s'] < 900) and
        (r['state'] != 'LEGAL' or r['within_budget']) for r in records))
    check('first_legal_time', diagnostic['first_legal_candidate_s'] ==
          (min(r['completed_at_s'] for r in legal) if legal else None))
    check('first_candidate_time', diagnostic['first_candidate_received_s'] ==
          (min(r['received_at_s'] for r in records) if records else None))
    check('decode_rejection_count', diagnostic['decode_rejections'] ==
          sum(r['state'] == 'REJECTED' and r['within_budget'] for r in records))
    for index, receipt in enumerate(records):
        logical = receipt.get('logical_values', {})
        if logical.get('vector_valid'):
            families = logical['families']
            check(f'logical_counts/{index}', set(families) == {'y', 'x', 'rho', 'J', 'w'} and
                  sum(f['count'] for f in families.values()) == 75825 and families['y']['count'] == 6422)
            check(f'original_integer_tolerance/{index}', logical['integer_tolerance'] == 1e-6)
        if receipt['state'] == 'LEGAL':
            check(f'legal_logical_membership/{index}', logical.get('accepted') is True)
    evaluations = diagnostic['evaluations']
    legal_sources = {r['source'] for r in legal}
    check('evaluations_follow_in_budget_legal_receipts',
          all(r['source'] in legal_sources for r in evaluations))
    safe = [r for r in evaluations if r['accepted_safe']]
    check('safe_receipts_complete_and_timely', all(
        r['evaluation']['state'] == 'SAFE' and r['evaluation']['rankable_energy'] and
        r['evaluation']['completed_at_elapsed_s'] < 900 for r in safe))
    check('first_safe_time', diagnostic['first_safe_receipt_s'] ==
          (min(r['evaluation']['completed_at_elapsed_s'] for r in safe) if safe else None))
    check('safe_U_from_receipts_only', (result['state'] == 'SAFE' and
          Fraction(result['safe_upper_bound_J']) == min(Fraction(r['evaluation']['safe_upper_bound_J']) for r in safe)
          and any(result['safe_candidate'] == r['candidate'] for r in safe)) if safe else
          (result['state'] == 'UNRESOLVED' and result['safe_upper_bound_J'] is None and result['safe_candidate'] is None))
    check('no_independent_proof_from_solver_status', not result['independently_proven_optimal'] and
          not result['independently_proven_infeasible'] and not diagnostic['solver_bounds_independently_certified'])
    check('feedback_only_before_deadline', all(f['within_budget'] and f['completed_at_elapsed_s'] < 900
          for f in result['feedback']))
    closed = read(folder/'matlab/closed.json')
    check('cleanup_not_new_evidence', closed['cleanup_not_available_for_new_evidence'])
    comparison = {'prior_solver_entered_s': old['diagnostic']['solver_entered_received_s'],
        'solver_entered_s': diagnostic['solver_entered_received_s'],
        'prior_rootlp_s': first_event(old, 'rootlp'), 'rootlp_s': first_event(result, 'rootlp'),
        'prior_cutgen_s': first_event(old, 'cutgen'), 'cutgen_s': first_event(result, 'cutgen'),
        'first_received_s': diagnostic['first_candidate_received_s'],
        'first_legal_s': diagnostic['first_legal_candidate_s'], 'first_safe_s': diagnostic['first_safe_receipt_s'],
        'candidate_receipts': diagnostic['candidate_receipts'], 'decode_rejections': diagnostic['decode_rejections'],
        'safe_receipts': len(safe), 'safe_U_J': result['safe_upper_bound_J'],
        'scope': 'single-call diagnostic; no statistical timing or general speedup claim'}
    output = {'all_passed': all(c['passed'] for c in checks), 'passed': sum(c['passed'] for c in checks),
        'total': len(checks), 'checks': checks, 'comparison': comparison, 'raw_worker_outputs': raw_outputs,
        'verification_script_sha256': digest(Path(__file__)),
        'scope': 'existing archives only; no construction, solve, decode or thermal evaluation'}
    (folder/'verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: output[k] for k in ('all_passed', 'passed', 'total', 'comparison')}, ensure_ascii=False, indent=2))
    if not output['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
