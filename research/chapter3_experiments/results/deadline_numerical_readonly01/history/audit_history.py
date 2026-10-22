"""K165 targeted stored-report/native-receipt history review; zero scientific calls.

Reads three existing 40-row CSVs and eight specifically selected whole-method
native receipts (R1/R2 in P0, P1, P2 and the deadline batch). No model, MAT
reconstruction, numerical solve, candidate decode or thermal evaluation.
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ROOT=REPO/'research/chapter3_experiments'
RESULTS=ROOT/'results'
HASHES={}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(path):
    path=Path(path);HASHES[path.relative_to(REPO).as_posix()]=sha(path)
    return path.read_text(encoding='utf-8-sig')


def read(path):return json.loads(text(path))


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def native(label, replicate, campaign, prefix):
    folder=RESULTS/campaign/'calls'/(prefix+'__'+replicate)/'whole_milp'
    raw=read(folder/'wrapper_raw_result.json')
    response=read(folder/'matlab/request_000001.response.json')
    python=read(folder/'matlab/request_000001.python.json')
    meta=read(folder/'matlab/request_000001.input.json')
    admission=read(folder/'matlab/request_000001.initial.json')
    session=read(folder/'matlab/session.json')
    options=response.get('options') or {}
    initial=response.get('initial_point') or {}
    callbacks=[{k:value.get(k) for k in ('state','request_wall_seconds','values')}
               for value in response.get('callbacks') or []]
    progress=raw.get('diagnostic',{}).get('solver_progress') or []
    summary=raw.get('model_summary') or {}
    nc=raw.get('numerical_consistency') or {}
    return {'condition':label,'replicate':replicate,'problem_id':raw.get('problem_id'),
        'source_folder':folder.relative_to(REPO).as_posix(),
        'raw_state':raw.get('state'),'raw_reason':raw.get('reason'),
        'root_s':raw.get('timing',{}).get('method_elapsed_s'),
        'root_budget_exhausted':raw.get('budget_exhausted'),
        'first_initial_SAFE_s':raw.get('first_initial_safe_s'),
        'initial_SAFE_U_J':raw.get('initial_safe_upper_bound_J'),
        'initialisation_state':raw.get('initialisation',{}).get('state'),
        'saved_SAFE_candidate_sha256':canonical(raw.get('safe_candidate')),
        'variables':summary.get('variables'),'rows':summary.get('rows'),
        'retained_options':summary.get('options'),
        'formulation':summary.get('formulation'),
        'matlab_startup_s':raw.get('timing',{}).get('phases_exclusive_s',{}).get('solver_startup'),
        'request_entry_remaining_s':meta.get('case_budget_at_entry_s'),
        'native_MaxTime_s':options.get('MaxTime'),
        'native_intlinprog_call_s':response.get('phase_seconds',{}).get('intlinprog_call'),
        'response_exitflag':response.get('exitflag'),
        'response_x_empty':response.get('x')==[],
        'response_fval':response.get('fval'),
        'response_final_numfeaspoints':response.get('output',{}).get('numfeaspoints'),
        'response_final_numnodes':response.get('output',{}).get('numnodes'),
        'response_final_message':response.get('output',{}).get('message'),
        'native_callbacks':callbacks,
        'saved_progress_events':progress,
        'reported_root_LP_objective':None,
        'root_LP_observability':'No explicit root-LP objective/status event in these saved init/done receipts; zero nodes does not identify the internal stopping stage.',
        'python_receipt_status':python.get('status'),
        'python_receipt_accepted_for_evaluation':python.get('accepted_for_evaluation'),
        'late_native_receipt_used_for_new_evidence':False,
        'python_x0_admission':admission,
        'native_initial_point':initial,
        'x0_provided_and_received':admission.get('provided') is True and initial.get('provided') is True,
        'x0_metadata_matches':initial.get('length')==admission.get('length')
            and initial.get('initial_objective')==admission.get('initial_objective')
            and initial.get('python_admission')==admission,
        'solver_x0_acceptance':initial.get('solver_acceptance'),
        'numerical_consistency_state':nc.get('state'),
        'numerical_consistency':nc,
        'bridge_sha256':session.get('source_sha256',{}).get('matlab_bridge.py'),
        'worker_sha256':session.get('source_sha256',{}).get('solve_model.m'),
        'key_options':{k:options.get(k) for k in ('ConstraintTolerance','IntegerTolerance',
            'LPPreprocess','IntegerPreprocess','CutMaxIterations','AbsoluteGapTolerance',
            'RelativeGapTolerance','ObjectiveCutOff','ObjectiveImprovementThreshold','RootLPAlgorithm')},
        'native_options':options}


def all_reported_terminals():
    result=[]
    for label,folder in [('P0','p0_resume01'),('P1','p1_execution01'),('P2','p2_execution01')]:
        rows=list(csv.DictReader(text(RESULTS/folder/'analysis01/results40.csv').splitlines()))
        result.append({'condition':label,'rows':len(rows),
            'execution_status_counts':dict(Counter(row.get('execution_status') or row.get('method_state') for row in rows)),
            'comparison_usable_n':sum(row.get('comparison_usable')=='True' for row in rows),
            'scope':'Existing method-terminal report only; not a complete search of late/unaccepted native responses.'})
        text(RESULTS/folder/'analysis01/summary.md')
    return result


def historical_conflicts():
    base=RESULTS/'formal_comparison02/response_R__R2__milp'
    old=read(base/'result.json')
    response=read(base/'matlab/request_000001.response.json')
    initial=read(base/'matlab/request_000001.initial.json')
    text(RESULTS/'infeasible_audit01/summary.md')
    text(RESULTS/'infeasible_audit01/native_trace.md')
    pair=RESULTS/'fixed_unit_pair02/all_opp_start'
    result=read(pair/'result.json')
    response131=read(pair/'matlab/request_000001.response.json')
    text(RESULTS/'fixed_unit_pair02/analysis01/summary.md')
    text(RESULTS/'numerical_conflict_audit01/summary.md')
    solver131=result['scenes']['AB_offset_0ms']['solver_result']
    return [
        {'stage':'K105/K106','problem':'historical response_R__R2, older physical/control formulation',
         'root_reason':old.get('reason'),'root_s':old.get('timing',{}).get('method_elapsed_s'),
         'native_exitflag':response.get('exitflag'),'x_empty':response.get('x')==[],
         'numfeaspoints_final':response.get('output',{}).get('numfeaspoints'),
         'numnodes_final':response.get('output',{}).get('numnodes'),
         'native_MaxTime_s':response.get('options',{}).get('MaxTime'),
         'native_intlinprog_call_s':response.get('phase_seconds',{}).get('intlinprog_call'),
         'python_x0_admission':initial,
         'callbacks':response.get('callbacks'),
         'source_folder':base.relative_to(REPO).as_posix(),
         'old_repair_scope':'K106 adopted LPPreprocess=none based on its fixed-logic saved pair; not a universal solver-correctness guarantee.'},
        {'stage':'K131/K132','problem':'base__R1 fixed-unit AB subproblem, older unaugmented local expression',
         'root_reason':result.get('reason'),
         'numerical_consistency':solver131.get('numerical_consistency'),
         'native_exitflag':response131.get('exitflag'),'x_empty':response131.get('x')==[],
         'native_options':response131.get('options'),
         'native_MaxTime_s':response131.get('options',{}).get('MaxTime'),
         'native_intlinprog_call_s':response131.get('phase_seconds',{}).get('intlinprog_call'),
         'source_folder':pair.relative_to(REPO).as_posix(),
         'later_adaptation_scope':'K132 examined the stored arithmetic and proposed the local augmented expression; its scope does not certify all whole-MILP payloads.'}]


def write_csv(path,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v
                             for k,v in row.items()})


def main():
    if (HERE/'facts.json').exists():raise FileExistsError('Do not replace an existing history audit')
    terminals=all_reported_terminals()
    locations=[('Deadline','R1','deadline_execution01','beta_1.0'),
        ('Deadline','R2','deadline_resume01','beta_1.0'),
        ('P0','R1','p0_execution01','base'),('P0','R2','p0_resume01','base'),
        ('P1','R1','p1_execution01','response_R'),('P1','R2','p1_execution01','response_R'),
        ('P2','R1','p2_execution01','initial_78'),('P2','R2','p2_execution01','initial_78')]
    rows=[native(*location) for location in locations]
    earlier=historical_conflicts()
    checkpoints={
        'three_existing_40_terminal_reports':len(terminals)==3 and all(v['rows']==40 for v in terminals),
        'all_existing_reported_terminal_rows_comparison_usable':all(v['comparison_usable_n']==40 for v in terminals),
        'eight_targeted_receipts_only':len(rows)==8,
        'same_bridge_worker_hashes_in_eight_sessions':len({r['bridge_sha256'] for r in rows})==1 and len({r['worker_sha256'] for r in rows})==1,
        'all_eight_explicit_x0_metadata_matches':all(r['x0_provided_and_received'] and r['x0_metadata_matches'] for r in rows),
        'all_eight_x0_numerically_admitted_not_solver_certified':all(r['python_x0_admission']['accepted_numerically'] is True and r['solver_x0_acceptance']=='not_independently_observed' for r in rows),
        'all_eight_done_count_one_final_zero':all(r['native_callbacks'][-1]['state']=='done' and r['native_callbacks'][-1]['values']['numfeaspoints']==1 and r['response_final_numfeaspoints']==0 for r in rows),
        'all_eight_no_branch_node_or_root_LP_objective_recorded':all(r['response_final_numnodes']==0 and all(v['values'].get('fval')==[] and v['values'].get('lowerbound')==[] for v in r['native_callbacks']) for r in rows),
        'all_eight_LP_and_integer_preprocess_none':all(r['key_options']['LPPreprocess']=='none' and r['key_options']['IntegerPreprocess']=='none' for r in rows),
        'only_current_R2_native_negative2_in_targeted_eight':[(r['condition'],r['replicate']) for r in rows if r['response_exitflag']==-2]==[('Deadline','R2')],
        'older_same_named_K131_conflict_exists':earlier[1]['numerical_consistency']['state']=='NUMERICAL_ADMISSION_STATUS_CONFLICT',
        'P1R2_native_MaxTime_exceeds_current_R2':next(r for r in rows if r['condition']=='P1' and r['replicate']=='R2')['native_MaxTime_s']>rows[1]['native_MaxTime_s'],
    }
    assert all(checkpoints.values()),checkpoints
    facts={'protocol':'K165-targeted-history-native-receipts-readonly-v1',
        'conclusion':'Recurrence of an already documented numerical-admission/solver-status conflict family. No observed new x0-metadata loss or bridge/worker source change in this targeted comparison; exact current root cause remains unresolved.',
        'reported_P0_P1_P2_terminals':terminals,'targeted_receipts':rows,'prior_conflicts':earlier,
        'checks':checkpoints,'checks_run':len(checkpoints),'passed':True,
        'source_sha256':HASHES,'script_sha256':sha(Path(__file__)),
        'new_solver_calls':0,'new_models':0,'new_thermal_evaluations':0,'new_post_calls':0,
        'old_files_modified':False,'literature_expansion':False,
        'scope':'Targeted existing reports and native JSON receipts only; no MAT loading/rebuild, no full-file blind scan, no new causal claim.'}
    with (HERE/'facts.json').open('x',encoding='utf-8') as stream:json.dump(facts,stream,ensure_ascii=False,indent=2);stream.write('\n')
    flat=[{k:v for k,v in row.items() if k not in ('native_callbacks','saved_progress_events',
        'native_options','native_initial_point','numerical_consistency','python_x0_admission','formulation')}
        for row in rows]
    write_csv(HERE/'native_R1_R2_comparison.csv',flat)
    lines=['# K165：R1/R2与既有数值冲突的只读历史对照','',
        '**本次更接近旧数值接纳／solver-reported状态冲突的复发，尚未定位为新的传参接口差错。** K105/K106的旧整体MILP和K131固定设备AB子问题均已有同族记录；K131已直接保存同名`NUMERICAL_ADMISSION_STATUS_CONFLICT`。原模型不同，不能把以前的局部修正自动套用于本次。','',
        '|条件|重复|变量数|MATLAB启动/s|native MaxTime/s|intlinprog调用/s|exitflag|根时钟/s|Python回执|',
        '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for row in rows:
        lines.append(f"|{row['condition']}|{row['replicate']}|{row['variables']}|{row['matlab_startup_s']:.3f}|{row['native_MaxTime_s']:.3f}|{row['native_intlinprog_call_s']:.3f}|{row['response_exitflag']}|{row['root_s']:.3f}|{row['python_receipt_status']}|")
    lines+=['',
        '1. **传参链没有显示新的元数据丢失。** 八份定向回执都明确提供并由worker收到x0，长度、初始目标及Python接纳元数据一致；两份当前会话及六份P0/P1/P2会话的桥接与worker源码hash相同。全部使用LPPreprocess=none、IntegerPreprocess=none、ConstraintTolerance=1e−9、IntegerTolerance=1e−6及CutMaxIterations=10。此核对不等同于逐元素复核MAT数组，后者由本阶段其他只读审查负责。','',
        '2. **done计数1不是x0接纳证明。** 八份回执全部表现为init可行点计数0、done计数1、最终计数0、x/fval为空、节点数0；其中七份native退出0，仅本次R2为−2。该计数差异不是本次独有，也不能据此认定solver真正保留了一个可返回候选。','',
        '3. **根LP状态仍不可观测。** 已保存记录只有init/done等事件，未出现可读取的根LP目标或lowerbound。零节点只说明没有记录到分支树节点，不能据此定位在根LP、割或其他内部阶段，也不能称根LP独立已证无解。','',
        '4. **启动与剩余时间是关联，不是原因。** 本次R2启动10.875 s、native MaxTime270.103 s，比R1的57.047 s和223.254 s留下更长原生片；但P1 R2已有更长的275.603 s，P2 R2也有268.913 s，均为时间退出0。本组不同响应、初温、期限和模型维数，不构成同矩阵单因素配对，不能归因于“运行久了”“期限更紧”或某个参数阈值。','',
        '5. **P0/P1/P2已完成档案不否定旧冲突。** 三份40行方法终态报告均是40份可比较SAFE，未登记本次数值冲突；定向读取的六份whole原生回执均为exit0，Python按原预算拒收后续输出。这个范围未穷查所有未接纳晚回执，不能泛化为过去所有内部步骤从未冲突。','',
        '6. **历史修正的边界。** K106旧整体模型曾在x0数值接纳后exit−2；其固定逻辑对子问题支持采用LPPreprocess=none。K131在LP none下又出现同名冲突，后续局部增广适配主要处理局部物理条件行的数值表示。本次whole仍需独立核对当前payload，不能认定旧工程兼容设置已覆盖全部数值问题，更不能把LP none或局部增广写成通用正确性保证。','',
        '结论：已知异常家族复发、当前确切原因未决；未发现本次独有的初始点元数据传输损失。优先完成当前payload／接纳／原生返回一致性核对，再决定是否存在范围明确的工程修正。本核查不建议调容差、追加时间或补跑，也不把安全初始化U升级为数值求解成功。','',
        '来源：当前期限组及P0/P1/P2的八份`wrapper_raw_result.json`与`matlab/request_000001.*.json`；K106的`infeasible_audit01/summary.md`、`native_trace.md`及原response；K131的`fixed_unit_pair02/all_opp_start/result.json`、原response及分析报告；K132的`numerical_conflict_audit01/summary.md`。准确路径、JSON字段和hash见facts.json。','',
        f'只读核对{len(checkpoints)}项通过；新模型、求解、热评价、post均0次。']
    with (HERE/'summary.md').open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')
    manifest={'script_sha256':sha(Path(__file__)),'facts_sha256':sha(HERE/'facts.json'),
        'summary_sha256':sha(HERE/'summary.md'),'csv_sha256':sha(HERE/'native_R1_R2_comparison.csv'),
        'sources_unchanged_after_read':all(sha(REPO/name)==digest for name,digest in HASHES.items()),
        'read_file_count':len(HASHES),'new_solver_thermal_post_or_model_calls':0,'old_files_modified':False}
    assert manifest['sources_unchanged_after_read']
    with (HERE/'manifest.json').open('x',encoding='utf-8') as stream:json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({'passed':True,'checks':len(checkpoints),'targeted_receipts':len(rows),
           'existing_terminal_report_rows':120,'new_scientific_calls':0,'output':str(HERE)})


if __name__=='__main__':main()
