"""Read four already completed P1 records to validate extraction only."""
import json
from pathlib import Path
from fractions import Fraction as F
import analyse_p2 as a


def run():
    sources = {}
    def read(path):
        path = Path(path)
        sources[path.relative_to(a.REPO).as_posix()] = a.sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    root = a.ROOT/'results/p1_execution01'
    ledger = read(root/'ledger.json')
    references = read(root/'analysis01/facts.json')['rows']
    checks = []
    for record in ledger['calls'][:4]:
        slot = {k: record[k] for k in ('id', 'method', 'problem_id', 'slot_id', 'seconds', 'ordinal')}
        if 'seed' in record: slot['seed'] = record['seed']
        folder = root/'calls'/record['problem_id']/record['id']
        raw = read(folder/'wrapper_raw_result.json')
        instance = read(root/'inputs'/record['problem_id']/'instance.json')
        row = a.summary_row(slot, record, raw, folder, instance, read)
        prior = next(v for v in references if v['problem_id'] == slot['problem_id'] and v['method'] == slot['id'])
        tests = {'original_U_exact': F(row['usable_U_exact_J']) == F(prior['safe_U_exact']),
            'original_U_float': row['safe_U_J'] == prior['safe_U_J'],
            'comparison_usable': row['comparison_usable'] == prior['comparison_usable'],
            'first_SAFE': row['first_SAFE_s'] == prior['first_SAFE_s'],
            'first_strict_improvement': row['first_strict_improvement_s'] == prior['first_strict_improvement_s'],
            'root_time': row['method_root_s'] == prior['method_root_s'],
            'matlab_startup': row['matlab_startup_s'] == prior['matlab_startup_s'],
            'independent_L0': row['certified_L0_J'] == prior['independent_L0_J'],
            'feedback': row['feedback_saved_rows'] == prior['feedback_saved_rows'],
            'thermal_violation_saved_records': row['thermal_violation_saved_records'] == prior['violation_saved_rows']}
        if slot['method'] == 'linked_fixed_unit_opp_start':
            tests['two_phases'] = len(row['method_phases']) == 2
            for i, phase in enumerate(row['method_phases'], 1):
                tests[f'phase{i}_energy'] = float(F(phase['end_complete_energy_interval_J'][1])) == prior[f'phase{i}_U_J']
        checks.append({'method': slot['id'], 'tests': tests, 'passed': all(tests.values())})
    return {'passed': all(c['passed'] for c in checks), 'count': sum(len(c['tests']) for c in checks),
            'checks': checks, 'source_sha256': sources,
            'analysis_script_sha256': a.sha(a.HERE/'analyse_p2.py'),
            'validation_script_sha256': a.sha(Path(__file__)),
            'new_scientific_evaluations': 0, 'P2_read_or_analysed': False}


if __name__ == '__main__':
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['passed'] else 1)
