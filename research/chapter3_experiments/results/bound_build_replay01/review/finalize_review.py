"""Bind final K171 review to immutable evidence; no scientific or bound API calls."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
REPO = HERE.parents[4]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    records = read(HERE / 'record_checks_run01.json')
    integrity = read(HERE / 'after_manifest.json')
    helpers = read(HERE / 'helper_checks_run01.json')
    run = read(AUDIT / 'run02/results.json')
    assert records['passed'] and integrity['passed'] and helpers['passed'] and run['passed']
    for name, value in records['record_sha256_after'].items():
        assert sha(REPO / name) == value, name
    paths = [AUDIT / 'protocol.md', AUDIT / 'summary.md', AUDIT / 'replay.py',
        AUDIT / 'timeline/facts.json', AUDIT / 'timeline/summary.md', AUDIT / 'timeline/extract_timeline.py',
        AUDIT / 'domain/facts.json', AUDIT / 'domain/summary.md', AUDIT / 'domain/extract_domains.py',
        AUDIT / 'domain/facts_run01.json', AUDIT / 'run01/results.json', AUDIT / 'run02/results.json',
        HERE / 'before_manifest.json', HERE / 'after_manifest.json', HERE / 'integrity.py',
        HERE / 'protocol_review.md', HERE / 'test_replay_helpers.py', HERE / 'helper_checks_run01.json',
        HERE / 'helper_function_binding.json', HERE / 'verify_records.py', HERE / 'record_checks_run01.json',
        REPO / 'research/chapter3_experiments/conditional_energy_bound/bounds.py']
    hashes = {str(p.relative_to(REPO)).replace('\\', '/'): sha(p) for p in paths}
    assert run['summary'] == {'builds': 20, 'open_mode_instances': 180, 'excludable_modes': 0,
        'excludable_nonzero_option_columns': 0, 'beyond_conditioned_legacy': 0, 'forced_extra_over_capacity': 0}
    review = {'protocol': 'K171-independent-final-review-v1', 'state': 'PASS_WITH_SCOPE_LIMITS',
        'active_root_run': 'run02/results.json', 'evidence_sha256': hashes,
        'checks': {
            'timeline_33_updates_20_original_builds_not_final_U_backfill': True,
            'same_call_complete_global_U_before_build_rederived': True,
            'phase_partial_original_two_scene_fixed_units_closed_OPPs_only': True,
            'real_open_mode_domain_and_old_filter_exclusions_separate': True,
            'independent_1201_record_checks_pass': True,
            'independent_17_pure_helper_fixtures_pass_and_final_AST_identical': True,
            'exact_strict_compare_ties_kept_no_production_pruning_token': True,
            'global_U_not_required_to_satisfy_child': True,
            'compatible_original_SAFE_and_actual_warm_modes_preserved': True,
            'root_report_counts_timing_and_closest_gap_match': True,
            'old_253_sources_and_2085_unique_original_artifacts_unchanged': True,
            'deadline_16_consumed_24_unstarted_and_K168_pending_preserved': True,
            'new_readonly_sources_not_claimed_covered_by_old_K168_inventory': True,
            'no_production_integration_or_scientific_calls': True},
        'summary': {'builds': 20, 'complete_original_updates': 33, 'phase1_open_modes': 60,
            'phase2_open_modes': 120, 'open_mode_instances': 180,
            'nonzero_open_option_instances': 3463, 'closed_option_instances': 60,
            'timely_excludable_modes': 0, 'timely_excludable_options': 0,
            'closest_gap_J_approx': '0.01974418371933061',
            'closest_mode': 'base__R1/phase_2/AC_offset_0ms/A.main@NPU0:H',
            'closest_mode_original_options': 19},
        'scope_limits': [
            'Zero exclusions concerns exactly the twenty original build-start instants and 180 one-mode conditions; no multi-mode tree or per-candidate-update screening was tested.',
            'The bounds relax starts, resources and thermal constraints; this is not a recreated MILP matrix or a new safety certificate.',
            'Read-only archive and arithmetic wall time is not already charged to the historical 300-second calls and is not an algorithm speedup measurement.',
            'Existing complete SAFE receipts are verified and reused as archive evidence, without new thermal evaluation.',
            'Earlier K170 posthoc exclusion counts remain valid in their scope, but do not establish timely production benefit.',
            'Internal review is not external ChatGPT approval and grants no K168 run or deadline resumption authority.'],
        'recommendation': 'Stop current one-mode production screening integration; retain standalone quality bound. Discuss pending K168 separately if continuing experimental preparation.',
        'root_algebra_only_calls_are_not_scientific_calls': True,
        'independent_bound_API_calls': 0, 'new_models': 0, 'solver_calls': 0,
        'thermal_or_post_calls': 0, 'new_research_calls': 0, 'external_approval': False}
    save(HERE / 'final_review.json', review)
    markdown = '''# K171独立终审

**限定范围通过，建议停止当前单模式构模前筛选接线。** 20个原构模时点均有及时的同次完整安全U，但180个实际开放模式、3463个开放起点选项中，严格能量排除为0。

- 17项纯夹具通过；最终脚本的三个闸门函数AST与受测版本相同。未来／错调用／局部SAFE／未交付U均拒绝，恰等构模时刻不视为已提前可用；严格有理比较保留并列。
- 独立1201项记录核对通过。从原phase condition重新提取两个场景的固定设备及关闭OPP，逐条核对原开放mode／起点列、同次及时最小U、完整receipt身份、三个完整界取max、兼容安全见证及实际warm保持。未调用bound接口或生产函数。
- 最接近排除的是R1第二阶段AC的A.main／NPU0／H，19个原起点，U－LB仍为19.744183719 mJ。终期更低U形成太晚，不能倒用；第一阶段开放的B.post/H在第二阶段已关闭为L，也不能算后期新增筛选机会。
- 总稿的33次完整更新、20构模、60／120开放模式及3463／60开放／关闭列与原记录一致。run02约1.14秒只读回放成本不等于原调用已支付成本或求解加速。
- 2085个唯一原件前后hash无差异，包括253份旧源码、P0全部860个调用文件及155个claims、期限原件与旧K170证据。期限仍16已消费／24未启动，K168仍pending且零消费；新增脚本不在旧253执行清单内。

0排除只覆盖本协议的构模开始点和单模式条件，不代表所有下界机制无效。K170后验排除仍成立，但当前未转化成可及时使用的筛选机会。本轮无新安全U、优化结果、热评价、节能或最优性结论。

建议保留下界作质量工具，暂不接生产、不追加界开关实验或另建B&B。若继续实验准备，K168预算与启动确认独立讨论；本审查不授予执行或期限续接权限。

证据绑定见`final_review.json`与`final_manifest.json`，原件核对见`before_manifest.json`、`after_manifest.json`。本结论为内部独立核对，不代替外部批准。
'''
    with (HERE / 'final_review.md').open('x', encoding='utf-8') as f:
        f.write(markdown)
    hashes[str((HERE / 'final_review.json').relative_to(REPO)).replace('\\', '/')] = sha(HERE / 'final_review.json')
    hashes[str((HERE / 'final_review.md').relative_to(REPO)).replace('\\', '/')] = sha(HERE / 'final_review.md')
    save(HERE / 'final_manifest.json', {'protocol': 'K171-independent-final-binding-v1',
        'active_review': str((HERE / 'final_review.json').relative_to(REPO)).replace('\\', '/'),
        'sha256': hashes, 'self_excluded': True, 'new_scientific_calls': 0})
    print(json.dumps({'state': review['state'], 'checks': 1201, 'helper_tests': 17,
        'review_sha256': sha(HERE / 'final_review.json'), 'old_integrity_differences': 0,
        'timely_exclusions': 0}, ensure_ascii=False))

if __name__ == '__main__':
    main()
