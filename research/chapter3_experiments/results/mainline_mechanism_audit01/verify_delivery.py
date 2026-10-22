"""Verify K169 saved algebra, bounds and unchanged sources; stdlib only.

No production module is imported. This checks recorded evidence, not a
schedule's temperature, a solver result, or a new research candidate.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output):
    if output.exists():
        raise FileExistsError('Do not overwrite a prior verification')
    c12 = read(HERE / 'c12/facts.json')
    c17 = read(HERE / 'c17/facts.json')
    reproduced = read(HERE / 'c17/reproduced.json')
    before = read(HERE / 'review/before_manifest.json')
    checks = {}
    checks['C17_independent_rerun_identical'] = c17 == reproduced
    checks['C12_four_structurally_legal_not_SAFE'] = (
        c12['complete_structurally_legal_hand_schedules'] == 4
        and not c12['continuous_80C_safety_proven']
        and not c12['strict_complete_energy_order_reversal_proven']
        and not c12['new_safe_U'])
    checks['C12_interval_context_cost_change'] = (
        F(c12['uncovered_scene_energy_difference_J'][0])
        - F(c12['covered_scene_energy_difference_J'][1]) == F('0.004425'))
    checks['C12_bound_files_bound_to_hash'] = all(
        sha(HERE / 'c12' / name) == digest
        for name, digest in c12['files'].items())
    checks['five_original_L0s_and_proposed_bounds'] = len(c17['cases']) == 5
    for case in c17['cases']:
        name = case['case']
        old = F(case['old_L0_J']['exact'])
        low = F(case['init_only_proposed_LB_J']['exact'])
        high = F(case['shared_consistent_proposed_LB_J']['exact'])
        checks[name + '_positive_increment_exact'] = low-old == F('0.11264')
        checks[name + '_below_all_old_U_not_an_optimum'] = (
            old < low <= high and len(case['stored_upper_bounds']) == 8
            and all(high < F(row['stored_U_J']['exact'])
                    for row in case['stored_upper_bounds']))
        checks[name + '_root_additional_gains_zero'] = (
            F(case['OPP_workload_additional_gain_J']['exact']) == 0
            and F(case['shared_deployment_additional_gain_J']['exact']) == 0)
    checks['old_sources_unchanged'] = all(
        sha(REPO / name) == digest
        for name, digest in before['source_sha256'].items())
    checks['C17_inputs_and_source_unchanged'] = all(
        sha(REPO / name) == digest
        for key in ('inputs_before_sha256', 'source_before_sha256')
        for name, digest in c17[key].items())
    checks['no_scientific_modules_in_C17_algebra'] = (
        c17['guard']['scientific_modules_loaded'] == [])
    links = re.findall(r'\]\(([^)]+)\)', (HERE / 'summary.md').read_text('utf-8'))
    checks['summary_local_links_exist'] = all(
        (HERE / name).is_file() for name in links if '://' not in name)
    passed = all(checks.values())
    result = {'protocol': 'K169-delivery-static-evidence-verification-v1',
              'passed': passed, 'checks': checks,
              'count': len(checks), 'scientific_calls': 0,
              'scope': 'Recorded algebra/hash/link consistency; not a proof by numerical samples'}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps({'passed': passed, 'checks': len(checks)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
