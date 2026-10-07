"""Read-only-to-results summary; no MATLAB invocation or schedule search."""
import csv, json, math, pathlib, statistics, sys

folder = pathlib.Path(sys.argv[1])
with (folder / 'summary.csv').open(encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))

def yes(s):
    return str(s).lower() in ('1', 'true')

def number(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return float('nan')

result = {'method_main': {}, 'case_main': {}, 'check_cases': [], 'notes': [
    'One deterministic run per case/method; no statistical speedup inference.',
    'Old thermal reference additionally requires optimal configuration set.',
    'NaN component times in old methods mean not instrumented, not zero.',
]}
for method in dict.fromkeys(r['method'] for r in rows):
    group = [r for r in rows if r['method'] == method and r['cohort'] == 'main']
    times = [number(r['elapsed_s']) for r in group]
    result['method_main'][method] = {
        'cases': len(group), 'valid_safe': sum(yes(r['complete']) and yes(r['legal']) and yes(r['safe']) for r in group),
        'value_proved': sum(yes(r['optimal_value_proved']) for r in group),
        'timeouts': sum(r['status'] == 'timeout' for r in group),
        'elapsed_min_s': min(times), 'elapsed_max_s': max(times),
        'median_s': statistics.median(times),
        'repair_trials': sum(number(r['repair_trials']) for r in group),
        'repair_success': sum(number(r['repair_success']) for r in group),
        'popped': sum(number(r['popped']) for r in group),
    }
for r in rows:
    if r['cohort'] != 'main':
        result['check_cases'].append({k:r[k] for k in ('case_id','method','status','safe','energy_mJ','lower_mJ','upper_mJ')})
        continue
    result['case_main'].setdefault(r['case_id'], {})[r['method']] = {
        k:r[k] for k in ('status','safe','energy_mJ','lower_mJ','upper_mJ','optimal_value_proved',
                        'elapsed_s','first_safe_s','popped','repair_trials','repair_success','thermal_calls')}
out = folder / 'comparison_summary.json'
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result['method_main'], ensure_ascii=False, indent=2))
