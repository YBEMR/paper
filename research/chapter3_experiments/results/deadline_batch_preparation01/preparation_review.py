"""Independent stdlib-only K162 preparation review; never research execution.

Default output uses exclusive creation. Re-run with --check-only to inspect
the same material without overwriting review records. This script imports no
production scheduler, evaluator, solver, or precheck modules.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
REPO = ROOT.parents[1]
SOURCE = ROOT/'deadline_batch'
PROTOCOL = 'K162-deadline-beta1.0-preparation-only-v1'
COUNTERS = ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations')
PROBLEMS = tuple('beta_1.0__R'+str(i) for i in range(1, 6))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def differences(left, right, prefix=''):
    if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
        return [item for key in sorted(left)
                for item in differences(left[key], right[key], prefix+'/'+key)]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [item for index, (one, two) in enumerate(zip(left, right))
                for item in differences(one, two, prefix+'/'+str(index))]
    return [] if left == right else [{'path': prefix, 'P0': left, 'Deadline': right}]


def review():
    checks = []
    def check(name, passed, **detail):
        checks.append({'name': name, 'passed': bool(passed), **detail})
    declaration = read(OUT/'declaration.json')
    precheck = read(OUT/'precheck.json')
    inherited = read(ROOT/'results/p2_execution01/declaration.json')
    ledger = read(OUT/'ledger.json')
    subject = sha(OUT/'declaration.json')

    check('preparation_state_and_execution_authorization_closed',
        declaration.get('protocol') == PROTOCOL
        and declaration.get('state') == 'PREPARED_NOT_AUTHORIZED'
        and declaration.get('authorised_to_execute') is False
        and declaration.get('execution_budget_approved') is False
        and declaration.get('real_batch_launcher') == 'NOT_IMPLEMENTED'
        and declaration.get('historical_initialization') is False)
    check('zero_consumption_reservation_and_no_claims',
        ledger == {'protocol': PROTOCOL, 'state': 'NOT_AUTHORIZED', 'consumed': 0,
                   'reserved_method_budget_s': 0, 'calls': []}
        and not (OUT/'claims').exists()
        and not (OUT/'calls').exists()
        and all(declaration.get(key) == 0 for key in COUNTERS))
    check('budget_is_only_a_proposal',
        [declaration.get(k) for k in ('proposed_calls', 'proposed_seconds_each',
            'proposed_method_budget_s', 'proposed_calendar_reserve_s')]
        == [40, 300, 12000, 19200])
    check('precheck_evidence_and_protocol_hashes_bound',
        all(sha(OUT/name) == declaration.get(key) for name, key in (
            ('precheck.json', 'precheck_sha256'), ('protocol.md', 'protocol_sha256'),
            ('input_contrast.json', 'input_contrast_sha256')))
        and sha(SOURCE/'protocol.md') == sha(OUT/'protocol.md')
        and declaration.get('inherited_declaration_sha256')
            == sha(ROOT/'results/p2_execution01/declaration.json'))
    check('182_guarded_pure_tests_passed_without_skips',
        precheck.get('protocol') == PROTOCOL and precheck.get('passed') is True
        and precheck.get('tests_run') == 182
        and all(precheck.get(k) == 0 for k in ('errors', 'failures', 'skipped', *COUNTERS))
        and precheck.get('error') is None
        and precheck.get('source_unchanged') is True
        and precheck.get('prior_archives_unchanged') is True,
        tests_run=precheck.get('tests_run'))
    expected_guards = {'whole', 'linked', 'heuristic', 'matlab', 'milp', 'linprog',
                       'model', 'heat', 'candidate_heat', 'scene_heat', 'subprocess',
                       'seed_generator'}
    check('all_twelve_guard_counters_zero',
        set(precheck.get('blocked_calls', {})) == expected_guards
        and all(value == 0 for value in precheck['blocked_calls'].values()),
        guards=precheck.get('blocked_calls'))
    check('successful_precheck02_copied_exactly',
        sha(ROOT/'results/deadline_precheck02/checks.json') == sha(OUT/'precheck.json'))
    failed = read(ROOT/'results/deadline_precheck01/checks.json')
    changed_checks = sorted(name for name, digest in failed['source_sha256'].items()
                            if precheck['source_sha256'].get(name) != digest)
    allowed_repair = {f'research/chapter3_experiments/deadline_batch/{name}' for name in
                      ('prepare_deadline.py', 'test_deadline.py', 'protocol.md')}
    check('first_failed_precheck_retained_and_repair_limited_to_new_contract',
        failed.get('passed') is False and failed.get('tests_run') == 182
        and failed.get('errors') == 3 and failed.get('failures') == 0
        and all(value == 0 for value in failed.get('blocked_calls', {}).values())
        and (ROOT/'results/deadline_precheck01/unittest.txt').is_file()
        and set(changed_checks) == allowed_repair,
        failed_errors=failed.get('errors'), changed_new_files=changed_checks)
    all_sources = declaration['source_sha256']
    old_sources = inherited['source_sha256']
    check('234_sources_include_all_224_unchanged_inherited_sources',
        len(all_sources) == 234 and len(old_sources) == 224
        and set(old_sources) <= set(all_sources)
        and all(all_sources[name] == digest for name, digest in old_sources.items())
        and precheck['source_sha256'] == all_sources)
    bad_live = [name for name, digest in all_sources.items()
                if not (REPO/name).is_file() or sha(REPO/name) != digest]
    bad_snapshot = [name for name, digest in all_sources.items()
                   if not (OUT/'source_snapshot'/name).is_file()
                   or sha(OUT/'source_snapshot'/name) != digest]
    check('all_live_sources_and_frozen_snapshot_hashes_match',
        not bad_live and not bad_snapshot,
        mismatched_live=bad_live, mismatched_snapshot=bad_snapshot)
    frozen_names = {p.relative_to(OUT/'source_snapshot').as_posix()
                    for p in (OUT/'source_snapshot').rglob('*') if p.is_file()}
    check('source_snapshot_has_exact_declared_file_coverage', frozen_names == set(all_sources))
    bad_old = [name for name, digest in precheck['prior_archive_sha256'].items()
               if not (REPO/name).is_file() or sha(REPO/name) != digest]
    check('twelve_recorded_prior_archive_identities_unchanged',
        len(precheck['prior_archive_sha256']) == 12 and not bad_old,
        mismatched_prior_artifacts=bad_old,
        scope='12 recorded prior receipt/ledger/inventory files; not a rehash of all old result payloads')

    lineage = read(SOURCE/'lineage.json')
    lineage_ok = len(lineage) == 1
    for item in lineage:
        origin, target = REPO/item['origin'], SOURCE/item['target']
        text = origin.read_text(encoding='utf-8')
        lineage_ok = lineage_ok and sha(origin) == item['sha256']
        lineage_ok = lineage_ok and item.get('function') is None
        lineage_ok = lineage_ok and item['replacements'] == [[
            'from p2_entry import jobs, fresh_input',
            'from deadline_entry import jobs, fresh_input']]
        for old, new in item['replacements']:
            lineage_ok = lineage_ok and text.count(old) == 1
            text = text.replace(old, new)
        lineage_ok = lineage_ok and text == target.read_text(encoding='utf-8')
    check('scientific_dispatch_exact_except_input_module_import', lineage_ok)
    source_tree = ast.parse((SOURCE/'prepare_deadline.py').read_text(encoding='utf-8'))
    refused = any(isinstance(node, ast.If)
        and ast.unparse(node.test) == "args.mode == 'run'"
        and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == 'error' for statement in node.body for call in ast.walk(statement))
        for node in ast.walk(source_tree))
    check('run_cli_explicitly_refused_in_preparation_source', refused)
    protocol = (OUT/'protocol.md').read_text(encoding='utf-8')
    check('protocol_records_thirteen_fields_and_no_scientific_expansion',
        '13' in protocol and 'ablation_input' in protocol
        and 'NO_COMPLETE_SAFE_LINKED_SEED' in protocol
        and 'authorised_to_execute=false' in protocol
        and '没有新的初始化模板' in protocol)

    contrast = read(OUT/'input_contrast.json')
    check('exact_five_problem_ids_in_declared_and_frozen_inputs',
        set(declaration['inputs']) == set(PROBLEMS) == set(contrast)
        and {p.name for p in (OUT/'inputs').iterdir() if p.is_dir()} == set(PROBLEMS))
    expected_deadlines = [('95', '121', '110'), ('76', '145.2', '110'),
        ('114', '96.8', '110'), ('95', '96.8', '132'), ('95', '145.2', '88')]
    observed_deadlines = {}
    for pid, expected in zip(PROBLEMS, expected_deadlines):
        definition = declaration['inputs'][pid]
        folder = OUT/'inputs'/pid
        values = [read(folder/(name+'.json')) for name in ('raw', 'config', 'instance')]
        raw, config, instance = values
        check(pid+':three_input_hashes_and_identity_map',
            all(canonical(value) == definition[key] == definition['input_identities'][key]
                for value, key in zip(values,
                    ('raw_config_sha256', 'config_sha256', 'input_sha256')))
            and definition['problem_id'] == instance['id'] == pid)
        base_folder = ROOT/'results/p0_batch_preparation01/inputs'/pid.replace('beta_1.0__', 'base__')
        base_raw, base_config, base = [read(base_folder/(name+'.json'))
                                     for name in ('raw', 'config', 'instance')]
        delta = differences(base, instance)
        expected_paths = {'/id', '/condition_id', '/experiment_group',
                          '/settings/deadline_beta', '/ablation_input'}
        expected_paths |= {f'/scenarios/{i}/requests/{j}/{name}' for i in range(2)
                           for j in range(2) for name in ('relative_deadline_ms', 'deadline_ms')}
        check(pid+':independent_thirteen_field_difference_and_unchanged_modes',
            len(delta) == 13 and {v['path'] for v in delta} == expected_paths
            and raw == base_raw and config == base_config
            and instance['stage_modes'] == base['stage_modes']
            and instance['ablation_input'] is False and base['ablation_input'] is True
            and sorted(delta, key=lambda x: x['path']) == sorted(contrast[pid]['differences'], key=lambda x: x['path']))
        requests = [r for s in instance['scenarios'] for r in s['requests']]
        got = {r['application']: F(r['relative_deadline_ms']) for r in requests}
        expected_table = dict(zip('ABC', map(F, expected)))
        check(pid+':exact_cpu_high_reference_deadline_formula_and_table',
            F(instance['settings']['deadline_beta']) == 1
            and F(base['settings']['deadline_beta']) == F('1.3')
            and got == expected_table
            and all(F(r['relative_deadline_ms']) == F(r['reference_CPU_H_chain_ms'])
                    and F(r['deadline_ms']) == F(r['release_ms'])+F(r['reference_CPU_H_chain_ms'])
                    for r in requests),
            relative_deadline_ms={k: str(v) for k, v in got.items()})
        observed_deadlines[pid] = {k: str(v) for k, v in got.items()}
        check(pid+':complete_scenes_and_physical_conditions_retained',
            instance['response_variant'] == 'H' and F(instance['window_ms']) == 400
            and F(instance['start_grid_ms']) == 5
            and len(instance['scenarios']) == 2
            and all(len(s['requests']) == 2 and len(s['stage_instances']) == 6
                    and len(s['dependencies']) == 4
                    and list(map(F, s['entry']['temperature_degC'])) == [F(50)]*4
                    and list(map(F, s['maximum_temperature_degC'])) == [F(80)]*4
                    for s in instance['scenarios']))
        base_definition = read(ROOT/'results/p0_batch_preparation01/declaration.json')['inputs'][base['id']]
        check(pid+':unchanged_two_and_four_opened_masks_and_scene_spec',
            all(definition[key] == base_definition[key] for key in
                ('scene_spec', 'first_opened_by_scene', 'linked_opened_by_job'))
            and all(len(v) == 2 for v in definition['first_opened_by_scene'].values())
            and all(len(v) == 4 for v in definition['linked_opened_by_job']['anchor_linked4'].values()))

    methods = [dict(id='whole_milp', method='milp'),
        dict(id='anchor_linked4', method='linked_fixed_unit_opp_start', opened_count=4,
             preeliminate_closed_anchors=True), dict(id='heft', method='heft', seed=None)]
    expected_slots = []
    for index, pid in enumerate(PROBLEMS):
        blocks = [[dict(v)] for v in methods]+[[dict(id='sa'+str(seed), method='sa', seed=seed)
                                               for seed in range(101, 106)]]
        rotate = index % 4
        jobs = [v for block in blocks[rotate:]+blocks[:rotate] for v in block]
        expected_slots.extend(dict(v, problem_id=pid, slot_id=pid+'__'+v['id'], seconds=300,
                                   ordinal=index*8+position+1)
                              for position, v in enumerate(jobs))
    slots = declaration['proposed_slots']
    check('forty_slots_exact_rotation_seed_order_and_unique_identities',
        slots == expected_slots and len({s['slot_id'] for s in slots}) == 40
        and Counter(s['problem_id'] for s in slots) == dict.fromkeys(PROBLEMS, 8)
        and sum(s['seconds'] for s in slots) == 12000)
    check('review_did_not_change_subject_declaration', subject == sha(OUT/'declaration.json'))
    return {'schema': 'K162-independent-stdlib-preparation-review-v1',
        'reviewed_at_utc': datetime.now(timezone.utc).isoformat(),
        'review_scope': 'independent internal preparation audit; not external approval or physical reproduction',
        'subject_declaration_sha256': subject,
        'review_script_sha256': sha(__file__),
        'passed': all(row['passed'] for row in checks),
        'check_count': len(checks), 'checks': checks,
        'deadline_table_ms': observed_deadlines,
        'authorised_to_execute': False, 'new_research_calls': 0,
        'new_native_calls': 0, 'new_physical_models': 0, 'new_thermal_evaluations': 0,
        'limitations': ['No production scheduler/evaluator imported or run.',
            'No native MILP vector or new thermal trajectory independently reproduced.',
            'Guard-zero evidence is checked from the saved precheck; the 182 tests were not re-run here.',
            'Only the twelve explicitly recorded prior archive identities are rehashed, not all historic payloads.']}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--check-only', action='store_true')
    args = cli.parse_args()
    paths = [OUT/'preparation_review.json', OUT/'internal_review.md']
    if not args.check_only and any(p.exists() for p in paths):
        raise FileExistsError('Review files already exist; use --check-only instead of overwriting')
    result = review()
    if not args.check_only:
        with paths[0].open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        failed = [r['name'] for r in result['checks'] if not r['passed']]
        text = ('# K162期限组准备独立内部核查\n\n'
            f"结论：{'通过' if result['passed'] else '未通过'}；{result['check_count']}项只读核查，失败{len(failed)}项。"
            '这是本项目内部的独立存档核查，不是另一ChatGPT会话的外部批准，不授权研究调用。\n\n'
            '核对了234份当前源码及快照哈希、224份继承源码、5份期限输入及13字段差异、'
            '40拟议槽位/轮转/种子、零预算账本和无claims、182项预检凭据及12个生产调用守卫。'
            '首轮182项中3项契约错误保留；修正只涉及新准备器、其测试和协议，未修改科学生成器。\n\n'
            '各请求期限按CPU最高频参考链长×β生成；β从1.3改为1.0，H响应、50°C初温、80°C温限、'
            '400 ms窗口、5 ms起点、活动/基准/本地温度漏电、auto-L及原完整场景/分解范围保持。'
            'ablation_input由true变false是既有条件目录标识，已独立列入第13项差异，未增加消融调用。\n\n'
            '本核查仅使用标准库读取材料、计算文件/JSON哈希、逐字段与有理数核对；'
            '未导入生产规划/评价器，未重跑182项测试、求解器、种子生成或热积分。'
            '旧归档保护只复核预检列出的12份库存/账本/终态身份，不冒称重新计算全部历史结果。\n\n'
            f"绑定声明SHA256：`{result['subject_declaration_sha256']}`。\n\n"
            '执行预算仍未批准：建议40×300秒、方法12000秒、日历19200秒；'
            '正式执行还须独立预算确认及真实受控启动流程冻结/预检。\n\n'
            f"详细结果：[preparation_review.json](preparation_review.json)。失败项：{failed or '无'}。\n\n"
            '复跑：`F:/Anaconda3/python.exe -B research/chapter3_experiments/results/'
            'deadline_batch_preparation01/preparation_review.py --check-only`。\n')
        with paths[1].open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    print(json.dumps({'passed': result['passed'], 'checks': result['check_count'],
        'failed': [v['name'] for v in result['checks'] if not v['passed']],
        'new_research_calls': 0, 'writes': not args.check_only}, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
