"""K171 read-only original-artifact baseline/final check; standard library only."""
from pathlib import Path
import argparse
import hashlib
import json
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

def save(name, value):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def scan_dir(folder):
    return sorted(rel(p) for p in folder.rglob('*') if p.is_file())

def current_state():
    slots = read(RESULTS / 'deadline_execution01/declaration.json')['slots']
    unexpected = []
    for slot in slots[16:]:
        for campaign in ('deadline_execution01', 'deadline_resume01'):
            path = RESULTS / campaign / 'claims' / (slot['slot_id'] + '.json')
            if path.exists():
                unexpected.append(rel(path))
    k168 = RESULTS / 'whole_native_diagnostic_precheck01/run01/real_preparation'
    declaration = read(k168 / 'declaration.json')
    ledger = read(k168 / 'ledger.json')
    pending = (declaration['plan']['authorized'] is False
        and declaration['research_calls_consumed'] == 0
        and ledger['state'] == 'PENDING_USER_CONFIRMATION'
        and ledger['research_calls_consumed'] == 0
        and ledger['native_requests_consumed'] == 0
        and ledger['claim'] is None)
    return {'original_deadline_consumed': 16, 'original_deadline_unstarted': len(slots[16:]),
            'unexpected_claims': unexpected, 'K168_pending': pending,
            'K168_declared_authorized': declaration['plan']['authorized'],
            'K168_ledger_state': ledger['state'], 'K168_consumed': ledger['research_calls_consumed'],
            'K168_native_consumed': ledger['native_requests_consumed'], 'K168_claim': ledger['claim']}

def before():
    started = time.perf_counter()
    old_before = read(RESULTS / 'partial_bound_precheck01/review/before_manifest.json')
    expected_groups = {k: v for k, v in old_before.items() if k.endswith('_sha256') and isinstance(v, dict)}
    groups = {}
    expected_difference = []
    cache = {}
    def get(path):
        if path not in cache:
            cache[path] = sha(REPO / path) if (REPO / path).is_file() else None
        return cache[path]
    for kind, mapping in expected_groups.items():
        groups[kind] = {p: get(p) for p in mapping}
        for p, old in mapping.items():
            if groups[kind][p] != old:
                expected_difference.append({'group': kind, 'path': p, 'expected': old, 'actual': groups[kind][p]})
    frozen_scope_roots = [
        RESULTS / 'p0_execution01/calls', RESULTS / 'p0_resume01/calls',
        RESULTS / 'p0_execution01/claims', RESULTS / 'p0_resume01/claims',
        RESULTS / 'partial_bound_precheck01', RESULTS / 'conditional_energy_bound_precheck01',
        ROOT / 'conditional_energy_bound']
    frozen_scopes = {}
    for folder in frozen_scope_roots:
        frozen_scopes[rel(folder)] = {p: get(p) for p in scan_dir(folder)}
    p0_states = {}
    for campaign in ('p0_execution01', 'p0_resume01'):
        folder = RESULTS / campaign
        for p in sorted(folder.glob('*.json')):
            p0_states[rel(p)] = get(rel(p))
    groups['P0_campaign_terminal_management_sha256'] = p0_states
    # Bind original reference identity and the previous final report manifest.
    anchors = [RESULTS / 'partial_bound_precheck01/review/final_manifest.json',
        RESULTS / 'partial_bound_precheck01/review/preparation_record.json',
        RESULTS / 'partial_bound_precheck01/review/reference_source_binding.json']
    groups['K170_reference_anchors_sha256'] = {rel(p): get(rel(p)) for p in anchors}
    state = current_state()
    passed = (not expected_difference and state['original_deadline_unstarted'] == 24
        and not state['unexpected_claims'] and state['K168_pending'])
    save('before_manifest.json', {'protocol': 'K171-independent-readonly-before-v1',
        'groups': groups, 'frozen_directory_scopes': frozen_scopes,
        'original_scientific_source_count': len(groups['source_sha256']),
        'source_inventory_not_extended_to_new_replay_files': True,
        'prior_hash_differences': expected_difference, 'state': state,
        'unique_files_hashed': len(cache), 'readonly_hash_wall_s': time.perf_counter() - started,
        'new_scientific_calls': 0, 'new_candidate_or_safe_U': 0,
        'current_new_audit_directory_excluded': rel(HERE.parent), 'passed': passed})
    assert passed, expected_difference
    print(json.dumps({'before_pass': passed, 'old_sources': len(groups['source_sha256']),
        'unique_files_hashed': len(cache), 'prior_differences': len(expected_difference),
        'frozen_scopes': {k: len(v) for k, v in frozen_scopes.items()}, 'state': state}, ensure_ascii=False))

def after():
    started = time.perf_counter()
    baseline = read(HERE / 'before_manifest.json')
    differences = []
    cache = {}
    def get(path):
        if path not in cache:
            cache[path] = sha(REPO / path) if (REPO / path).is_file() else None
        return cache[path]
    for category in ('groups', 'frozen_directory_scopes'):
        for kind, mapping in baseline[category].items():
            for p, old in mapping.items():
                if get(p) != old:
                    differences.append({'category': category, 'group': kind, 'path': p,
                                        'before': old, 'after': get(p)})
            if category == 'frozen_directory_scopes':
                added = sorted(set(scan_dir(REPO / kind)) - set(mapping))
                differences.extend({'category': category, 'group': kind, 'added': p} for p in added)
    state = current_state()
    passed = not differences and state == baseline['state']
    save('after_manifest.json', {'protocol': 'K171-independent-readonly-after-v1',
        'before_manifest_sha256': sha(HERE / 'before_manifest.json'),
        'unique_files_rehashed': len(cache), 'differences': differences,
        'state_before': baseline['state'], 'state_after': state,
        'old253_contents_preserved': not any(d.get('group') == 'source_sha256' for d in differences),
        'new_module_or_replay_not_covered_by_K168_inventory': True,
        'new_scientific_calls': 0, 'readonly_hash_wall_s': time.perf_counter() - started, 'passed': passed})
    assert passed, differences
    print(json.dumps({'after_pass': passed, 'unique_files_rehashed': len(cache),
        'differences': len(differences), 'state': state}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--after', action='store_true')
    args = parser.parse_args()
    after() if args.after else before()
