"""Read saved K145 evidence only; no method import, decoding or thermal solve."""
from pathlib import Path
from fractions import Fraction as Q
from itertools import combinations
from collections import Counter
import csv
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def interval(value):
    low, high = map(Q, value)
    assert low <= high
    return low, high

def stored_safe_check(instance, candidate, receipt, cutoff):
    assert receipt['state'] == 'SAFE' and receipt['rankable_energy'] is True
    assert 0 <= receipt['completed_at_elapsed_s'] < cutoff
    assert receipt['problem_id'] == instance['id']
    assert receipt['legality']['state'] == 'SCHEDULE_VALID_THERMAL_UNCHECKED'
    scenes = {s['id']: s for s in instance['scenarios']}
    assert set(candidate['scenes']) == set(receipt['scenes']) == set(scenes)
    assert not receipt['violations']
    shared, schedule_rows, physical = {}, [], {}
    weighted_low = weighted_high = Q(0)
    for sid, scene in scenes.items():
        stages = {s['id']: s for s in scene['stage_instances']}
        requests = {r['id']: r for r in scene['requests']}
        rows = candidate['scenes'][sid]
        assert len(rows) == len(stages) and {r['stage_id'] for r in rows} == set(stages)
        expanded = {}
        archived = {r['stage_id']: r for r in receipt['legality']['scenes'][sid]['rows']}
        for row in rows:
            stage = stages[row['stage_id']]
            key = stage['shared_stage_id']
            mode = [m for m in instance['stage_modes'][key]
                    if (m['unit_id'], m['opp_id']) == (row['unit'], row['opp'])]
            assert len(mode) == 1
            mode = mode[0]
            if key in shared:
                assert shared[key] == row['unit']
            shared[key] = row['unit']
            start, duration = Q(row['start_ms']), Q(mode['duration_ms'])
            end = start + duration
            request = requests[stage['request_id']]
            assert start >= Q(request['release_ms']) and end <= Q(request['deadline_ms'])
            assert end <= Q(instance['window_ms']) and start % Q(instance['start_grid_ms']) == 0
            saved = archived[row['stage_id']]
            assert Q(saved['start_ms']) == start and Q(saved['duration_ms']) == duration
            assert Q(saved['end_ms']) == end and saved['unit'] == row['unit']
            assert saved['opp'] == row['opp'] and saved['domain_id'] == mode['domain_id']
            expanded[row['stage_id']] = (start, end, row['unit'], row['opp'], mode['domain_id'])
            schedule_rows.append(dict(method=None, scene=sid, stage=row['stage_id'], unit=row['unit'],
                                      opp=row['opp'], start_ms=str(start), end_ms=str(end),
                                      duration_ms=str(duration), deadline_ms=request['deadline_ms']))
        for before, after in scene['dependencies']:
            assert expanded[before][1] <= expanded[after][0]
        for left, right in combinations(expanded.values(), 2):
            overlaps = left[0] < right[1] and right[0] < left[1]
            if overlaps:
                assert left[2] != right[2]
                assert left[4] != right[4] or left[3] == right[3]
        saved = receipt['scenes'][sid]
        assert saved['state'] == 'SAFE' and saved['complete'] and saved['rankable_energy']
        assert saved['energy_accuracy_met'] and not saved['violations']
        window = Q(instance['window_ms']) / 1000
        assert Q(saved['covered_until_s']) == window and Q(saved['trace'][-1]['time_s']) == window
        # Trace rows are accepted subinterval endpoints, not initial samples.
        segments = receipt['legality']['scenes'][sid]['segments']
        cursor = Q(0)
        for segment in segments:
            assert Q(segment['start_ms']) == cursor
            assert Q(segment['end_ms']) > cursor
            assert Q(segment['duration_ms']) == Q(segment['end_ms']) - cursor
            cursor = Q(segment['end_ms'])
        assert cursor == Q(instance['window_ms'])
        assert 0 < Q(saved['trace'][0]['time_s']) <= window
        assert all(Q(a['time_s']) <= Q(b['time_s']) for a, b in zip(saved['trace'], saved['trace'][1:]))
        nodes = instance['platform']['node_order']
        assert set(saved['peaks_degC']) == set(nodes)
        peaks = {}
        for node, limit in zip(nodes, scene['maximum_temperature_degC']):
            low, high = interval(saved['peaks_degC'][node])
            assert high <= Q(limit)
            peaks[node] = float(high)
        energy_low, energy_high = interval(saved['energy_J'])
        assert 0 <= energy_low
        weight = Q(scene['weight'])
        weighted_low += weight * energy_low
        weighted_high += weight * energy_high
        physical[sid] = dict(energy_interval_J=saved['energy_J'], peaks_upper_degC=peaks,
                             complete_window_s=str(window),
                             energy_components_J=saved['energy_components_J'],
                             request_completion_ms={rid: str(max(expanded[i][1] for i in req['stage_instance_ids']))
                                                    for rid, req in requests.items()})
    low, high = interval(receipt['weighted_energy_J'])
    assert low <= weighted_low <= weighted_high <= high
    assert Q(receipt['safe_upper_bound_J']) == high
    assert shared == receipt['legality']['shared_deployment']
    return physical, schedule_rows

