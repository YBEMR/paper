"""Read archived files and check exact arithmetic only; never construct schedules.

Run from the repository root with Python -B. Output is stdout, no file writes.
This is a post-run audit, outside the frozen scientific executor.
"""
import gzip
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FREEZE = ROOT / 'research/chapter3_calibration_supplement/results/frozen_supplement01'
RUN = ROOT / 'research/chapter3_calibration_supplement/results/supplement_execution01'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def audit():
    plan, freeze = read(FREEZE / 'plan.json'), read(FREEZE / 'freeze.json')
    inventory = read(FREEZE / 'inventory.json')
    batch, aggregate = read(RUN / 'batch_result.json'), read(RUN / 'summary.json')
    require(digest(FREEZE / 'plan.json') == freeze['plan_sha256'] == batch['plan_sha256'], 'PLAN')
    for path, sha in {**freeze['protected_files'], **plan['source_files']}.items():
        require(digest(ROOT / path) == sha, path)
    require(batch['state'] == 'STOPPED_EXCEPTION' and batch['consumed_conditions'] == 3, 'TERMINAL')
    require(batch['completed_conditions'] == 3 and batch['elapsed_s'] < 1800, 'BUDGET')
    require(batch['final_error']['type'] == 'PermissionError', 'ERROR_TYPE')
    require('status.json.tmp' in batch['final_error']['error'], 'ERROR_FILE')
    require([r['condition_id'] for r in batch['rows']] == [c['condition_id'] for c in plan['calls']], 'COVERAGE')
    require(all(r['state'] == 'NOT_RUN' for r in batch['rows'][3:]), 'UNSTARTED')
    require(aggregate['usable_conditions'] == 3 and aggregate['state'] == 'PARTIAL', 'AGGREGATE')
    count, schedule_count, counters = 0, 0, {}
    compact, windows = {}, {}
    for row in batch['rows'][:3]:
        cid = row['condition_id']
        directory = RUN / cid
        receipt, claim = read(directory / 'result.json'), read(directory / 'call_claim.json')
        require(row['state'] == receipt['state'] == 'COMPLETE', cid)
        require(receipt['token'] == claim['token'], 'TOKEN')
        require(row['elapsed_s'] <= 60 and receipt['elapsed_s'] <= row['elapsed_s'], 'CLOCK')
        require(receipt['source_files'] == plan['source_files'], 'SOURCE_BINDING')
        require(digest(directory / 'result.json') == row['result_sha256'], 'RESULT_HASH')
        for key, file in [('evidence', 'evidence.json.gz'), ('workload', 'generated_workload.json.gz'), ('summary', 'summary.json')]:
            require(digest(directory / file) == receipt[key + '_sha256'], key)
        evidence, summary = read(directory / 'evidence.json.gz'), read(directory / 'summary.json')
        require(read(directory / 'generated_workload.json.gz') == evidence['workload'], 'WORKLOAD')
        require(receipt['beta_selected'] is None and not receipt['denied_events'] and not receipt['denied_imports'], 'SCOPE')
        call = claim['call']
        roles = {'branch_multi': evidence}
        for role, key in [('branch_join', call['parent_id']), ('serial', call['comparison_ids'][0]), ('layered', call['comparison_ids'][1])]:
            ref = inventory['archive_references'][key]['files']['evidence']
            require(digest(ROOT / ref['path']) == ref['sha256'], 'ARCHIVE_HASH')
            roles[role] = read(ROOT / ref['path'])
        compact[cid] = {}
        for key, value in receipt['counters'].items():
            counters[key] = counters.get(key, 0) + value
        for beta in ['1', '13/10', '8/5', '2']:
            for opp in ['H', 'M', 'L']:
                for role, raw in roles.items():
                    check = raw['reference']['checks'][opp]
                    require(check['state'] == 'TIME_STRUCTURAL_VALID', 'STRUCTURAL_CHECK')
                    stats = summary['by_beta'][beta][opp]['roles'][role]
                    hits, scenes = 0, 0
                    for sid, deadlines in raw['deadlines'][beta]['requests'].items():
                        scene_hits = 0
                        for rid, deadline in deadlines.items():
                            due, release, relative = (F(deadline[k]) for k in ['deadline_ms', 'release_ms', 'relative_deadline_ms'])
                            finish = F(check['completions_ms'][sid][rid])
                            require(due == release + relative and relative > 0, 'DEADLINE')
                            reported = stats['scenes'][sid]['requests'][rid]
                            require(F(reported['response_ms']) == finish - release, 'RESPONSE')
                            require(F(reported['slack_ms']) == due - finish, 'SLACK')
                            require(F(reported['eta']) == (due - finish) / relative, 'ETA')
                            require(reported['on_time'] == (finish <= due), 'ON_TIME')
                            scene_hits += finish <= due
                            count += 1
                        hits += scene_hits
                        scenes += scene_hits == len(deadlines)
                    require(hits == stats['requests_on_time'] and scenes == stats['scenes_on_time'], 'COUNTS')
                    require(stats['family_all_on_time'] == (scenes == stats['scene_count']), 'FAMILY_COUNT')
                if beta == '13/10':
                    compact[cid][opp] = {role: {k: stats[k] for k in ['family_all_on_time', 'scenes_on_time', 'requests_on_time', 'minimum_eta']}
                                         for role, stats in summary['by_beta'][beta][opp]['roles'].items()}
        windows[cid] = {}
        for beta, wr in evidence['window_receipts'].items():
            values = {F(m['window_ms']) for m in wr['members'].values()}
            require(len(values) == 1, 'COMMON_WINDOW')
            due = F(wr['latest_deadline_ms'])
            expect = 5 * (-(-due // 5))
            require(values == {expect}, 'WINDOW_CEILING')
            windows[cid][beta] = str(expect)
        schedule_count += sum(len(c['completions_ms']) for c in evidence['reference']['checks'].values())
    require(counters['timetable_constructions'] == 9 and counters['mapping_constructions'] == 0, 'COUNTERS')
    require(counters['formal_method_calls'] == counters['thermal_integrations'] == 0, 'NO_SCIENCE_CALLS')
    old_status, temporary = read(RUN / 'status.json'), read(RUN / 'status.json.tmp')
    require(len(old_status['rows']) == 2 and len(temporary['rows']) == 3, 'PROGRESS_INTERRUPTION')
    return {
        'state': 'READ_ONLY_AUDIT_PASS', 'executor_state': batch['state'],
        'coverage': {'completed': 3, 'not_run': 25, 'S4': '3/16', 'S7': '0/12'},
        'exact_request_arithmetic_checks': count, 'new_family_timetables': 9,
        'new_scenario_schedules': schedule_count, 'counters': counters,
        'frozen_sources_unchanged': len(plan['source_files']),
        'protected_files_unchanged': len(freeze['protected_files']),
        'executor_elapsed_s': batch['elapsed_s'], 'window_ms': windows,
        'beta_1_3': compact, 'beta_selected': None,
        'all_beta_aggregate': aggregate['by_axis']['S4']['all_scales']['by_beta'],
        'diagnosis': 'status atomic replace WinError5; actual lock/permission origin undetermined',
        'new_scheduling_calls': 0, 'new_thermal_calls': 0,
        'evidence_hashes': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p)
                            for p in sorted(RUN.rglob('*')) if p.is_file()},
        'audit_source_sha256': digest(Path(__file__))
    }


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
