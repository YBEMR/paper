"""Read saved 68 results only: no solving, repair, or thermal evaluation."""
from pathlib import Path
import csv
import hashlib
import json
import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/matlab_config_value_src/milp68_reports/frozen_20260927_113720_286'

def read(f, obj):
    if isinstance(obj, h5py.Group):
        return {k: read(f, v) for k, v in obj.items()}
    a = obj[()]
    kind = obj.attrs.get('MATLAB_class', b'').decode()
    if kind == 'char':
        return ''.join(chr(int(x)) for x in a.flatten())
    if a.dtype == h5py.ref_dtype:
        return [read(f, f[x]) for x in a.flatten()]
    if obj.attrs.get('MATLAB_empty', 0):
        return []
    if a.size == 1:
        return a.item()
    return a.T.tolist()

records = []
for i in range(1, 11):
    for j in (1, 2):
        with h5py.File(OUT / f'case{i:02d}_method{j:02d}.mat') as f:
            r = read(f, f['r'])
        records.append({k: v for k, v in r.items() if k != 'schedule'})
(OUT / 'saved_diagnostics.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')

before = json.loads((ROOT / 'research/milp68_audit/history_before.json').read_text(encoding='utf-8-sig'))
checks = []
for item in before:
    current = hashlib.sha256(Path(item['Path']).read_bytes()).hexdigest()
    checks.append({'path': item['Path'], 'unchanged': current.lower() == item['Hash'].lower(), 'sha256': current})
assert all(c['unchanged'] for c in checks)
(OUT / 'history_after.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')

with (OUT / 'summary.csv').open(encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
for r in records:
    print(r['input_id'], r['method'], r['status'], 'U_mJ', r['upper_J']*1000,
          't', round(r['elapsed_s'], 4), 'first', round(r['first_safe_s'], 4),
          'stats', r['stats'], 'cost', r.get('cost_s', {}))
print('HISTORICAL_HASHES_UNCHANGED', len(checks))
