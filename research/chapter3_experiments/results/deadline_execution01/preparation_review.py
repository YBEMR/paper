"""K163 independent pre-launch inspection using the standard library only.

This inspects saved inputs, source hashes and lifecycle code. It never imports
the scientific package, creates a candidate, or runs a model/solver/heat check.
--check-only prints a fresh inspection without overwriting any review record.
The pre-launch assertions deliberately fail after the unique launcher starts.
"""
import argparse
import ast
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]
PREP = ROOT/'results/deadline_batch_preparation01'
CODE = ROOT/'deadline_execution'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def differences(a, b, prefix=''):
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [v for key in a for v in differences(a[key], b[key], prefix+'/'+key)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [v for i, (x, y) in enumerate(zip(a, b)) for v in differences(x, y, prefix+'/'+str(i))]
    return [] if a == b else [{'path': prefix, 'P0': a, 'deadline': b}]


def functions(text, names):
    lines = text.splitlines(keepends=True)
    nodes = {n.name: n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    return '\n\n'.join(''.join(lines[nodes[name].lineno-1:nodes[name].end_lineno]).rstrip()
                        for name in names)+'\n'


def inspect():
    checks = []
    def check(name, value):
        checks.append({'name': name, 'passed': bool(value)})
    d = read(HERE/'declaration.json')
    old = read(PREP/'declaration.json')
    gate = read(HERE/'precheck.json')
    ledger = read(HERE/'ledger.json')
    check('exact_protocol_and_execution_budget', d.get('protocol') == 'K163-deadline-beta1.0-authorized-40x300-once-v1'
          and d.get('authorized') is True and (d.get('call_limit'), d.get('seconds_each'),
          d.get('total_reserved_method_seconds'), d.get('calendar_stop_s')) == (40, 300, 12000, 19200))
    check('evidence_and_watchdog_limits_distinct', (d.get('method_return_watchdog_s'),
          d.get('slot_watchdog_s'), d.get('post_seconds')) == (420, 480, 60))
    check('no_retries_or_historical_initialization', d.get('retry_methods') is False
          and d.get('historical_initialization') is False
          and d.get('change_condition') == 'P0_original_H_deadline_beta_1.3_to_1.0_only')
    live = (CODE/'deadline_controller.py').read_text(encoding='utf-8')
    literals = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(live).body
                if isinstance(n, ast.Assign) and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'AUTHORIZATION'}
    authorization = d.get('authorization', '')
    check('authorization_accurately_records_contextual_continue', authorization == literals.get('AUTHORIZATION')
          and all(word in authorization for word in ('继续吧', '40', '300', '12000', '19200', '不补跑', '不延时')))
    check('old_preparation_remains_unapproved', old.get('authorised_to_execute') is False
          and old.get('execution_budget_approved') is False
          and read(PREP/'ledger.json') == {'protocol': old['protocol'], 'state': 'NOT_AUTHORIZED',
                                         'consumed': 0, 'reserved_method_budget_s': 0, 'calls': []}
          and not (PREP/'claims').exists())
    check('bound_preparation_and_precheck_hashes', d.get('deadline_preparation_sha256') == sha(PREP/'declaration.json')
          and d.get('precheck_sha256') == sha(HERE/'precheck.json'))
    check('protocol_copy_and_live_source_match', d.get('protocol_sha256') == sha(HERE/'protocol.md')
          == sha(CODE/'protocol.md'))
    check('all_240_current_and_snapshot_sources_match', len(d['source_sha256']) == 240
          and all(sha(REPO/name) == digest == sha(HERE/'source_snapshot'/name)
                  for name, digest in d['source_sha256'].items()))
    check('all_original_234_sources_preserved', len(old['source_sha256']) == 234
          and all(d['source_sha256'].get(name) == digest for name, digest in old['source_sha256'].items()))
    added = set(d['source_sha256'])-set(old['source_sha256'])
    check('only_six_execution_files_added', added == {f'research/chapter3_experiments/deadline_execution/{name}'
          for name in ('deadline_controller.py', 'deadline_supervise.py', 'deadline_run_precheck.py',
                       'test_deadline_execution.py', 'protocol.md', 'lineage.json')})
    check('205_guarded_tests_passed', gate.get('passed') is True and gate.get('tests_run') == 205
          and gate.get('source_sha256') == d['source_sha256'] and gate.get('source_unchanged') is True
          and gate.get('prior_archives_unchanged') is True
          and gate.get('errors') == gate.get('failures') == gate.get('skipped') == 0
          and gate.get('error') is None)
    check('all_twelve_production_guards_zero', len(gate.get('blocked_calls', {})) == 12
          and not any(gate['blocked_calls'].values())
          and all(gate.get(name) == 0 for name in ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')))
    check('prior_archives_unchanged', bool(gate.get('prior_archive_sha256'))
          and all(sha(REPO/name) == digest for name, digest in gate['prior_archive_sha256'].items()))
    check('P0_P1_P2_archive_manifests_bound',
          d.get('P0_manifest_sha256') == sha(ROOT/'results/p0_resume01/archive_inventory.json')
          and d.get('P1_manifest_sha256') == sha(ROOT/'results/p1_execution01/archive_inventory.json')
          and d.get('P2_manifest_sha256') == sha(ROOT/'results/p2_execution01/archive_inventory.json'))
    for item in read(CODE/'lineage.json'):
        origin = REPO/item['origin']
        source = origin.read_text(encoding='utf-8')
        target = (CODE/item['target']).read_text(encoding='utf-8')
        if item.get('functions'):
            source, target = functions(source, item['functions']), functions(target, item['functions'])
        for a, b in item['replacements']:
            source = source.replace(a, b)
        check('declared_inheritance:'+item['target'], sha(origin) == item['sha256'] and source == target)
    check('current_deadline_gate_cannot_be_ignored',
          "records.get('current_schedule_audit',{}).get('passed') is True" in live)
    check('normal_no_U_skips_post_hook',
          "if okay and records.get('usable_U_J') is None:" in live
          and "row['postcheck_wall_s']=0.0" in live
          and "elif okay:" in live)
    expected_ids = tuple('beta_1.0__R'+str(i) for i in range(1, 6))
    check('same_five_inputs_as_preparation', set(d['inputs']) == set(expected_ids) and d['inputs'] == old['inputs'])
    table = [('95', '121', '110'), ('76', '145.2', '110'), ('114', '96.8', '110'),
             ('95', '96.8', '132'), ('95', '145.2', '88')]
    for pid, values in zip(expected_ids, table):
        triple = [read(HERE/'inputs'/pid/name) for name in ('raw_config.json', 'config.json', 'instance.json')]
        prepared = [read(PREP/'inputs'/pid/name) for name in ('raw.json', 'config.json', 'instance.json')]
        ids = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'), map(canonical, triple)))
        check(pid+':three_identities_match', triple == prepared and ids == d['inputs'][pid]['input_identities'])
        one = triple[2]
        check(pid+':H_50_80_400_5_autoL', one['response_variant'] == 'H' and F(one['settings']['deadline_beta']) == 1
              and one['window_ms'] == '400' and one['start_grid_ms'] == '5'
              and all(s['entry']['temperature_degC'] == ['50']*4 and s['maximum_temperature_degC'] == ['80']*4
                      and len(s['requests']) == 2 and len(s['stage_instances']) == 6 for s in one['scenarios'])
              and one['execution_rules'].get('idle_policy') == 'auto_low_immediate_v1')
        expected = dict(zip('ABC', map(F, values)))
        check(pid+':exact_request_deadlines', all(F(r['relative_deadline_ms']) == expected[r['application']]
              == F(r['reference_CPU_H_chain_ms'])
              and F(r['deadline_ms']) == F(r['release_ms'])+expected[r['application']]
              for scene in one['scenarios'] for r in scene['requests']))
        base = read(ROOT/'results/p0_batch_preparation01/inputs'/pid.replace('beta_1.0__', 'base__')/'instance.json')
        expected_paths = {'/id', '/condition_id', '/experiment_group', '/settings/deadline_beta', '/ablation_input'}
        expected_paths |= {f'/scenarios/{i}/requests/{j}/{name}' for i in range(2) for j in range(2)
                           for name in ('relative_deadline_ms', 'deadline_ms')}
        delta = differences(base, one)
        check(pid+':thirteen_deadline_catalog_changes_only', len(delta) == 13
              and {v['path'] for v in delta} == expected_paths and base['stage_modes'] == one['stage_modes'])
    slots = d['slots']
    check('exact_prepared_slots_and_ordinals', slots == old['proposed_slots']
          and len(slots) == len({s['slot_id'] for s in slots}) == 40
          and [s['ordinal'] for s in slots] == list(range(1, 41))
          and sum(s['seconds'] for s in slots) == 12000)
    for pid in expected_ids:
        rows = [s for s in slots if s['problem_id'] == pid]
        check(pid+':eight_slots_fixed_SA_seeds', len(rows) == 8
              and [s['seed'] for s in rows if s['method'] == 'sa'] == list(range(101, 106))
              and {s['id'] for s in rows} == {'whole_milp', 'anchor_linked4', 'heft', *('sa'+str(k) for k in range(101, 106))})
    check('unconsumed_initial_execution_ledger', ledger == {'protocol': d['protocol'], 'state': 'DECLARED',
          'prior_consumed': 0, 'consumed_new': 0, 'consumed_total': 0,
          'reserved_total_method_s': 0, 'calls': [], 'active': None})
    check('unique_launcher_and_research_not_started', not list((HERE/'claims').iterdir())
          and not list((HERE/'calls').iterdir()) and not (HERE/'launcher_claim.json').exists()
          and not (ROOT/'results/deadline_execution_claim01.json').exists())
    failed = [c['name'] for c in checks if not c['passed']]
    return {'protocol': 'K163-independent-prelaunch-review-v1', 'passed': not failed,
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(), 'checks_run': len(checks),
        'checks': checks, 'failed_checks': failed, 'new_research_calls': 0,
        'new_native_calls': 0, 'new_physical_models': 0, 'new_thermal_evaluations': 0,
        'production_modules_imported': False, 'declaration_sha256': sha(HERE/'declaration.json'),
        'review_script_sha256': sha(__file__), 'external_approval': False,
        'scope': 'Independent internal stored input/source/lifecycle inspection before the one launcher; not a scientific run or external approval'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        result = inspect()
    except Exception:
        result = {'protocol': 'K163-independent-prelaunch-review-v1', 'passed': False,
                  'checks_run': 0, 'failed_checks': ['REVIEW_EXCEPTION'], 'error': traceback.format_exc(),
                  'new_research_calls': 0, 'production_modules_imported': False,
                  'review_script_sha256': sha(__file__)}
    if not args.check_only:
        with (HERE/'preparation_review.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({k: result.get(k) for k in ('passed', 'checks_run', 'failed_checks', 'new_research_calls', 'error')}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
