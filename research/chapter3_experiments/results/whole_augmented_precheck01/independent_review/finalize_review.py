"""Finalize K167 independent review from frozen source and pure-fixture records."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE.parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    before,after=read(HERE/'before_manifest.json'),read(HERE/'after_manifest01.json')
    current=read(OUT/'run03/checks.json')
    probe=read(HERE/'callback_identity_probe01/probe.json')
    source=ROOT/'whole_augmented.py'
    check_sources=current['source_sha256_before']
    checks={
        'final_run03_passed':current.get('passed') is True and current.get('tests_run')==26
            and current.get('failures')==0 and current.get('errors')==0,
        'run03_source_before_after_equal':check_sources==current['source_sha256_after'],
        'run03_sources_match_current_files':all(sha(Path(name))==digest for name,digest in check_sources.items()),
        'run03_scientific_guard_zero':current['guard']['all_scientific_attempts_zero'] is True
            and all(value==0 for value in current['guard']['blocked_entry_attempts'].values()),
        'only_expected_formal_hook_changes_old248':after['old_source_changes']==[audit_allowed()]
            and after['all_other_247_sources_and_old_artifacts_preserved'] is True,
        'whole_source_matches_final_integrity':sha(source)==after['whole_augmented_sha256'],
        'formal_source_matches_final_integrity':sha(ROOT/'formal_milp.py')==after['formal_hook_sha256'],
        'default_hooks_restore_old_AST':after.get('hook_AST_passed') is True and after.get('hook_AST_tests_run')==3,
        'prior432_target30_and_call400_bound':before['prior_artifact_count']==432
            and before['target_count']==30 and before['archived_call_files_count']==400,
        'consumed16_unstarted24_preserved':after['consumed']==16 and after['unstarted']==24
            and not after['unexpected_started_remaining_slots'],
        'independent_callback_probe_old_source_not_mislabeled_final':probe['context_latched'] is True
            and probe['same_event_number'] is True and probe['different_callback_content'] is True
            and probe['derived_accepted_for_evaluation'] is False
            and probe['source_sha256_before']==probe['source_sha256_after'],
        'final_source_contains_callback_header_identity_gate':'CALLBACK_RESPONSE_CONTENT_IDENTITY_MISMATCH' in source.read_text('utf-8'),
    }
    assert all(checks.values()),checks
    review={'protocol':'K167-internal-independent-whole-interface-review-v1','decision':'PASS_INTERFACE_AND_PURE_FIXTURES_ONLY',
        'scope':'Internal child-agent review, not external ChatGPT approval; no native compatibility, old R2 repair or optimization claim.',
        'checks':checks,'checks_run':len(checks),'passed':True,
        'final_whole_source_sha256':sha(source),'formal_hook_sha256':sha(ROOT/'formal_milp.py'),
        'precheck_run':'run03','precheck_tests':26,'precheck_sha256':sha(OUT/'run03/checks.json'),
        'hook_AST_tests':3,
        'independent_probe_scope':{'source_sha256':probe['source_sha256_before']['whole_augmented.py'],
            'final_source_reexecuted':False,'reason':'Earlier-source adversarial callback probe retained as development evidence; final source retains the rejecting header gate and is bound to run03.'},
        'source_locators':{
            'formal_milp.py':'solve_formal_diagnostic recorder_factory and execute_formal_milp diagnostic_solver optional hooks only; entire old bodies recovered by AST substitution',
            'whole_augmented.py':'WholeAugmentedContext.prepare; _WholeRequest.assess_vector/fail; WholeAugmentedRecorder.poll/assess; WholeAugmentedSession.solve/_derived; audit_whole_augmented_evidence',
            'solve_model.m':'callback intentionally clears x only in final callback summary; immutable live event retains original vector'},
        'remaining_unverified':['No original R2 trusted-label recovery, transformation, numeric vector recheck or solve.',
            'No full-scale whole transformed-row coverage, expanded size/cost or native compatibility measurement.',
            'No proof of the prior exitflag -2 cause or universal numerical correctness.',
            'No new physical SAFE, energy improvement, solver bound or independent optimality/infeasibility certificate.'],
        'integrity_before_sha256':sha(HERE/'before_manifest.json'),
        'integrity_after_sha256':sha(HERE/'after_manifest01.json'),
        'new_solver_calls':0,'new_models':0,'new_thermal_evaluations':0,'new_post_calls':0,
        'old_files_modified_by_review':False,'old24_slots_started':False,
        'further_native_or_research_authorization':False}
    with (HERE/'final_review.json').open('x',encoding='utf-8') as stream:json.dump(review,stream,ensure_ascii=False,indent=2);stream.write('\n')
    summary='''# K167内部独立审查

**通过接口与纯夹具范围内的审查；未验证原生兼容或原R2修复。** 最终whole源码绑定run03的26项通过记录，3项独立AST检查通过。此为本线程子代理内部审查，不替代外部ChatGPT审批，不授权恢复24次调用。

|边界|核查结论|
|---|---|
|默认方法与热反馈|formal只增加两个可选hook；去掉hook后完整函数AST恢复旧版，反馈条件、见证检查及加入位置保持|
|当前数组/标签/映射|取同一whole Recorder的live Model；逐请求新建映射与原/增广身份；旧R2没有被恢复标签或变换|
|原坐标数值门|x0追加、callback及final先过原/增广/链接门，之后才交原Recorder解码和全场景评价；final保留增广坐标至该门，不发生误双投影|
|事件身份|请求号与预期前缀绑定；callback元数据摘要与不可变发布文件匹配，文件hash保留原向量。worker按原协议在最终callback摘要省略x，故摘要比较明确排除该字段|
|原生/派生回执|native_rounds及原python回执保持原样，派生token绑定请求/矩阵/native hash；原生−2和数值异常不变成独立无解|
|预算与故障|同一MethodBudget覆盖变换、记录和数值门；技术失败与预算拒绝分列；锁存后不新开请求；已有budget取消文件不覆盖|
|已成SAFE/U|不借历史候选，沿原初始化包装及Recorder保留已有完整见证；迟到或错误新向量不新增U|

独立小矩阵负例在较早源码上验证了“同callback编号但不同内容”被拒绝、原合法live替身SAFE保留，记录原样保存；没有把这次探测冒称最终源码重跑。最终源码仍有该身份门，并重新绑定run03。所有SAFE均为显式评价替身，不能作为研究安全结果。

最终完整性：248旧源中只有formal_milp.py的预期可选hook变化；其余247源、旧432工件、当前30目标、16调用400个文件及声明/终态/输入保持，24槽仍未启动。全部源hash和核对见before_manifest、after_manifest与final_review.json。

仍未知：完整whole实际转换行覆盖数、扩维规模与成本、原生是否接纳、原−2具体原因及真实节能效果。K167只完成必要接口和纯夹具工作；本审查新增构模、原R2变换/数值复检、solver、热积分及post均0。
'''
    with (HERE/'summary.md').open('x',encoding='utf-8') as stream:stream.write(summary)
    manifest={'review_sha256':sha(HERE/'final_review.json'),'summary_sha256':sha(HERE/'summary.md'),
        'script_sha256':sha(Path(__file__)),'run03_sha256':sha(OUT/'run03/checks.json'),
        'before_sha256':sha(HERE/'before_manifest.json'),'after_sha256':sha(HERE/'after_manifest01.json'),
        'new_scientific_calls':0}
    with (HERE/'review_manifest.json').open('x',encoding='utf-8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({'passed':True,'review_checks':len(checks),'run03_tests':26,'hook_AST_tests':3,'no_native_or_research_approval':True})


def audit_allowed():return 'research/chapter3_experiments/formal_milp.py'


if __name__=='__main__':main()
