"""Enforce the current task's 120 s/process and 600 s cumulative wall budget."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ledger = HERE / 'budget.jsonl'
previous = [json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
used = sum(x['wall_s'] for x in previous)
limit = min(120.0, 600.0-used)
if limit <= 0:
    raise SystemExit('Auxiliary budget exhausted')
name = sys.argv[1]
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
           NUMBA_CACHE_DIR=str(HERE / 'cache'), OPENBLAS_NUM_THREADS='1',
           MKL_NUM_THREADS='1', OMP_NUM_THREADS='1', NUMBA_NUM_THREADS='1')
started = time.perf_counter()
status = 'UNKNOWN'
with (HERE / (name+'.log')).open('wb') as log:
    try:
        result = subprocess.run([sys.executable, str(HERE/(name+'.py')), *sys.argv[2:]],
                                stdout=log, stderr=subprocess.STDOUT, env=env, timeout=limit)
        status = 'PASS' if result.returncode == 0 else 'FAIL'
    except subprocess.TimeoutExpired:
        status = 'TIMEOUT'
elapsed = time.perf_counter()-started
record = dict(script=name, arguments=sys.argv[2:], limit_s=limit, wall_s=elapsed,
              cumulative_s=used+elapsed, status=status)
with ledger.open('a', encoding='utf-8') as stream:
    stream.write(json.dumps(record)+'\n')
print(json.dumps(record))
print((HERE/(name+'.log')).read_text(encoding='utf-8', errors='replace')[-10000:])
if status != 'PASS':
    raise SystemExit(1)
