"""K124 N1 interface checks, small fixtures only; no optimizer or research run."""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

import numpy as np
import scipy.optimize
import milp
import matlab_bridge
import neighborhood
import neighborhood_adapter
import scene_adapter
import thermal
from control_policy import with_auto_low_idle
from inputs import load_config
from initial_point import complete_initial_point
from test_partial_deployment import small_case
from thermal import Budget

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASELINE = 'bd9293c5572a3d7e3e930aad19b41e22c73431e2'
BASE_GATE = HERE/'results/cumulative_pair_precheck01/checks.json'
TESTS = ('test_neighborhood_condition', 'test_neighborhood_milp',
         'test_neighborhood_adapter', 'test_cumulative_precedence')
EXTRA = ('neighborhood.py', 'neighborhood_adapter.py',
         'test_neighborhood_condition.py', 'test_neighborhood_milp.py',
         'test_neighborhood_adapter.py', 'run_neighborhood_precheck.py',
         'test_partial_deployment.py', 'test_control_policy.py',
         'test_auto_milp.py', 'run_scene_precheck.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2,
        default=str, allow_nan=False)+'\n').encode('utf-8'))


def source_identity():
    baseline = json.loads(BASE_GATE.read_text(encoding='utf-8'))['source_sha256']
    unchanged = [p for p, h in baseline.items()
                 if p != 'research/chapter3_experiments/milp.py' and sha(REPO/p) != h]
    if unchanged:
        raise ValueError('Untouched baseline files changed: '+str(unchanged))
    names = set(baseline) | {'research/chapter3_experiments/'+p for p in EXTRA}
    return {p: sha(REPO/p) for p in sorted(names)}


def fingerprint(payload):
    result = {}
    for name, value in payload.items():
        arrays = (value.indptr, value.indices, value.data) if name in ('A', 'Aeq') else (value,)
        result[name] = {'shape': list(value.shape), 'arrays': [
            {'dtype': str(a.dtype), 'shape': list(a.shape),
             'sha256': hashlib.sha256(a.tobytes()).hexdigest()} for a in arrays]}
    return result


def default_identity(out):
    raw = subprocess.check_output(['git', 'show',
        BASELINE+':research/chapter3_experiments/milp.py'], cwd=REPO)
    path = out/'reference_milp.py'
    path.write_bytes(raw)
    spec = importlib.util.spec_from_file_location('_k124_previous_milp', path)
    previous = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = previous
    spec.loader.exec_module(previous)
    case, shared, _ = small_case()
    cfg = with_auto_low_idle(load_config())
    flags = dict(include_physics=False, fixed_shared_deployment=shared,
                 prefilter_deadlines=True, relax_auxiliary_integrality=True)
    old = previous.build_model(deepcopy(case), cfg, budget=Budget(seconds=120), **flags)
    current = milp.build_model(deepcopy(case), cfg, budget=Budget(seconds=120), **flags)
    a, b = fingerprint(old.as_solver_dict()), fingerprint(current.as_solver_dict())
    assert a == b and old.summary() == current.summary()
    assert old.rows == current.rows and old.names == current.names
    assert old.options == current.options
    return {'passed': True, 'baseline_commit': BASELINE,
        'reference_source_sha256': sha(path),
        'scope': 'one small structural fixture, no physics coefficients or solve',
        'old_and_new_default_exports_rows_options_summary_identical': True,
        'fingerprint': b, 'summary': current.summary()}


