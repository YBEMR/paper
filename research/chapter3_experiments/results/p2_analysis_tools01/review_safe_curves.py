"""Exact stored-receipt running minima; does not redraw or alter old figures."""
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
FACTS = HERE.parent/'p2_execution01/analysis01/facts.json'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    facts = json.loads(FACTS.read_text(encoding='utf-8')); rows = []
    for row in facts['rows']:
        saved = [v for v in row['safe_curve'] if v.get('safe_upper_bound_J') is not None]
        values = [F(v['safe_upper_bound_J']) for v in saved]
        final = F(row['usable_U_exact_J']) if row['usable_U_exact_J'] is not None else None
        running = []; best = None
        for receipt, value in zip(saved, values):
            best = value if best is None else min(best, value)
            running.append({'completed_at_s': receipt.get('completed_at_s'),
                'record_source': receipt.get('source'), 'original_safe_upper_J': str(value),
                'running_minimum_safe_upper_J': str(best)})
        rows.append({'problem_id': row['problem_id'], 'method': row['method'], 'points': len(values),
            'raw_SAFE_energy_increases': sum(b > a for a, b in zip(values, values[1:])),
            'minimum_equals_original_final_U': best == final, 'minimum_exact_J': None if best is None else str(best),
            'final_U_exact_J': None if final is None else str(final), 'running_minimum': running})
    return {'passed': all(r['minimum_equals_original_final_U'] for r in rows), 'count': len(rows),
        'exact_matches': sum(r['minimum_equals_original_final_U'] for r in rows),
        'curves_with_raw_SAFE_energy_increases': sum(r['raw_SAFE_energy_increases'] > 0 for r in rows),
        'rows': rows, 'source_facts_sha256': sha(FACTS), 'script_sha256': sha(Path(__file__)),
        'scope': 'Exact Fraction minima of saved complete SAFE receipts, not reconstructed algorithm update events.',
        'recommendation': 'Retain original figure; create a separately labeled best-known-safe-witness running-minimum figure.',
        'old_plot_or_analysis_modified': False, 'new_scientific_evaluations': 0}


if __name__ == '__main__':
    report = run()
    with (HERE/'safe_curve_review.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print({k: report[k] for k in ('passed', 'count', 'exact_matches', 'curves_with_raw_SAFE_energy_increases')})
