"""K132: one archived AB expression replay; never a method invocation.

The saved condition's Budget token is replayed as data identity only. A
separate monotonic 120 s deadline applies to every production budget check.
No evaluator, optimizer, MATLAB, candidate generation, or new SAFE receipt is
called. The exclusive attempt file prevents accidental second construction.
After replay, all eight model arrays must exactly match saved MAT arrays
(intcon compared after the documented Python-to-MATLAB +1 conversion).
"""
from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np
from scipy.io import loadmat
from scipy.sparse import issparse

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = HERE.parents[4]
SOURCE = ROOT / 'research' / 'chapter3_experiments'
ARCHIVE = SOURCE / 'results' / 'fixed_unit_pair02' / 'all_opp_start'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + '\n', encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    # Imports are outside the separately reported build/export clock.
    from timing import MethodBudget
    from thermal import Exhausted
    from milp import build_model

    declaration = json.loads((AUDIT / 'declaration.json').read_text(encoding='utf-8'))
    changed = [p for p, expected in declaration['source_sha256'].items()
               if digest(ROOT / p) != expected]
    if changed:
        raise RuntimeError('Frozen source mismatch: ' + repr(changed))
    saved_result = json.loads((ARCHIVE / 'result.json').read_text(encoding='utf-8'))
    instance = json.loads((ARCHIVE / 'input_instance.json').read_text(encoding='utf-8'))
    config = json.loads((ARCHIVE / 'input_config.json').read_text(encoding='utf-8'))
    condition = deepcopy(saved_result['condition'])
    original_mat = ARCHIVE / 'matlab' / 'request_000001.mat'
    original = loadmat(original_mat)
    if any(k.lower() in {'names', 'tags', 'row_names', 'row_tags'} for k in original):
        raise RuntimeError('Saved labels found; do not consume technical rebuild')

    # This is an explicitly labelled archive replay adapter, not a new live
    # Budget/SAFE identity. Production validators are unchanged and all run.
    class HistoricalExpressionReplayBudget(MethodBudget):
        def __init__(self):
            super().__init__(float(condition['budget_identity']['seconds']))
            self.technical_started = time.monotonic()
            self.technical_deadline = self.technical_started + 120.0
            self.replayed_elapsed_origin = max(
                p['completed_at_elapsed_s'] for p in
                [condition['seed_receipt'], *condition['seed_receipt']['scenes'].values()]) + 1.0
            self._scene_adapter_budget_identity = deepcopy(condition['budget_identity'])

        def check(self):
            if time.monotonic() >= self.technical_deadline:
                raise Exhausted('K132_technical_replay_120_seconds')

        @property
        def elapsed(self):
            # Historical receipt checks need their recorded completion stamps
            # to precede this replay view; this is never new method timing.
            return self.replayed_elapsed_origin + time.monotonic() - self.technical_started

    attempt = {
        'scope': 'historical expression replay only; not a method/SAFE/solver invocation',
        'started_at_utc': now(), 'technical_limit_s': 120,
        'original_mat_sha256': digest(original_mat),
        'condition_sha256': condition['condition_sha256'],
        'builder_flags': saved_result['builder_options'],
        'starts_argument': None,
        'scene': 'AB_offset_0ms',
        'historical_budget_identity_replayed_as_data_only': condition['budget_identity'],
        'production_validators_modified_or_skipped': False,
        'new_SAFE_or_method_budget_credential_created': False,
        'source_files_verified': len(declaration['source_sha256']),
        'solver_calls': 0, 'matlab_starts': 0, 'candidate_thermal_evaluations': 0,
        'status': 'STARTED',
    }
    with (HERE / 'rebuild_attempt.json').open('x', encoding='utf-8') as handle:
        json.dump(attempt, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    started = time.monotonic()
    try:
        budget = HistoricalExpressionReplayBudget()
        model = build_model(instance, config, starts=None, budget=budget,
            fixed_shared_deployment=saved_result['shared_deployment'],
            fixed_scene_id='AB_offset_0ms', neighborhood_condition=condition,
            **saved_result['builder_options'])
        built = time.monotonic()
        exported = model.as_solver_dict()
        exported_at = time.monotonic()
        comparison = {}
        for key in ('c', 'A', 'b', 'Aeq', 'beq', 'lb', 'ub', 'intcon'):
            old, new = original[key], exported[key]
            if key == 'intcon':
                new = new + 1
            if issparse(new):
                old, new = old.tocsr(), new.tocsr()
                diff = old - new
                comparison[key] = {
                    'old_shape': list(old.shape), 'new_shape': list(new.shape),
                    'equal_elementwise': bool(old.shape == new.shape and diff.nnz == 0),
                    'different_element_count': int(diff.nnz),
                    'max_abs_difference': float(max(abs(diff.data), default=0)),
                }
            else:
                old, new = np.asarray(old).reshape(-1), np.asarray(new).reshape(-1)
                comparison[key] = {
                    'old_length': len(old), 'new_length': len(new),
                    'equal_elementwise': bool(np.array_equal(old, new)),
                    'different_element_count': int(np.count_nonzero(old != new)) if old.shape == new.shape else None,
                }
        identical = all(v['equal_elementwise'] for v in comparison.values())
        save(HERE / 'rebuild_comparison.json', {
            'all_arrays_identical': identical, 'arrays': comparison,
            'intcon_convention': 'rebuilt Python 0 based + 1 compared to saved MATLAB 1 based',
            'build_wall_s': built-started, 'export_wall_s': exported_at-built,
            'build_and_export_wall_s': exported_at-started,
            'labels_usable': identical,
        })
        if not identical:
            attempt['status'] = 'MATRIX_MISMATCH_STOPPED_NO_LABEL_USE'
            return
        # Only the completed exact comparison above authorizes label use.
        names = model.names
        with (HERE / 'variables.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['column_zero_based', 'name', 'lb', 'ub', 'x0', 'c', 'in_intcon'])
            integer = set(model.integer)
            x0 = original['x0'].reshape(-1)
            for j, name in enumerate(names):
                writer.writerow([j, name, model.lb[j], model.ub[j], x0[j], model.c[j], j in integer])
        a, b = original['A'].tocsr(), original['b'].reshape(-1)
        activity = a @ x0
        residual = activity-b
        with (HERE / 'rows.csv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['row_zero_based', 'tag', 'rhs', 'Ax0_minus_b'])
            for i, row in enumerate(model.rows):
                writer.writerow([i, row['tag'], b[i], residual[i]])
        save(HERE / 'labels.json', {'names': names, 'row_tags': [r['tag'] for r in model.rows],
                                   'scope': 'usable only after exact comparison of all eight arrays'})
        selected = {13838, int(np.argmax(residual)), *map(int, np.argsort(residual)[-20:]),
                    *map(int, np.argsort(np.where(b != 0, abs(b), np.inf))[:20])}
        details = []
        for i in sorted(selected):
            row = model.rows[i]
            details.append({'row_zero_based': i,
                **{k: v for k, v in row.items() if k != 'coef'},
                'Ax0': float(activity[i]), 'Ax0_minus_b': float(residual[i]),
                'entries': [{'column_zero_based': j, 'name': names[j], 'coefficient': v,
                             'x0': float(x0[j]), 'product': float(v*x0[j]),
                             'lb': float(model.lb[j]), 'ub': float(model.ub[j])}
                            for j, v in row['coef'].items()]})
        save(HERE / 'selected_rows.json', details)
        families = {}
        for i, row in enumerate(model.rows):
            item = families.setdefault(row['tag'], {'count': 0, 'positive_residual_count': 0,
                'abs_residual_le_1e9_negative_exponent_count': 0, 'zero_rhs_count': 0,
                'nonzero_abs_rhs_lt_1e12_negative_exponent_count': 0,
                'max_residual': -float('inf'), 'max_residual_row_zero_based': None})
            item['count'] += 1
            item['positive_residual_count'] += int(residual[i] > 0)
            item['abs_residual_le_1e9_negative_exponent_count'] += int(abs(residual[i]) <= 1e-9)
            item['zero_rhs_count'] += int(b[i] == 0)
            item['nonzero_abs_rhs_lt_1e12_negative_exponent_count'] += int(0 < abs(b[i]) < 1e-12)
            if residual[i] > item['max_residual']:
                item['max_residual'] = float(residual[i])
                item['max_residual_row_zero_based'] = i
        save(HERE / 'row_family_facts.json', families)
        attempt.update(status='EXACT_MATCH_LABELS_RESTORED',
                       build_and_export_wall_s=exported_at-started,
                       max_inequality_residual=float(max(residual)),
                       total_rows=len(model.rows), total_variables=len(names))
    except BaseException as error:
        attempt.update(status='FAILED_OR_INTERRUPTED_NO_RETRY',
                       error=repr(error), traceback=traceback.format_exc())
        raise
    finally:
        attempt.update(completed_at_utc=now(), total_replay_and_analysis_wall_s=time.monotonic()-started)
        save(HERE / 'rebuild_attempt.json', attempt)
        print(json.dumps(attempt, ensure_ascii=False))


if __name__ == '__main__':
    main()
