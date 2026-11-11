"""K125 N1 lifecycle checks: mocked native protocol, real small physical path.

No LP/MILP or MATLAB is started. The physical integration fixture returns its
freshly admitted x0 through the existing callback protocol; it is not a search
or an energy-improvement experiment. Existing results are never seed inputs.
"""
import argparse
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

import numpy as np
import scipy.optimize
import matlab_bridge
import milp
import neighborhood_method
import scene_adapter
import thermal
from control_policy import with_auto_low_idle
from inputs import load_config
from test_partial_deployment import small_case

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE_CHECKS = HERE/'results/neighborhood_precheck01/checks.json'
TESTS = ('test_neighborhood_method', 'test_partial_method', 'test_neighborhood_adapter')
NEW = ('neighborhood_method.py', 'test_neighborhood_method.py',
       'run_neighborhood_method_precheck.py', 'test_partial_method.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_bytes((json.dumps(value, ensure_ascii=False, indent=2,
        default=str, allow_nan=False)+'\n').encode('utf-8'))


def source_identity():
    old = json.loads(BASE_CHECKS.read_text(encoding='utf-8'))
    if old['passed'] is not True:
        raise ValueError('K124 basis is not passed')
    changed = [p for p, digest in old['source_sha256'].items() if sha(REPO/p) != digest]
    if changed:
        raise ValueError('K124 source/input changed: '+str(changed))
    paths = set(old['source_sha256']) | {'research/chapter3_experiments/'+p for p in NEW}
    return {p: sha(REPO/p) for p in sorted(paths)}


def physical_lifecycle(out):
    """Two real small models/thermal paths, native request transport mocked."""
    config = with_auto_low_idle(load_config())
    instance, shared, _ = small_case()
    before = scene_adapter.canonical_hash(instance)
    opened = {s['id']: [t['id'] for t in s['stage_instances']
                       if t['shared_stage_id'] != 'A.pre'] for s in instance['scenarios']}
    sessions, requests, construction = [], [], []

    def loader(budget):
        budget.check()
        return deepcopy(config), deepcopy(instance)

    def builder(original, cfg, **kwargs):
        construction.append({'scene_id': kwargs['fixed_scene_id'],
            'condition_sha256': kwargs['neighborhood_condition']['condition_sha256'],
            'original_input_sha256': scene_adapter.canonical_hash(original),
            'budget_id': id(kwargs['budget'])})
        return milp.build_model(original, cfg, **kwargs)

    class EchoSession:
        """Echo a validated x0, not an optimizer and not a reference answer."""
        def __init__(self, folder, *, total_budget_s, budget):
            self.workdir = Path(folder)
            self.workdir.mkdir(parents=True, exist_ok=False)
            self.budget = budget
            self.counter = 0
            self.event_consumer = None
            self.closed = False
            self.request_blocked = False
            sessions.append(self)

        def solve(self, payload, *, remaining_s, budget, x0=None, **kwargs):
            budget.check()
            assert budget is self.budget and x0 is not None
            # Repeat full numerical row admission on the exact submitted model.
            admitted = matlab_bridge._prepare(payload, x0=x0)
            assert admitted['x0_validation']['accepted_numerically'] is True
            vector = np.asarray(x0).reshape(-1).tolist()
            self.counter += 1
            prefix = self.workdir/('request_%03d'%self.counter)
            requests.append({'mock_native': True, 'remaining_s': remaining_s,
                'budget_id': id(budget), 'dimension': len(vector),
                'x0_validation': admitted['x0_validation']})
            for sequence, event in enumerate(({'kind': 'solver_entered'},
                    {'kind': 'incumbent', 'x': vector, 'values': {}}), 1):
                save(Path(str(prefix)+'.event_%06d.json'%sequence), event)
                if self.event_consumer is not None:
                    self.event_consumer(prefix)
            return {'status': 'SOLVED', 'x': vector, 'exitflag': 1,
                'budget_valid': budget.remaining > 0,
                'accepted_for_evaluation': budget.remaining > 0,
                'intlinprog_entered': False, 'output': {}, 'callbacks': [],
                'precheck_transport': 'mock echoes fresh validated x0; no native solver'}

        def close(self):
            self.event_consumer = None
            self.closed = True

    result = neighborhood_method.execute_n1_neighborhood(loader, out/'physical_call',
        shared_deployment=shared, opened_by_scene=opened, seconds=180,
        model_builder=builder, session_factory=EchoSession)
    save(out/'physical_fixture_result.json', result)
    assert result['state'] == 'SAFE', result.get('reason')
    assert result['reason'] == 'SCENE_SEARCH_SEQUENCE_COMPLETE', result.get('error')
    assert result['safe_upper_bound_J'] == result['initial_global_safe_upper_bound_J']
    assert result['weighted_energy_J'] == result['initial_global_weighted_energy_J']
    assert not result['independently_proven_optimal']
    assert not result['independently_proven_infeasible']
    assert not result['inner_MILP_improved_initial_upper_bound']
    assert len(sessions) == 1 and len(requests) == len(instance['scenarios']) == 2
    assert sessions[0].closed and sessions[0].event_consumer is None
    assert all(r['dimension'] > 1 for r in requests)
    assert len({r['budget_id'] for r in requests+construction}) == 1
    assert all(r['original_input_sha256'] == before for r in construction)
    assert scene_adapter.canonical_hash(instance) == before
    assert scene_adapter.canonical_hash(result['aggregation']['safe_candidate']) == scene_adapter.canonical_hash(result['safe_candidate'])
    save(out/'physical_fixture_input.json', {'config': config, 'instance': instance,
        'shared_deployment': shared, 'opened_by_scene': opened})
    return {'passed': True, 'scope': 'small correctness fixture, mocked request transport, real physical evaluator',
        'fresh_complete_safe_seed_before_condition_model': True,
        'original_all_scene_aggregate_only': True,
        'same_energy_as_this_call_seed': True,
        'original_input_unchanged': True, 'construction': construction,
        'requests': requests, 'native_calls': 0, 'optimizer_calls': 0, 'research_calls': 0}


