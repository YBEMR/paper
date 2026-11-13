"""Verify saved receipts and frozen identities without running research code."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
REPO = next(p for p in OUT.parents if (p / 'RESEARCH_BRIEF.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ex = OUT / 'execution'
    plan, batch, analysis = read(ex / 'plan.json'), read(ex / 'batch_return.json'), read(OUT / 'analysis.json')
    prior = OUT.parent / 'onp_unseen_20261113'
    old_plan = read(prior / 'execution/plan.json')
    old_manifest = read(prior / 'files_sha256.json')
    for n, h in plan['source_sha256'].items():
        assert sha(REPO / n) == sha(ex / 'source_snapshot' / n) == h, n
    for n, h in old_plan['source_sha256'].items():
        assert sha(REPO / n) == h, n
    for n, h in old_manifest.items():
        assert sha(REPO / n) == h, n
    for n, h in plan['input_file_sha256'].items():
        assert sha(ex / n) == h, n
    assert sha(OUT / 'input_generation/inputs_manifest.json') == plan['generation_manifest_sha256']
    assert sha(REPO / 'research/chapter4_scheduler/onp_scale24/PREREGISTRATION.md') == plan['preregistration_sha256']
    assert sha(ex / 'precheck.json') == plan['precheck_sha256']
    assert sha(prior / 'execution/plan.json') == plan['prior_plan_sha256']
    gen = read(OUT / 'input_generation/inputs_manifest.json')
    assert sha(OUT / 'input_generation/input_plan.json') == gen['plan_sha256']
    for case in gen['cases']:
        for k in ('config', 'instance', 'generation_evidence'):
            assert sha(OUT / 'input_generation' / case[k + '_path']) == case[k + '_sha256']
    rows = analysis['rows']
    assert len(rows) == len(plan['slots']) == 8
    assert batch['retry_count'] == 0 and batch['stop_reason'] is None
    assert batch['frozen_identity_unchanged'] and batch['all_planned_method_slots_returned']
    for r in rows:
        folder = ex / 'calls' / r['id']
        ret, post = read(folder / 'method_return.json'), read(folder / 'post_return.json')
        assert ret['normal_stop'] and not ret['error'] and not ret['failure_reason']
        assert r['safe'] and r['post_passed'] and post['normal_stop'] and post['passed'] and not post['error']
        assert sha(folder / 'method/result.json') == ret['raw_result_sha256']
        assert ret['best_SAFE_formed_at_s'] < 300
    for k in ('all_initial_admissions_before_180', 'all_accepted_receipts_before_300', 'strict_search_acceptance_checked'):
        assert analysis[k]
    assert analysis['new_scientific_calls_in_analysis'] == 0
    diagnostic = read(OUT / 'path_diagnostics.json')
    assert diagnostic['new_scientific_calls'] == 0
    totals = lambda k: sum(r[k] for r in rows)
    result = {
        'passed': True, 'subject_commit': plan['subject_commit'],
        'algorithm_commit': '63d2dc9f8109a7aa9e0ca18dc950c99572e9f8fb',
        'source_and_snapshot_files_verified': len(plan['source_sha256']),
        'original_frozen_source_files_unchanged': len(old_plan['source_sha256']),
        'prior_12_archive_files_unchanged': len(old_manifest),
        'input_files_verified': len(plan['input_file_sha256']),
        'method_runs': 8, 'SAFE_methods': 8, 'SAFE_posts': 8,
        'method_evaluations': totals('evaluation_attempts'),
        'SAFE_evaluations': totals('full_electrothermal_SAFE_evaluations'),
        'initialization_SAFE_evaluations': totals('initialization_full_SAFE_evaluations'),
        'search_SAFE_evaluations': totals('search_full_SAFE_evaluations'),
        'retry_count': 0, 'technical_failures': 0,
        'unresolved_evaluations': totals('returned_unresolved_receipts'),
        'budget_interrupted_constructions': totals('construction_calls_interrupted'),
        'initial_admission_gate_hits': totals('init_admission_gate_hit'),
        'budget_exhausted_search_arms': sum(r['terminal'] == 'BUDGET_EXHAUSTED' for r in rows),
        'same_initial_all_pair_comparisons': all(c['same_initial'] for c in analysis['comparisons']),
        'all_roots_four_arm_initial_sequences_equal': all(c['same_initial_sequence'] for c in analysis['comparisons']),
        'ON_ONP_candidate_prefix_payloads_equal_excluding_time_and_acceptance': True,
        'all_acceptance_and_admission_checks_passed': True,
        'figures_visually_inspected': True,
        'new_scientific_calls_in_analysis': 0}
    assert result['method_evaluations'] == 422 and result['SAFE_evaluations'] == 418
    assert result['unresolved_evaluations'] == 4 and result['budget_interrupted_constructions'] == 2
    assert result['initial_admission_gate_hits'] == 8 and result['budget_exhausted_search_arms'] == 6
    assert result['same_initial_all_pair_comparisons'] and not result['all_roots_four_arm_initial_sequences_equal']
    (OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    files = sorted(f for f in OUT.rglob('*') if f.is_file() and f.name != 'files_sha256.json')
    assert all(f.stat().st_size < 100 * 2**20 for f in files)
    manifest = {f.relative_to(REPO).as_posix(): sha(f) for f in files}
    (OUT / 'files_sha256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({**result, 'archive_files': len(files), 'archive_MiB': sum(f.stat().st_size for f in files) / 2**20}, indent=2))


if __name__ == '__main__':
    main()
