"""K161 read-only source/input/budget freeze check; no scientific imports."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = HERE.parents[3]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def audit():
    checks = {}
    d = read(HERE/'declaration.json'); g = read(HERE/'precheck.json')
    prior = read(ROOT/'results/p2_batch_preparation01/declaration.json')
    ledger = read(HERE/'ledger.json')
    checks['authorized_40x300_12000_19200'] = (d['authorized'] is True and d['call_limit'] == 40
        and d['seconds_each'] == 300 and d['total_reserved_method_seconds'] == 12000
        and d['calendar_stop_s'] == 19200)
    checks['old_preparation_not_rewritten'] = (prior['authorised_to_execute'] is False
        and d['P2_preparation_sha256'] == sha(ROOT/'results/p2_batch_preparation01/declaration.json')
        and read(ROOT/'results/p2_batch_preparation01/ledger.json')['consumed'] == 0)
    checks['170_pure_checks_passed'] = (g['passed'] is True and g['tests_run'] == 170
        and g['errors'] == g['failures'] == g['skipped'] == 0 and g['error'] is None)
    checks['no_scientific_precheck_calls'] = (not any(g['blocked_calls'].values())
        and all(g[k] == 0 for k in ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')))
    checks['224_sources_bound'] = len(d['source_sha256']) == 224 and g['source_sha256'] == d['source_sha256']
    checks['current_and_snapshot_exact'] = all(sha(REPO/n) == h == sha(HERE/'source_snapshot'/n)
        for n, h in d['source_sha256'].items())
    checks['inherited_218_unchanged'] = len(prior['source_sha256']) == 218 and all(
        d['source_sha256'].get(n) == h for n, h in prior['source_sha256'].items())
    checks['evidence_protocol_hashes'] = d['precheck_sha256'] == sha(HERE/'precheck.json') and d['protocol_sha256'] == sha(HERE/'protocol.md')
    checks['P0_P1_archives_bound'] = d['P0_manifest_sha256'] == sha(ROOT/'results/p0_resume01/archive_inventory.json') and d['P1_manifest_sha256'] == sha(ROOT/'results/p1_execution01/archive_inventory.json')
    checks['40_once_only_slots'] = d['slots'] == prior['proposed_slots'] and len({s['slot_id'] for s in d['slots']}) == 40 and sum(s['seconds'] for s in d['slots']) == 12000
    checks['zero_consumption_before_launch'] = ledger['consumed_total'] == ledger['reserved_total_method_s'] == 0 and ledger['calls'] == [] and ledger['active'] is None
    checks['no_claim_before_launch'] = not list((HERE/'claims').iterdir()) and not (HERE/'launcher_claim.json').exists() and not (ROOT/'results/p2_execution_claim01.json').exists()
    checks['supervision_and_post_unchanged'] = (d['method_return_watchdog_s'], d['slot_watchdog_s'], d['post_seconds']) == (420, 480, 60)
    checks['no_retry_or_historical_initialization'] = d['retry_methods'] is False and d['historical_initialization'] is False
    checks['H_78_only_condition'] = d['change_condition'] == 'P0_original_H_initial_temperature_50_to_78_only'
    for pid, definition in d['inputs'].items():
        triple = [read(HERE/'inputs'/pid/name) for name in ('raw_config.json', 'config.json', 'instance.json')]
        checks[pid+'/prepared_identity'] = definition == prior['inputs'][pid] and definition['input_identities'] == dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'), map(canonical, triple)))
        one = triple[2]
        checks[pid+'/original_H_78_entry_80_limit'] = one['response_variant'] == 'H' and all(s['entry']['temperature_degC'] == ['78']*4 and s['maximum_temperature_degC'] == ['80']*4 for s in one['scenarios'])
    return {'protocol': 'K161-P2-prelaunch-readonly-check-v1', 'passed': all(checks.values()),
        'count': len(checks), 'checks': checks, 'script_sha256': sha(Path(__file__)),
        'declaration_sha256': sha(HERE/'declaration.json'), 'research_calls': 0}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
