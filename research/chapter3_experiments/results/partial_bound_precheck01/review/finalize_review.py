"""K170 final read-only integrity and report binding; stdlib only, no bound calls."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPO = HERE.parents[4]
RESULTS = ROOT / 'results'
SOURCE = ROOT / 'conditional_energy_bound/bounds.py'
EXPECTED = '9b4fc402a00c71d9f919c3829df0b43277df614fbd5fcfe2aec6d67de02c6e0a'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while block := f.read(1048576):
            h.update(block)
    return h.hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(name, payload):
    with (HERE / name).open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write('\n')

def relative(path):
    return Path(path).relative_to(REPO).as_posix()

def main():
    started = time.perf_counter()
    before = load(HERE / 'before_manifest.json')
    groups = {}
    differences = []
    for key, mapping in before.items():
        if not key.endswith('_sha256') or not isinstance(mapping, dict):
            continue
        actual = {}
        for name, expected in mapping.items():
            p = REPO / name
            got = sha(p) if p.is_file() else None
            actual[name] = got
            if got != expected:
                differences.append({'group': key, 'path': name, 'before': expected, 'after': got})
        groups[key] = {'count': len(mapping), 'sha256': actual}
    preparation = load(HERE / 'preparation_record.json')
    read_actual = {}
    for name, expected in preparation['read_artifact_sha256'].items():
        p = REPO / name
        got = sha(p) if p.is_file() else None
        read_actual[name] = got
        if got != expected:
            differences.append({'group': 'preparation_read_artifacts', 'path': name, 'before': expected, 'after': got})
    binding = load(HERE / 'reference_source_binding.json')
    reference_actual = {}
    for case in binding['cases']:
        mapping = dict(case['reference_files_sha256'])
        mapping[case['historical_artifact_manifest']] = case['historical_manifest_sha256']
        for name, expected in mapping.items():
            p = REPO / name
            got = sha(p) if p.is_file() else None
            reference_actual[name] = got
            if got != expected:
                differences.append({'group': 'historical_reference_binding', 'path': name, 'before': expected, 'after': got})
    slots = load(RESULTS / 'deadline_execution01/declaration.json')['slots']
    unstarted = []
    for slot in slots[16:]:
        found = []
        for camp in ('deadline_execution01', 'deadline_resume01'):
            path = RESULTS / camp / 'claims' / (slot['slot_id'] + '.json')
            if path.exists():
                found.append(relative(path))
        unstarted.append({'ordinal': slot['ordinal'], 'slot_id': slot['slot_id'], 'claims_found': found})
    k168 = RESULTS / 'whole_native_diagnostic_precheck01/run01/real_preparation'
    k168_declaration = load(k168 / 'declaration.json')
    k168_ledger = load(k168 / 'ledger.json')
    pending = (k168_declaration['plan']['authorized'] is False
               and k168_declaration['research_calls_consumed'] == 0
               and k168_ledger['state'] == 'PENDING_USER_CONFIRMATION'
               and k168_ledger['research_calls_consumed'] == 0
               and k168_ledger['native_requests_consumed'] == 0
               and k168_ledger['claim'] is None)
    source_actual = sha(SOURCE)
    guards_ok = not differences and len(unstarted) == 24 and not any(s['claims_found'] for s in unstarted) and pending and source_actual == EXPECTED
    after = {'protocol': 'K170-independent-after-v1', 'before_manifest_sha256': sha(HERE / 'before_manifest.json'),
             'groups': groups, 'preparation_read_artifacts_sha256': read_actual,
             'reference_original_artifacts_sha256': reference_actual,
             'differences': differences, 'old_source_count': 253,
             'old_source_inventory_not_extended_to_new_module': True,
             'original_consumed_unchanged': 16, 'unstarted_original_slots': unstarted,
             'K168_pending': pending, 'new_standalone_source_sha256': source_actual,
             'new_module_not_covered_by_old_K168_inventory': True,
             'no_scientific_imports_or_API_calls_in_this_checker': True,
             'read_hash_wall_s': time.perf_counter() - started, 'passed': guards_ok}
    save('after_manifest.json', after)
    assert guards_ok, differences

    run = load(HERE / 'probe_cost_run02/results.json')
    checks_path = RESULTS / 'conditional_energy_bound_precheck01/run05/checks.json'
    checks = load(checks_path)
    analysis = load(HERE / 'analysis.json')
    expected_counts = {'all_probes': 490, 'energy_prunes': 255, 'ordinary_deadline_excluded': 40,
        'energy_prune_after_deadline': 217, 'new_beyond_deadline_and_legacy_form': 187,
        'device_layer_compatible': 195, 'device_layer_energy_prunes': 66,
        'new_beyond_deadline_legacy_inside_device_layer': 66,
        'forced_additional_beyond_capacity': 22, 'forced_additional_inside_device_layer': 11}
    assert analysis['counts'] == expected_counts
    assert run['passed'] and run['error'] is None and run['repetitions'] == 3
    assert run['source_sha256_before'] == run['source_sha256_after'] == EXPECTED
    assert checks['tests_run'] == 9 and checks['failures'] == checks['errors'] == 0 and checks['test_successful']
    assert checks['source_unchanged'] and checks['guard']['all_attempts_zero']
    assert checks['source_before_sha256'][relative(SOURCE)] == EXPECTED
    assert run['new_models'] == run['new_schedules'] == run['solver_calls'] == run['thermal_or_post_calls'] == 0
    assert len(analysis['forced_extra_examples']) == 22
    example = analysis['illustrative_compatible_example']
    assert example['within_existing_linked_device_layer']
    assert Fraction(example['legacy_conditioned_J']) <= Fraction(example['reference_U_J'])
    assert Fraction(example['capacity_J']) <= Fraction(example['reference_U_J']) < Fraction(example['forced_J'])
    assert Fraction(example['strict_margin_J']) == Fraction(example['forced_J']) - Fraction(example['reference_U_J'])
    record_paths = [SOURCE, ROOT / 'conditional_energy_bound/precheck.py', ROOT / 'conditional_energy_bound/README.md',
        RESULTS / 'partial_bound_precheck01/summary.md', checks_path,
        HERE / 'contract_math.md', HERE / 'implementation_review.json', HERE / 'implementation_review.md',
        HERE / 'probe_protocol.md', HERE / 'frozen_probes.json', HERE / 'probe_scope.json',
        HERE / 'deadline_scope.json', HERE / 'conditional_chain_probe.json', HERE / 'cost_guard_revision.json',
        HERE / 'probe_cost_run01/results.json', HERE / 'probe_cost_run02/results.json',
        HERE / 'analysis.json', HERE / 'probe_summary.md', HERE / 'reference_source_binding.json',
        HERE / 'before_manifest.json', HERE / 'after_manifest.json']
    hashes = {relative(p): sha(p) for p in record_paths}
    review = {'protocol': 'K170-independent-final-review-v1', 'state': 'PASS_WITH_SCOPE_LIMITS',
        'source_sha256': EXPECTED, 'bound_records_sha256': hashes,
        'checks': {
            'final_run05_nine_test_groups_pass': True,
            'final_run02_fixed_three_repetitions_and_stable_source': True,
            'run01_source_drift_failure_retained_not_used_as_final_timing': True,
            'frozen_490_probe_counts_match_report': True,
            'ordinary_deadline_and_legacy_exclusions_separated': True,
            'forced_additional_22_inside_device_layer_11_verified': True,
            'illustrative_28_472119_microJ_strict_example_verified': True,
            'cold_warm_archive_IO_reported_separately': True,
            'original_253_sources_and_frozen_original_evidence_unchanged': True,
            'original_16_consumed_24_unstarted_and_K168_pending_unchanged': True,
            'old_K168_inventory_not_claimed_to_cover_new_module': True,
            'no_new_scientific_calls_or_SAFE_U_or_speedup_claim': True},
        'counts': expected_counts,
        'remaining_limitations': [
            'Overlapping frozen conditions are not visited nodes, disjoint search volume, or a measured production pruning rate.',
            'Reference U is per-case best of eight completed historical P0 methods; no free new-method initial witness and no earlier build-time availability claim.',
            'Device-layer compatibility does not establish mode/OPP/start openness after anchors or existing presolve.',
            'No comparison with the solver internal energy_state_lower_bound or LP presolve was performed.',
            'Archive reference admission is a posthoc prototype, not a connected same-call production upper-bound lifecycle.',
            'No production speed, smaller MILP, new energy gain, or full optimality is established.'],
        'next_step_recommendation': 'Read-only replay of same-call completed U and actual mode/anchor domain at each model-build start; only consider production prefilter if timely new exclusions remain. No separate B&B.',
        'external_approval': False, 'new_research_calls': 0,
        'no_bound_or_reference_API_calls_in_final_review': True}
    save('final_review.json', review)
    markdown = '''# K170独立终审

**限定范围通过。** 总报告、README、最终run05和纯算术run02一致；没有发现需要修改生产算法或补研究调用的问题。

- 冻结490个重叠部分条件中能量排除255项；扣普通期限必要条件后217项，再扣同条件派生旧界后新增187项，其中66项与现联动设备层兼容。
- forced驻留比容量分摊额外排除22项，其中设备层兼容11项。R1 AB B.post＝CPU2/H例，capacity≤U<forced，严格差28.472119 µJ；精确分数核对成立。
- 成本为固定3次算术测量：每题准备＋root中位8.72—11.80 ms，98条件计算＋比较116.95—137.00 ms，原参照读取／hash145—392 ms单列。没有整方法加速结论。
- 最终9组纯预检通过，run02源码前后固定9b4fc402…；开发期run01源码漂移失败保留，不使用其成本形成结论。
- 原253份源、432项既有工件映射、30项目标映射、期限400个原文件、17项账本／声明／终态及K168、K169证据均无变更。期限仍16已消费／24未启动，K168仍未授权、零消费；新增模块不在旧253源码清单内。

**价值与限制：** 该界已有可复现、非共同常数的排除能力，值得保留。历史各题8次方法中的最低U可能来自别的方法或末期，当前195个设备层兼容条件也不是实际局部模型的完整开放域；因此不能声称旧联动法当时就能剪掉66项，或产生了更低能耗与加速。

**下一步建议：** 先只读回放各次构模开始时同次已形成的完整安全U与实际mode／OPP／闭锚。若新界能在构模前新增排除仍开放的模式，才讨论接入现有构造器；若没有，保留为质量分析工具并停止生产筛选投入，不另建B&B。

本审查只读原件、检查精确算术记录与hash，未调用bound接口、求解器、构模、热积分或post。内部审查不代表外部批准。绑定与完整性记录分别见`final_review.json`、`after_manifest.json`和`final_manifest.json`。
'''
    (HERE / 'final_review.md').open('x', encoding='utf-8').write(markdown)
    hashes[relative(HERE / 'final_review.json')] = sha(HERE / 'final_review.json')
    hashes[relative(HERE / 'final_review.md')] = sha(HERE / 'final_review.md')
    save('final_manifest.json', {'protocol': 'K170-independent-final-record-binding-v1',
        'active_review': relative(HERE / 'final_review.json'), 'sha256': hashes,
        'self_excluded': True, 'new_scientific_calls': 0})
    print(json.dumps({'passed': True, 'integrity_differences': len(differences),
                      'original_sources': 253, 'original_call_files': 400,
                      'unstarted': len(unstarted), 'K168_pending': pending,
                      'counts': expected_counts, 'review_sha256': sha(HERE / 'final_review.json')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
