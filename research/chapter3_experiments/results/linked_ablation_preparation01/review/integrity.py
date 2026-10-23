"""K172 original-evidence protection; hashing only, no scientific imports."""
import argparse
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = HERE.parents[4]
RESULTS = ROOT / 'results'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1048576):
            h.update(block)
    return h.hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def rel(path):
    return Path(path).relative_to(REPO).as_posix()

def scan(path):
    return sorted(rel(p) for p in path.rglob('*') if p.is_file())

def state():
    declaration = read(RESULTS / 'deadline_execution01/declaration.json')
    unexpected = []
    for slot in declaration['slots'][16:]:
        for camp in ('deadline_execution01', 'deadline_resume01'):
            path = RESULTS / camp / 'claims' / (slot['slot_id'] + '.json')
            if path.exists():
                unexpected.append(rel(path))
    folder = RESULTS / 'whole_native_diagnostic_precheck01/run01/real_preparation'
    k168, ledger = read(folder / 'declaration.json'), read(folder / 'ledger.json')
    return {'deadline_consumed_preserved': 16, 'deadline_unstarted': len(declaration['slots'][16:]),
        'unexpected_claims': unexpected, 'K168_authorized': k168['plan']['authorized'],
        'K168_research_consumed': ledger['research_calls_consumed'],
        'K168_native_consumed': ledger['native_requests_consumed'], 'K168_claim': ledger['claim'],
        'K168_state': ledger['state']}

def save(name, value):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main(after=False):
    started = time.perf_counter()
    cache = {}
    def get(name):
        if name not in cache:
            cache[name] = sha(REPO / name) if (REPO / name).is_file() else None
        return cache[name]
    if not after:
        k171_path = RESULTS / 'bound_build_replay01/review/before_manifest.json'
        k171 = read(k171_path)
        expected = {**k171['groups'], **k171['frozen_directory_scopes']}
        prior_differences = []
        groups = {}
        for label, mapping in expected.items():
            groups[label] = {name: get(name) for name in mapping}
            prior_differences.extend({'group': label, 'path': name, 'expected': old, 'actual': get(name)}
                for name, old in mapping.items() if get(name) != old)
        scopes = {}
        for folder in [RESULTS / 'p0_execution01', RESULTS / 'p0_resume01', RESULTS / 'p1_execution01',
                       RESULTS / 'p2_execution01', RESULTS / 'bound_build_replay01']:
            scopes[rel(folder)] = {name: get(name) for name in scan(folder)}
        current = state()
        passed = (not prior_differences and current['deadline_unstarted'] == 24
            and not current['unexpected_claims'] and current['K168_authorized'] is False
            and current['K168_research_consumed'] == current['K168_native_consumed'] == 0
            and current['K168_claim'] is None and current['K168_state'] == 'PENDING_USER_CONFIRMATION')
        value = {'protocol': 'K172-independent-integrity-before-v1',
            'K171_before_manifest_sha256': sha(k171_path), 'groups': groups,
            'frozen_directory_scopes': scopes, 'original_scientific_source_count': 253,
            'new_task_directory_excluded': rel(HERE.parent), 'prior_differences': prior_differences,
            'state': current, 'unique_files_hashed': len(cache),
            'hash_only_wall_s': time.perf_counter() - started, 'new_scientific_calls': 0,
            'source_inventory_not_extended_as_K168_run_approval': True, 'passed': passed}
        save('before_manifest.json', value)
        print(json.dumps({'passed': passed, 'files': len(cache), 'prior_differences': len(prior_differences),
            'scopes': {name: len(v) for name, v in scopes.items()}, 'state': current}, ensure_ascii=False))
    else:
        before = read(HERE / 'before_manifest.json')
        differences = []
        for category in ('groups', 'frozen_directory_scopes'):
            for label, mapping in before[category].items():
                differences.extend({'category': category, 'group': label, 'path': name,
                    'expected': old, 'actual': get(name)} for name, old in mapping.items() if get(name) != old)
                if category == 'frozen_directory_scopes':
                    differences.extend({'category': category, 'group': label, 'added': name}
                        for name in sorted(set(scan(REPO / label)) - set(mapping)))
        current = state()
        passed = not differences and current == before['state']
        save('after_manifest.json', {'protocol': 'K172-independent-integrity-after-v1',
            'before_manifest_sha256': sha(HERE / 'before_manifest.json'), 'differences': differences,
            'unique_files_rehashed': len(cache), 'state_before': before['state'], 'state_after': current,
            'hash_only_wall_s': time.perf_counter() - started, 'new_scientific_calls': 0, 'passed': passed})
        print(json.dumps({'passed': passed, 'files': len(cache), 'differences': len(differences), 'state': current}, ensure_ascii=False))
    assert passed

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--after', action='store_true')
    main(parser.parse_args().after)
