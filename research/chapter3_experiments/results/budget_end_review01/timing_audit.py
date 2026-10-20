"""K143: stdlib-only extraction of stored K142 clocks and energy intervals.

No project imports, solver, decode, thermal evaluation, repair or new witness.
Only timing_metrics.json/csv in this directory are written.
"""
from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OLD = REPO / 'research/chapter3_experiments/results/fair_comparison_preparation01'
SOURCES: dict[str, str] = {}
ROWS: list[dict] = []


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def load(path: Path):
    identity = sha(path)
    value = json.loads(path.read_text(encoding='utf-8'))
    assert identity == sha(path), 'source changed during read: ' + str(path)
    SOURCES[ref(path)] = identity
    return value


def q(value):
    assert not isinstance(value, bool)
    return Fraction(str(value))


def interval(value):
    assert isinstance(value, list) and len(value) == 2
    low, high = map(q, value)
    assert 0 <= low <= high
    return low, high


def metric(job, section, ident, name, value, status, unit, source):
    ROWS.append(dict(job=job, section=section, id=ident, metric=name,
                     value=value, status=status, unit=unit, source=source))


def method_record(job, saved):
    path = ref(OLD / job / 'result.json')
    timing = saved['timing']
    startup = [r for r in timing['phase_records'] if r['phase'] == 'solver_startup']
    assert len(startup) == 1
    frame = startup[0]
    assert abs(frame['wall_s'] - (frame['end_s'] - frame['start_s'])) < 1e-8
    initial_energy = (saved['evaluation']['weighted_energy_J'] if job == 'whole_milp'
                      else saved['initial_global_weighted_energy_J'])
    first_safe = saved['first_initial_safe_s'] if job == 'whole_milp' else saved['first_safe_at_s']
    interval(initial_energy)
    assert 0 <= first_safe < timing['limit_s']
    answer = dict(status='EXECUTED', root_budget_s=timing['limit_s'],
                  root_stop_at_s=timing['method_elapsed_s'],
                  deadline_overshoot_s=timing['deadline_overshoot_s'],
                  clock_origin=timing['clock_origin'],
                  matlab_startup=dict(status='MEASURED', start_s=frame['start_s'],
                                      end_s=frame['end_s'], wall_s=frame['wall_s']),
                  first_complete_SAFE_at_s=first_safe,
                  initial_complete_SAFE_energy_interval_J=initial_energy,
                  cleanup_s=timing['cleanup_s'],
                  first_strict_improvement_at_s=None,
                  strict_improvement_status='NOT_OBSERVED_BEFORE_CUTOFF')
    for key in ('root_budget_s', 'root_stop_at_s', 'deadline_overshoot_s', 'first_complete_SAFE_at_s', 'cleanup_s'):
        metric(job, 'method', '', key, answer[key], 'MEASURED', 's', path + '#/timing' if key not in ('first_complete_SAFE_at_s',) else path)
    for key in ('start_s', 'end_s', 'wall_s'):
        metric(job, 'matlab_startup', '', key, answer['matlab_startup'][key], 'MEASURED', 's', path + '#/timing/phase_records')
    return answer


