"""Read-only archive checks; no model build, decoding, solve or heat evaluation.

Checks reported receipts and their identities, not independently recomputed
MILP residuals or thermal trajectories. The original evaluator owns SAFE.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def identity(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str).encode()).hexdigest()


def verify(folder):
    folder = Path(folder)
    result = read(folder/'result.json')
    instance = read(folder/'input_instance.json')
    integrity = read(folder/'source_integrity.json')
    old = folder.parent/'base_long_diagnostic04'
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})

    check('original_input_config_bytes_match_K88',
          sha(folder/'input_config.json') == sha(old/'input_config.json'))
    check('original_input_instance_bytes_match_K88',
          sha(folder/'input_instance.json') == sha(old/'input_instance.json'))
    check('complete_model_summary_matches_K88',
          result['model_summary'] == read(old/'result.json')['model_summary'])
    check('source_before_after_match', integrity['before'] == integrity['after'] and integrity['unchanged'])
    for name, digest in integrity['before'].items():
        check('source_snapshot/'+name, sha(folder/'source_snapshot'/name) == digest)
    prerequisite = read(result['prerequisites']['entry']['path'])
    check('entry_precheck_36_passed', prerequisite['passed'] is True and prerequisite['count'] == 36
          and all(row['passed'] for row in prerequisite['checks']))
    claim = read(integrity['original_claim'])
    check('one_call_protocol_180_no_solver', claim['seconds'] == 180
          and claim['problem_id'] == 'base__R1' and claim['retries'] == 0
          and claim['integer_solver_calls'] == 0)
    check('no_actual_solver_or_MATLAB_acceptance_claim',
          result['solver_request_attempts'] == 0 and result['integer_solver_entered'] is False
          and result['matlab_actual_acceptance'] == 'NOT_TESTED')
    check('method_completion_inside_declared_budget',
          result['timing']['method_elapsed_s'] < result['timing']['limit_s'] == 180)
    check('safe_and_point_ready_separate_status', result['state'] == 'SAFE' and result['point_ready'] is True
          and result['reason'] == 'SAFE_POINT_READY_NUMERICAL_ONLY')
    evaluation = result['evaluation']
    check('SAFE_receipt_input_and_candidate_identity', evaluation['evidence_identity'] == {
        'input_sha256': identity(instance), 'candidate_sha256': identity(result['safe_candidate'])})
    check('SAFE_receipt_completed_in_budget',
          evaluation['completed_at_elapsed_s'] < 180 and evaluation['rankable_energy'] is True
          and evaluation['state'] == 'SAFE' and not evaluation['violations'])
    weighted = [F(0), F(0)]
    for scene in instance['scenarios']:
        sid = scene['id']; receipt = evaluation['scenes'][sid]
        check(sid+'/full_window_including_idle_tail', receipt['complete'] is True
              and receipt['state'] == 'SAFE'
              and F(receipt['covered_until_s']) == F(instance['settings']['window_ms'])/1000)
        check(sid+'/reported_peaks_below_limits', all(
            F(receipt['peaks_degC'][node][1]) <= F(limit) for node, limit in zip(
                instance['platform']['node_order'], scene['maximum_temperature_degC'])))
        done = evaluation['legality']['scenes'][sid]['request_completion_ms']
        check(sid+'/reported_request_deadlines', all(
            F(done[request['id']]) <= F(request['deadline_ms']) for request in scene['requests']))
        for endpoint in (0, 1):
            weighted[endpoint] += F(scene['weight'])*F(receipt['energy_J'][endpoint])
    check('weighted_full_energy_matches_scene_receipts',
          weighted == list(map(F, evaluation['weighted_energy_J'])))
    check('upper_bound_is_energy_interval_upper',
          F(result['safe_upper_bound_J']) == weighted[1])
    vector_path = folder/'initial_point_vector.json'
    vector = read(vector_path); metadata = result['x0_metadata']
    check('full_vector_length_and_finiteness', len(vector) == metadata['length']
          == result['model_summary']['variables'] == 91844 and all(math.isfinite(v) for v in vector))
    check('vector_archive_identity', sha(vector_path) == metadata['archive_sha256'])
    numerical = metadata['numerical_acceptance']
    check('reported_numerical_row_acceptance_without_repair', numerical['accepted_numerically'] is True
          and numerical['rounding_or_repair_performed'] is False
          and all(numerical[key] <= 1e-9 for key in ['inequality_violation',
                  'equality_violation', 'lower_bound_violation', 'upper_bound_violation'])
          and numerical['integer_violation'] <= 1e-6 and metadata['completed_at_s'] < 180)
    check('no_optimality_infeasibility_or_performance_claim',
          result['independently_proven_optimal'] is False
          and result['independently_proven_infeasible'] is False
          and result['formal_comparison'] is False)
    report = {'passed': all(row['passed'] for row in checks), 'count': len(checks),
              'checks': checks, 'verification_source_sha256': sha(__file__),
              'scope': 'read-only archive and reported-receipt consistency; no new heat/row calculation'}
    (folder/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'count': len(checks)}, ensure_ascii=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.result_dir)['passed'] else 1)
