"""K121 targeted cumulative-precedence integration checks, no optimizer.

Only correctness fixtures are constructed. A frozen pre-change builder is
compared with the default current builder including physical rows. Tests may
mock physical receipts, but never run a thermal trajectory or native solver.
Outputs are append-only new directories; prior failures remain available.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
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
import scipy
import scipy.optimize
from scipy.io import loadmat

import matlab_bridge
import milp
import scene_adapter
import thermal
from inputs import build_instance, load_config
from control_policy import with_auto_low_idle
from run_milp_precheck import select_fixture
from thermal import Budget


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASELINE = '229eef82f90a30b82d1138356adf170c11843de2'
TESTS = ('test_cumulative_precedence', 'test_cumulative_wrappers',
         'test_partial_method', 'test_partial_slice', 'test_shared_search')
BASE_DECLARATION = HERE/'results/cut_pair_diagnostic01/declaration.json'
CHANGED = {'research/chapter3_experiments/'+name for name in
           ('milp.py', 'partial_method.py', 'scene_method.py', 'shared_search.py')}
EXTRA = ('precedence_check.py', 'test_cumulative_precedence.py',
         'test_cumulative_wrappers.py', 'run_cumulative_precheck.py',
         'run_scene_precheck.py',
         'test_partial_method.py', 'test_partial_slice.py', 'test_shared_search.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    default=str, allow_nan=False)+'\n', encoding='utf-8')


def sources():
    baseline = json.loads(BASE_DECLARATION.read_text(encoding='utf-8'))['source_sha256']
    stale = [name for name, digest in baseline.items()
             if name not in CHANGED and sha(REPO/name) != digest]
    if stale:
        raise ValueError('Untouched baseline sources changed: '+str(stale))
    names = set(baseline) | {'research/chapter3_experiments/'+name for name in EXTRA}
    return {name: sha(REPO/name) for name in sorted(names)}


def matrix_fingerprint(payload):
    output = {}
    for name, value in payload.items():
        arrays = (value.indptr, value.indices, value.data) if name == 'A' or name == 'Aeq' else (value,)
        output[name] = {'shape': list(value.shape), 'arrays': [
            {'dtype': str(a.dtype), 'shape': list(a.shape),
             'sha256': hashlib.sha256(a.tobytes()).hexdigest()} for a in arrays]}
    return output


def reference_check(out):
    """One small physical chain, three builders; never a research instance."""
    raw = subprocess.check_output(['git', 'show', BASELINE+':research/chapter3_experiments/milp.py'], cwd=REPO)
    reference = out/'reference_milp.py'
    reference.write_bytes(raw)
    spec = importlib.util.spec_from_file_location('_k121_reference_milp', reference)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    cfg = with_auto_low_idle(load_config())
    base = with_auto_low_idle(build_instance(cfg, 'base__R1'))
    sid = base['scenarios'][0]['id']
    instance, starts = select_fixture(base, 'k121_reference_chain',
        {sid: ['A.pre', 'A.main']}, {'A.pre': [0], 'A.main': [10, 15]})
    flags = dict(fix_late_options=True, aggregate_opp_locks=True,
                 relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True)
    models = [builder(deepcopy(instance), deepcopy(cfg), starts=starts,
                      budget=Budget(seconds=120), **flags, **extra)
              for builder, extra in ((old.build_model, {}), (milp.build_model, {}),
                                     (milp.build_model, {'cumulative_precedence': True}))]
    previous, current, enabled = models
    a, b = previous.as_solver_dict(), current.as_solver_dict()
    identity = matrix_fingerprint(a) == matrix_fingerprint(b)
    assert identity and previous.rows == current.rows
    assert previous.names == current.names and previous.options == current.options
    assert previous.summary() == current.summary()
    kept = [r for r in enabled.rows if r['tag'] != 'dependency_cumulative']
    assert kept == current.rows
    assert enabled.names == current.names and enabled.options == current.options
    for name in ('lb', 'ub', 'integer', 'c', 'logical_binary'):
        assert getattr(enabled, name) == getattr(current, name), name
    added = [r for r in enabled.rows if r['tag'] == 'dependency_cumulative']
    assert added
    assert all(r['rhs'] == 0 and r['rounding_allowance'] == '0'
               and set(r['coef'].values()) <= {-1.0, 1.0} for r in added)
    report = {'passed': True, 'baseline_commit': BASELINE,
        'reference_source_sha256': sha(reference), 'scope': 'small physical correctness fixture only',
        'input_sha256': milp._digest(instance), 'starts': starts,
        'physical_model_builds': 3, 'default_export_matches_previous': identity,
        'default_summary_options_and_rows_match_previous': True,
        'enabled_only_adds_cumulative_rows': True,
        'added_rows': len(added), 'added_nnz': sum(len(r['coef']) for r in added),
        'fingerprint': matrix_fingerprint(b), 'summary': current.summary()}
    save(out/'default_matrix_identity.json', report)
    return report


def archived_row_check(out):
    """Export only local dependency rows from an already saved option catalog.

    No original-scale scheduling/physical model is rebuilt. Saved x0 is read
    only for y values, never decoded or accepted as a new safety witness.
    """
    audit = HERE/'results/cumulative_precedence_audit01'
    facts = json.loads((audit/'reproduced/costs.json').read_text(encoding='utf-8'))
    receipt = json.loads((audit/'verification.json').read_text(encoding='utf-8'))
    for path in (audit/'reproduced/costs.json',):
        assert sha(path) == receipt['evidence_sha256'][path.relative_to(REPO).as_posix()]
    archive = HERE/'results/cut_pair_diagnostic01'
    instance = json.loads((archive/'call_10/invocation/input_instance.json').read_text(encoding='utf-8'))
    results = []
    for scene in facts['scenes']:
        model = milp.Model({'id': 'fixture_k121_archived_dependency_rows',
                           'platform': instance['platform']}, Budget(seconds=30))
        options, start, end = {}, {}, {}
        for stage in scene['stages']:
            options[stage['stage_id']] = []
            for record in stage['recovered_unselected_local_options']:
                y = model.var('y:'+record['option_id'], integer=True)
                assert y == record['y_zero_based']
                options[stage['stage_id']].append((record, y))
                start[y], end[y] = F(record['start_ms'])/1000, F(record['end_ms'])/1000
        arcs = [(arc['before'], arc['after']) for arc in scene['arcs']]
        milp.add_cumulative_precedence(model, scene['scene_id'], options, start, end, dependencies=arcs)
        expected = []
        for arc in scene['arcs']:
            for decision in arc['threshold_decisions']:
                if decision['decision'] != 'KEEP':
                    continue
                tau = F(decision['tau_ms'])/1000
                row = {y: -1.0 for _, y in options[arc['before']] if end[y] <= tau}
                row.update({y: 1.0 for _, y in options[arc['after']] if start[y] <= tau})
                expected.append(row)
        assert [r['coef'] for r in model.rows] == expected
        assert all(r['rhs'] == 0 and r['rounding_allowance'] == '0' for r in model.rows)
        prefix = archive/f"call_10/invocation/matlab/request_{scene['archived_request_number']:06d}.mat"
        assert sha(prefix) == facts['source_sha256'][prefix.relative_to(REPO).as_posix()]
        x0 = loadmat(prefix, variable_names=['x0'])['x0'].reshape(-1)
        assert all(sum(F.from_float(v)*F.from_float(float(x0[y]))
                       for y, v in row['coef'].items()) <= 0 for row in model.rows)
        results.append({'scene_id': scene['scene_id'], 'rows': len(model.rows),
            'nnz': sum(len(r['coef']) for r in model.rows),
            'exact_rows_match_K120_catalog': True, 'saved_y_retained': True,
            'stats': model.cumulative_precedence_stats})
    assert sum(r['rows'] for r in results) == 190
    assert sum(r['nnz'] for r in results) == 16656
    report = {'passed': True, 'scope': 'two local dependency-only exports from saved catalogs',
              'scenes': results, 'new_schedules_or_safety_witnesses': 0,
              'full_original_model_reconstruction': False}
    save(out/'archived_rows.json', report)
    return report


def run(out):
    out = Path(out).resolve(); out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    before = sources()
    save(out/'source_sha256.json', before)
    for name in before:
        target = out/'source_snapshot'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    started = time.monotonic()
    output = io.StringIO()
    count = {'current_model_initializations_in_correctness_checks': 0}
    original_init = milp.Model.__init__

    def counted_init(self, *args, **kwargs):
        count['current_model_initializations_in_correctness_checks'] += 1
        return original_init(self, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError('Optimizer/native/thermal trajectory outside K121 precheck scope')

    old_temp = tempfile.tempdir
    temporary = REPO/'.runtime/k121_precheck'; temporary.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(temporary)
    result = reference = archived = None
    error = None
    try:
        with patch.object(scipy.optimize, 'linprog', side_effect=forbidden), \
             patch.object(scipy.optimize, 'milp', side_effect=forbidden), \
             patch.object(matlab_bridge.MatlabSession, '__init__', side_effect=forbidden), \
             patch.object(thermal, 'evaluate_piecewise', side_effect=forbidden), \
             patch.object(scene_adapter, 'evaluate_piecewise', side_effect=forbidden), \
             patch.object(milp.Model, '__init__', counted_init):
            suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            if result.wasSuccessful():
                reference = reference_check(out)
                archived = archived_row_check(out)
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        (out/'error_traceback.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        tempfile.tempdir = old_temp
        (out/'unittest.txt').write_text(output.getvalue(), encoding='utf-8')
    after = sources()
    passed = (result is not None and result.wasSuccessful() and reference is not None and archived is not None
              and error is None and before == after)
    report = {'protocol': 'cumulative-precedence-integration-precheck-v1',
        'passed': passed, 'test_targets': list(TESTS),
        'tests_run': 0 if result is None else result.testsRun,
        'failures': None if result is None else len(result.failures),
        'errors': None if result is None else len(result.errors),
        'source_unchanged': before == after, 'source_sha256': after,
        'test_execution_count': 1, 'error': error, 'elapsed_s': time.monotonic()-started,
        **count, 'reference_check_completed': reference is not None,
        'reference_check': None if reference is None else 'default_matrix_identity.json',
        'archived_dependency_only_check': None if archived is None else 'archived_rows.json',
        'new_LP_MILP_native_thermal_trajectory_or_research_calls': 0,
        'old_whole_gate_claimed_current': False,
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'numpy': np.__version__, 'scipy': scipy.__version__},
        'completed_at_utc': datetime.now(timezone.utc).isoformat()}
    save(out/'checks.json', report)
    details = {name: getattr(sys.modules.get(name), 'RECORDS', {}) for name in TESTS[:2]}
    save(out/'unit_details.json', details)
    print(json.dumps({k: report[k] for k in ('passed', 'tests_run', 'failures', 'errors', 'error', 'elapsed_s')}, ensure_ascii=False), flush=True)
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.out) else 1)
