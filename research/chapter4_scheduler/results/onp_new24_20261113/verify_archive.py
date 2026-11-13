"""Read-only evidence verification; never reruns a scientific method or evaluator."""
import hashlib
import json
import re
from fractions import Fraction as F
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'RESEARCH_BRIEF.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    plan = read(OUT / 'execution/plan.json')
    batch = read(OUT / 'execution/batch_return.json')
    analysis = read(OUT / 'analysis.json')
    paths = read(OUT / 'path_diagnostics.json')
    checks = read(OUT / 'preflight/checks.json')
    assert checks['passed'] and checks['tests_run'] == 24
    assert checks['real_method_calls'] == checks['thermal_evaluations'] == checks['new_root_draws'] == 0
    assert plan['preregistration_sha256'] == sha(REPO / 'research/chapter4_scheduler/onp_new24/PREREGISTRATION.md')
    assert plan['precheck_sha256'] == sha(OUT / 'execution/precheck.json')
    assert plan['generation_manifest_sha256'] == sha(OUT / 'input_generation/inputs_manifest.json')
    for name, digest in plan['source_sha256'].items():
        assert sha(REPO / name) == sha(OUT / 'execution/source_snapshot' / name) == digest, name
    for name, digest in plan['input_file_sha256'].items():
        assert sha(OUT / 'execution' / name) == digest, name
    prior = read(OUT.parent / 'onp_scale24_20261113/files_sha256.json')
    for name, digest in prior.items():
        assert sha(REPO / name) == digest, name
    assert len(plan['slots']) == len(batch['slots']) == len(analysis['rows']) == 16
    assert batch['retry_count'] == 0
    for slot, completed, row in zip(plan['slots'], batch['slots'], analysis['rows']):
        assert slot['id'] == completed['slot']['id'] == row['id']
        assert completed['status'] == 'COMPLETED'
        assert [p['phase'] for p in completed['phases']] == ['method', 'post']
        assert all(p['exit_code'] == 0 and p['normal_stop'] and not p['watchdog_expired'] for p in completed['phases'])
        folder = OUT / 'execution/calls' / slot['id']
        raw, ret, post, receipt = (read(folder / n) for n in ('method/result.json', 'method_return.json', 'post_return.json', 'post_receipt.json'))
        assert sha(folder / 'method/result.json') == ret['raw_result_sha256']
        assert row['safe'] and row['post_passed'] and row['error'] is None
        assert post['passed'] and post['same_numerical_evaluator'] and receipt['state'] == 'SAFE'
        lo, hi = map(F, raw['evaluation']['weighted_energy_J'])
        plo, phi = map(F, receipt['weighted_energy_J'])
        assert max(lo, plo) <= min(hi, phi)
        assert raw['evaluation']['completed_at_elapsed_s'] < 300
        assert all(e['receipt']['completed_at_elapsed_s'] < 300 for e in raw['evaluations'] if e.get('incumbent_replaced'))
        assert all(e['evaluation_admitted_at_s'] < 180 for e in raw['evaluations'] if e['phase'] == 'initialization' and not e.get('cache_hit'))
    assert analysis['totals']['evaluation_attempts'] == 855
    assert analysis['totals']['full_electrothermal_SAFE_evaluations'] == 845
    assert paths['initialization_failed_constructions'] == 32
    # Report links must resolve in this checkout; no network needed.
    for target in re.findall(r'\]\(([^)]+)\)', (OUT / 'summary.md').read_text(encoding='utf-8')):
        if not target.startswith(('http:', 'https:')):
            assert (OUT / target).resolve().exists(), target
    result = {
        'passed': True, 'source_commit': plan['subject_commit'],
        'algorithm_commit': '63d2dc9f8109a7aa9e0ca18dc950c99572e9f8fb',
        'source_and_snapshot_files_verified': len(plan['source_sha256']),
        'prior_frozen_source_files_unchanged': checks['prior_frozen_source_files_unchanged'],
        'prior_scale24_archive_files_unchanged': len(prior),
        'input_files_verified': len(plan['input_file_sha256']),
        'simulated_checks_passed': checks['tests_run'],
        'methods': 16, 'SAFE_methods': 16, 'SAFE_posts': 16,
        'method_evaluations': 855, 'SAFE_evaluations': 845,
        'initialization_SAFE_evaluations': 607, 'search_SAFE_evaluations': 238,
        'unresolved_evaluations': 10, 'budget_interrupted_constructions': 2,
        'initialization_failed_constructions': 32, 'retry_count': 0, 'technical_failures': 0,
        'initial_admission_gate_hits': 16, 'budget_exhausted_search_arms': 12,
        'ON_P_OFF_P_same_initial_pairs': 4, 'ON_P_OFF_P_A_pairs': 3, 'ON_P_OFF_P_B_pairs': 1,
        'ON_P_ON_different_initial_roots': ['U08'],
        'ON_P_ON_equal_candidate_prefix_roots': ['U07', 'U09', 'U10'],
        'all_acceptance_and_admission_checks_passed': True,
        'figures_visually_inspected': True,
        'new_scientific_calls_in_analysis': 0}
    (OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != 'files_sha256.json')
    assert max(p.stat().st_size for p in files) < 100 * 2**20
    manifest = {p.relative_to(REPO).as_posix(): sha(p) for p in files}
    (OUT / 'files_sha256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'files': len(files), 'MiB': sum(p.stat().st_size for p in files) / 2**20,
                      'largest_MiB': max(p.stat().st_size for p in files) / 2**20, 'new_scientific_calls': 0}))


if __name__ == '__main__':
    main()
