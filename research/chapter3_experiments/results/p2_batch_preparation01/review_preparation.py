"""Read-only preparation audit: standard library only, no scientific imports."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def audit():
    checks = []
    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
    d = read(HERE/'declaration.json'); g = read(HERE/'precheck.json')
    base = read(ROOT/'results/p1_execution01/declaration.json')
    contrast = read(HERE/'input_contrast.json')
    ids = ['initial_78__R'+str(i) for i in range(1, 6)]
    check('P2_not_authorized', d['authorised_to_execute'] is False
          and d['execution_budget_approved'] is False and d['state'] == 'PREPARED_NOT_AUTHORIZED')
    check('no_launcher_no_claims', d['real_batch_launcher'] == 'NOT_IMPLEMENTED' and not (HERE/'claims').exists())
    ledger = read(HERE/'ledger.json')
    check('zero_budget_consumption_and_reservation', ledger['state'] == 'NOT_AUTHORIZED'
          and ledger['consumed'] == ledger['reserved_method_budget_s'] == 0 and ledger['calls'] == [])
    check('153_pure_checks', g['passed'] and g['tests_run'] == 153
          and g['errors'] == g['failures'] == g['skipped'] == 0 and g['error'] is None)
    check('physical_guards_zero', bool(g['blocked_calls']) and not any(g['blocked_calls'].values()))
    check('zero_scientific_calls', all(d[k] == g[k] == 0 for k in
          ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')))
    check('precheck_sources_and_prior_archives_unchanged', g['source_unchanged'] and g['prior_archives_unchanged'])
    check('218_sources_bound', len(d['source_sha256']) == 218 and g['source_sha256'] == d['source_sha256'])
    check('original_211_sources_unchanged', len(base['source_sha256']) == 211
          and all(d['source_sha256'].get(n) == h == sha(REPO/n) for n, h in base['source_sha256'].items()))
    check('current_and_snapshot_hashes', all(sha(REPO/n) == h == sha(HERE/'source_snapshot'/n)
          for n, h in d['source_sha256'].items()))
    check('prior_archive_hashes', all(sha(REPO/n) == h for n, h in g['prior_archive_sha256'].items()))
    check('evidence_hashes', d['precheck_sha256'] == sha(HERE/'precheck.json')
          and d['protocol_sha256'] == sha(HERE/'protocol.md')
          and d['input_contrast_sha256'] == sha(HERE/'input_contrast.json')
          and d['inherited_declaration_sha256'] == sha(ROOT/'results/p1_execution01/declaration.json'))
    slots = d['proposed_slots']
    check('draft_40_slots_not_budget', len(slots) == 40 and len({s['slot_id'] for s in slots}) == 40
          and all(s['seconds'] == 300 for s in slots) and d['proposed_method_budget_s'] == 12000
          and d['proposed_calendar_reserve_s'] == 19200)
    check('five_declared_conditions', set(d['inputs']) == set(contrast) == set(ids)
          and {s['problem_id'] for s in slots} == set(ids))
    for pid in ids:
        folder = HERE/'inputs'/pid
        raw, config, one = [read(folder/(n+'.json')) for n in ('raw', 'config', 'instance')]
        identity = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                            map(canonical, (raw, config, one))))
        check(pid+':snapshot_identity', identity == d['inputs'][pid]['input_identities'])
        check(pid+':H_original_mode_table', one['response_variant'] == one['settings']['response_variant'] == 'H'
              and contrast[pid]['stage_modes_identical'] and len(contrast[pid]['differences']) == 12)
        check(pid+':78_entry_80_limit_and_original_domain', one['settings']['initial_temperature_degC'] == '78'
              and one['window_ms'] == '400' and one['start_grid_ms'] == '5'
              and len(one['scenarios']) == 2 and all(s['entry']['temperature_degC'] == ['78']*4
                  and s['maximum_temperature_degC'] == ['80']*4 and len(s['stage_instances']) == 6
                  and len(s['dependencies']) == 4 for s in one['scenarios']))
    return {'passed': all(c['passed'] for c in checks), 'count': len(checks), 'checks': checks,
            'research_calls': 0, 'physical_models': 0, 'thermal_evaluations': 0,
            'audit_script_sha256': sha(Path(__file__)), 'declaration_sha256': sha(HERE/'declaration.json')}


if __name__ == '__main__':
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
