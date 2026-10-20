"""K142 independent analysis/document cross-check; saved JSON/hash only."""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json

OUT=Path(__file__).resolve().parent
FROZEN=OUT.parent
ROOT=next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    own=read(OUT/'verification.json')
    facts=read(OUT/'analysis01/facts.json')
    boundary=read(OUT/'analysis01/technical_boundary.json')
    ledger=read(FROZEN/'ledger.json')
    declaration=read(FROZEN/'declaration.json')
    byid={r['id']:r for r in facts['calls']}
    linked=read(FROZEN/'linked_n1/result.json')
    summary=(OUT/'summary.md').read_text(encoding='utf-8')
    checks={}
    def check(name,value):checks[name]=bool(value)
    check('independent37_original_items_pass',own['passed'] and own['check_count']==37
        and all(own['checks'].values()))
    check('analysis_exact_four_display_rows_two_not_run',list(byid)==['whole_milp','linked_n1','heft','sa101']
        and all(byid[j]['state']=='NOT_RUN' and byid[j].get('final_U_J') is None
            and byid[j].get('timing') is None for j in ['heft','sa101']))
    check('two_energy_intervals_firstSAFE_and_clocks_agree',all(
        tuple(map(F,byid[j]['final_energy_J']))==tuple(map(F,r['energy_J']))
        and F(byid[j]['final_U_J'])==F(r['U_J'])
        and byid[j]['first_SAFE_s']==r['first_complete_SAFE_at_s']
        and byid[j]['timing']['method_elapsed_s']==r['method_elapsed_s']
        for j,r in own['calls'].items()))
    check('analysis301_original_artifacts_intact',len(facts['raw_hashes_before'])==301
        and facts['raw_archives_unchanged']
        and facts['raw_hashes_before']==facts['raw_hashes_after']
        and all(sha(FROZEN/p)==v for p,v in facts['raw_hashes_before'].items()))
    check('source159_still_unchanged',len(declaration['source_sha256'])==159
        and all(sha(ROOT/p)==v==sha(FROZEN/'source_snapshot'/p)
            for p,v in declaration['source_sha256'].items()))
    total=sum(r['method_elapsed_s'] for r in own['calls'].values())
    check('method_total600047_includes_stop_overshoot',facts['method_elapsed_total_s']==total
        and abs(total-600.047)<1e-8
        and all(0<=u['at_s']<300 for r in own['calls'].values()
            for u in r['first_to_final_U_updates']))
    check('cleanup_wrapper_process_clocks_separate',
        abs(sum(r['cleanup_s'] for r in own['calls'].values())-28.781)<1e-8
        and facts['launcher_timing']==read(FROZEN/'launcher_timing.json')
        and abs(facts['launcher_timing']['complete_driver_process_wall_s']-636.282)<1e-8
        and abs(facts['wrapper_timing']['wrapper_run_through_primary_archives_wall_s']-634.468)<1e-8)
    phase2=next(r for r in facts['linked_phase_attribution'] if r['phase_index']==2)
    phase1=next(r for r in facts['linked_phase_attribution'] if r['phase_index']==1)
    check('second_phase_zero_U_decrease_and77s_cost',phase2['committed_U_decrease_count']==0
        and F(phase2['U_decrease_J'])==0
        and phase2['strict_energy_improvement_vs_own_before_interval'] is False
        and abs(phase2['inclusive_phase_elapsed_s']-77.687)<1e-8
        and own['linked_phase_details']['phase2_complete_U_update_count']==0)
    check('first_phase_two_complete_updates219s',phase1['committed_U_decrease_count']==2
        and abs(phase1['inclusive_phase_elapsed_s']-219.953)<1e-8
        and [u['at_s'] for u in own['linked_phase_details']['complete_updates'] if u['phase_index']==1]
            ==[160.34400000004098,222.25])
    check('incomplete_comparison_distinct_from_SAFE_audit',facts['all_four_calls_executed_once'] is False
        and facts['all_four_comparison_valid'] is False and facts['all_saved_SAFE_consistent'] is True
        and own['four_method_comparison_completed'] is False
        and own['research_execution_status']=='BLOCKED')
    check('boundary_original_issue_and_saved_gates_match',
        boundary['ledger_technical_issues']==ledger['calls'][1]['technical_issues']
        and boundary['linked_request_2_fields']['failure_reasons']
            ==linked['augmented_transport']['requests'][1]['failure_reasons']
        and all(g['accepted'] and g['within_budget'] and g['completed_at_s']<300
            for g in boundary['linked_request_2_saved_numerical_gates']))
    check('boundary_does_not_recast_unresolved_as_invalid',boundary['safety_receipts_remain_valid']
        and not boundary['four_method_comparison_complete']
        and 'does not demonstrate a rejected numerical candidate' in boundary['interpretation'])
    check('analysis_zero_new_evidence_and_no_history_injection',facts['new_native_model_decode_heat_calls']==0
        and facts['historical_candidate_or_U_used'] is False
        and boundary['new_research_heat_decode_calls']==0)
    check('summary_preserves_actual_cost_and_stop_meaning',all(v in summary for v in
        ['未启动','不把32／15毫秒','28.781','636.282','第二遍含准备77.687秒',
        '没有新增完整U更新','不能据这一状态断言候选非法','未运行不等于方法失败']))
    report={'stage':'K142','scope':'separate independent cross-check; original37 audit count unchanged',
        'passed':all(checks.values()),'check_count':len(checks),'checks':checks,
        'analysis_raw_file_count':301,'new_research_native_model_thermal_calls':0}
    (OUT/'analysis_crosscheck.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    marker='## 分析与汇总交叉核对'
    path=OUT/'independent_review.md'
    text=path.read_text(encoding='utf-8')
    if marker not in text:
        text+='\n'+marker+'\n\n'+f'另行{len(checks)}项交叉核对'+('通过' if report['passed'] else '未全通过')+'，'
        text+='原37项终审计数不变。分析301份原工件hash、两份安全区间/首SAFE、600.047秒停止钟、28.781秒清理、636.282秒完整进程、第二遍77.687秒零新增改善及未运行两方法均一致。预算未闭合被如实记为未决，没有改写成数值残差错误；完整四法比较仍未完成。见analysis_crosscheck.json。\n'
        path.write_text(text,encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'count':len(checks),'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))


if __name__=='__main__':main()
