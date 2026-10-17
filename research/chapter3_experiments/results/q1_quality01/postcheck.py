"""Post-stop read-only witness verification and display, never search evidence."""
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import csv
import json
from pathlib import Path
import sys
import time

OUT = Path(__file__).resolve().parent
HERE = OUT.parents[1]
sys.path.insert(0, str(HERE))
from thermal import evaluate_candidate
from timing import MethodBudget
from q1_case import canonical_hash


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def save(path, value): path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
def val(value):
    if value is None: return None
    f = F(value)
    return float(f)


def main():
    started = time.monotonic()
    rows, rechecks = [], []
    calls = {r['method']: r for r in read(OUT/'calls.json')}
    inputs, series = [], {}
    for name in ('milp', 'reference'):
        root = OUT/name
        result = read(root/'result.json')
        instance, config = read(root/'input_instance.json'), read(root/'input_config.json')
        inputs.append(canonical_hash(instance))
        receipt = result.get('evaluation') or {}
        diagnostic = result.get('diagnostic') or {}
        initial = result.get('initialisation') or {}
        seed_eval = (initial.get('witness') or {}).get('evaluation') or {}
        first_safe = seed_eval.get('completed_at_elapsed_s') if seed_eval else result.get('first_safe_at_s')
        first_milp_safe = diagnostic.get('first_safe_receipt_s')
        row = dict(method=name, state=result['state'], reason=result['reason'],
            method_wall_s=result['timing']['method_elapsed_s'],
            process_wall_s=calls[name]['process_wall_s'],
            cleanup_s=result['timing'].get('cleanup_s', 0),
            first_safe_at_s=first_safe, first_MILP_safe_at_s=first_milp_safe,
            first_legal_MILP_at_s=diagnostic.get('first_legal_candidate_s'),
            U_J=val(result.get('safe_upper_bound_J')),
            L0_J=val(result['independent_lower_bound']['lower_bound_J']),
            certified_L_J=val(result.get('certified_lower_bound_J')),
            coverage_complete=result.get('coverage_complete'),
            independently_proven_optimal=result.get('independently_proven_optimal'),
            independently_proven_infeasible=result.get('independently_proven_infeasible'),
            budget_exhausted=result.get('budget_exhausted'),
            counters=result.get('counters'),
            finite_optimal_enclosure_J=result.get('finite_domain_optimal_value_enclosure_J'))
        if row['U_J'] is not None:
            row['relative_gap_to_L0_percent'] = 100*(row['U_J']-row['L0_J'])/row['U_J']
            with localcontext() as context:
                context.prec = 70
                upper = D(result['safe_upper_bound_J'])
                lower = F(result['certified_lower_bound_J'])
                lower_decimal = D(lower.numerator)/D(lower.denominator)
                row['certified_absolute_gap_J'] = str(upper-lower_decimal)
                row['relative_gap_to_certified_L_percent'] = str(100*(upper-lower_decimal)/upper)
        if name == 'milp':
            row.update(initial_U_J=val(result.get('initial_safe_upper_bound_J')),
                milp_improved_seed=result.get('milp_improved_initial_upper_bound'),
                strict_seed_improvement=result.get('strict_energy_improvement_certified'),
                solver_entered=result.get('integer_solver_entered'),
                solver_entered_at_s=diagnostic.get('solver_entered_received_s'),
                solver_requests=result.get('solver_request_attempts'),
                feedback_count=len(result.get('feedback', [])))
            row['solver_progress'] = [{k: ev.get(k) for k in ('method_elapsed_s','state','values')}
                for ev in diagnostic.get('solver_progress', [])]
        rows.append(row)
        events = []
        if name == 'milp':
            if seed_eval.get('safe_upper_bound_J'):
                events.append([first_safe, val(seed_eval['safe_upper_bound_J'])])
            for item in diagnostic.get('evaluations', []):
                ev = item.get('evaluation', {})
                if item.get('accepted_safe') and ev.get('safe_upper_bound_J'):
                    events.append([ev['completed_at_elapsed_s'], val(ev['safe_upper_bound_J'])])
        else:
            events = [[ev['at_s'], val(ev['energy_J'][1])] for ev in result['events']
                      if ev['kind'] == 'safe_upper_bound']
        series[name] = sorted(events)
        if result.get('safe_candidate') is not None:
            budget = MethodBudget(120)
            checked = evaluate_candidate(instance, result['safe_candidate'], config['accuracy_targets'], budget)
            old = receipt.get('weighted_energy_J')
            new = checked.get('weighted_energy_J')
            overlap = bool(old and new and max(D(old[0]), D(new[0])) <= min(D(old[1]), D(new[1])))
            rechecks.append({'method': name, 'state': checked['state'], 'energy_enclosures_overlap': overlap,
                'elapsed_s': budget.elapsed, 'scope': 'after-stop verification only; not credited to method U or time',
                'evaluation': checked})
            save(root/'saved_safe_schedule.json', result['safe_candidate'])
    summary = {'scope': 'Q1 main-only finite start reference; full chain study unchanged',
        'rows': rows, 'identical_method_input_sha256': len(set(inputs)) == 1,
        'input_sha256': inputs, 'poststop_witness_rechecks': [{k: v for k, v in r.items() if k != 'evaluation'} for r in rechecks],
        'source_unchanged': read(OUT/'source_integrity.json')['unchanged'],
        'poststop_check_wall_s': time.monotonic()-started}
    reference = rows[1]
    if reference['finite_optimal_enclosure_J']:
        lo, hi = map(D, reference['finite_optimal_enclosure_J'])
        upper = D(read(OUT/'milp/result.json')['safe_upper_bound_J'])
        with localcontext() as context:
            context.prec = 70
            summary['MILP_true_regret_J_enclosure'] = [str(max(D(0), upper-hi)), str(max(D(0), upper-lo))]
    save(OUT/'summary.json', summary)
    save(OUT/'poststop_rechecks.json', rechecks)
    fields = ['method','state','reason','U_J','L0_J','certified_L_J','first_safe_at_s',
              'first_MILP_safe_at_s','method_wall_s','process_wall_s','coverage_complete',
              'independently_proven_optimal','budget_exhausted']
    with (OUT/'summary.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), constrained_layout=True)
    for ax, name, row in zip(axes, ('milp','reference'), rows):
        points = series[name]
        if points:
            best = float('inf'); xy = []
            for t, value in points:
                best = min(best,value); xy.append((t,best))
            xy.append((row['method_wall_s'],best))
            ax.step([p[0] for p in xy],[p[1] for p in xy], where='post',label='Rechecked safe U')
        ax.axhline(row['L0_J'],color='gray',linestyle='--',label='Independent L0')
        if name == 'milp':
            bound = [(ev['method_elapsed_s'],ev.get('values',{}).get('lowerbound'))
                     for ev in read(OUT/'milp/result.json').get('diagnostic',{}).get('solver_progress', [])]
            bound = [(t,v) for t,v in bound if isinstance(v,(int,float))]
            if bound: ax.step([p[0] for p in bound],[p[1] for p in bound],where='post',
                             color='orange',linestyle=':',label='Solver-reported bound')
        elif row['coverage_complete'] and row['finite_optimal_enclosure_J']:
            ax.plot([row['method_wall_s']],[row['certified_L_J']],marker='o',color='green',label='Final certified L')
        ax.set(title=name, xlabel='Method time (s)',ylabel='Weighted energy (J)')
        ax.set_xlim(0, max(r['method_wall_s'] for r in rows)*1.03)
        ax.set_ylim(min(r['L0_J'] for r in rows)*.98,
                    max(v for points in series.values() for _, v in points)*1.02)
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.savefig(OUT/'energy_bounds.png',dpi=180)
    fig.savefig(OUT/'energy_bounds.svg')
    svg = OUT/'energy_bounds.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',
                   encoding='utf-8')
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False, indent=2))
    for row in rows:
        print(json.dumps({k: v for k,v in row.items() if k != 'solver_progress'},ensure_ascii=False))


if __name__ == '__main__': main()
