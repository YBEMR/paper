"""Conclude the K168 preparation review from hashes and completed pure checks."""
import argparse
import json
from pathlib import Path
import audit_preparation as audit

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPO=HERE.parents[4]
RESULTS=ROOT/'results'

def main(run):
    run=Path(run).resolve();before=audit.read(HERE/'before_manifest.json')
    after={key:audit.mismatches(before[key]) for key in ('source_sha256','prior_artifact_sha256',
        'target_sha256','original16_call_files_sha256','ledger_declaration_terminal_sha256','previous_evidence_sha256')}
    old=RESULTS/'deadline_execution01';resume=RESULTS/'deadline_resume01'
    slots=audit.read(old/'declaration.json')['slots'];unexpected=[]
    for slot in slots[16:]:
        for camp in (old,resume):
            p=camp/'claims'/(slot['slot_id']+'.json')
            if p.exists():unexpected.append(audit.relative(p))
    evidence=audit.read(run/'checks.json')
    prepared=run/'real_preparation'
    declaration=audit.read(prepared/'declaration.json')
    validation=audit.read(prepared/'validation.json')
    ledger=audit.read(prepared/'ledger.json')
    plan=declaration['plan'];budget=plan['budget']
    checks={
        'before_frozen_originals_unchanged':not any(after.values()),
        'original16_and_unstarted24_preserved':len(before['original16_call_files_sha256'])==400 and len(slots[16:])==24 and not unexpected,
        'completed_pure_prechecks_passed':evidence['passed'] is True and evidence['failures']==evidence['errors']==0,
        'precheck_scientific_guard_zero':evidence['guard']['all_attempts_zero'] is True and not any(evidence['guard']['blocked_attempts'].values()),
        'precheck_test_source_identity':evidence['source_sha256_before']==evidence['source_sha256_after'] and all(audit.sha(p)==h for p,h in evidence['source_sha256_before'].items()),
        'real_preparation_passed':validation['passed'] is True and validation['launch_authorized'] is False,
        'frozen_source_identity':all(audit.sha(REPO/p)==h for p,h in declaration['source_sha256'].items()),
        'frozen_artifact_identity':all(audit.sha(REPO/p)==h for p,h in declaration['artifact_sha256'].items()),
        'pending_not_authorized':plan['status']=='PENDING_USER_CONFIRMATION' and plan['authorized'] is False and plan['execution_ready'] is False and declaration['approval'] is None,
        'zero_consumed_reserved_and_no_claim':declaration['research_calls_consumed']==declaration['native_requests_consumed']==0 and declaration['scientific_work_performed'] is False and ledger['reserved_method_seconds']==0 and ledger['claim'] is None,
        'fixed_1_method_1_native_1_round':plan['research_call_limit']==plan['native_request_limit']==plan['max_outer_rounds']==1,
        'fixed_budget_300_40_420_480_no_post':budget['method_seconds']==300 and budget['cleanup_window_seconds']==40 and budget['method_return_watchdog_seconds']==420 and budget['slot_watchdog_seconds']==480 and budget['post_heat_seconds']==0,
        'original24_not_resumed_or_budget_reused':plan['resume_original_24'] is False and budget['reuse_old_campaign_budget'] is False and plan['retry'] is False and plan['extend_budget'] is False,
        'archived_input_contract_not_fresh_science':declaration['input_contract']['matches_original_R2'] is True and declaration['input_contract']['new_input_construction'] is False and declaration['input_contract']['old_answer_or_vector_loaded'] is False,
        'run_gate_unconditionally_refuses':'raise PermissionError' in (ROOT/'whole_native_diagnostic/prepare.py').read_text('utf8')}
    assert all(checks.values()),checks
    after_record={'protocol':'K168-independent-preparation-after-v1','mismatches':after,
        'unexpected_original24_claims':unexpected,'original_consumed':16,'original_unstarted':24,
        'all_originals_preserved':not any(after.values()) and not unexpected,'scientific_calls':0}
    audit.save(HERE/'after_manifest.json',after_record)
    review={'protocol':'K168-independent-preparation-review-v1','decision':'PASS_PREPARATION_ONLY_PENDING_USER_CONFIRMATION',
        'passed':True,'checks':checks,'checks_run':len(checks),'precheck_tests':evidence['tests_run'],
        'declaration_sha256':audit.sha(prepared/'declaration.json'),'checks_sha256':audit.sha(run/'checks.json'),
        'before_manifest_sha256':audit.sha(HERE/'before_manifest.json'),'after_manifest_sha256':audit.sha(HERE/'after_manifest.json'),
        'protocol_sha256':audit.sha(ROOT/'whole_native_diagnostic/protocol.md'),
        'proposed_method_seconds':300,'proposed_method_calls':1,'proposed_native_requests_maximum':1,
        'proposed_cleanup_window_seconds':40,'proposed_method_watchdog_seconds':420,'proposed_slot_watchdog_seconds':480,
        'authorized':False,'execution_chain_accepted':False,'actual_executed':False,
        'research_calls':0,'model_builds':0,'original_payload_transformations':0,'LP_MILP_calls':0,'thermal_post_calls':0,
        'limits':['No real launcher is present or accepted; implementation and fresh hash/guard checks are necessary after confirmation.',
            'One successful future call cannot establish old conflict causality, universal repair or performance improvement.',
            'Initialization SAFE, Python numerical x0 admission, worker receipt and native returned-vector acceptance must stay separate.',
            'No old budget or original24 continuation is authorized.'],
        'scope':'Internal independent preparation review, not user authorization or external ChatGPT approval.'}
    audit.save(HERE/'final_review.json',review)
    summary=f'''# K168准备阶段独立终核

**准备协议通过，仍待用户确认1次×300秒预算；未启动研究。** {len(checks)}项终核与{evidence['tests_run']}项纯预检通过，所有科学入口守卫为0。冻结声明和原输入身份匹配。

建议预算为：最多1次方法、最多1次native、实际外层1轮；方法证据300秒，清理窗口40秒、返回监督420秒、整项480秒，post为0。全部额外时段只允许停止/只读保存，不形成新U。现run入口无条件拒绝，没有真实launcher；用户确认后仍需新管理入口的冻结与必要预检。

配方保留原whole域、fresh初始化、独立L0和连续热安全；不固定A部署，不借旧x0/SAFE/缓存。旧入口固定outer标签50与实际诊断上限1分别记录。具体判读见scope_and_budget_review.md及冻结protocol，0native/无候选/正常截止/数值冲突均不补跑。

250份已绑定源、旧432/当前30工件、原16次400文件及账本/终态保持；24槽无claim。原第16槽不替换，新技术诊断不回填期限组或形成同轮排名。一次兼容成功也不证明旧故障根因、普遍修复、收益或最优。
'''
    with (HERE/'summary.md').open('x',encoding='utf8') as stream:stream.write(summary)
    audit.save(HERE/'review_manifest.json',{'final_review_sha256':audit.sha(HERE/'final_review.json'),
        'summary_sha256':audit.sha(HERE/'summary.md'),'script_sha256':audit.sha(Path(__file__)),
        'declaration_sha256':review['declaration_sha256'],'checks_sha256':review['checks_sha256'],
        'authorized':False,'scientific_calls':0})
    print({'passed':True,'independent_checks':len(checks),'pure_precheck_tests':evidence['tests_run'],'authorized':False,'scientific_calls':0})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True)
    main(parser.parse_args().run)
