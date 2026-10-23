"""Independent metadata-only final K172 design review; no scientific imports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
REPO = HERE.parents[4]
CHECKS = []

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def check(name, value):
    CHECKS.append({'name': name, 'passed': bool(value)})

def save(name, value):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    proposal_path = AUDIT / 'preparation02/proposal.json'
    proposal = read(proposal_path)
    machine = read(AUDIT / 'proposal_checks_run02/checks.json')
    pure = read(AUDIT / 'precheck/run02/checks.json')
    audit = read(AUDIT / 'audit/facts.json')
    after = read(HERE / 'after_manifest.json')
    archive = read(HERE / 'archive_budget_seed_evidence.json')
    check('final_proposal_prepare_source_binding', proposal['preparation_source_sha256'] == sha(AUDIT / 'prepare.py') == machine['preparation_source_sha256'])
    check('14_final_recipe_checks_pass', machine['passed'] and machine['count'] == 14 and all(machine['checks'].values()))
    check('8_final_pure_label_clock_checks_pass', pure['tests_run'] == 8 and pure['failures'] == pure['errors'] == 0 and pure['sources_and_original_archives_unchanged'] and pure['guard']['all_zero'])
    check('static_source_audit_passed', audit['passed'])
    check('4735_old_files_preserved', after['passed'] and after['unique_files_rehashed'] == 4735 and not after['differences'])
    check('deadline_and_K168_not_changed', after['state_before'] == after['state_after'] and after['state_after']['deadline_unstarted'] == 24 and after['state_after']['deadline_consumed_preserved'] == 16 and after['state_after']['K168_authorized'] is False)
    check('all_new_execution_flags_false', proposal['authorized'] is False and proposal['scientific_execution_enabled'] is False and proposal['preparation_only'] is True and proposal['real_launcher_implemented'] is False)
    check('zero_consumption_reserved_native_post_and_no_claim', proposal['research_calls_consumed'] == proposal['research_seconds_reserved'] == proposal['native_requests_consumed'] == proposal['post_calls_consumed'] == 0 and proposal['claim'] is None)
    check('exact_development_cases', [c['common']['case_id'] for c in proposal['cases']] == ['base__R1', 'base__R3'])
    check('counterbalanced_fixed_six_slots', [(s['case_id'], s['variant']) for s in proposal['slots']] == [('base__R1', 'A'), ('base__R1', 'B'), ('base__R1', 'C'), ('base__R3', 'C'), ('base__R3', 'B'), ('base__R3', 'A')])
    check('all_slots_pending_once_300_and_post60', all(s['run_once'] is True and s['method_seconds'] == 300 and s['post_seconds_max'] == 60 and s['state'] == 'PENDING_USER_CONFIRMATION' for s in proposal['slots']))
    for case in proposal['cases']:
        common = case['common']
        cid = common['case_id']
        campaign = 'p0_execution01' if cid == 'base__R1' else 'p0_resume01'
        old = REPO / 'research/chapter3_experiments/results' / campaign / 'calls' / cid / 'anchor_linked4'
        result, config, instance = [read(old / name) for name in ('result.json', 'input_config.json', 'input_instance.json')]
        check(cid + '_original_full_input_and_config_IDs', common['input_sha256'] == canonical(instance) == result['identity']['full_input_sha256'] and common['config_sha256'] == canonical(config))
        check(cid + '_original_common_rule_inputs', common['shared_deployment'] == result['shared_deployment'] and common['builder_options'] == result['builder_options'] and common['accuracy_targets'] == config['accuracy_targets'] and common['control_policy'] == result['control_policy'])
        check(cid + '_opened_sets_from_actual_phase_conditions', common['first_opened_by_scene'] == result['phases'][0]['condition']['opened_by_scene'] and common['second_opened_by_scene'] == result['phases'][1]['condition']['opened_by_scene'])
        check(cid + '_window_grid_and_scenes_unchanged', common['window_ms'] == instance['window_ms'] and common['start_grid_ms'] == instance['start_grid_ms'] and common['scene_order'] == [s['id'] for s in instance['scenarios']] and common['scene_weights'] == {s['id']: s['weight'] for s in instance['scenarios']})
        arms = case['recipes']
        check(cid + '_A_single_phase_150_no_phase2_kwargs', arms['A']['entry_module'] == 'neighborhood_method' and arms['A']['entry_function'] == 'execute_n1_neighborhood' and arms['A']['second_phase'] is False and arms['A']['kwargs']['scene_slice_s'] == 150 and 'linked_opened_by_scene' not in arms['A']['kwargs'] and 'preeliminate_closed_anchors' not in arms['A']['kwargs'])
        b, c = deepcopy(arms['B']['kwargs']), deepcopy(arms['C']['kwargs'])
        off, on = b.pop('preeliminate_closed_anchors'), c.pop('preeliminate_closed_anchors')
        check(cid + '_B_C_only_preelimination_parameter_differs', b == c and off is False and on is True and b['scene_slice_s'] == 60)
        for label, arm in arms.items():
            check(cid + '_' + label + '_same_root_and_fresh_rules', arm['kwargs']['seconds'] == 300 and arm['kwargs']['shared_deployment'] == common['shared_deployment'] and arm['kwargs']['builder_options'] == common['builder_options'] and arm['kwargs']['opened_by_scene'] == common['first_opened_by_scene'] and arm['new_bound_filter'] is False and arm['scientific_execution_authorized'] is False)
            check(cid + '_' + label + '_no_archived_warm_seed_U_or_cache', not {'seed_candidate', 'warm_candidate', 'seed_receipt', 'warm_receipt', 'safe_upper_bound_J', 'cache'}.intersection(arm['kwargs']))
            check(cid + '_' + label + '_arm_import_under_same_root_recipe', 'before arm-entry import' in arm['runtime_arguments']['budget'])
    full = proposal['budget_proposal']['recommended_full_development']
    reduced = proposal['budget_proposal']['reduced_B_C_only']
    check('full_6x300_plus_unique6x60_separate_wall', full['research_calls_max'] == 6 and full['method_seconds_total_max'] == 1800 and full['post_seconds_total_max'] == 360 and full['method_plus_post_seconds_max'] == 2160 and full['overall_wall_proposal_s'] == 3600 and full['slot_wall_sum_max_s'] == 2880)
    check('reduced_4x300_plus4x60_separate_wall', reduced['research_calls_max'] == 4 and reduced['method_seconds_total_max'] == 1200 and reduced['post_seconds_total_max'] == 240 and reduced['method_plus_post_seconds_max'] == 1440 and reduced['overall_wall_proposal_s'] == 2400 and reduced['slot_wall_sum_max_s'] == 1920)
    check('budgets_pending_watchdogs_not_extension', proposal['budget_proposal']['watchdog_is_not_evidence_extension'] is True and proposal['budget_proposal']['all_budget_fields_pending'] is True and full['method_return_watchdog_s'] == 420 and full['slot_watchdog_s'] == 480)
    expected_options = {'AbsoluteGapTolerance': 0, 'RelativeGapTolerance': 0, 'ConstraintTolerance': '1e-9', 'IntegerTolerance': '1e-6', 'IntegerPreprocess': 'none', 'LPPreprocess': 'none', 'CutMaxIterations': 10, 'Display': 'off'}
    check('native_scientific_options_match_original', all(proposal['solver_options'][k] == value for k, value in expected_options.items()))
    check('scientific_sources_and_original_archive_IDs_current', all(sha(REPO / name) == value for name, value in proposal['source_sha256'].items()) and all(sha(REPO / name) == value for name, value in proposal['archive_readonly_sha256'].items()))
    check('own_archive_evidence_still_bound', all(sha(REPO / r['path']) == r['sha256'] for r in archive['records']) and all(sha(REPO / name) == value for name, value in archive['source_sha256'].items()))
    check('no_real_claim_or_launcher_in_proposal', proposal['claim'] is None and proposal['real_launcher_implemented'] is False)
    assert all(c['passed'] for c in CHECKS), [c for c in CHECKS if not c['passed']]
    paths = [AUDIT / 'README.md', AUDIT / 'protocol.md', AUDIT / 'prepare.py', AUDIT / 'check_proposal.py',
        proposal_path, AUDIT / 'preparation01/proposal.json', AUDIT / 'proposal_checks_run02/checks.json',
        AUDIT / 'proposal_checks_run01/checks.json', AUDIT / 'precheck/run02/checks.json',
        AUDIT / 'precheck/check_labels.py', AUDIT / 'precheck/README.md', AUDIT / 'audit/facts.json',
        AUDIT / 'audit/source_budget_audit.md', AUDIT / 'audit/proposal_review.json',
        HERE / 'before_manifest.json', HERE / 'after_manifest.json', HERE / 'design_review.md',
        HERE / 'archive_budget_seed_evidence.json', HERE / 'extract_archive_evidence.py', HERE / 'integrity.py',
        REPO / 'RESEARCH_BRIEF.md', REPO / 'research/03_证据与检索记录.md']
    hashes = {p.relative_to(REPO).as_posix(): sha(p) for p in paths}
    review = {'protocol': 'K172-independent-final-preparation-review-v1',
        'state': 'PREPARATION_ACCEPTED_PENDING_BUDGET_AND_LAUNCHER',
        'prepared_not_launcher_admitted_or_authorized': True, 'checks': CHECKS,
        'checks_passed': len(CHECKS), 'evidence_sha256': hashes,
        'source_subject_is_scientific_baseline_not_new_approval': proposal['source_subject'],
        'future_approval_must_bind_delivery_commit_and_frozen_launcher': True,
        'comparison_interpretation': {
            'A_vs_B': 'End-to-end one-phase versus two-phase search organization including allocation, extra construction and existing phase2 transport, not a single-variable causal estimate.',
            'B_vs_C': 'One declared parameter differs; own independent phase1 anchors must match before interpreting same-subproblem elimination. Different anchors allow only end-to-end result statements.',
            'development_limits': 'R1/R3 are openly selected development cases; two pairs do not establish general ranking, stability or novelty.'},
        'recommendation': 'Six pending calls answer both organization and preprocessing; four B/C calls suffice only for preprocessing. Submit for review; run neither option now.',
        'remaining_execution_acceptance': ['one-shot source/env/claim/ledger binding',
            'same root before arm imports and all case work; public imports recorded separately',
            'N1-only versus linked result-shape audit and normal-status/identity/isolation gate before post',
            'same-rule independent fresh seed and own complete phase1 anchor identity',
            'single 60s post for eligible final SAFE only, no new or replaced U',
            'fault/late evidence/source drift cleanup and stop behavior in fake end-to-end checks'],
        'old_integrity': {'unique_files': 4735, 'differences': 0, 'old_sources': 253,
            'deadline_consumed': 16, 'deadline_unstarted': 24, 'K168_pending': True},
        'new_scientific_calls': 0, 'new_models': 0, 'optimizer_or_native_calls': 0,
        'thermal_or_post_calls': 0, 'new_candidate_or_SAFE_U': 0,
        'budget_authorized': False, 'external_approval': False}
    save('final_review.json', review)
    text = '''# K172独立终审

**准备通过，可提交预算审查；当前未获执行授权，也未验收真实启动链。** 最终02配方、8项纯夹具和14项参数核对一致，本审查另核''' + str(len(CHECKS)) + '''项元数据／原件身份，均通过。

- A使用既有N1接口、每场景150秒软上限、同300秒绝对根；B/C原四片60秒，仅第二阶段预消元开关不同。A提前返回不补满、不加遍；所有臂入口导入及病例工作纳入同一根，公共依赖导入单列。
- B/C若第一阶段锚不同，只能比较端到端本次结果，不能将全部终值差唯一归因于同锚删列。A/B还包含时间配置、额外构模及第二阶段原数值传输，不是单变量消融。
- 4次B/C足以只核预消元；6次A/B/C才能同时核“继续N1还是转入联动块”。完整方法1800秒＋唯一post最多360秒＝2160秒、日历3600秒；缩减方案1200＋240＝1440秒、日历2400秒，均待批。post前先过方法正常终态、身份及隔离门，不因已有U越过技术阻断。
- 独立hash前后4735个旧文件零差异，含旧253源码、完整P0/P1/P2、K170/K171、期限原件及K168。期限仍16已消费／24未启动，K168仍pending、零消费；本任务不挪用其预算。
- 旧归档只提取输入／seed标签hash及有效参数，未给新调用导出候选、U或缓存。纯标签／时钟夹具不是模型、热安全或真实MATLAB验证。

本轮0构模、0优化／原生请求、0热积分／post、0新候选／安全U。后续若获批，须绑定新交付commit及独占薄执行层，完成fake整槽准入；科学基线2a2ab35及旧K168凭据不自动授予这批执行权。

证据绑定见`final_review.json`、`final_manifest.json`，原件核对见`before_manifest.json`／`after_manifest.json`。内部审查不代替用户或外部批准。
'''
    with (HERE / 'final_review.md').open('x', encoding='utf-8') as f:
        f.write(text)
    hashes[(HERE / 'final_review.json').relative_to(REPO).as_posix()] = sha(HERE / 'final_review.json')
    hashes[(HERE / 'final_review.md').relative_to(REPO).as_posix()] = sha(HERE / 'final_review.md')
    save('final_manifest.json', {'protocol': 'K172-independent-final-evidence-binding-v1',
        'active_review': (HERE / 'final_review.json').relative_to(REPO).as_posix(),
        'sha256': hashes, 'self_excluded': True, 'prepared_only': True, 'new_scientific_calls': 0})
    print(json.dumps({'state': review['state'], 'checks_passed': len(CHECKS),
        'review_sha256': sha(HERE / 'final_review.json'), 'old_differences': 0,
        'execution_authorized': False}, ensure_ascii=False))

if __name__ == '__main__':
    main()
