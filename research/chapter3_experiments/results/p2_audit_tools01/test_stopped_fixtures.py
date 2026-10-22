"""Synthetic stopped terminal views of old P1 data; no physical computation."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import audit_terminal as a


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run():
    old = a.ROOT/'results/p1_execution01'
    d = a.read(old/'declaration.json')
    original_hashes = {str(p): a.sha(p) for p in
        (old/'declaration.json', old/'ledger.json', old/'process_terminal.json')}
    results = []
    temp_parent = a.HERE/'fixture_runtime'; temp_parent.mkdir(exist_ok=True)
    for consumed in (0, 1):
        with tempfile.TemporaryDirectory(dir=temp_parent) as tmp:
            folder = Path(tmp)
            for name in ('declaration.json', 'precheck.json', 'protocol.md', 'launcher_claim.json'):
                shutil.copyfile(old/name, folder/name)
            for name in ('source_snapshot', 'inputs'):
                shutil.copytree(old/name, folder/name)
            (folder/'claims').mkdir(); (folder/'calls').mkdir()
            worker = {'state': 'STOPPED_EXCEPTION', 'consumed_total': consumed, 'research_calls_retried': False}
            terminal = {'state': 'STOPPED_PROCESS_OR_WORKER_FAILURE', 'returncode': 1,
                'watchdog_stop': 'TEST_ONLY_SIMULATED_STOP', 'ended_utc': a.read(old/'launcher_claim.json')['started_utc'],
                'research_retry': False, 'worker_terminal': worker}
            ledger = {'state': 'BLOCKED', 'consumed_total': consumed,
                'reserved_total_method_s': consumed*300, 'calls': []}
            if consumed:
                slot = d['slots'][0]
                write(folder/'claims'/(slot['slot_id']+'.json'), {**slot, 'no_retry': True})
                ledger['calls'] = [deepcopy(slot)]
            write(folder/'ledger.json', ledger)
            write(folder/'worker_terminal.json', worker)
            write(folder/'process_terminal.json', terminal)
            result = a.audit(fixture_p1=True, _fixture_folder=folder)
            passed = (result['passed'] and result['campaign_completed_40'] is False
                and result['consumed_calls'] == consumed
                and result['reserved_method_seconds_from_claims'] == consumed*300
                and result['post_verified_safe_outputs'] == 0
                and result['new_post_evaluations'] == 0 and not any(result['blocked_calls'].values())
                and (consumed == 0 or len(result['unresolved_or_partial_evidence']) == 1))
            results.append({'consumed': consumed, 'passed': passed,
                'audit_checks': result['checks_run'], 'failed_checks': result['failed_checks'],
                'unresolved': result['unresolved_or_partial_evidence'], 'guards': result['blocked_calls']})
    unchanged = all(a.sha(Path(p)) == h for p, h in original_hashes.items())
    final = {'passed': unchanged and all(v['passed'] for v in results),
        'scope': 'TEST_ONLY synthetic stopped zero/one-consumed views; no P2 runtime reads',
        'fixtures': results, 'old_P1_unchanged': unchanged,
        'audit_script_sha256': a.sha(a.HERE/'audit_terminal.py'),
        'test_script_sha256': a.sha(Path(__file__)),
        'research_calls': 0, 'physical_models': 0, 'thermal_evaluations': 0, 'new_post_evaluations': 0}
    print(json.dumps(final, ensure_ascii=False, indent=2))
    return final


if __name__ == '__main__':
    result = run()
    write(a.HERE/'stopped_fixture01.json', result)
    raise SystemExit(0 if result['passed'] else 1)
