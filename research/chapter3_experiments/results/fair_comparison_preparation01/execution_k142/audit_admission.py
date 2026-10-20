"""Independent saved-identity admission only; never imports a method."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

OUT = Path(__file__).resolve().parent
FROZEN = OUT.parent
ROOT = next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
canonical = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False,
    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def main():
    d = read(FROZEN/'declaration.json')
    ledger = read(FROZEN/'ledger.json')
    gate = read(FROZEN/'wrapper_checks.json')
    prior = read(FROZEN/'verification.json')
    context = read(FROZEN/'phase_context.json')
    checks = []
    def check(name, value, evidence):
        checks.append({'name': name, 'passed': bool(value), 'evidence': evidence})
    check('zero_consumption_before_authorized_run', ledger['state']=='DECLARED'
        and ledger['consumed']==0 and ledger['calls']==[]
        and ledger['method_budget_s_reserved']==0, 'ledger.json captured before launcher')
    check('all_execution_claims_absent', not list((FROZEN/'claims').iterdir())
        and not (FROZEN/'launcher_claim.json').exists()
        and not (FROZEN.parent/'minimal_comparison_claim01.json').exists(), 'claims/global/launcher')
    check('four_calls_fixed_order', [j['id'] for j in d['jobs']]
        ==['whole_milp','linked_n1','heft','sa101']
        and d['jobs'][-1]['seed']==101, 'declaration.jobs')
    check('single_300_second_budgets_no_retry', d['method_call_limit']==4
        and d['per_method_budget_s']==300 and not d['retry_allowed']
        and not d['extend_budget_allowed'] and d['technical_fault_stops_remaining_jobs'],
        'declaration budget/retry flags')
    check('all159_current_sources_match_freeze', len(d['source_sha256'])==159
        and all(sha(ROOT/p)==h for p,h in d['source_sha256'].items()), 'current source SHA256')
    check('all159_source_snapshots_match', all(sha(FROZEN/'source_snapshot'/p)==h
        for p,h in d['source_sha256'].items()), 'source_snapshot SHA256')
    inherited = read(FROZEN.parent/'linked_quality_pair01/declaration.json')
    check('all157_K140_sources_unchanged', len(inherited['source_sha256'])==157
        and all(d['source_sha256'].get(p)==h for p,h in inherited['source_sha256'].items()),
        'K140 declaration identities')
    check('three_input_files_byte_identity', all(sha(FROZEN/p)==h
        for p,h in d['input_file_sha256'].items()), 'frozen input bytes')
    check('three_input_semantic_identities', all(canonical(read(FROZEN/p))==d[k]
        ==d['input_identities'][k] for p,k in [('input_raw.json','raw_config_sha256'),
        ('input_config.json','config_sha256'),('input_instance.json','input_sha256')]),
        'independent canonical JSON SHA256')
    check('final_mock25_gate_identity', gate['passed'] and gate['tests_run']==25
        and gate['errors']==0 and gate['failures']==0
        and gate['source_sha256']==d['source_sha256']
        and sha(FROZEN/'wrapper_checks.json')==d['wrapper_checks_sha256'], 'wrapper gate03 archive')
    check('mock_gate_zero_research_native_heat', not any(gate['blocked_calls'].values())
        and all(gate[k]==0 for k in ['native_calls','research_calls','physical_models','thermal_evaluations']),
        'wrapper gate forbidden call counters; not rerun')
    check('prior_independent24_pass', prior['passed'] and prior['count']==24
        and all(c['passed'] for c in prior['checks']), 'K141 verification; not rerun')
    check('protocol_context_byte_bindings', all(context[k+'_sha256']==sha(FROZEN/p)
        for k,p in [('protocol','protocol.md'),('launcher','launcher.py'),
        ('declaration','declaration.json'),('source_audit','source_audit.json')]), 'phase_context.json')
    audit = read(FROZEN/'source_audit.json')
    check('old_evidence_scope_preserved', audit['passed'] and audit['old_unchanged_count']==122
        and audit['old_changed_source_count']==3 and audit['no_current_whole_67_matching_claim'],
        'source_audit; no blanket current125/old67 assertion')
    check('original_input_and_physics_rules', d['window_ms']==400 and d['start_grid_ms']==5
        and d['entry_temperature_degC']==50 and d['maximum_temperature_degC']==80
        and d['idle_policy']=='auto_low_immediate_v1', 'frozen model identities and explicit declarations')
    check('only_linked_fixed_unit_scope', d['shared_deployment_linked_only']
        =={'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'}
        and d['whole_builder_options']=={'prefilter_deadlines':True,'cumulative_precedence':False},
        'execute dispatch reviewed; whole/HEFT/SA mapping choices retained')
    check('linked_scope_and_dual_anchor_declared', d['new_opened_by_scene']==d['linked_opened_by_scene']
        and all(len(v)==4 for v in d['new_opened_by_scene'].values())
        and all(len(v)==2 for v in d['old_opened_by_scene'].values()),
        '4-open/2-closed second pass; original unit and first-pass SAFE closed anchors')
    check('approved_host_single_launcher', context['execution_context_for_future_run']=='approved_host'
        and "'--execution-authorized'" in (FROZEN/'launcher.py').read_text(encoding='utf-8'),
        'launcher source inspected: no retry/restart and separate process wall clock')
    result = {'stage':'K142','reviewer':'本线程独立子代理；非主线⑥跨会话审查',
        'scope':'read-only identity/protocol admission; no tests, model, heat, native or Git',
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'passed':all(c['passed'] for c in checks),'count':len(checks),'checks':checks,
        'new_research_native_model_thermal_calls':0,'frozen_declaration_sha256':sha(FROZEN/'declaration.json')}
    (OUT/'admission_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'admission_review.md').write_text('# K142执行准入独立审查\n\n'
        f'**结论：{"通过" if result["passed"] else "不通过"}，{len(checks)}项。** '
        '当前159源及快照、157项继承、三份输入、25项包装凭据、24项既有独审及协议/launcher/context身份匹配；'
        'ledger仍为0调用、claim均未消费。用户已明确授权四方法各一次300秒，可按冻结顺序执行。\n\n'
        '不重跑测试、构模、热评价或原生探针。四者同原问题、同安全接纳，但搜索覆盖和初始化不等能力；'
        '联动设备固定不施加给三个参照。预算后不得补记新SAFE；技术故障停止剩余调用。'
        'SA101仅单种子探索。本审查为本线程子代理，非主线⑥。\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'count':result['count']},ensure_ascii=False))


if __name__=='__main__':
    main()
