"""Read-only D282 archive verification; no CPLEX import, load, solve or evaluation.

Run: F:/Anaconda3/python.exe -B <this-file>
Requires the recorded NumPy/SciPy environment. Writes no files.
"""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'preflight'))
from transport_contract import MatrixPacket


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


manifest = read(ROOT / 'manifest.json')
for name, expected in manifest['files'].items():
    assert sha(ROOT / name) == expected, name
plan = read(ROOT / 'preflight/plan.json')
assert sha(ROOT / 'preflight/plan.json') == read(ROOT / 'preflight/plan.identity.json')['sha256']
for name, expected in plan['code_hashes'].items():
    assert sha(ROOT / 'preflight' / name) == expected, name
controller = read(ROOT / 'execution/controller_receipt.json')
assert controller['passed'] and controller['plan_sha256'] == sha(ROOT / 'preflight/plan.json')
for name, expected in controller['scientific_evidence_hashes'].items():
    assert sha(ROOT / 'execution' / name) == expected, name
worker = read(ROOT / 'execution/worker_receipt.json')
assert worker['passed'] and worker['native_objects_created'] == 1
assert worker['native_handle_closed'] and worker['algorithm_attempts'] == []
assert all(n == 0 for n in worker['calls'].values())
assert controller['owned']['cleanup_ok'] and controller['owned']['job_accounting']['active_processes'] == 0
diff = read(ROOT / 'execution/comparison.json')
assert len(diff['invariants']) == 16 and all(diff['invariants'].values())
assert len(diff['fields']) == 15 and all(x['mismatch_count'] == 0 for x in diff['fields'])
with np.load(ROOT / 'execution/native_readback.npz', allow_pickle=False) as a:
    matrices = {k: (tuple(a[k+'_shape'].tolist()), a[k+'_row'], a[k+'_col'], a[k+'_data']) for k in ('A','Aeq')}
    packet = MatrixPacket(len(a['c']), matrices['A'], matrices['Aeq'],
                          **{k:a[k] for k in ('c','b','beq','lb','ub','intcon','x0')},
                          column_ids=tuple(range(len(a['c']))))
    assert packet.hashes() == plan['matrices']['complement']['canonical_arrays_sha256']
candidate = read(ROOT / 'D283_candidate.json')
assert sha(ROOT / 'D283_candidate.json') == read(ROOT / 'D283_candidate.identity.json')['sha256']
assert not candidate['execution_authorized'] and not candidate['ready_to_execute']
audit = read(ROOT / 'audit.json')
assert audit['passed'] and all(audit['checks'].values())
print(json.dumps({'passed': True, 'manifest_files': len(manifest['files']),
                  'complete_archive_arrays_match': True, 'native_calls_in_this_audit': 0,
                  'limitation': 'Verifies stored evidence, not a new native execution or independent physical proof'}))
