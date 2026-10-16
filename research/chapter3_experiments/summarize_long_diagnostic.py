"""Archive-only extraction from existing diagnostic receipts; never evaluate."""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--result-dir', required=True)
    args = parser.parse_args()
    folder = Path(args.result_dir)
    result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    diagnostic = result.get('diagnostic', {})
    rows = []
    for event in diagnostic.get('solver_progress', []):
        values = event.get('values', {})
        rows.append({'method_elapsed_s': event['method_elapsed_s'],
            'kind': event.get('kind'), 'phase': values.get('phase'),
            'request': event.get('request'), 'source': 'solver-reported',
            'solver_reported_lowerbound_J': values.get('lowerbound'),
            'solver_reported_fval_J': values.get('fval'),
            'solver_reported_numfeaspoints': values.get('numfeaspoints'),
            'independently_checked_U_J': None})
    safe = []
    for receipt in diagnostic.get('evaluations', []):
        if not receipt['accepted_safe']:
            continue
        evaluation = receipt['evaluation']
        assert evaluation['state'] == 'SAFE' and evaluation['rankable_energy']
        assert evaluation['completed_at_elapsed_s'] < result['timing']['limit_s']
        safe.append(receipt)
        rows.append({'method_elapsed_s': evaluation['completed_at_elapsed_s'],
            'kind': 'safe_receipt', 'source': 'independent complete evaluation',
            'independently_checked_U_J': evaluation['safe_upper_bound_J']})
    rows.sort(key=lambda row: row['method_elapsed_s'])
    fields = ['method_elapsed_s', 'kind', 'phase', 'request', 'source',
              'solver_reported_lowerbound_J', 'solver_reported_fval_J',
              'solver_reported_numfeaspoints', 'independently_checked_U_J']
    with (folder/'timeline.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fields)
        writer.writeheader(); writer.writerows(rows)
    if safe:
        assert Fraction(result['safe_upper_bound_J']) == min(Fraction(r['evaluation']['safe_upper_bound_J']) for r in safe)
        assert diagnostic['first_safe_receipt_s'] == min(r['evaluation']['completed_at_elapsed_s'] for r in safe)
    else:
        assert result['safe_upper_bound_J'] is None
        assert diagnostic.get('first_safe_receipt_s') is None
    integrity = json.loads((folder/'source_integrity.json').read_text(encoding='utf-8'))
    old = folder.parent/'base_method_diagnostic01/input_instance.json'
    same_input = json.loads(old.read_text(encoding='utf-8')) == json.loads((folder/'input_instance.json').read_text(encoding='utf-8'))
    assert integrity['match'] and same_input
    summary = {k: result.get(k) for k in ['state', 'reason', 'budget_exhausted',
        'integer_solver_entered', 'model_complete', 'matrix_complete', 'solver_request_attempts',
        'safe_upper_bound_J', 'independently_proven_optimal', 'independently_proven_infeasible']}
    summary.update({k: diagnostic.get(k) for k in ['first_candidate_received_s',
        'first_legal_candidate_s', 'first_safe_receipt_s', 'solver_entered_received_s',
        'worker_events', 'candidate_receipts', 'duplicate_receipts']})
    summary.update(method_elapsed_s=result['timing']['method_elapsed_s'],
        phases_exclusive_s=result['timing']['phases_exclusive_s'],
        cleanup_s=result['timing']['cleanup_s'],
        accepted_safe_receipts=len(safe), independent_checks=len(diagnostic.get('evaluations', [])),
        input_identical_to_K80=same_input, source_unchanged_during_run=integrity['match'],
        formal_comparison=False, original_case_calls=1,
        observations_scope='one fixed diagnostic; no statistical timing claim',
        callback_flag_semantics='method flag denotes live-check interface enabled; actual check count is independent_checks',
        postprocess_scope='existing receipts only; no new solve, decode, evaluation or safety evidence',
        analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    # Late worker messages remain diagnostic, never populate budgeted U/bounds.
    raw_responses = []
    for path in sorted((folder/'matlab').glob('*.response.json')):
        raw = json.loads(path.read_text(encoding='utf-8'))
        raw_responses.append({'file': path.name, 'status': raw.get('status'),
            'exitflag': raw.get('exitflag'), 'output': raw.get('output'),
            'phase_seconds': raw.get('phase_seconds'),
            'acceptance': 'consult in-budget rounds; this archival read grants no acceptance'})
    summary['raw_worker_responses'] = raw_responses
    (folder/'diagnostic_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
