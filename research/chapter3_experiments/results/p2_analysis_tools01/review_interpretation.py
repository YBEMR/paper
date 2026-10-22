"""Audit terminal P2 interpretation against immutable saved method returns."""
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CAMPAIGN = HERE.parent/'p2_execution01'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    sources = {}
    def read(path):
        sources[path.relative_to(REPO).as_posix()] = sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    facts = read(CAMPAIGN/'analysis01/facts.json')
    terminal = read(CAMPAIGN/'process_terminal.json')
    declaration = read(CAMPAIGN/'declaration.json')
    thermal = read(HERE/'thermal_acceptance_review.json')
    curves = read(HERE/'safe_curve_review.json')
    checks = {}; exact_U_matches = 0; post_separate = 0
    direct_violations = []; unresolved_reasons = Counter(); peaks = []
    for row in facts['rows']:
        slotid = row['problem_id']+'__'+row['method']
        record = read(CAMPAIGN/'claims'/(slotid+'_result.json'))
        raw = read(CAMPAIGN/'calls'/row['problem_id']/row['method']/'wrapper_raw_result.json')
        if row['usable_U_exact_J'] is not None:
            if F(row['usable_U_exact_J']) == F(record['records']['usable_U_J']): exact_U_matches += 1
        if record['postcheck'].get('passed') is True and record['postcheck'].get('new_U') is False:
            post_separate += 1
        checks[slotid+':all_complete_SAFE_receipts_before_cutoff'] = all(
            v.get('completed_at_s') is not None and v['completed_at_s'] < 300 for v in row['safe_curve'])
        for value in raw.get('evaluations') or []:
            evaluation = value.get('evaluation') or {}
            if evaluation.get('state') == 'THERMAL_VIOLATION':
                direct_violations.append({'problem_id': row['problem_id'], 'method': row['method'],
                    'candidate_sha256': value.get('candidate_sha256'), 'source': value.get('source'),
                    'accepted_safe': value.get('accepted_safe'), 'reason': evaluation.get('reason')})
        for item in row['evaluation_record_index']:
            if item['state'] == 'UNRESOLVED': unresolved_reasons[item.get('reason')] += 1
        peaks.extend(float(F(pair[1])) for s in row['final_scene_data'].values()
                     for pair in (s.get('peaks_degC') or {}).values())
    checks.update({'terminal_completed_40': terminal['state'] == 'COMPLETED' and terminal['returncode'] == 0
            and terminal.get('watchdog_stop') is None and terminal['worker_terminal']['consumed_total'] == 40,
        '40_original_U_exact_match': exact_U_matches == 40,
        '40_post_passed_not_new_U': post_separate == 40,
        'method_and_calendar_limits': facts['method_root_sum_s'] <= 12000 and terminal['process_wall_s'] <= 19200,
        'full_safe_and_comparison_40': facts['safe_original_receipts'] == facts['post_verified_safe_receipts'] == facts['comparison_usable_calls'] == 40,
        'no_feedback_saved': sum(r['feedback_saved_rows'] for r in facts['rows']) == 0,
        '46_direct_heuristic_thermal_rejections': len(direct_violations) == 46
            and all(v['accepted_safe'] is False and v['reason'] == 'POINT_WITNESS' for v in direct_violations),
        '25_saved_UNRESOLVED_are_wall_deadline': dict(unresolved_reasons) == {'wall_time_limit': 25},
        'no_bound_anomaly_or_independent_proof': not facts['bound_anomalies']
            and all(not r['independently_proven_optimal'] and not r['independently_proven_infeasible'] for r in facts['rows']),
        'all_final_node_upper_peaks_at_most_80': bool(peaks) and max(peaks) <= 80,
        'same_P0_SAFE_candidate_now_violated_5': thermal['passed'] and thermal['P0_SAFE_to_P2_violated_same_full_candidate'] == 5,
        'final_HEFT_schedule_unchanged_5': thermal['P0_P2_final_HEFT_candidates_identical'] == 5,
        'running_minimum_final_U_exact_40': curves['passed'] and curves['exact_matches'] == 40})

    p0path = HERE.parent/'p0_execution01/calls/base__R1/heft/wrapper_raw_result.json'
    p2path = CAMPAIGN/'calls/initial_78__R1/heft/wrapper_raw_result.json'
    old = read(p0path); new = read(p2path)
    def components(raw):
        sums = {}
        for scene in raw['evaluation']['scenes'].values():
            for key, pair in scene['energy_components_J'].items():
                target = sums.setdefault(key, [F(0), F(0)])
                target[0] += F(pair[0])/2; target[1] += F(pair[1])/2
        return sums
    previous, current = components(old), components(new)
    deltas = {k: [current[k][0]-previous[k][1], current[k][1]-previous[k][0]] for k in current}
    midpoint_changes = {k: float(sum(current[k])/2-sum(previous[k])/2) for k in current}
    stable = all(max(previous[k][0], current[k][0]) <= min(previous[k][1], current[k][1])
                 for k in ('baseline', 'activity', 'external_common'))
    checks['R1_HEFT_nonthermal_components_overlap_exactly'] = stable
    delta_total = [F(new['evaluation']['weighted_energy_J'][0])-F(old['evaluation']['weighted_energy_J'][1]),
                   F(new['evaluation']['weighted_energy_J'][1])-F(old['evaluation']['weighted_energy_J'][0])]
    checks['R1_temperature_delta_overlaps_total_delta'] = max(delta_total[0], deltas['temperature_correction'][0]) <= min(delta_total[1], deltas['temperature_correction'][1])
    linked = [r for r in facts['rows'] if r['method'] == 'anchor_linked4']
    phase_counts = {str(i): sum(p.get('strict_energy_reduction_from_entry') is True
                    for r in linked for p in r['method_phases'] if p.get('phase_index') == i) for i in (1, 2)}
    heft_faster = sum(next(r for r in facts['rows'] if r['problem_id'] == l['problem_id'] and r['method'] == 'heft')['method_root_s'] < l['method_root_s'] for l in linked)
    return {'passed': all(checks.values()), 'count': len(checks), 'checks': checks,
        'numeric_summary': {'method_root_sum_s': facts['method_root_sum_s'],
            'calendar_s': terminal['process_wall_s'], 'consumed': facts['consumed_total'],
            'status_counts': facts['execution_status_counts'],
            'linked_vs_HEFT_reduction_percent_R1_R5': [100*c['linked_vs_HEFT_reduction_fraction'] for c in facts['cohorts']],
            'linked_strict_lower_than_HEFT_n': sum(c['linked_strictly_lower_than_HEFT'] is True for c in facts['cohorts']),
            'HEFT_lower_total_method_time_n': heft_faster, 'linked_strict_phase_improvement_counts': phase_counts,
            'saved_thermal_rejections': len(direct_violations),
            'rejections_by_method_kind': dict(Counter('HEFT' if v['method'] == 'heft' else 'SA' for v in direct_violations)),
            'saved_UNRESOLVED_reasons': dict(unresolved_reasons), 'feedback_rows': 0,
            'maximum_final_node_peak_upper_degC': max(peaks)},
        'R1_HEFT_same_final_schedule_energy_composition': {
            'P0_U_J': old['safe_upper_bound_J'], 'P2_U_J': new['safe_upper_bound_J'],
            'P0_components_J': {k: list(map(str, v)) for k, v in previous.items()},
            'P2_components_J': {k: list(map(str, v)) for k, v in current.items()},
            'component_delta_intervals_J': {k: list(map(str, v)) for k, v in deltas.items()},
            'component_midpoint_changes_J': midpoint_changes,
            'total_delta_interval_J': list(map(str, delta_total)),
            'nonthermal_components_overlap': stable},
        'can_write': ['In five saved HEFT candidate pairs, P0 full SAFE becomes a strict P2 point violation for exactly the same complete arrangement.',
            'These thermal checks reject real candidates; all 40 final stored arrangements remain SAFE and pass their once-only post checks.',
            'Only R2 linked energy is strictly below HEFT here; phase2 improves four of five linked calls, not five.',
            'R1 final HEFT schedule is identical in P0/P2; its energy increase is consistent entirely with the temperature-correction component.'],
        'cannot_write': ['Do not claim final HEFT schedules changed: all five are identical across P0/P2.',
            'Do not claim net benefit from continuous MILP thermal feedback: saved feedback count is zero and no feedback ablation was run.',
            'Do not label the 25 wall-time UNRESOLVED evaluations as numerical failures; they belong to normal deadline handling.',
            'Do not treat SAFE-evaluation oscillations in the old plot as deterioration of retained U or as formal update-event counts.',
            'Do not claim global optimality or general algorithm superiority from this fixed five-instance cohort.'],
        'source_sha256': sources, 'script_sha256': sha(Path(__file__)),
        'frozen_source_count': len(declaration['source_sha256']), 'new_scientific_evaluations': 0,
        'old_U_post_or_original_plot_modified': False}


if __name__ == '__main__':
    report = run()
    with (HERE/'interpretation_review.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({'passed': report['passed'], 'count': report['count'], 'summary': report['numeric_summary']})
