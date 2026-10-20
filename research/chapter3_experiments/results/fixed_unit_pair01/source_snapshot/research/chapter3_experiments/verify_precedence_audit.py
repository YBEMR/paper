"""Replay K120 exact algebra/static archive checks; never build or solve a model.

The scheduling matrices and x0 are read from the completed K119 local MAT
archive. The complete scheduling/thermal problem is not reevaluated. The
saved one-off unit-test transcript is checked, not executed again.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from scipy.io import loadmat

from precedence_check import build_precedence_system


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lhs(row, weights):
    return sum((v*weights.get(k, F(0)) for k, v in row['coef'].items()), F(0))


def verify(audit, archive, out):
    audit, archive, out = Path(audit).resolve(), Path(archive).resolve(), Path(out).resolve()
    out.relative_to(REPO)
    if out.exists():
        raise FileExistsError(out)
    original, costs = read(audit/'costs.json'), read(audit/'reproduced/costs.json')
    unit = read(audit/'unit_checks.json')
    declaration = read(archive/'declaration.json')
    checks = []

    def check(name, passed, detail):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    check('saved_unit_transcript_and_source',
        unit['result']['tests_run'] == unit['result']['passed'] == 11
        and unit['execution']['test_execution_count'] == 1
        and (audit/'unittest.txt').read_bytes().decode('utf-8') == unit['stdout']
        and all(sha(REPO/p) == h for p, h in unit['source_sha256'].items()),
        'One existing 11/11 execution, 384 local integer option pairs; no replay of unittest.')
    check('unchanged_34_production_and_frozen_sources',
        len(declaration['source_sha256']) == 34 and all(
            sha(REPO/p) == h == sha(archive/'source_snapshot'/p)
            for p, h in declaration['source_sha256'].items()),
        'K119 mathematical/thermal/transport sources and physical config unchanged.')
    check('static_cost_source_identity', all(sha(REPO/p) == h
        for p, h in costs['source_sha256'].items()),
        'Only existing JSON/source/MAT bytes are read.')
    check('persisted_cost_entry_reproduces_inline_result',
        original['aggregate_totals'] == costs['aggregate_totals']
        and original['scenes'] == costs['scenes'],
        'All recovered options, original row matches, threshold decisions and totals match.')

    rows_checked = nnz_checked = 0
    scene_checks = []
    for scene in costs['scenes']:
        request = scene['archived_request_number']
        x0 = loadmat(archive/f'call_10/invocation/matlab/request_{request:06d}.mat',
                     variable_names=['x0'])['x0'].reshape(-1)
        by_stage = {}
        weights = {}
        for stage in scene['stages']:
            options = stage['recovered_unselected_local_options']
            by_stage[stage['stage_id']] = [
                {'option_id': 'y:'+str(o['y_zero_based']),
                 'start': o['start_ms'], 'end': o['end_ms']}
                for o in options]
            for o in options:
                weights['y:'+str(o['y_zero_based'])] = F.from_float(float(x0[o['y_zero_based']]))
            assert all(weights[o['option_id']] in (0, 1) for o in by_stage[stage['stage_id']])
            assert sum((weights[o['option_id']] for o in by_stage[stage['stage_id']]), F(0)) == 1
        count_matches = existing_x0_retained = True
        for arc in scene['arcs']:
            system = build_precedence_system(by_stage[arc['before']], by_stage[arc['after']], simplify=True)
            raw = system['raw_cumulative_rows']
            selected = system['cumulative_rows']
            count_matches &= (len(raw) == arc['cumulative_raw_rows']
                and len(selected) == arc['cumulative_kept_rows']
                and sum(len(r['coef']) for r in selected) == arc['cumulative_kept_nnz'])
            for row, decision in zip(raw, arc['threshold_decisions']):
                count_matches &= (row['threshold'] == F(decision['tau_ms'])
                    and len(row['coef']) == decision['raw_nnz']
                    and sum(v < 0 for v in row['coef'].values()) == decision['predecessor_prefix_size']
                    and sum(v > 0 for v in row['coef'].values()) == decision['successor_prefix_size'])
            existing_x0_retained &= (lhs(system['expected_row'], weights) <= 0
                                    and all(lhs(row, weights) <= 0 for row in selected))
            rows_checked += len(selected)
            nnz_checked += sum(len(row['coef']) for row in selected)
        scene_checks.append({'scene_id': scene['scene_id'],
            'independent_generator_matches_costs': bool(count_matches),
            'stored_initial_y_exact_binary_onehot': True,
            'stored_initial_y_passes_new_rows': bool(existing_x0_retained)})
    check('independent_generator_matches_190_rows_and_16656_nnz',
        rows_checked == 190 and nnz_checked == 16656 and all(
            s['independent_generator_matches_costs'] for s in scene_checks), scene_checks)
    check('archived_initial_choices_are_retained', all(
        s['stored_initial_y_passes_new_rows'] for s in scene_checks),
        'Stored y only; no new schedule decoding, candidate search or thermal propagation.')

    before = [{'option_id': f'p{k}', 'start': 0, 'end': end}
              for k, end in enumerate((1, 5, 9))]
    after = [{'option_id': f's{k}', 'start': start, 'end': start+1}
             for k, start in enumerate((2, 6, 10))]
    system = build_precedence_system(before, after)
    w = {'p0': F(1, 2), 'p2': F(1, 2), 's1': F(1)}
    expected_value = lhs(system['expected_row'], w)
    cumulative_value = lhs(next(r for r in system['cumulative_rows'] if r['threshold'] == 6), w)
    check('local_fractional_separation', expected_value == -1 and cumulative_value == F(1, 2),
        {'expected_lhs': str(expected_value), 'cumulative_at_6_lhs': str(cumulative_value),
         'scope': 'Local precedence relaxation only; not a feasible/optimal point of the full old LP.'})
    output = {'passed': all(c['passed'] for c in checks), 'count': len(checks), 'checks': checks,
        'source_sha256': {p.relative_to(REPO).as_posix(): sha(p) for p in
            (HERE/'precedence_check.py', HERE/'test_precedence_check.py',
             HERE/'analyze_precedence_cost.py', Path(__file__).resolve())},
        'evidence_sha256': {p.relative_to(REPO).as_posix(): sha(p) for p in
            (audit/'costs.json', audit/'reproduced/costs.json', audit/'unit_checks.json', audit/'unittest.txt')},
        'new_model_LP_MILP_heat_native_or_research_calls': 0,
        'rows_checked': rows_checked, 'nnz_checked': nnz_checked,
        'scope': 'Exact algebra and static saved-array checks only; no optimizer performance result.'}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'passed': output['passed'], 'count': output['count'],
                      'rows_checked': rows_checked, 'nnz_checked': nnz_checked}), flush=True)
    return output['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--archive', type=Path, default=HERE/'results/cut_pair_diagnostic01')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.audit, args.archive, args.out) else 1)