def main():
    review = load(HERE / 'audit.json')
    whole = load(OLD / 'whole_milp/result.json')
    linked = load(OLD / 'linked_n1/result.json')
    methods = {job: method_record(job, saved) for job, saved in (('whole_milp', whole), ('linked_n1', linked))}
    assert not whole['milp_improved_initial_upper_bound']
    assert not whole['strict_energy_improvement_certified']
    assert not whole['diagnostic']['candidate_receipts']
    updates = linked['global_updates']
    initial_low, initial_high = interval(linked['initial_global_weighted_energy_J'])
    assert interval(updates[0]['weighted_energy_J']) == (initial_low, initial_high)
    previous = (initial_low, initial_high)
    strict_updates = []
    for index, update in enumerate(updates):
        current = interval(update['weighted_energy_J'])
        assert q(update['safe_upper_bound_J']) == current[1]
        assert 0 <= update['committed_at_s'] < linked['timing']['limit_s']
        if index and current[1] < initial_low:
            strict_updates.append(dict(index=index, phase_index=update['phase_index'],
                                       committed_at_s=update['committed_at_s'],
                                       strict_vs_initial=True,
                                       strict_vs_previous=current[1] < previous[0],
                                       energy_interval_J=update['weighted_energy_J']))
        previous = current
    first_strict = strict_updates[0]['committed_at_s'] if strict_updates else None
    assert first_strict == review['first_strict_improvement_vs_initial_at_s']
    assert [r['committed_at_s'] for r in strict_updates] == [r['committed_at_s'] for r in review['strict_complete_energy_updates']]
    methods['linked_n1'].update(first_strict_improvement_at_s=first_strict,
                                strict_improvement_status='OBSERVED_INTERVAL_STRICT')
    for job in methods:
        metric(job, 'method', '', 'first_strict_improvement_at_s', methods[job]['first_strict_improvement_at_s'],
               methods[job]['strict_improvement_status'], 's', ref(OLD / job / 'result.json') + '#/global_updates' if job == 'linked_n1' else ref(OLD / job / 'result.json'))
    phases, slices = [], []
    first_phase_end = linked['phases'][0]['completed_at_s']
    for phase in linked['phases']:
        pid = phase['phase_index']
        start, end = phase['started_at_s'], phase['completed_at_s']
        setup = q(start) - q(first_phase_end) if pid == 2 else Fraction(0)
        before = [u for u in updates if u['committed_at_s'] <= start]
        assert before
        baseline = interval(before[-1]['weighted_energy_J'])
        changes = [u for u in updates if u['phase_index'] == pid and u['committed_at_s'] >= start
                   and interval(u['weighted_energy_J'])[1] < baseline[0]]
        first = changes[0]['committed_at_s'] if changes else None
        record = dict(phase_index=pid, name=phase['name'], start_s=start, end_s=end,
                      recorded_interval_s=float(q(end)-q(start)), pre_record_setup_s=float(setup),
                      inclusive_phase_s=float(q(end)-q(start)+setup),
                      planned_total_cap_s=None, planned_cap_status='SHARED_ROOT_BUDGET_NO_FIXED_PHASE_TOTAL',
                      allocation_rule='first pass scene cap 60; second pass min(60, remaining/scenes_left) after preparation',
                      root_remaining_at_phase_entry_s=float(q(300)-q(start)),
                      root_remaining_at_phase_end_s=float(max(Fraction(0), q(300)-q(end))),
                      baseline_complete_energy_interval_J=before[-1]['weighted_energy_J'],
                      first_strict_improvement_at_root_s=first,
                      first_strict_improvement_after_phase_entry_s=None if first is None else float(q(first)-q(start)),
                      strict_improvement_status='OBSERVED_INTERVAL_STRICT' if first is not None else 'NOT_OBSERVED_BEFORE_CUTOFF')
        if pid == 2:
            assert first == review['phase2_strict_improvement_at_s']
        phases.append(record)
        for key in ('recorded_interval_s', 'pre_record_setup_s', 'inclusive_phase_s',
                    'root_remaining_at_phase_entry_s', 'root_remaining_at_phase_end_s',
                    'first_strict_improvement_at_root_s', 'first_strict_improvement_after_phase_entry_s'):
            metric('linked_n1', 'phase', pid, key, record[key], record['strict_improvement_status'] if key.startswith('first') else 'DERIVED_FROM_SAVED_TIMESTAMPS', 's', ref(OLD / 'linked_n1/result.json') + '#/phases')
        for scene, sc in phase['scenes'].items():
            sr = sc['solver_result']
            a, b = sr['slice_started_at_s'], sc['search_returned_at_s']
            row = dict(phase_index=pid, scene=scene, planned_cooperative_cap_s=sr['scene_slice_s'],
                       root_start_s=a, root_return_s=b, actual_search_return_difference_s=float(q(b)-q(a)),
                       root_remaining_at_search_entry_s=float(q(300)-q(a)),
                       root_remaining_at_search_end_s=float(max(Fraction(0), q(300)-q(b))),
                       request_settled=sr['request_settled'],
                       local_scene_first_SAFE_at_s=sr['diagnostic'].get('first_safe_receipt_s'))
            slices.append(row)
            for key, value in row.items():
                if key.endswith('_s'):
                    metric('linked_n1', 'scene_slice', str(pid)+':'+scene, key, value,
                           'UNKNOWN' if value is None else 'SAVED_OR_TIMESTAMP_DERIVED', 's', ref(OLD / 'linked_n1/result.json') + '#/phases')
    natives = []
    for job, saved in (('whole_milp', whole), ('linked_n1', linked)):
        method_rounds = saved['rounds'] if job == 'whole_milp' else [r for p in saved['phases'] for sc in p['scenes'].values() for r in sc['solver_result']['rounds']]
        round_by_request = {r['request_number']: r for r in method_rounds}
        for request_path in sorted((OLD / job / 'matlab').glob('*.request.json')):
            req = load(request_path)
            n = int(request_path.name.split('.')[0].split('_')[1])
            response_path = request_path.with_name(request_path.name.replace('.request.json', '.response.json'))
            response = load(response_path) if response_path.exists() else None
            rec = round_by_request.get(n, {})
            effective = (response.get('options') or {}).get('MaxTime') if response else None
            actual = (response.get('phase_seconds') or {}).get('intlinprog_call') if response else None
            row = dict(job=job, request_number=n, request_root_remaining_s=req.get('remaining_s'),
                       request_solver_MaxTime_declared_s=req.get('solver_max_time_s_declared'),
                       request_solver_MaxTime_upper_s=req.get('solver_max_time_s'),
                       native_effective_MaxTime_s=effective,
                       native_effective_MaxTime_status='SAVED_NATIVE_DIAGNOSTIC' if effective is not None else 'UNKNOWN',
                       actual_native_call_s=actual,
                       stop_delay_over_native_effective_MaxTime_s=None if effective is None or actual is None else max(0, actual-effective),
                       method_budget_valid=rec.get('budget_valid'),
                       accepted_for_evaluation=rec.get('accepted_for_evaluation'),
                       method_boundary_status=rec.get('status'),
                       response_diagnostic_only_not_new_U=not bool(rec.get('budget_valid')),
                       request_source=ref(request_path), response_source=ref(response_path) if response else None)
            natives.append(row)
            for key, value in row.items():
                if key.endswith('_s'):
                    status = 'UNKNOWN' if value is None else 'SAVED_NATIVE_DIAGNOSTIC' if key in ('native_effective_MaxTime_s', 'actual_native_call_s', 'stop_delay_over_native_effective_MaxTime_s') else 'SAVED_REQUEST_UPPER_LIMIT_NOT_NATIVE_EFFECTIVE'
                    metric(job, 'native_request', n, key, value, status, 's', row['response_source'] if key in ('native_effective_MaxTime_s', 'actual_native_call_s', 'stop_delay_over_native_effective_MaxTime_s') else row['request_source'])
    for job in ('heft', 'sa101'):
        assert not (OLD / job / 'result.json').exists()
        methods[job] = dict(status='NOT_RUN', matlab_startup=dict(status='NOT_RUN', wall_s=None),
                            future_existing_pure_python_entry_matlab_applicability='NOT_APPLICABLE',
                            first_complete_SAFE_at_s=None, first_strict_improvement_at_s=None)
        metric(job, 'method', '', 'method_time_s', None, 'NOT_RUN', 's', 'K142 result absent; no historical fill-in')
        metric(job, 'matlab_startup', '', 'wall_s', None, 'NOT_RUN', 's', 'future unchanged pure-Python entry is NOT_APPLICABLE, not measured zero')
    checks = dict(first_strict_independently_interval_verified_and_matches_audit=first_strict == review['first_strict_improvement_vs_initial_at_s'],
                  phase2_no_interval_strict_update=phases[1]['first_strict_improvement_at_root_s'] is None,
                  startup_values_match=abs(methods['whole_milp']['matlab_startup']['wall_s']-17.125)<1e-8 and abs(methods['linked_n1']['matlab_startup']['wall_s']-72.297)<1e-8,
                  phase_values_match=abs(phases[0]['inclusive_phase_s']-219.953)<1e-8 and abs(phases[1]['inclusive_phase_s']-77.687)<1e-8,
                  final_native_effective_distinct_from_request_upper=natives[-1]['native_effective_MaxTime_s'] != natives[-1]['request_solver_MaxTime_upper_s'],
                  final_late_response_diagnostic_only=natives[-1]['response_diagnostic_only_not_new_U'])
    assert all(checks.values())
    after = {name: sha(REPO/name) for name in SOURCES}
    assert after == SOURCES, 'read sources changed during extraction'
    output = dict(stage='K143', scope='stored JSON extraction only; no new candidate, decoding, thermal evaluation, solver, U or production change',
                  methods=methods, linked_phases=phases, scene_slices=slices,
                  native_requests=natives, interval_strict_complete_updates=strict_updates,
                  checks=checks, passed=all(checks.values()), sources_sha256=SOURCES,
                  source_hashes_after=after, sources_unchanged=True,
                  extraction_script_sha256=sha(Path(__file__)),
                  caveats=['K142 remains two executed calls, not completed four-method comparison',
                           'late raw native response values are diagnostics only, never new accepted U',
                           'request solver_max_time_s is an upper limit; response.options.MaxTime is native effective',
                           'NOT_RUN differs from NOT_APPLICABLE and UNKNOWN; missing values are not zero',
                           'derived clocks describe this execution only; no stability or causal speed claim'])
    (HERE/'timing_metrics.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (HERE/'timing_metrics.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['job','section','id','metric','value','status','unit','source'])
        writer.writeheader()
        writer.writerows(ROWS)
    print(json.dumps(dict(passed=True, checks=checks, saved_sources=len(SOURCES), rows=len(ROWS)), ensure_ascii=False))


if __name__ == '__main__':
    main()