def run(out):
    out = Path(out).resolve()
    out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    before = source_identity()
    for name in before:
        destination = out/'source_snapshot'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPO/name).read_bytes())
    save(out/'source_sha256.json', before)
    started = time.monotonic()
    output, result, physical, error = io.StringIO(), None, None, None
    counts = {'small_models': 0, 'real_thermal_evaluations': 0}
    old_model, old_heat = milp.Model.__init__, thermal.evaluate_piecewise

    def count_model(self, *args, **kwargs):
        counts['small_models'] += 1
        return old_model(self, *args, **kwargs)

    def count_heat(*args, **kwargs):
        counts['real_thermal_evaluations'] += 1
        return old_heat(*args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError('Native optimizer is outside K125 precheck scope')

    prior_temp = tempfile.tempdir
    temp = REPO/'.runtime/k125_precheck'
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
                physical = physical_lifecycle(out)
                save(out/'physical_checks.json', physical)
    except Exception:
        error = traceback.format_exc()
        output.write(error)
    finally:
        tempfile.tempdir = prior_temp
    (out/'unittest.txt').write_bytes(output.getvalue().encode('utf-8'))
    after = source_identity()
    passed = bool(result and result.wasSuccessful() and physical is not None
                  and error is None and before == after)
    report = {'protocol': 'K125-n1-method-lifecycle-precheck-v1', 'passed': passed,
        'tests_run': 0 if result is None else result.testsRun,
        'failures': None if result is None else len(result.failures),
        'errors': None if result is None else len(result.errors), 'error': error,
        'source_sha256': after, 'source_unchanged': before == after,
        'basis': {'path': str(BASE_CHECKS.relative_to(REPO)), 'sha256': sha(BASE_CHECKS),
                  'scope': 'unchanged K124 files only, not a new whole-suite gate'},
        'test_targets': TESTS, 'physical_lifecycle_completed': physical is not None,
        **counts, 'original_size_models': 0, 'optimizer_calls': 0,
        'native_calls': 0, 'research_calls': 0, 'elapsed_s': time.monotonic()-started,
        'environment': {'python': sys.version, 'platform': platform.platform()},
        'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'checks.json', report)
    save(out/'unit_details.json', {name: getattr(sys.modules.get(name), 'RECORDS', {}) for name in TESTS})
    print(json.dumps({key: report[key] for key in
        ('passed', 'tests_run', 'failures', 'errors', 'error', 'elapsed_s')}, ensure_ascii=False), flush=True)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
