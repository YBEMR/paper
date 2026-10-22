"""K165 existing-request transport/native audit. Never launch a solver or heat."""
from contextlib import ExitStack
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch
import warnings

import numpy as np
from scipy.io import loadmat, whosmat
import scipy.optimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = ROOT.parents[1]
FOLDER = ROOT/'results/deadline_resume01/calls/beta_1.0__R2/whole_milp'
LIBRARY = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/toolbox/optim/optim/intlinprog.m')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def normalize(value, key=None):
    """Compare MAT numeric empties and MATLAB char empties to original JSON."""
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return '' if value.dtype.kind in 'US' else []
        return normalize(value.tolist(), key)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: normalize(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v, key) for v in value]
    return value


def matches(source, fragment):
    return fragment in Path(source).read_text(encoding='utf-8')


def audit():
    archive = ROOT/'results/deadline_resume01'
    if not (archive/'process_terminal.json').is_file():
        raise RuntimeError('Stopped campaign evidence required')
    declaration = read(archive/'declaration.json')
    frozen = declaration['source_sha256']
    originals = declaration['prior_artifact_sha256']
    original_files = {p.relative_to(REPO).as_posix(): sha(p)
                      for p in sorted(FOLDER.rglob('*')) if p.is_file()}
    guards = dict.fromkeys(('subprocess', 'LP', 'MILP'), 0)
    def forbidden(key):
        def fail(*args, **kw):
            guards[key] += 1
            raise AssertionError('Forbidden transport-audit call: '+key)
        return fail
    with ExitStack() as stack:
        stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess')))
        stack.enter_context(patch.object(scipy.optimize, 'linprog', side_effect=forbidden('LP')))
        stack.enter_context(patch.object(scipy.optimize, 'milp', side_effect=forbidden('MILP')))
        raw = read(FOLDER/'wrapper_raw_result.json')
        row = read(archive/'claims/beta_1.0__R2__whole_milp_result.json')
        meta = read(FOLDER/'matlab/request_000001.input.json')
        init = read(FOLDER/'matlab/request_000001.initial.json')
        req = read(FOLDER/'matlab/request_000001.request.json')
        native_json = read(FOLDER/'matlab/request_000001.response.json')
        python = read(FOLDER/'matlab/request_000001.python.json')
        session = read(FOLDER/'matlab/session.json')
        root_budget = read(FOLDER/'method_budget_identity.json')
        cleanup = read(FOLDER/'matlab/closed.json')
        event_paths = sorted((FOLDER/'matlab').glob('request_000001.event_*.json'))
        events = [read(p) for p in event_paths]
        payload_shape = whosmat(FOLDER/'matlab/request_000001.mat')
        payload = loadmat(FOLDER/'matlab/request_000001.mat',
            variable_names=['c', 'intcon', 'x0', 'x0_validation', 'remaining_s', 'cut_max_iterations'],
            simplify_cells=True)
        # The native opts object is MATLAB opaque data. Select only the native
        # numeric/struct variables; no MATLAB process or object execution.
        native = loadmat(FOLDER/'matlab/request_000001.native.mat',
            variable_names=['initialPoint', 'x', 'fval', 'exitflag', 'output', 'callbacks'],
            simplify_cells=True)
        x0 = np.asarray(payload['x0'], dtype=np.float64).reshape(-1)
        received = np.asarray(native['initialPoint'], dtype=np.float64).reshape(-1)
        initial_objective = float(np.dot(np.asarray(payload['c']).reshape(-1), x0))
        integer_indices = np.asarray(payload['intcon']).reshape(-1)
        callbacks = [v for v in events if v.get('kind') == 'callback']
        done = [v for v in callbacks if v.get('state') == 'done']
        entry = [v for v in events if v.get('kind') == 'solver_entered']
        recorded_native_callbacks = normalize(native['callbacks'])
        if isinstance(recorded_native_callbacks, dict):
            recorded_native_callbacks = [recorded_native_callbacks]
        # solve_model deliberately removes event.kind/number from neither path;
        # the immutable event's vector is copied into response as empty only
        # after publication. Here both original event vectors are empty too.
        checks = {
            'actual_release_and_entry_bound': read(FOLDER/'matlab/ready.json')['release'] == '2023b'
                and session['method_deadline_bound'] is True,
            'payload_has_real_double_full_x0': dict((name, (tuple(shape), kind))
                for name, shape, kind in payload_shape)['x0'] == ((23464, 1), 'double')
                and x0.size == 23464 and np.isfinite(x0).all(),
            'same_x0_saved_by_native_worker_exactly': np.array_equal(x0, received)
                and x0.tobytes() == received.tobytes(),
            'objective_matches_at_all_transport_points': initial_objective
                == init['initial_objective'] == meta['initial_point']['initial_objective']
                == native_json['initial_point']['initial_objective'],
            'original_x0_admission_metadata_preserved': normalize(payload['x0_validation']) == init
                == meta['initial_point'] == native_json['initial_point']['python_admission'],
            'integer_indices_have_correct_matlab_one_based_range': integer_indices.size == 1131
                and np.array_equal(integer_indices, np.arange(1, 1132, dtype=float))
                and meta['intcon_convention'] == 'Python_zero_based_converted_to_MATLAB_one_based',
            'first_request_x0_wrapper_present': matches(ROOT/'initial_point.py',
                'return self.session.solve(model, x0=self.x0, **kwargs)'),
            'bridge_serializes_x0_as_column_without_new_rounding': matches(ROOT/'matlab_bridge.py',
                "savemat(str(temporary), payload, appendmat=False, oned_as='column')")
                and matches(ROOT/'matlab_bridge.py', "result['x0'], result['x0_validation'] = _check_initial_point(result, x0)"),
            'worker_passes_x0_as_ninth_argument_options_as_tenth': matches(ROOT/'solve_model.m',
                'p.A,p.b(:),p.Aeq,p.beq(:),p.lb(:),p.ub(:),initialPoint,opts);')
                and matches(ROOT/'solve_model.m', 'initialPoint=p.x0(:);'),
            'installed_R2023b_function_matches_call_signature': matches(LIBRARY,
                'function [x, fval, exitflag, output] = intlinprog(f, intcon, A, b, Aeq, beq, lb, ub, x0, options)')
                and matches(LIBRARY, 'problem.x0 = x0;'),
            'native_output_and_json_agree_before_python_diagnostic': normalize(native['output']) == native_json['output']
                and int(native['exitflag']) == native_json['exitflag'] == python['exitflag'] == -2
                and np.asarray(native['x']).size == np.asarray(native['fval']).size == 0
                and native_json['x'] == python['x'] == native_json['fval'] == python['fval'] == [],
            'native_callbacks_and_response_agree': recorded_native_callbacks == native_json['callbacks'],
            'immutable_events_agree_with_native_callbacks': callbacks == native_json['callbacks']
                and [e['event_number'] for e in events] == [1, 2, 3],
            'done_callback_has_no_hidden_new_vector': len(done) == 1
                and done[0]['x'] == [] and done[0]['values']['fval'] == []
                and done[0]['values']['numfeaspoints'] == 1
                and native_json['output']['numfeaspoints'] == 0,
            'native_options_match_unchanged_declared_tolerances':
                native_json['options']['ConstraintTolerance'] == 1e-9
                and native_json['options']['IntegerTolerance'] == 1e-6
                and native_json['options']['AbsoluteGapTolerance'] == 0
                and native_json['options']['RelativeGapTolerance'] == 0
                and native_json['options']['IntegerPreprocess'] == 'none'
                and native_json['options']['LPPreprocess'] == 'none',
            'cut_limit_same_in_json_mat_effective_options': req['cut_max_iterations']
                == int(payload['cut_max_iterations']) == meta['cut_max_iterations_declared']
                == native_json['cut_max_iterations_actual_effective'] == native_json['options']['CutMaxIterations'] == 10,
            'raw_solver_response_before_absolute_root_deadline': python['budget_valid'] is True
                and python['solver_response_complete_at_monotonic'] < root_budget['deadline']
                and root_budget['start']+300 == root_budget['deadline'] == meta['absolute_deadline']
                and raw['timing']['method_elapsed_s'] < 300 and raw['budget_exhausted'] is False,
            'native_call_below_its_own_time_allocation': native_json['phase_seconds']['intlinprog_call']
                < native_json['options']['MaxTime'] < req['remaining_s']
                and native_json['worker_elapsed_seconds'] < session['worker_guard_seconds'],
            'no_native_callback_or_warning_error_archived': not native_json.get('callback_error')
                and not native_json.get('error_identifier') and not native_json.get('error_message')
                and native_json['solver_warning_identifier'] == native_json['solver_warning_message'] == '',
            'python_did_not_promote_native_infeasible_flag_to_a_certificate': python['accepted_for_evaluation'] is False
                and python['numerical_consistency']['independent_certificate'] is False
                and python['numerical_consistency']['worker_solver_x0_acceptance'] == 'not_independently_observed'
                and raw['independently_proven_infeasible'] is False,
            'safe_U_remains_original_value_and_formation_time': row['records']['usable_U_J'] == raw['safe_upper_bound_J']
                and row['records']['execution']['usable_safe_formed_at_s'] == raw['evaluation']['completed_at_elapsed_s']
                and not (FOLDER/'postcheck.json').exists() and not (FOLDER/'postcheck.claim.json').exists(),
            'source248_and_old_two_slot_archive_unchanged': len(frozen) == 248
                and all(sha(REPO/name) == h for name, h in frozen.items())
                and all(sha(REPO/name) == h for name, h in originals.items()),
            'stopped_original_request_files_unchanged': all(sha(REPO/name) == h for name, h in original_files.items()),
            'no_process_LP_or_MILP_call': not any(guards.values()),
        }
    checks = {name: bool(value) for name, value in checks.items()}
    libraries = {LIBRARY.as_posix(): sha(LIBRARY)}
    return {
        'protocol': 'K165-readonly-native-x0-transport-review-v1',
        'passed': all(checks.values()), 'checks_run': len(checks), 'checks': checks,
        'failed_checks': [k for k, v in checks.items() if not v],
        'slot_id': 'beta_1.0__R2__whole_milp',
        'located_transport_bug': None,
        'located_metadata_scope_issue': {
            'source': 'p0_batch/audit_whole.py:105-109 -> execution_status.py:144-147',
            'fact': 'A status-consistency diagnostic sets observed_numerical_rejection=True; '
                    'the shared reason then says ACTUAL_NUMERICAL_REPORT_REJECTED although '
                    'all archived x0 residual admissions passed.',
            'effect': 'It overstates the kind of numerical evidence; retaining unresolved status '
                      'and halting remains appropriate. No reclassification or repair performed.'},
        'excluded_from_saved_artifacts': [
            'x0 absent or truncated in MAT transport', 'worker initialPoint differs from input x0',
            'ninth/tenth intlinprog argument swap', 'wrong one-based intcon range',
            'Python rewrote native -2 to create the disagreement',
            'JSON discarded a nonempty native solution vector',
            'done event contained a usable hidden candidate', 'response outside root300 deadline'],
        'not_established': [
            'native solver internally accepted x0 as incumbent',
            'the exact real-arithmetic MILP is feasible',
            'the native -2 report is an independently checked infeasibility certificate',
            'a particular scaling/cut/internal-tolerance step caused the outcome',
            'every callback stop return was false (return values were not archived)',
            'a general solver defect or a mathematically contradictory proof'],
        'x0_facts': {'length': int(x0.size), 'same_payload_and_native_bytes': True,
            'payload_and_native_vector_sha256': sha256(x0.tobytes()).hexdigest(),
            'objective_dot': initial_objective, 'integer_index_count': int(integer_indices.size),
            'integer_index_first_last': [int(integer_indices.min()), int(integer_indices.max())]},
        'native_return': {'status': native_json['status'], 'exitflag': native_json['exitflag'],
            'x': native_json['x'], 'fval': native_json['fval'], 'output': native_json['output'],
            'callbacks': native_json['callbacks'], 'phase_seconds': native_json['phase_seconds'],
            'options': native_json['options']},
        'clock_facts': {'root_method_elapsed_s': raw['timing']['method_elapsed_s'],
            'native_request_allocation_s': req['remaining_s'],
            'native_MaxTime_s': native_json['options']['MaxTime'],
            'native_intlinprog_call_s': native_json['phase_seconds']['intlinprog_call'],
            'native_done_request_wall_s': done[0]['request_wall_seconds'],
            'native_done_optimValues_time_s': done[0]['values']['time'],
            'python_response_root_elapsed_s_exact_from_recorded_decimals':
                str(F(str(python['solver_response_complete_at_monotonic']))-F(str(root_budget['start']))),
            'worker_elapsed_s': native_json['worker_elapsed_seconds'],
            'worker_guard_s': session['worker_guard_seconds'],
            'clock_origins_are_distinct': True, 'callback_stop_returns_recorded': False},
        'MAT_reader_scope': 'scipy.io.loadmat selected numeric/struct variables; native opts '
            'is a MATLAB opaque object and was not executed or decoded. Full whosmat on that '
            'native object raises a SciPy TypeError; this reader limitation is unrelated to '
            'the original solver stop. Numeric/struct original fields loaded successfully.',
        'official_sources_checked': [
            {'url': 'https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html',
             'scope': 'Syntax, x0 input, exitflag/output, not current-version algorithm behavior'},
            {'url': 'https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html',
             'scope': 'Callback x/state/numfeaspoints/time meanings'}],
        'artifact_sha256': original_files, 'frozen_source_sha256': frozen,
        'installed_R2023b_library_sha256': libraries,
        'source_locations': {'one_call_x0_injection': 'initial_point.py:175-193',
            'x0_preparation_and_one_based_conversion': 'matlab_bridge.py:194-219',
            'request_MAT_JSON_publication': 'matlab_bridge.py:563-656',
            'status_diagnostic_no_certificate': 'matlab_bridge.py:223-249',
            'response_budget_and_status_admission': 'matlab_bridge.py:690-716',
            'MAT_x0_load': 'solve_model.m:36-44', 'native_call': 'solve_model.m:155-156',
            'native_archive': 'solve_model.m:174-178', 'callback': 'solve_model.m:208-231',
            'installed_signature': str(LIBRARY)+':1', 'installed_x0_assignment': str(LIBRARY)+':184'},
        'blocked_calls': guards, 'review_source_sha256': sha(__file__),
        'new_research_calls': 0, 'new_LP_MILP_solves': 0, 'new_thermal_evaluations': 0,
        'new_post': False, 'source_or_original_data_modified': False,
        'tolerances_changed': False, 'remaining24_started': False,
        'conclusion': 'The saved transport chain passes and the numerical-status discrepancy '
            'already exists in native evidence. The precise solver-side cause remains unresolved. '
            'The old safe U survives; no proof, new candidate, normal-cutoff reclassification '
            'or execution authorization follows from this read-only audit.'}


if __name__ == '__main__':
    report = audit()
    serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    with (HERE/'transport_review.json').open('x', encoding='utf-8') as stream:
        stream.write(serialized+'\n')
    print(json.dumps({k: report[k] for k in ('passed', 'checks_run', 'failed_checks',
        'located_transport_bug', 'x0_facts', 'clock_facts', 'blocked_calls')}, ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)
