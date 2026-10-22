"""Pure report extraction for the final, fixed-version arithmetic run."""
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import platform
import sys
import prepare_probes as audit

HERE=Path(__file__).resolve().parent

def main():
    source=HERE/'probe_cost_run02/results.json';data=audit.read(source)
    assert data['passed'] and data['source_sha256_after']=='9b4fc402a00c71d9f919c3829df0b43277df614fbd5fcfe2aec6d67de02c6e0a'
    refs={r['case']:r for r in audit.read(HERE/'reference_U.json')['cases']}
    rows=data['probes'];metrics=[];forced_examples=[]
    def is_new(r):return r['decision']['prune'] and not r['already_excluded_by_ordinary_deadline_necessity'] and not r['legacy_form_conditioned_algebra_prunes']
    def forced_extra(r):return r['decision']['prune'] and F(r['bound']['capacity_lower_bound_J'])<=F(refs[r['case']]['reference_U_exact_J'])
    for case in data['case_results']:
        selected=[r for r in rows if r['case']==case['case']]
        extra=[r for r in selected if forced_extra(r)]
        assert all(is_new(r) for r in extra)
        values={'case':case['case'],'all_probes':len(selected),
            'energy_prunes':sum(r['decision']['prune'] for r in selected),
            'ordinary_deadline_excluded':sum(r['already_excluded_by_ordinary_deadline_necessity'] for r in selected),
            'energy_prune_after_deadline':sum(r['decision']['prune'] and not r['already_excluded_by_ordinary_deadline_necessity'] for r in selected),
            'new_beyond_deadline_and_legacy_form':sum(is_new(r) for r in selected),
            'device_layer_compatible':sum(r['within_existing_linked_device_layer'] for r in selected),
            'device_layer_energy_prunes':sum(r['within_existing_linked_device_layer'] and r['decision']['prune'] for r in selected),
            'new_beyond_deadline_legacy_inside_device_layer':sum(r['within_existing_linked_device_layer'] and is_new(r) for r in selected),
            'forced_additional_beyond_capacity':len(extra),
            'forced_additional_inside_device_layer':sum(r['within_existing_linked_device_layer'] for r in extra),
            'cold_prepare_and_root_median_s':case['cold_total_statistics']['median_s'],
            'warm_98_bound_and_decision_median_s':case['warm_joint_statistics']['median_s'],
            'reference_archive_IO_hash_s':case['reference_archive_admission_IO_hash_s']}
        metrics.append(values)
        for r in extra:
            forced_examples.append({'probe_id':r['probe_id'],'case':r['case'],
                'within_existing_linked_device_layer':r['within_existing_linked_device_layer'],
                'partial':r['partial'],'legacy_conditioned_J':r['bound']['legacy_conditioned_lower_bound_J'],
                'capacity_J':r['bound']['capacity_lower_bound_J'],'forced_J':r['bound']['forced_residency_lower_bound_J'],
                'reference_U_J':refs[r['case']]['reference_U_exact_J'],
                'strict_margin_J':str(F(r['bound']['lower_bound_J'])-F(refs[r['case']]['reference_U_exact_J']))})
    counts={k:sum(m[k] for m in metrics) for k in metrics[0] if k not in ('case',
        'cold_prepare_and_root_median_s','warm_98_bound_and_decision_median_s','reference_archive_IO_hash_s')}
    assert counts['energy_prunes']==255 and counts['new_beyond_deadline_and_legacy_form']==187
    assert counts['forced_additional_beyond_capacity']==22 and counts['forced_additional_inside_device_layer']==11
    example=next(r for r in forced_examples if r['case']=='base__R1' and
        r['partial']=={'by_scene':{'AB_offset_0ms':{'AB_offset_0ms::B_r1::B.post':{'unit':'CPU2','opp':'H'}}}})
    ref_bind=[]
    for case,reference in refs.items():
        method=reference['reference_methods'][0]
        row=next(r for r in reference['all8_original_U'] if r['method']==method)
        result=audit.REPO/row['source_path'];camp=result.parents[3]
        claim=camp/'claims'/f'{case}__{method}_artifact_sha256.json'
        declared=audit.read(claim);bound={}
        for name in ('result.json','postcheck.json','input_instance.json','wrapper_raw_result.json'):
            path=result.parent/name;actual=audit.sha(path)
            assert actual==declared[name]
            bound[path.relative_to(audit.REPO).as_posix()]=actual
        ref_bind.append({'case':case,'method':method,'historical_artifact_manifest':claim.relative_to(audit.REPO).as_posix(),
            'historical_manifest_sha256':audit.sha(claim),'reference_files_sha256':bound,
            'binding_checked_after_benchmark_against_original_campaign_artifact_hashes':True,
            'no_reference_re_evaluation_or_API_timing_repetition':True})
    audit.save('reference_source_binding.json',{'protocol':'K170-reference-original-campaign-artifact-binding-v1',
        'cases':ref_bind,'post_or_scientific_calls':0})
    results={'protocol':'K170-final-probe-cost-analysis-v1','source_results_sha256':audit.sha(source),
        'module_sha256':data['source_sha256_after'],'counts':counts,'cases':metrics,
        'forced_extra_examples':forced_examples,'illustrative_compatible_example':example,
        'overlap_warning':'Conditions overlap and are not visited search nodes or a disjoint domain volume.',
        'legacy_warning':'Legacy-conditioned field is an algebraic old-form comparator extended to these conditions, not a historical search trace.',
        'cost_environment':{'python':sys.version,'platform':platform.platform(),'repetitions':3,
            'function_profile_enabled':False,'scientific_import_and_process_audit':True},
        'history':{'run01':{'passed':False,'reason':'source changed during run; retained, no timing/quality best selection'},'final_run':'run02'},
        'method_effect_not_measured':True,'new_scientific_calls':0}
    audit.save('analysis.json',results)
    text='''# K170固定部分赋值探针与成本

**新界具有条件区分能力，不只是提高root公共常数；尚未证明实际搜索节省或更低能耗。** 原490项探针和3次重复均未改变。最终run02绑定`9b4fc402…`，无构模、调度候选、热或求解调用；run01因源码漂移失败，原记录保留，不参与择优。

|范围|探针数|新界能量排除|扣普通期限与旧式条件界后的新增|
|---|---:|---:|---:|
'''
    for m in metrics:text+=f'|{m["case"]}|98|{m["energy_prunes"]}|{m["new_beyond_deadline_and_legacy_form"]}|\n'
    text+='''|合计|490|255|187|

其中40项已经被既有DAG最短完成期限必要条件排除，38项也被能量界排除；这部分不算新界独特贡献。与当前联动**设备层兼容**的195项中有66项能量排除，均超过普通期限/旧式条件界；其余189项排除在该设备层之外。兼容仅指unit一致，不证明探针完整条件域就是某个实际邻域，也不是实际访问记录。所有一层条件相互重叠，不能把255/490称作搜索空间缩小比例。

进一步，22项是capacity界尚不超过参考U、而forced驻留界严格超过U；其中11项设备层兼容、11项域外。这22项均不属于既有期限或旧式条件界可排除项，说明驻留分项在这些条件下有额外作用。R1的AB/B.post=CPU2/H例：旧式条件界约0.740287846341 J、capacity约0.859641815453 J、forced约0.860691815453 J，参考U约0.860663343334 J；严格裕量约28.472119 µJ。比较使用精确有理数，未舍入决定排除。

**参考U来自本批40份历史结果中各题8份安全结果的最低值，而非新方法在这些节点当时已有的U。** 有的参考来自其他方法，且可能到二遍末期才形成；因此以上不能写成旧N1及时剪去了这些分支。当前API对P0档案只读核同，原post来源又与原campaign artifact hash匹配，未重新评价。未来真实方法必须使用同次、预算内已成完整安全U，不能免费借本表答案。

## 固定三次成本

|输入|cold prepare＋root中位/ms|98项warm bound＋decision中位/ms|参照档案IO/hash/ms（单列）|
|---|---:|---:|---:|
'''
    for m in metrics:text+=f'|{m["case"]}|{1000*m["cold_prepare_and_root_median_s"]:.3f}|{1000*m["warm_98_bound_and_decision_median_s"]:.3f}|{1000*m["reference_archive_IO_hash_s"]:.3f}|\n'
    text+='''
原始三值、范围、每探针bound/decision及预热/上下文准备见run02/results.json；文件读取和参照验证均单列。最终计时无逐函数profile，仍保留科学导入/进程audit、模块清单和前后hash核对；完整函数入口守卫由独立纯预检承担。三次样本仅说明本次机器/版本的算术成本，不作稳定性或MILP加速结论。

额外三H链单列，forced比capacity高16.625 mJ；其A.main=CPU2在旧联动固定NPU0层外，不能拿它证明当前主法收益，也不计入490项。

## 下一项建议

**先只读回放每次真实构模开始时已有的自身U，再决定是否实现构模前模式筛选。** 同时核该模式是否仍在当时邻域和既有期限/固定锚过滤后的选项中，检查参考warm不会被删。若在实际时刻没有新增可排除模式，保留新界作为质量与停止工具，暂停生产筛选；不另造B&B树或追加扫描。

这条路线可复用现MILP构造和完整安全门。要证明方法收益，还缺同次U形成时刻、真实剩余模式、筛选开销以及后续同预算结果；本轮未完成生产接入或研究实验。K168仍pending，旧期限16/24不动。
'''
    with (HERE/'probe_summary.md').open('x',encoding='utf-8') as s:s.write(text)
    print({'counts':counts,'example_margin_microJ':float(F(example['strict_margin_J'])*1000000),
        'references_original_hash_bound':len(ref_bind),'scientific_calls':0})

if __name__=='__main__':main()
