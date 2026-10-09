"""Read-only K.34 evidence audit; no evaluator, simulation or planner imports.

Print deterministic JSON. --verify FILE compares it with a saved consolidation.
All interval comparisons use exact rationals parsed from the stored decimals.
"""
import argparse
import hashlib
import json
from fractions import Fraction as Q
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = HERE / 'results' / 'diagnostic01'
PULSE = ROOT / 'research' / 'thermal_pulse_certificate'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    checks, sources = [], {}

    def check(name, condition):
        checks.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise ValueError(name)

    def read(path):
        sources[path.relative_to(ROOT).as_posix()] = sha(path)
        return load(path)

    manifest = read(OLD / 'artifact_manifest.json')
    check('33_original_artifacts_unchanged', len(manifest) == 33 and all(
        sha(OLD / p) == h for p, h in manifest.items()))
    integrity = read(PULSE / 'historical_integrity.json')
    check('47_historical_files_unchanged', len(integrity['files']) == 47 and all(
        sha(ROOT / x['path']) == x['sha256'] for x in integrity['files']))
    post = read(PULSE / 'certificate01' / 'postcheck.json')
    check('5_certificate_artifacts_match', len(post['artifacts_sha256']) == 5 and all(
        sha(PULSE / p) == h for p, h in post['artifacts_sha256'].items()))
    check('saved_certificate_checks_pass', post['passed'] and len(post['checks']) == 16
          and all(x['passed'] for x in post['checks']))
    cert = read(PULSE / 'certificate01' / 'result.json')
    check('17_certificate_dependencies_match', len(cert['binding']['pulse_sources']) == 17
          and all(sha(ROOT / p) == h for p, h in cert['binding']['pulse_sources'].items()))
    old = {i: read(OLD / f'{i:02}.json') for i in (16, 17, 18, 19, 23, 27)}
    for key in ('candidate_sha256', 'safety_scope_sha256', 'safety_analysis_sha256',
                'evaluation_sha256', 'source_sha256'):
        check('new_old_binding_' + key, cert['binding'][key] == old[18]['result']['binding'][key])
    receipt = cert['safety_receipt']
    check('receipt_binding', receipt['binding'] == cert['binding'])
    safety = receipt['result']
    check('new_sustained_safe_all_declared', cert['status'] == 'certified_safety_only'
          and cert['budget_status'] == 'within_limit' and safety['status'] == 'sustained_safe'
          and safety['input_status'] == 'valid' and safety['deadline']['status'] == 'pass'
          and safety['coverage'] == 'all_declared_processes_certified')
    check('old_unresolved_and_safety_only_preserved', old[18]['result']['status'] == 'unresolved'
          and old[18]['result']['certified_candidate_energy']['status'] == 'unavailable'
          and cert['certified_candidate_energy']['status'] == 'unavailable')
    check('old_full_cpu_sustained_safe', old[16]['result']['sustained_safety']['status'] == 'sustained_safe'
          and old[16]['result']['certified_candidate_energy']['status'] == 'available')
    energies = {}
    for i in (16, 18):
        j, r = old[i], old[i]['result']
        agg = r['finite_path_energy']['aggregate']
        check(f'{i}_U1_paths_weights', agg['status'] == 'valid' and agg['trace_ids'] == ['F1', 'F2']
              and list(map(Q, agg['weights'])) == [Q(1, 2), Q(1, 2)]
              and j['bundle']['evaluation']['weights'] == ['0.5', '0.5'])
        weighted = [Q(0), Q(0)]
        for name in ('F1', 'F2'):
            x = r['finite_path_energy']['traces'][name]
            t = x['thermal']
            check(f'{i}_{name}_complete_safe', x['rankable_energy'] and x['input_status'] == 'valid'
                  and x['execution_status'] == 'valid' and x['failure'] is None
                  and x['energy_scope'] == 'complete_window' and t['status'] == 'safe'
                  and t['complete'] and t['precision_met'] and t['covered_until_us'] == 80000
                  and all(Q(v[1]) <= 80 for v in t['peak_C']))
            for k in (0, 1):
                weighted[k] += Q(t['energy_J'][k]) / 2
        lo, hi = map(Q, agg['energy_J'])
        check(f'{i}_aggregate_encloses_exact_weighted_energy', lo <= weighted[0] <= weighted[1] <= hi)
        energies[r['id']] = agg['energy_J']
    exclusions = {}
    for full, probe in ((17, 23), (19, 27)):
        r = old[probe]['result']
        check(f'{probe}_same_candidate_scope', r['binding'] == old[full]['result']['binding'])
        check(f'{probe}_legal_B_only_violation', r['status'] == 'violation'
              and r['deadline_failure'] is None and r['membership'][0]['matching_entry_blocks'] == [2]
              and r['membership'][0]['transitions_and_window'] == 'valid'
              and r['path']['trace']['initial_mode'] == 'B'
              and r['path']['trace']['switch_requests'] == []
              and any(x['node'] == 'NPU' and Q(x['lower_temperature_C']) > Q(x['limit_C'])
                      and Q(x['witness_time_s']) == Q(17, 800) for x in r['known_violations']))
        check(f'{full}_no_invalid_energy_rank', old[full]['result']['finite_path_energy']['aggregate']['status']
              == 'not_aggregatable')
        exclusions[old[full]['result']['id']] = r['known_violations']
    c, n = [list(map(Q, energies[k])) for k in ('a_cb_c', 'a_nb_c')]
    check('strict_U1_energy_order', n[1] < c[0])
    summary = read(OLD / 'summary.json')
    local = summary['available_mode_scores_J']
    check('valid_local_A_preference_agrees', Q(local['a_n'][1]) < Q(local['a_c'][0]))
    check('local_B_incomplete_preserved', 'b_n' not in local and summary['local_choice_status'] == 'unresolved')
    for k in energies:
        for name in ('F1', 'F2'):
            a = summary['attribution'][k][name]
            check(k + '_' + name + '_positive_consistent_history', a['status'] == 'consistent'
                  and Q(a['history_J'][0]) > 0)
    return {
        'stage': 'K.34', 'kind': 'retrospective_evidence_consolidation', 'passed': True,
        'checks': checks, 'sources_sha256': sources, 'audit_source_sha256': sha(Path(__file__)),
        'scope': 'four fixed TP-1 plans; sustained feasibility in declared domain; energy on U1 F1/F2 only',
        'energy_interval_J': energies, 'excluded_by_B_only_counterexample': exclusions,
        'best_of_four_fixed_plans': 'a_nb_c', 'strict_best': True,
        'energy_difference_acbc_minus_anbc_J_exact': [str(c[0] - n[1]), str(c[1] - n[0])],
        'extra_joint_optimization_gain_demonstrated': False,
        'full_local_baseline_completed': False, 'global_optimization_proof': False,
        'new_thermal_energy_or_search_calls': 0,
        'historical_results_rewritten': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    result = build()
    if args.verify:
        if load(args.verify) != result:
            raise ValueError('saved consolidation differs from current read-only audit')
        print(f"PASS: {len(result['checks'])} checks; saved consolidation matches")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
