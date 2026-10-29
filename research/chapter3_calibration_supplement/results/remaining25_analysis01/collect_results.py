"""Collect the completed continuation and original three records; no new schedules."""
import json
import sys
from pathlib import Path
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from research.chapter3_calibration_supplement import protocol as p, continuation as c
from research.chapter3_calibration_supplement.persistence import read_terminal_record, write_once


def main():
    folder = Path(__file__).resolve().parent
    run = p.PACKAGE / 'results/remaining25_execution01'
    frozen = p.PACKAGE / 'results/frozen_remaining25_01'
    exit_file = p.PACKAGE / 'results/remaining25_execution01_exit.json'
    exit_record = json.loads(exit_file.read_text(encoding='utf-8-sig'))
    batch = read_terminal_record(run, exit_code=exit_record['exit_code'])
    combined = c.combined_summary(frozen, run, exit_code=exit_record['exit_code'])
    plan, inv, record = p.check_frozen(frozen, full_archive_check=True)
    write_once(folder / 'combined_summary.json', combined)
    counters, clocks, structural = {}, [], {}
    windows = {}
    for index, call in enumerate(p.planned_conditions()):
        base = c.PRIOR if index < 3 else run
        rows = p.read_json(base / 'batch_result.json')['rows']
        row = next(r for r in rows if r['condition_id'] == call['condition_id'])
        if row['state'] != 'COMPLETE':
            continue
        directory = base / call['condition_id']
        evidence = p.read_gzip(directory / 'evidence.json.gz')
        summary = p.read_json(directory / 'summary.json')
        if index >= 3:
            clocks.append(row['elapsed_s'])
            for key, value in p.read_json(directory / 'result.json')['counters'].items():
                counters[key] = counters.get(key, 0) + value
        if call['axis'] == 'S4':
            for role, structure in summary['structure_by_role'].items():
                for app in structure['applications'].values():
                    key = (role, app['nodes'], app['longest_path_nodes'], app['incomparable_pairs'])
                    structural[key] = structural.get(key, 0) + 1
        windows[call['condition_id']] = {beta: wr['latest_deadline_ms'] for beta, wr in evidence['window_receipts'].items()}
    tables = {}
    for axis, axis_data in combined['by_axis'].items():
        tables[axis] = {}
        for beta, beta_data in axis_data['all_scales']['by_beta'].items():
            tables[axis][beta] = {opp: {'roles': {role: {k: metrics[k] for k in
                ('conditions','families_on_time','scenes','scenes_on_time','requests','requests_on_time',
                 'condition_minimum_eta_range')} for role, metrics in row['roles'].items()},
                'paired': row['paired']} for opp, row in beta_data.items()}
    facts = {
        'state': 'READ_ONLY_COLLECTION_COMPLETE', 'run_state': batch['state'],
        'exit_code': exit_record['exit_code'], 'new_limits': batch['limits'],
        'new_elapsed_s': batch['elapsed_s'], 'new_consumed_conditions': batch['consumed_conditions'],
        'new_completed_conditions': batch['completed_conditions'], 'new_counters': counters,
        'new_condition_elapsed_range_s': [min(clocks),max(clocks)] if clocks else None,
        'combined_state': combined['state'], 'combined_usable_conditions': combined['usable_conditions'],
        'combined_statuses': combined['condition_status_counts'], 'execution_accounts': combined['execution_accounts'],
        'plan_sha256': record['plan_sha256'], 'source_count': len(plan['source_files']),
        'protected_files': len(record['protected_files']), 'prior_protected_files': len(c.prior_evidence()[-1]),
        'all_beta_tables': tables, 'by_scale': {axis: data['by_scale'] for axis,data in combined['by_axis'].items()},
        'S4_structure_histogram': [{'role':r,'nodes':n,'longest_path_nodes':cp,'incomparable_pairs':ip,'applications':count}
                                 for (r,n,cp,ip),count in sorted(structural.items())],
        'group_latest_deadlines_ms': windows, 'beta_selected':None,
        'new_scheduling_calls_in_collection':0,'thermal_integrations_in_collection':0,
        'evidence_sha256': {str(path.relative_to(ROOT)).replace('\\','/'):p.sha(path)
                           for path in sorted(run.rglob('*')) if path.is_file()},
        'actual_exit_record_sha256':p.sha(exit_file), 'collector_sha256':p.sha(Path(__file__))}
    write_once(folder / 'facts.json', facts)
    print(json.dumps({k:facts[k] for k in ('run_state','new_elapsed_s','new_completed_conditions',
                     'combined_usable_conditions','new_counters','new_condition_elapsed_range_s')},ensure_ascii=False))


if __name__ == '__main__':
    main()