def main():
    declaration, ledger = read(HERE/'declaration.json'), read(HERE/'ledger.json')
    assert ledger['state'] == 'COMPLETED' and ledger['consumed'] == 2
    assert ledger['reserved_method_budget_s'] == 600
    assert [(r['id'], r['seed']) for r in ledger['calls']] == [('heft', None), ('sa101', 101)]
    assert len(list((HERE/'claims').glob('*_result.json'))) == 2
    for name, value in declaration['source_sha256'].items():
        assert digest(ROOT/name) == value == digest(HERE/'source_snapshot'/name)
    for name, value in declaration['input_file_sha256'].items():
        assert digest(HERE/name) == value
    instance = read(HERE/'input_instance.json')
    checks, rows, schedules, progress, physicals = {}, [], [], [], {}
    for call in ledger['calls']:
        name = call['id']
        raw = read(HERE/name/'result.json')
        archived_call = read(HERE/'claims'/(name+'_result.json'))
        assert archived_call['execution'] == call['execution']
        assert not call['errors'] and call['source_identity_valid'] is True
        assert call['execution']['execution_status'] in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        assert call['execution']['safe_witness_preserved'] and call['usable_U_J'] is not None
        assert raw['input_sha256'] == declaration['input_sha256']
        assert canonical(read(HERE/name/'input_instance.json')) == declaration['input_sha256']
        assert canonical(read(HERE/name/'input_config.json')) == declaration['config_sha256']
        assert not raw['candidate_and_cache_shared_between_calls']
        assert raw['independently_proven_optimal'] is False and raw['independently_proven_infeasible'] is False
        assert raw['coverage_complete'] is False and raw['timing']['limit_s'] == 300
        accepted = [e for e in raw['evaluations'] if e['accepted_safe']]
        for entry in accepted:
            assert canonical(entry['candidate']) == entry['candidate_sha256']
            stored_safe_check(instance, entry['candidate'], entry['evaluation'], 300)
        minimum = min(Q(e['evaluation']['safe_upper_bound_J']) for e in accepted)
        assert minimum == Q(raw['safe_upper_bound_J']) == Q(call['usable_U_J'])
        physical, plan = stored_safe_check(instance, raw['safe_candidate'], raw['evaluation'], 300)
        physicals[name] = physical
        schedules.extend(dict(row, method=name) for row in plan)
        metric = call['completion_metrics']
        first = min(e['evaluation']['completed_at_elapsed_s'] for e in accepted)
        assert first == metric['first_complete_SAFE_at_s'] == raw['first_safe_at_s']
        first_receipt = min(accepted, key=lambda e: e['evaluation']['completed_at_elapsed_s'])['evaluation']
        initial_low, initial_high = interval(first_receipt['weighted_energy_J'])
        strict = [e for e in accepted if e['evaluation']['completed_at_elapsed_s'] > first
                  and Q(e['evaluation']['safe_upper_bound_J']) < initial_low]
        first_strict = min((e['evaluation']['completed_at_elapsed_s'] for e in strict), default=None)
        assert metric['first_strict_improvement_at_s'] == first_strict
        assert metric['matlab_startup']['status'] == 'NOT_APPLICABLE'
        timing = raw['timing']
        assert abs(sum(timing['phases_exclusive_s'].values()) + timing['unattributed_s'] - timing['method_elapsed_s']) < 1e-7
        assert call['method_return_inclusive_wall_s'] >= timing['method_elapsed_s']
        for event in raw['events']:
            assert 0 <= event['at_s'] < 300
            assert any(e['candidate_sha256'] == event['candidate_sha256']
                       and e['evaluation']['completed_at_elapsed_s'] == event['at_s']
                       and e['evaluation']['safe_upper_bound_J'] == event['safe_upper_bound_J'] for e in accepted)
            progress.append(dict(method=name, at_s=event['at_s'], U_J=float(Q(event['safe_upper_bound_J'])),
                                 L0_J=float(Q(raw['certified_lower_bound_J'])), source=event['source']))
        low, high = interval(raw['evaluation']['weighted_energy_J'])
        lower = Q(raw['certified_lower_bound_J'])
        assert lower <= low
        record = dict(method=name, state=raw['state'], execution_status=call['execution']['execution_status'],
                      budget_s=300, method_elapsed_s=timing['method_elapsed_s'],
                      method_return_inclusive_wall_s=call['method_return_inclusive_wall_s'],
                      post_method_record_wall_s=call['post_method_record_wall_s'],
                      archive_only_wall_s=read(HERE/name/'archive_timing.json')['wall_s'],
                      first_legal_s=raw['first_legal_candidate_at_s'], first_safe_s=first,
                      first_strict_improvement_s=first_strict,
                      initial_U_J=float(initial_high), U_J=float(high), L0_J=float(lower),
                      certified_gap_percent_of_U=float((high-lower)/high*100),
                      own_initial_energy_decrease_percent=float((initial_high-high)/initial_high*100),
                      candidate_requests=raw['candidate_count'], physical_evaluations=raw['thermal_evaluations'],
                      cache_hits=raw['cache_hits'], accepted_safe_receipts=len(accepted),
                      distinct_safe_schedules=len({e['candidate_sha256'] for e in accepted}),
                      receipt_states=dict(Counter(e['evaluation']['state'] for e in raw['evaluations'])),
                      unaccepted_safe_receipts=sum(e['evaluation']['state']=='SAFE' and not e['accepted_safe'] for e in raw['evaluations']),
                      violations=len(raw['violations']), unresolved_observations=len(call['unresolved_evaluation_records']),
                      safe_bound_updates=len(raw['events']),
                      final_safe_formed_s=raw['evaluation']['completed_at_elapsed_s'],
                      no_independent_optimality_proof=True)
        events = raw['events']
        decreases = {}
        for previous, event in zip(events, events[1:]):
            delta = Q(previous['safe_upper_bound_J']) - Q(event['safe_upper_bound_J'])
            assert delta > 0
            label = event['source']
            decreases[label] = decreases.get(label, Q(0)) + delta
        record['best_bound_decrease_by_source_J'] = {key: float(value) for key, value in decreases.items()}
        record['thermal_evaluation_exclusive_s'] = timing['phases_exclusive_s'].get('continuous_thermal_energy_evaluation')
        record['method_overshoot_s'] = timing['deadline_overshoot_s']
        rows.append(record)
        checks[name] = dict(input_source_identity=True, schedule_exact_rational_recheck=True,
                            all_accepted_receipts_complete_timely_and_hash_bound=True,
                            stored_continuous_peak_enclosures_safe=True, weighted_energy_enclosure=True,
                            final_U_matches_best_accepted=True, first_safe_and_strict_times=True,
                            phase_accounting=True, no_shared_candidate_cache=True,
                            no_optimal_or_infeasible_claim=True)
    assert rows[0]['L0_J'] == rows[1]['L0_J']
    output = dict(stage='K145', passed=True, methods=rows, checks=checks,
                  same_batch_energy_reduction_SA_vs_HEFT_percent=(rows[0]['U_J']-rows[1]['U_J'])/rows[0]['U_J']*100,
                  new_research_calls=2, extra_solver_or_heat_calls=0,
                  scope='saved JSON and exact arithmetic only; peak enclosures checked, trajectories not recomputed',
                  source_sha256=declaration['source_sha256'], physicals=physicals)
    (HERE/'k145_analysis.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for filename, data in [('k145_metrics.csv', rows), ('k145_schedules.csv', schedules), ('k145_progress.csv', progress)]:
        with (HERE/filename).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    print(json.dumps({k:v for k,v in output.items() if k not in ('source_sha256','physicals','checks')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
