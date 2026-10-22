"""Recheck saved K170 evidence with stdlib; no bound/solver/heat calls."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
from statistics import median

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXPECTED = '9b4fc402a00c71d9f919c3829df0b43277df614fbd5fcfe2aec6d67de02c6e0a'


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output):
    if output.exists():
        raise FileExistsError('Verification records are append-only')
    checks = {}
    core = REPO/'research/chapter3_experiments/conditional_energy_bound/bounds.py'
    tests = read(HERE.parent/'conditional_energy_bound_precheck01/run05/checks.json')
    review = read(HERE/'review/implementation_review.json')
    raw = read(HERE/'review/probe_cost_run02/results.json')
    analysis = read(HERE/'review/analysis.json')
    checks['frozen_core_current'] = sha(core) == EXPECTED
    checks['final_tests_passed9'] = (tests['tests_run'] == 9 and tests['test_successful']
                                   and tests['errors'] == tests['failures'] == 0)
    checks['final_test_sources_match'] = all(sha(REPO/name) == value
        for name, value in tests['source_after_sha256'].items())
    checks['implementation_review_passed19'] = (len(review['checks']) == 19
        and all(row['passed'] for row in review['checks']))
    checks['implementation_review_sources_match'] = all(sha(REPO/name) == value
        for name, value in review['source_and_original_artifact_sha256'].items())
    checks['no_scientific_entry'] = (tests['guard']['all_attempts_zero'] and
                                   raw['guard']['all_zero'] and
                                   raw['guard']['scientific_modules_after'] == [])
    checks['cost_run_final_sources_stable'] = (raw['passed'] and
        raw['source_sha256_before'] == raw['source_sha256_after'] and
        raw['frozen_files_sha256'] == raw['frozen_files_sha256_after'])
    rows = raw['probes']
    checks['fixed490_not_a_search_tree'] = len(rows) == 490
    checks['decisions_are_exact_strict'] = all(row['decision']['prune'] == (
        F(row['bound']['lower_bound_J']) > F(row['decision']['archived_upper_bound_J'])) for row in rows)
    checks['bounds_take_max_not_sum'] = all(F(row['bound']['lower_bound_J']) == max(
        F(row['bound'][key]) for key in ('legacy_conditioned_lower_bound_J',
        'capacity_lower_bound_J','forced_residency_lower_bound_J')) for row in rows)
    pruned = [row for row in rows if row['decision']['prune']]
    new = [row for row in pruned if not row['already_excluded_by_ordinary_deadline_necessity']
           and not row['legacy_form_conditioned_algebra_prunes']]
    forced = [row for row in pruned if F(row['bound']['capacity_lower_bound_J']) <=
              F(row['decision']['archived_upper_bound_J'])]
    checks['counts255_187_66'] = (len(pruned) == 255 and len(new) == 187 and
        sum(row['within_existing_linked_device_layer'] for row in new) == 66)
    checks['forced_extra22_inside11'] = (len(forced) == 22 and
        sum(row['within_existing_linked_device_layer'] for row in forced) == 11)
    checks['forced_extras_not_legacy_deadline'] = all(
        not row['already_excluded_by_ordinary_deadline_necessity'] and
        not row['legacy_form_conditioned_algebra_prunes'] for row in forced)
    checks['cost_three_fixed_values_medians'] = all(
        all(len(case[key]['three_values_s']) == 3 and
            median(case[key]['three_values_s']) == case[key]['median_s']
            for key in ('cold_total_statistics','warm_joint_statistics'))
        for case in raw['case_results'])
    checks['analysis_bound_to_raw'] = (analysis['source_results_sha256'] ==
                                     sha(HERE/'review/probe_cost_run02/results.json'))
    checks['summary_local_links'] = all((HERE/path).is_file() for path in re.findall(
        r'\]\(([^)]+)\)', (HERE/'summary.md').read_text('utf-8')) if '://' not in path)
    old = read(HERE/'review/after_manifest.json')
    checks['originals_and_pending_preserved'] = old['passed']
    result = {'protocol':'K170-delivery-saved-evidence-recheck-v1',
              'passed':all(checks.values()),'checks':checks,'count':len(checks),
              'new_optimization_or_thermal_calls':0,
              'scope':'Recomputed evidence arithmetic, hashes and consistency; no new search or candidate evaluation'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'passed':result['passed'],'checks':len(checks)}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
