"""Final K167 independent review; binds final run04 and preserves all history."""
import hashlib
import json
from pathlib import Path
import unittest
import audit_integrity as audit
import test_hook_invariants as hook

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE.parent

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(name,value):
    with (HERE/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')

def main():
    before=read(HERE/'before_manifest.json')
    tests=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(hook.HookInvariantTests))
    after=audit.verify(before)
    after.update(whole_augmented_sha256=sha(ROOT/'whole_augmented.py'),formal_hook_sha256=sha(ROOT/'formal_milp.py'),
        hook_AST_passed=tests.wasSuccessful(),hook_AST_tests_run=tests.testsRun)
    save('after_manifest02.json',after)
    original_probe=HERE/'archive_retention_probe01/probe.json'
    correction={'protocol':'K167-independent-probe-scope-correction-v1',
        'superseded_probe_sha256':sha(original_probe),'production_bug_finding':False,
        'reason':'The earlier probe replaced _WholeRequest.archive itself with an exception, bypassing its documented _save exception handling. It cannot establish a production bug.',
        'valid_replacement':'archive_save_probe02/probe.json','replacement_sha256':sha(HERE/'archive_save_probe02/probe.json'),
        'raw_probe_preserved':True,'new_scientific_calls':0}
    save('probe_scope_correction.json',correction)
    run=read(OUT/'run04/checks.json');probe=read(HERE/'archive_save_probe02/probe.json')
    callback=read(HERE/'callback_identity_probe01/probe.json')
    technical=read(OUT/'run04/fixtures/test_technical_exception_keeps_previous_safe_and_stops/fixture_result.json')
    checks={
        'run04_passed26':run['passed'] and run['tests_run']==26 and run['failures']==run['errors']==0,
        'run04_sources_unchanged':run['source_sha256_before']==run['source_sha256_after'],
        'run04_matches_current_source':all(sha(Path(p))==h for p,h in run['source_sha256_before'].items()),
        'guard_all_zero':run['guard']['all_scientific_attempts_zero'] and not any(run['guard']['blocked_entry_attempts'].values()),
        'final_whole_SHA_matches_parent_freeze':sha(ROOT/'whole_augmented.py')=='f913b927e7ef6e1c58e682442d4bfd94e137fa7dfbc6ecb834b5aaf5e49d98bc',
        'default_AST3_passed':tests.wasSuccessful() and tests.testsRun==3,
        'only_expected_old_source_hook':after['old_source_changes']==[audit.ALLOWED] and after['all_other_247_sources_and_old_artifacts_preserved'],
        'original432_target30_call400_bound':before['prior_artifact_count']==432 and before['target_count']==30 and before['archived_call_files_count']==400,
        '16consumed24unstarted':after['consumed']==16 and after['unstarted']==24 and not after['unexpected_started_remaining_slots'],
        'technical_reason_is_derived_not_timeout':technical['reason']=='WHOLE_AUGMENTED_TRANSPORT_UNRESOLVED' and technical['formal_reason_before_admission_classification']=='SOLVER_RETURN_AFTER_BUDGET' and 'interface' in technical['whole_augmented']['failure_categories'],
        'technical_fixture_prior_SAFE_preserved':technical['state']=='SAFE' and technical['safe_upper_bound_J']=='1.0',
        'real_save_exception_contract_passed':probe['passed'] and probe['source_sha256_before']==probe['source_sha256_after']==sha(ROOT/'whole_augmented.py'),
        'old_archive_probe_explicitly_invalidated':correction['production_bug_finding'] is False,
        'callback_probe_historical_and_rejecting':callback['source_sha256_before']==callback['source_sha256_after'] and callback['context_latched'] and not callback['derived_accepted_for_evaluation'],
        'final_callback_identity_gate_retained':'CALLBACK_RESPONSE_CONTENT_IDENTITY_MISMATCH' in (ROOT/'whole_augmented.py').read_text('utf-8')}
    assert all(checks.values()),checks
    review={'protocol':'K167-internal-independent-whole-interface-review-v2','active':True,
        'decision':'PASS_INTERFACE_AND_PURE_FIXTURES_ONLY','passed':True,'checks':checks,'checks_run':len(checks),
        'final_whole_source_sha256':sha(ROOT/'whole_augmented.py'),'formal_hook_sha256':sha(ROOT/'formal_milp.py'),
        'precheck_run':'run04','precheck_tests':26,'precheck_sha256':sha(OUT/'run04/checks.json'),
        'hook_AST_tests':3,'historical_review':'final_review.json',
        'historical_review_sha256':sha(HERE/'final_review.json'),
        'integrity_before_sha256':sha(HERE/'before_manifest.json'),'integrity_after_sha256':sha(HERE/'after_manifest02.json'),
        'archive_save_probe_sha256':sha(HERE/'archive_save_probe02/probe.json'),
        'probe_correction_sha256':sha(HERE/'probe_scope_correction.json'),
        'callback_probe_source_sha256':callback['source_sha256_before']['whole_augmented.py'],
        'callback_probe_is_final_source_reexecution':False,
        'scope':'Internal child-agent interface review, not external ChatGPT approval, native compatibility or physical safety validation.',
        'remaining_unverified':['Old R2 label recovery, transformation, numeric recheck and exitflag -2 cause.',
            'Full-scale whole transformed-row coverage, expanded size and cost.',
            'Real MATLAB admission and native numerical compatibility.',
            'Physical safety, energy improvement and independent optimum/infeasibility proof.'],
        'new_solver_calls':0,'new_models':0,'new_thermal_evaluations':0,'new_post_calls':0,
        'further_native_or_research_authorization':False}
    save('final_review02.json',review)
    summary='''# K167独立审查：最终run04

**接口与纯夹具审查通过。** 有效版本为`final_review02.json`，绑定whole源码`f913b927…`及run04的26项通过；旧`final_review.json`对应ef1/run03，仅作历史记录。本审查为内部子代理核查，不替代外部审批，不授权恢复24个未启动槽。

|核查项|结论|
|---|---|
|默认流程及反馈|3项独立AST检查通过；去除可选hook后完整旧函数保持，热反馈时机不变|
|当前身份与坐标|同次live标签、数组、映射及原生/派生回执分列；x0、callback、final先通过原/增广/链接门，再交原坐标完整评价|
|事件身份|请求前缀及编号绑定；不可变事件文件保留向量，返回callback摘要按worker原协议省略x。较早源码的同编号异内容负例作为历史探测，最终门仍在|
|非预算技术故障|新adapter将仍有时间的技术拒绝派生为TRANSPORT_UNRESOLVED，另存原formal的RETURN_AFTER_BUDGET reason；不改旧formal及raw native|
|落盘异常与旧U|在真实_save层注入第二次admission保存OSError，实际archive捕获、锁存interface，返回明确archive未决，并保留已成替身SAFE/U|
|完整性|除formal预期hook外247旧源不变；旧432工件、当前30目标、16调用400文件及输入/终态不变，24槽未启动|

原archive_retention_probe01替换了整个archive方法，绕开生产异常契约，不能说明生产缺陷；原始记录保留，纠正说明见probe_scope_correction.json。有效替代仅注入_save层，8项核对通过，未增加科学工作。

最终15项审查通过，run04及探测均无真实solver、科学构模、热积分或post。所有夹具SAFE/U都是明确替身，不能作为真实研究结果。原R2仍未变换、未补跑；原生能否接纳、真实whole转换覆盖与成本、数值冲突根因及节能效果仍待验证。
'''
    with (HERE/'summary02.md').open('x',encoding='utf-8') as stream:stream.write(summary)
    save('review_manifest02.json',{'active_review':'final_review02.json','active_summary':'summary02.md',
        'historical_review':'final_review.json','review_sha256':sha(HERE/'final_review02.json'),
        'summary_sha256':sha(HERE/'summary02.md'),'after_sha256':sha(HERE/'after_manifest02.json'),
        'run04_sha256':sha(OUT/'run04/checks.json'),'script_sha256':sha(Path(__file__)),
        'source_sha256':sha(ROOT/'whole_augmented.py'),'new_scientific_calls':0})
    print({'passed':True,'review_checks':len(checks),'precheck_tests':26,'hook_AST_tests':3,'real_save_probe_checks':len(probe['checks']),'consumed':16,'unstarted':24})

if __name__=='__main__':main()
