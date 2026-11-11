"""Mechanical correction and read-only hash extraction; no scientific imports."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    began = datetime.now(timezone.utc).isoformat()
    tick = time.perf_counter()
    folder = Path(__file__).resolve().parent
    repo = folder.parents[2]
    original_names = ['extract_contract.py', 'logging_contract.json',
                      'logging_contract.csv', 'source_excerpts.txt',
                      'README.md', 'execution.json']
    before = {name: digest(folder/name) for name in original_names}
    archive = folder/'revision_01_original'
    archive.mkdir(exist_ok=False)
    for name in original_names:
        shutil.copy2(folder/name, archive/name)
    replacements = [
        (b'method/matlab/cleanup.json', b'method/matlab/closed.json'),
        (b'it alone proves no MILP improvement, native success or optimality.',
         b'it alone cannot establish MILP improvement, native success or optimality.')]
    changed = []
    # Preserve all first-execution bytes, including its output-hash references.
    # Only the generator and its human/machine-readable contract table change.
    for name in ['extract_contract.py', 'logging_contract.json', 'logging_contract.csv', 'README.md']:
        path = folder/name
        original = path.read_bytes()
        corrected = original
        counts = []
        for old, new in replacements:
            count = corrected.count(old)
            if count != 1:
                raise ValueError(f'Unexpected correction count in {name}: {old!r}: {count}')
            corrected = corrected.replace(old, new)
            counts.append(count)
        path.write_bytes(corrected)
        changed.append({'file': name, 'replacement_counts': counts,
                        'before_sha256': before[name], 'after_sha256': digest(path)})
    if digest(folder/'execution.json') != before['execution.json']:
        raise ValueError('First execution receipt changed')
    # Re-read all frozen source bytes only. Never import a research module.
    native_plan = json.loads((repo/'research/chapter3_support_propagation_20261110/native_pair_plan_NOT_RUN.json').read_text())
    checks = [{'path': name, 'expected_sha256': expected,
               'actual_sha256': digest(repo/name)}
              for name, expected in sorted(native_plan['runtime_source_sha256'].items())]
    if len(checks) != 217 or any(row['expected_sha256'] != row['actual_sha256'] for row in checks):
        raise ValueError('Frozen source drift')
    bridge = (repo/'research/chapter3_experiments/matlab_bridge.py').read_text().splitlines()
    if "_json(self.workdir / 'closed.json', cleanup)" not in bridge[820]:
        raise ValueError('Expected closed.json source location drift')
    # JSON parse and exact wording checks are data-format/identity checks only.
    contract = json.loads((folder/'logging_contract.json').read_text())
    assert len(contract['contract']) == 16
    assert 'closed.json' in contract['contract'][-1]['files_fields']
    assert 'cannot establish MILP improvement' in contract['contract'][-2]['does_not_support']
    record = {
        'revision': 2,
        'scope': 'Two wording/path corrections only; standard-library re-read and hash extraction. No re-solving, model construction or thermal evaluation.',
        'started_utc': began, 'ended_utc': datetime.now(timezone.utc).isoformat(),
        'elapsed_s': time.perf_counter()-tick,
        'cwd': str(repo), 'argv': [sys.executable, '-B', str(Path(__file__).relative_to(repo))],
        'script_sha256': digest(Path(__file__)),
        'corrections': [
            {'before': 'method/matlab/cleanup.json', 'after': 'method/matlab/closed.json',
             'source': 'research/chapter3_experiments/matlab_bridge.py:821'},
            {'before': 'it alone proves no MILP improvement, native success or optimality.',
             'after': 'it alone cannot establish MILP improvement, native success or optimality.',
             'reason': 'Top-level SAFE does not establish any of those claims; it does not prove absence of improvement.'}],
        'changed_files': changed,
        'first_execution_preserved': {'path': 'execution.json', 'sha256': before['execution.json'],
                                      'unchanged': True},
        'first_snapshot_archive': {str((archive/name).relative_to(folder)): digest(archive/name)
                                   for name in original_names},
        'frozen_217_sources_all_match': True, 'frozen_source_checks': checks,
        'outputs_sha256': {name: digest(folder/name) for name in original_names},
        'native_solver_calls': 0, 'matlab_launches': 0, 'model_construction_calls': 0,
        'thermal_evaluator_calls': 0, 'project_module_imports': 0}
    with (folder/'revision_02_receipt.json').open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: record[key] for key in ['started_utc','ended_utc','elapsed_s',
                     'frozen_217_sources_all_match','native_solver_calls']}, indent=2))


if __name__ == '__main__':
    main()