def physical_roundtrip(out):
    """One fresh small SAFE seed, conditional model and original-input checks."""
    cfg = with_auto_low_idle(load_config())
    case, shared, candidates = small_case()
    budget = Budget(seconds=180)
    accuracy = cfg['accuracy_targets']
    receipts = {sid: scene_adapter.evaluate_partial_scene(
        case, sid, shared, candidate, accuracy, budget)
        for sid, candidate in candidates.items()}
    seed = scene_adapter.aggregate_partial_scene_receipts(
        case, shared, receipts, candidates, accuracy, budget)
    assert seed['state'] == 'SAFE', seed['reason']
    opened = {sid: [r['stage_id'] for r in c['scenes'][sid]
                   if 'A.pre' not in r['stage_id']] for sid, c in candidates.items()}
    condition = neighborhood.make_n1_condition(case, shared, seed['safe_candidate'],
        seed, opened, budget=budget, accuracy=accuracy)
    sid = case['scenarios'][0]['id']
    model = milp.build_model(case, cfg, budget=budget,
        fixed_shared_deployment=shared, fixed_scene_id=sid,
        neighborhood_condition=condition, prefilter_deadlines=True,
        relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)
    local = candidates[sid]
    wrapper = neighborhood_adapter.evaluate_n1_scene(
        case, condition, sid, local, budget=budget, accuracy=accuracy)
    assert wrapper['state'] == 'SAFE', wrapper['reason']
    assert wrapper['receipt']['identity']['full_input_sha256'] == scene_adapter.canonical_hash(case)
    checked = milp.evaluate_model_candidate(model, local, accuracy, budget)
    assert checked['state'] == 'SAFE'
    completion = complete_initial_point(model, local, checked, budget)
    assert completion['state'] == 'INITIAL_POINT_READY', completion
    assert completion['decoded_roundtrip'] is True
    assert milp.decode(model, completion['x0']) == local
    updated = dict(receipts)
    updated[sid] = wrapper['receipt']
    merged = scene_adapter.aggregate_partial_scene_receipts(
        case, shared, updated, candidates, accuracy, budget)
    assert merged['state'] == 'SAFE' and merged['safe_candidate'] == seed['safe_candidate']
    assert merged['weighted_energy_J'] == seed['weighted_energy_J']
    assert not merged['independently_proven_optimal']
    save(out/'physical_fixture.json', {'input': case, 'candidates': candidates,
        'seed_aggregate': seed, 'condition': condition, 'wrapper': wrapper,
        'model_evaluation': checked, 'x0_completion': {
            **completion, 'x0': completion['x0'].tolist()},
        'model_summary': model.summary(), 'final_aggregate': merged})
    return {'passed': True, 'scope': 'small correctness fixture, no optimization or new research U',
        'model_complete_and_seed_retained': True, 'original_input_receipt_matches': True,
        'x0_decoded_and_full_matrix_numerically_admitted': True,
        'same_complete_window_energy_after_original_merge': True,
        'method_implemented': False, 'research_calls': 0}


def run(out):
    out = Path(out).resolve()
    out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    before = source_identity()
    for name in before:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    save(out/'source_sha256.json', before)
    started = time.monotonic()
    output = io.StringIO()
    result = reference = physical = None
    error = None
    counts = {'current_small_models': 0, 'real_thermal_evaluations': 0}
    old_init = milp.Model.__init__
    original_heat = thermal.evaluate_piecewise

    def count_model(self, *args, **kwargs):
        counts['current_small_models'] += 1
        return old_init(self, *args, **kwargs)

    def count_heat(*args, **kwargs):
        counts['real_thermal_evaluations'] += 1
        return original_heat(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError('Optimizer/native execution is outside K124 scope')

    previous_temp = tempfile.tempdir
    temp = REPO/'.runtime/k124_precheck'
    temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temp)
    try:
        with ExitStack() as stack, redirect_stdout(output), redirect_stderr(output):
            for owner, name in ((scipy.optimize, 'linprog'), (scipy.optimize, 'milp'),
                                (matlab_bridge.MatlabSession, '__init__')):
                stack.enter_context(patch.object(owner, name, side_effect=forbidden))
            stack.enter_context(patch.object(milp.Model, '__init__', count_model))
            stack.enter_context(patch.object(thermal, 'evaluate_piecewise', count_heat))
            stack.enter_context(patch.object(scene_adapter, 'evaluate_piecewise', count_heat))
            suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            if result.wasSuccessful():
                reference = default_identity(out)
                save(out/'default_identity.json', reference)
                physical = physical_roundtrip(out)
                save(out/'physical_checks.json', physical)
    except Exception:
        error = traceback.format_exc()
        output.write(error)
    finally:
        tempfile.tempdir = previous_temp
    (out/'unittest.txt').write_bytes(output.getvalue().encode('utf-8'))
    after = source_identity()
    passed = (result is not None and result.wasSuccessful() and reference is not None
              and physical is not None and error is None and before == after)
    report = {'protocol': 'K124-n1-condition-integration-precheck-v1',
        'passed': passed, 'tests_run': 0 if result is None else result.testsRun,
        'failures': None if result is None else len(result.failures),
        'errors': None if result is None else len(result.errors),
        'test_targets': TESTS, 'source_sha256': after,
        'source_unchanged': before == after, 'old_whole_gate_claimed_current': False,
        'default_identity_completed': reference is not None,
        'physical_roundtrip_completed': physical is not None, **counts,
        'original_size_models': 0, 'optimizer_calls': 0, 'research_calls': 0,
        'error': error, 'elapsed_s': time.monotonic()-started,
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'checks.json', report)
    save(out/'unit_details.json', {name: getattr(sys.modules.get(name), 'RECORDS', {})
                                 for name in TESTS})
    print(json.dumps({k: report[k] for k in ('passed', 'tests_run', 'failures',
        'errors', 'error', 'elapsed_s')}, ensure_ascii=False), flush=True)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
