"""Post-run static archival only; no solve, model construction or heat work."""
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'research/chapter3_experiments/fixed_integer_diagnostic'))
import core


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    started = time.monotonic()
    old_dir = REPO / 'research/chapter3_experiments/results/whole_long_budget01'
    d, r, terminal = [read(HERE / name) for name in ('declaration.json', 'method_return.json', 'terminal.json')]
    original, source = core.load_original_mat(old_dir / 'method/matlab/request_000001.mat')
    sent, sent_source = core.load_original_mat(HERE / 'matlab/request_000001.mat')
    identity = core.assert_only_fixed_integer_bounds_changed(original, sent)
    result = r['result']
    x, x0, ints = np.asarray(result['x']), original['x0'], original['intcon']
    changed = np.flatnonzero(x != x0)
    delta = x - x0
    exact_integer_match = np.array_equal(x[ints], x0[ints])
    old = read(old_dir / 'method/matlab/request_000001.response.json')
    raw_events = []
    for path in sorted((HERE / 'matlab').glob('request_000001.event_*.json')):
        event = read(path)
        vector = np.asarray(event.get('x', []))
        raw_events.append(dict(file=path.name, kind=event.get('kind'), state=event.get('state'),
            request_wall_seconds=event.get('request_wall_seconds'), values=event.get('values'),
            vector_length=int(vector.size),
            equals_x0_bitwise=bool(vector.dtype == x0.dtype and vector.tobytes() == x0.tobytes()) if vector.size else None))
    preserved = {}
    for name, info in d['source_files'].items():
        digest = hashlib.sha256((REPO / name).read_bytes()).hexdigest()
        preserved[name] = dict(sha256=digest, unchanged=digest == info['sha256'])
    assert all(v['unchanged'] for v in preserved.values())
    assert exact_integer_match
    report = dict(scope='post-run static archive; not new budgeted admission or physical validation',
        research_calls=1, native_requests=1, thermal_integrations=0, post_thermal_calls=0,
        retries=0, new_safe_or_U=False, numerical_version=d['numerical_version'],
        original_payload=source, transported_payload=sent_source, payload_identity=identity,
        original_sources=preserved, state=r['state'], technical_completion=r['technical_completion'],
        integer_options_exactly_original=exact_integer_match, changed_total_columns=int(len(changed)),
        changed_integer_columns=int(np.count_nonzero(delta[ints])),
        max_abs_coordinate_change=float(np.max(np.abs(delta))),
        max_change_column_1based=int(np.argmax(np.abs(delta))) + 1,
        changed_columns_1based=(changed + 1).tolist(),
        original_x0_objective=float(original['c'] @ x0), returned_auxiliary_objective=float(original['c'] @ x),
        auxiliary_objective_difference=float(original['c'] @ x - original['c'] @ x0),
        native_fval=result['fval'], original_vs_fixed_residuals=r['numeric'],
        method_elapsed_s=r['method_elapsed_s'], matlab_startup_s=next(
            p['end_s']-p['start_s'] for p in r['phases'] if p['phase']=='MATLAB_startup'),
        native_intlinprog_s=result['phase_seconds']['intlinprog_call'],
        native_request_s=result['matlab_request_wall_seconds'],
        root_numerical_acceptance_at_s=r['numeric_admission_completed_s'],
        controller_calendar_s=terminal['wall_s'],
        method_seconds_unused=300-r['method_elapsed_s'],
        cleanup_and_final_provenance_s=r['wall_including_cleanup_s']-r['method_elapsed_s'],
        original_native_exitflag=old['exitflag'], original_native_s=old['phase_seconds']['intlinprog_call'],
        new_native_exitflag=result['exitflag'], solver_output=result['output'],
        options_match_except_MaxTime=r['options_match_except_time'],
        original_MaxTime=old['options']['MaxTime'], new_MaxTime=result['options']['MaxTime'],
        callback_events=raw_events, lifecycle_complete=r['lifecycle_complete'],
        captured_processes_exited=terminal['observed_owned_processes_exited'],
        new_schedule=False, fixed_subproblem_optimality='solver-reported; no independent exact certificate',
        full_problem_optimality=False, free_integer_numerical_issue_resolved=False,
        analysis_seconds=time.monotonic()-started)
    with (HERE / 'analysis.json').open('x', encoding='utf-8', newline='\n') as out:
        json.dump(report, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    print(json.dumps({k: report[k] for k in ('state','changed_total_columns','changed_integer_columns',
        'max_abs_coordinate_change','auxiliary_objective_difference','method_elapsed_s','native_intlinprog_s',
        'controller_calendar_s')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
