"""Read-only frozen post-run audit; never builds, solves or evaluates heat."""
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
results = {}
for arm in 'ABC':
    target = OUT / (arm + '_audit.json')
    if target.exists():
        raise RuntimeError('Audit output already exists; preserve it')
    start = time.perf_counter()
    command = [r'F:/Anaconda3/python.exe', '-B',
               str(ROOT / 'work/cplex_ABC_v3/audit_result.py'),
               '--workspace', str(ROOT), '--plan', str(ROOT / 'work/cplex_ABC_v3/plan.json'),
               '--run', str(ROOT / 'work/cplex_ABC_execution_v2' / arm)]
    p = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=120)
    target.write_bytes(p.stdout)
    (OUT / (arm + '_audit.stderr.txt')).write_bytes(p.stderr)
    result = json.loads(p.stdout) if p.returncode == 0 else {}
    results[arm] = dict(command=command, returncode=p.returncode,
                        elapsed_s=time.perf_counter() - start,
                        audit_passed=result.get('audit_passed'),
                        retained_strict_success=result.get('retained_strict_success'))
    print(arm, json.dumps(results[arm]), flush=True)
(OUT / 'audit_execution.json').write_text(json.dumps(dict(
    kind='post_run_read_only_no_new_scientific_credit', solver_calls=0,
    model_builds=0, thermal_evaluations=0, results=results), indent=2), encoding='utf-8')
if not all(r['returncode'] == 0 and r['audit_passed'] for r in results.values()):
    raise SystemExit(1)
