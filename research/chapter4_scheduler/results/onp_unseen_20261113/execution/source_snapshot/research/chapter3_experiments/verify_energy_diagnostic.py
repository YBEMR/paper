"""Read-only evidence checks for the energy-strengthened 900 s diagnostic.

Only reads completed archives and exported MAT files, then writes one local
verification receipt. Does not import any planner, construct/solve a model,
decode a candidate, evaluate temperature, or accept post-budget evidence.
The added original-scale cuts are not individually certified by this script;
their validity relies on K87's derivation, small-domain certificates and an
unchanged mathematical source file.
"""
import argparse
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
               'relax_auxiliary_integrality': True, 'energy_lower_bounds': True}
OLD_ROWS, NEW_ROWS, VARIABLES, OPTIONS = 613164, 614943, 91844, 6422
K87_MILP_SHA256 = 'f53f02f7e64ba04d0d8c8953ab3f8a47f4109fc0753e97d3d9592aaeccedcd49'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolved(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (ROOT/path).resolve()


def matrix_equal(a, b):
    if issparse(a) or issparse(b):
        if not issparse(a) or not issparse(b) or a.shape != b.shape:
            return False
        a, b = a.tocsc(), b.tocsc()
        return (np.array_equal(a.indptr, b.indptr) and
                np.array_equal(a.indices, b.indices) and
                np.array_equal(a.data, b.data))
    return np.array_equal(a, b)


def phase_events(result, phase):
    return [{'request': e.get('request'), 'received_at_s': e['method_elapsed_s'],
             'worker_request_wall_seconds': e.get('request_wall_seconds'),
             'values': e.get('values', {}), 'evidence': 'solver-reported'}
            for e in result['diagnostic']['solver_progress']
            if e.get('values', {}).get('phase') == phase]


def first_phase_time(result, phase):
    events = phase_events(result, phase)
    return events[0]['received_at_s'] if events else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', required=True, type=Path)
    parser.add_argument('--prior-dir', type=Path)
    args = parser.parse_args()
    folder = args.result_dir.resolve()
    old_folder = (args.prior_dir or folder.parent/'base_long_diagnostic03').resolve()
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
                 'interval.py', 'config_v01.json', 'solve_model.m', 'matlab_bridge.py',
                 'timing.py', 'diagnostic_search.py']
    for name in unchanged:
        check('unchanged_physics_evaluator_and_solver/'+name,
              digest(folder/'source_snapshot'/name) == digest(old_folder/'source_snapshot'/name))
    check('mathematical_source_matches_K87_prechecked_version',
          digest(folder/'source_snapshot/milp.py') == K87_MILP_SHA256)

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
        energy = claim.get('energy_lower_bound_precheck')
        check('energy_precheck_record_present', isinstance(energy, dict))
        if isinstance(energy, dict):
            energy_path = resolved(energy['path'])
            energy_record = read(energy_path)
            check('energy_precheck_archive_hash', digest(energy_path) == energy['sha256'])
            check('energy_precheck_passed', energy_record.get('status') == 'PASS'
                  and energy_record.get('passed') == energy_record.get('total')
                  and len(energy_record.get('checks', [])) == energy_record.get('total')
                  and all(c.get('status') == 'PASS' for c in energy_record.get('checks', []))
                  and energy_record.get('matlab_small_domain_requested') is True)
            required_math = {'config_v01.json', 'inputs.py', 'schedules.py', 'thermal.py',
                             'milp.py', 'milp_coefficients.py', 'matlab_bridge.py',
                             'solve_model.m', 'interval.py'}
            covered = set()
            for source, sha in energy.get('checked_sources', {}).items():
                check('energy_precheck_manifest/'+source,
                      energy_record.get('source_sha256', {}).get(source) == sha)
                name = Path(source).name
                if name in integrity['before']:
                    check('energy_precheck_runtime_source/'+name, integrity['before'][name] == sha)
                    covered.add(name)
            check('energy_precheck_all_mathematical_sources_covered', required_math <= covered)
        prerequisites = path.parent/'original_prerequisites.json'
        if prerequisites.exists():
            prereq = read(prerequisites)
            check('prerequisites_passed', prereq['all_prerequisites_passed'])
            check('prerequisite_sources', prereq['source_hashes'] == integrity['before'])
            check('prerequisite_formulation', prereq.get('formulation') == FORMULATION)
            for name, record in prereq['records'].items():
                check('prerequisite_archive/'+name, digest(resolved(record['path'])) == record['sha256'])
                check('prerequisite_pass_record/'+name, record.get('passed') is True)

    summary = result['model_summary']
    check('requested_formulation', summary['formulation'] == FORMULATION)
    expected = {'options': OPTIONS, 'variables': VARIABLES, 'binary_variables': OPTIONS,
                'logical_binary_variables': 75825, 'deadline_fixed_options': 4741}
    for key, value in expected.items():
        check('model_count/'+key, summary[key] == value)
    check('initial_model_row_count', result['construction']['rows'] == NEW_ROWS)
    segments = sum(n-1 for n in summary['events_per_scene'].values())
    check('one_added_energy_row_per_segment', NEW_ROWS-OLD_ROWS == segments == 1779)
    check('events_and_coefficients_unchanged', summary['events_per_scene'] == old['model_summary']['events_per_scene']
          and summary['coefficient_sets'] == old['model_summary']['coefficient_sets'])

    current = loadmat(folder/'matlab/request_000001.mat')
    previous = loadmat(old_folder/'matlab/request_000001.mat')
    check('saved_initial_matrix_shape', current['A'].shape == (NEW_ROWS, VARIABLES))
    check('prior_initial_matrix_shape', previous['A'].shape == (OLD_ROWS, VARIABLES))
    check('saved_original_A_prefix_identical', matrix_equal(current['A'][:OLD_ROWS, :], previous['A']))
    check('saved_original_b_prefix_identical', np.array_equal(current['b'].reshape(-1)[:OLD_ROWS], previous['b'].reshape(-1)))
    check('saved_added_matrix_rows_nonempty', np.all(np.diff(current['A'][OLD_ROWS:, :].tocsr().indptr) > 0))
    for key in ('Aeq', 'beq', 'c', 'lb', 'ub', 'intcon'):
        check('saved_export_unchanged/'+key, matrix_equal(current[key], previous[key]))
    check('saved_integer_indices_exactly_all_options',
          np.array_equal(current['intcon'].reshape(-1), np.arange(1, OPTIONS+1)))
    check('construction_nonzeros_match_export', result['construction']['nonzeros_in_rows'] == current['A'].nnz)
    initial_nnz = int(current['A'].nnz)
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
                check('solver_max_time_uses_remainder/'+prefix, 0 <= options['MaxTime'] <= req['remaining_s'])
            raw_outputs.append({'request': prefix, 'status': raw.get('status'),
                'exitflag': raw.get('exitflag'), 'output': raw.get('output'),
                'returned_vector_length': len(raw.get('x') or []),
                'scope': 'native archive only; no post-budget candidate acceptance'})
    check('one_deadline_across_rounds', len(set(deadlines)) == 1)
    check('remaining_budget_never_replenished', all(b <= a for a, b in zip(available, available[1:])))
    check('late_rounds_not_accepted', all(not r.get('accepted_for_evaluation') or r.get('budget_valid')
          for r in result['rounds']))
    check('received_events_in_budget', all(0 <= e['method_elapsed_s'] < 900 for e in diagnostic['solver_progress']))
    check('progress_bounds_labeled_solver_reported', all(e.get('evidence') == 'solver-reported'
          for e in diagnostic['solver_progress']))

    records = diagnostic['decode_records']
    legal = [r for r in records if r['state'] == 'LEGAL' and r['within_budget']]
    check('decode_receipts_accounted', len(records) == diagnostic['candidate_receipts'])
    check('decode_timestamps_and_labels', all(r['received_at_s'] < 900
          and r['within_budget'] == (r['completed_at_s'] < 900)
          and (r['state'] != 'LEGAL' or r['within_budget']) for r in records))
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
                  sum(f['count'] for f in families.values()) == 75825 and families['y']['count'] == OPTIONS)
            check(f'original_integer_tolerance/{index}', logical['integer_tolerance'] == 1e-6)
        if receipt['state'] == 'LEGAL':
            check(f'legal_logical_membership/{index}', logical.get('accepted') is True)
    evaluations = diagnostic['evaluations']
    legal_sources = {r['source'] for r in legal}
    check('evaluations_follow_in_budget_legal_receipts', all(r['source'] in legal_sources for r in evaluations))
    safe = [r for r in evaluations if r['accepted_safe']]
    check('safe_receipts_complete_and_timely', all(r['evaluation']['state'] == 'SAFE'
          and r['evaluation']['rankable_energy']
          and r['evaluation']['completed_at_elapsed_s'] < 900 for r in safe))
    check('first_safe_time', diagnostic['first_safe_receipt_s'] ==
          (min(r['evaluation']['completed_at_elapsed_s'] for r in safe) if safe else None))
    check('safe_U_from_receipts_only', (result['state'] == 'SAFE' and
          Fraction(result['safe_upper_bound_J']) == min(Fraction(r['evaluation']['safe_upper_bound_J']) for r in safe)
          and any(result['safe_candidate'] == r['candidate'] and
                  Fraction(result['safe_upper_bound_J']) == Fraction(r['evaluation']['safe_upper_bound_J'])
                  and result['evaluation'] == r['evaluation'] for r in safe)) if safe else
          (result['state'] == 'UNRESOLVED' and result['safe_upper_bound_J'] is None and result['safe_candidate'] is None))
    check('no_independent_proof_from_solver_status', not result['independently_proven_optimal']
          and not result['independently_proven_infeasible'] and not diagnostic['solver_bounds_independently_certified'])
    check('feedback_only_before_deadline', all(f['within_budget'] and f['completed_at_elapsed_s'] < 900
          for f in result['feedback']))
    closed = read(folder/'matlab/closed.json')
    check('cleanup_not_new_evidence', closed['cleanup_not_available_for_new_evidence'])

    comparison = {'prior_solver_entered_s': old['diagnostic']['solver_entered_received_s'],
        'solver_entered_s': diagnostic['solver_entered_received_s'],
        'prior_rootlp_s': first_phase_time(old, 'rootlp'), 'rootlp_s': first_phase_time(result, 'rootlp'),
        'prior_rootlp_events_solver_reported': phase_events(old, 'rootlp'),
        'rootlp_events_solver_reported': phase_events(result, 'rootlp'),
        'prior_cutgen_s': first_phase_time(old, 'cutgen'), 'cutgen_s': first_phase_time(result, 'cutgen'),
        'first_received_s': diagnostic['first_candidate_received_s'],
        'first_legal_s': diagnostic['first_legal_candidate_s'], 'first_safe_s': diagnostic['first_safe_receipt_s'],
        'candidate_receipts': diagnostic['candidate_receipts'], 'decode_rejections': diagnostic['decode_rejections'],
        'safe_receipts': len(safe), 'safe_U_J': result['safe_upper_bound_J'],
        'initial_rows': NEW_ROWS, 'initial_nonzeros': initial_nnz,
        'scope': 'single-call diagnostic; rootlp fval is solver-reported LP progress, not a certified bound or incumbent; no statistical timing or general speedup claim'}
    output = {'all_passed': all(c['passed'] for c in checks), 'passed': sum(c['passed'] for c in checks),
        'total': len(checks), 'checks': checks, 'comparison': comparison, 'raw_worker_outputs': raw_outputs,
        'verification_script_sha256': digest(Path(__file__)),
        'added_cut_proof_scope': 'K87 derivation and small-domain certificates plus identical milp.py; no original-scale per-cut certificate audit was performed',
        'scope': 'existing archives only; no construction, solve, decode or thermal evaluation; writes verification.json only'}
    (folder/'verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: output[k] for k in ('all_passed', 'passed', 'total', 'comparison')}, ensure_ascii=False, indent=2))
    if not output['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
