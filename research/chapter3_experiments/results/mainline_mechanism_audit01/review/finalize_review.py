"""K169 final record review from stored evidence; no physical/scientific code."""
from fractions import Fraction as F
import json
from pathlib import Path
import integrity as audit

HERE=Path(__file__).resolve().parent
OUT=HERE.parent

def main():
    before=audit.read(HERE/'before_manifest.json');after=audit.read(HERE/'after_manifest.json')
    facts=audit.read(HERE/'facts.json');c12=audit.read(OUT/'c12/ledger_review.json');c17=audit.read(OUT/'c17/facts.json')
    summary=(OUT/'summary.md').read_text('utf-8')
    comparisons=[]
    for case in c17['cases']:
        L=F(case['shared_consistent_proposed_LB_J']['exact'])
        U=min(F(v['stored_U_J']['exact']) for v in case['stored_upper_bounds'])
        assert L<=U
        comparisons.append({'case':case['case'],'new_bound_exact':str(L),'best_old_U_exact':str(U),
            'posthoc_remaining_fraction_exact':str((U-L)/U),'old_bounds_not_modified':True})
    checks={
        'originals_and_pending_state_preserved':after['passed'] and all(after['checks'].values()),
        'current_source253_bound':before['source_count']==253,
        'old16_files400_and24_unstarted':len(before['original16_call_files_sha256'])==400 and not after['unexpected_old24_claims'],
        'pilot_reports_immutable_commit':all(v['commit']=='a8ecd41e41010f13b34962f057323bcd3624b9a2' for v in facts['pilot_reports'].values()),
        'pilot_old_worktree_not_replaced':facts['pilot_worktree_not_updated'] is True,
        'C12_no_false_SAFE':all(not v['continuous_80degC_safety_proven'] for v in c12['differences'].values()),
        'C12_reference_difference_sign':F(c12['differences']['uncovered']['D_reference_J'])==F(63,1000) and F(c12['differences']['covered']['D_reference_J'])==0,
        'C12_only_one_sided_full_order':F(c12['differences']['uncovered']['scene_full_energy_difference_interval_J'][0])>0 and F(c12['differences']['covered']['scene_full_energy_difference_interval_J'][0])<0<F(c12['differences']['covered']['scene_full_energy_difference_interval_J'][1]),
        'C17_all40_stored_U_not_undercut':len(comparisons)==5 and sum(len(x['stored_upper_bounds']) for x in c17['cases'])==40 and all(F(x['shared_consistent_proposed_LB_J']['exact'])<=F(u['stored_U_J']['exact']) for x in c17['cases'] for u in x['stored_upper_bounds']),
        'C17_initial_replacement_gain_exact':all(F(x['guaranteed_init_only_increment_over_old_J']['exact'])==F(352,3125) for x in c17['cases']),
        'C17_root_OPP_shared_extra_zero':all(F(x['shared_deployment_additional_gain_J']['exact'])==F(x['OPP_workload_additional_gain_J']['exact'])==0 for x in c17['cases']),
        'C17_no_science_modules_or_calls':not c17['guard']['scientific_modules_loaded'] and all(v==0 for k,v in c17['guard'].items() if k!='scientific_modules_loaded'),
        'C12_no_model_solver_thermal_evaluation':all(c12['operations'][k]==0 for k in ['input_builds','models_built','solver_calls','heat_integrations','formal_candidate_evaluations']),
        'P0_fixed_shared_A_before_seed':all(x['shared_deployment']=={'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'} and not x['global_deployment_search_performed'] for x in facts['P0_targeted_archives'].values()),
        'summary_bounds_combination_warning':'不能再全额相加' in summary and '不能把新旧完整温度项相加' in summary,
        'summary_posthoc_no_execution_claim':'后验' in summary and 'K168仍为待确认' in summary}
    assert all(checks.values()),checks
    bound_files={}
    for p in [OUT/'summary.md',OUT/'c12/check_ledger.py',OUT/'c12/ledger_review.json',OUT/'c12/summary.md',
        OUT/'c17/algebra_from_saved_inputs.py',OUT/'c17/facts.json',OUT/'c17/summary.md',OUT/'c17/source_locator.json',
        HERE/'facts.json',HERE/'inheritance_and_search_scope.md',HERE/'c17_mathematical_review.md',
        HERE/'before_manifest.json',HERE/'after_manifest.json']:
        bound_files[str(p.relative_to(OUT)).replace('\\','/')]=audit.sha(p)
    review={'protocol':'K169-independent-mathematical-and-scope-final-review-v1','passed':True,
        'decision':'ACCEPT_READONLY_MECHANISM_AND_POSTHOC_BOUND_AUDIT_NO_EXECUTION',
        'checks':checks,'checks_run':len(checks),'reviewed_evidence_sha256':bound_files,
        'mathematical_findings':[
            'C17 admissibility uses the same minimum positive system and its background/zero-initial forced-input decomposition; the two components may then add.',
            'Odd-Taylor background and nonnegative own-node deadline response have the correct lower-bound direction; initial-only replaces, not augments, the prior temperature term.',
            'min_unit sum_weight min_opp respects a common unit while relaxing per-scene OPP; nonnegative weights are required.',
            'Per-Stage domain baseline increment divided by domain capacity is a valid workload relaxation; full chain/residency bounds on the same increment must replace/max rather than add.',
            'C12 reference difference is 63u mJ, not a strict flip; only one full-energy direction has a signed analytic certificate, and 80degC safety remains unproved.',
            'Shared A unit is declared before fresh-seed generation; scene-local A OPP/start opening does not open A device choice.'],
        'posthoc_comparisons':comparisons,
        'unverified':['Production bound integration and partial-assignment API/rounding checks.',
            'Actual solver pruning, search speed or new energy improvement.',
            'Strict safe CPU/GPU order reversal under the mainline model.',
            'Universal numerical/native compatibility and original R2 conflict cause.'],
        'new_model_builds':0,'new_formal_candidate_evaluations':0,'new_thermal_integrations':0,
        'new_solver_calls':0,'new_post_calls':0,'original_consumed':16,'original_unstarted':24,
        'K168_status':'PENDING_USER_CONFIRMATION','further_execution_authorization':False,
        'reviewer_scope':'Internal child-agent independent review; not external ChatGPT approval.'}
    audit.save(HERE/'final_review.json',review)
    text='''# K169独立终审

**总稿通过，只限只读机制与事后数学下界审查；没有新实验或算法收益结论。**

- C17可相加的关键是同一最低正系统分解为“初温＋基准、无活动”的背景与“零初温、仅Stage活动”的响应。标量背景与自身节点响应下界方向正确，未重复初温或活动。共享unit的加权模式最小值是合法放松。
- CPU基准分摊与前驱/驻留界估计同一增量，只能替换、取最大或扣除已计部分；总稿已明确禁止全额叠加。五题根部驻留/共享额外增量确为0。
- C12的63u mJ及两场景31.5/0 mJ参考差正确；覆盖端并列不能写成严格翻转。单侧解析能量排序不等于四张安排已通过80°C连续安全。
- C18域分层准确：共享A部署在fresh seed前已固定；第二遍A.main只开放NPU0内OPP/起点。原完整MILP、HEFT和SA具备设备选择，不把局部限制归给完整模型。

16项终核通过，40份存档U均不小于新事后界。事后质量限可报告，但不能追记成旧预算内bound或性能收益；原L0/U不改。源码253、原432/30工件、原16次400文件与账本、K168 pending均保持，24槽仍无claim；pilot工作区未更新。完整性见after_manifest.json。

新增构模、正式候选评价、热积分、求解及post均0。新界接入、条件分支剪枝/成本及算法改进尚未完成；本审查不授权K168或恢复期限实验。
'''
    with (HERE/'final_review.md').open('x',encoding='utf-8') as s:s.write(text)
    audit.save(HERE/'final_manifest.json',{'review_sha256':audit.sha(HERE/'final_review.json'),
        'review_md_sha256':audit.sha(HERE/'final_review.md'),'summary_sha256':audit.sha(OUT/'summary.md'),
        'script_sha256':audit.sha(Path(__file__)),'new_scientific_calls':0})
    print({'passed':True,'checks':len(checks),'U_comparisons':40,'new_scientific_calls':0})

if __name__=='__main__':main()
