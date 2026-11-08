"""Read-only K122 CDF off/on pair analysis; no production module import.

Reuses unchanged K119 archive readers. MAT work compares already published
arrays only; no new decode, model, LP, solver, heat evaluation or U is made.
Run only after both independent calls have finished. PDF output may remain
ignored by Git; this entry performs no Git operation.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import summarize_cut_pair as core


EXPECTED = {'AB_offset_0ms':(99,9306),'AC_offset_0ms':(91,7350)}


def _energy_display(value):
    return '—' if value is None else f'{float(core._q(value)):.12f}'


def _seconds_display(value):
    return '—' if value is None else f'{float(value):.3f}'


def arrangement_identity(candidate):
    """Normalize saved decoded rows only; auxiliary native values are absent."""
    if not isinstance(candidate,dict) or not isinstance(candidate.get('scenes'),dict): return None
    try:
        scenes = {}
        for sid,rows in candidate['scenes'].items():
            scenes[sid] = sorted((row['stage_id'],row['unit'],row['opp'],str(core._q(row['start_ms'])))
                                 for row in rows)
        return core._hash(scenes)
    except (KeyError,TypeError,ValueError,ZeroDivisionError):
        return None


def compare_native_options(off,on):
    if not off or not on:
        return {'observed':False,'raw_options_equal':None,'settings_equal_except_MaxTime':None,'differences':{}}
    differences = {key:{'off':off.get(key),'on':on.get(key)}
        for key in sorted(set(off)|set(on)) if off.get(key) != on.get(key)}
    return {'observed':True,'raw_options_equal':not differences,
        'settings_equal_except_MaxTime':not (set(differences)-{'MaxTime'}),
        'both_CutMaxIterations_10':off.get('CutMaxIterations') == on.get('CutMaxIterations') == 10,
        'differences':differences}


def first_new_legal_time(changes,decode_records,limit):
    """Need an actual different decoded arrangement plus its saved LEGAL log."""
    times = []
    for change in changes:
        if change.get('different_from_initial_decoded_candidate') is not True: continue
        for record in decode_records.get(change['scene_id'],[]):
            stamp = record.get('completed_at_s')
            if (record.get('source') == change.get('source') and record.get('state') == 'LEGAL'
                    and record.get('within_budget') is True and core._timely(stamp,limit)):
                times.append(stamp)
    return min(times,default=None)


def compare_model_arrays(off,on,expected,option_count=None):
    """Inspect first-request arrays; do not derive or solve a new system."""
    import numpy as np
    def csr(value):
        value = value.tocsr(copy=True); value.sum_duplicates(); value.sort_indices()
        return value
    def same_sparse(left,right):
        left,right = csr(left),csr(right)
        return (left.shape == right.shape and np.array_equal(left.indptr,right.indptr)
            and np.array_equal(left.indices,right.indices) and np.array_equal(left.data,right.data))
    def same(left,right):
        if hasattr(left,'tocsr') and hasattr(right,'tocsr'): return same_sparse(left,right)
        return np.array_equal(np.asarray(left),np.asarray(right))
    a0,a1 = csr(off['A']),csr(on['A']); b0,b1 = np.asarray(off['b']).ravel(),np.asarray(on['b']).ravel()
    m = a0.shape[0]; has_prefix = a1.shape[0] >= m and a1.shape[1] == a0.shape[1]
    extra = a1[m:,:] if has_prefix else None
    extra_b = b1[m:] if has_prefix else None
    y = np.asarray(off['intcon'],dtype=int).ravel()-1
    result = {'observed':True,'off_A_shape':list(a0.shape),'on_A_shape':list(a1.shape),
        'off_A_nnz':int(a0.nnz),'on_A_nnz':int(a1.nnz),
        'unchanged_components':{key:same(off[key],on[key]) for key in core.MODEL_FIELDS if key not in ('A','b')},
        'old_A_prefix_equal':has_prefix and same_sparse(a0,a1[:m,:]),
        'old_b_prefix_equal':has_prefix and np.array_equal(b0,b1[:m]),
        'appended_rows':None if extra is None else int(extra.shape[0]),
        'appended_nnz':None if extra is None else int(extra.nnz),
        'appended_coefficients_only_plus_minus_one':None if extra is None else bool(np.isin(extra.data,[-1.,1.]).all()),
        'appended_rhs_zero':None if extra_b is None else bool((extra_b == 0).all()),
        'appended_columns_only_existing_integer':None if extra is None else bool(np.isin(extra.indices,y).all()),
        'appended_columns_only_existing_y':None if extra is None or not isinstance(option_count,int)
            else bool(((extra.indices >= 0) & (extra.indices < option_count)).all()),
        'saved_option_count':option_count,
        'option_column_scope':'saved options count; frozen exporter places all option y columns first',
        'expected_appended_rows':expected[0],'expected_appended_nnz':expected[1],
        'append_count_matches_static_audit':extra is not None and (extra.shape[0],extra.nnz) == expected,
        'scope':'first native exports only; structural equality/count check, not a new feasibility certificate'}
    return result


def _enrich(folder,enabled,record):
    call = core._call(folder,10,record)  # Both settings retain CutMaxIterations=10.
    call['cumulative_precedence'] = enabled
    call['label'] = 'CDF True' if enabled else 'CDF False'
    call['model_metadata'] = {}; call['first_new_legal_at_s'] = None
    if not call['result_present']: return call
    result = core._read(folder/'invocation/result.json'); decode = {}; changes = []; initial_references = []
    call['builder_options'] = result.get('builder_options')
    for sid,scene in result.get('scenes',{}).items():
        construction = scene.get('construction') or {}
        model_summary = scene.get('model_summary') or {}
        call['model_metadata'][sid] = {'model_summary':scene.get('model_summary'),
            'actual_CDF_formulation':(model_summary.get('formulation') or {}).get('cumulative_precedence',False)
                if model_summary else None,
            'construction_status':construction.get('status'),
            'construction_rows':construction.get('rows'),'construction_nnz':construction.get('nonzeros_in_rows'),
            'construction_components':construction.get('construction_components'),
            'construction_details':construction.get('construction_details'),
            'phase_wall_seconds':construction.get('phase_wall_seconds'),
            'CDF_construction_component':(construction.get('construction_components') or {}).get('cumulative_precedence')}
        decode[sid] = ((scene.get('solver_result') or {}).get('diagnostic') or {}).get('decode_records',[])
        initial_id = arrangement_identity(((scene.get('initialisation') or {}).get('witness') or {}).get('candidate'))
        initial_references.append(initial_id is not None)
        for saved in scene.get('model_view_evaluations',[]):
            if saved.get('source') == 'initial_constructor': continue
            candidate_id = arrangement_identity(saved.get('candidate')); physical = saved.get('evaluation') or {}
            changes.append({'scene_id':sid,'source':saved.get('source'),
                'candidate_arrangement_sha256':candidate_id,'initial_arrangement_sha256':initial_id,
                'different_from_initial_decoded_candidate':None if initial_id is None or candidate_id is None
                    else candidate_id != initial_id,
                'received_at_s':saved.get('received_at_s'),'state':physical.get('state'),
                'complete':physical.get('complete'),'rankable_energy':physical.get('rankable_energy'),
                'completed_at_elapsed_s':physical.get('completed_at_elapsed_s')})
    call['decoded_candidate_changes'] = changes
    call['arrangement_identity_scope'] = 'saved stage_id/unit/opp and exact Fraction(start_ms), sorted per scene; no native auxiliary values'
    changed = any(row['different_from_initial_decoded_candidate'] is True
                  and core._timely(row.get('received_at_s'),call['budget_s']) for row in changes)
    call['candidate_outcome'] = ('CERTIFIED_STRICT_IMPROVEMENT' if call['strict_improvement_certified'] is True else
        'DIFFERENT_DECODED_CANDIDATE_WITHOUT_CERTIFIED_STRICT_IMPROVEMENT' if changed else
        'NO_COMPLETE_INITIAL_CANDIDATE_REFERENCE' if not initial_references or not all(initial_references) else
        'NO_DIFFERENT_DECODED_CANDIDATE_OBSERVED')
    call['first_new_legal_at_s'] = first_new_legal_time(call['decoded_candidate_changes'],decode,call['budget_s'])
    call['first_new_legal_scope'] = 'different saved decoded arrangement plus same-source LEGAL/within-budget record; not callback numfeaspoints or a thermal SAFE claim'
    vectors = [v for request in call['requests'] for v in request.get('vectors_compared_to_published_x0',[])
               if v.get('length')]
    call['nonempty_native_vector_summary'] = {'observations':len(vectors),
        'all_exactly_x0':None if not vectors or any(v.get('exactly_x0') is None for v in vectors)
            else all(v['exactly_x0'] for v in vectors),
        'comparisons':vectors}
    call['feedback_rows'] = sum(entry.get('rows_added',0) for scene in result.get('scenes',{}).values()
        for entry in (scene.get('solver_result') or {}).get('feedback',[]))
    return call


def _first_requests(call):
    first = {}
    for request in call['requests']: first.setdefault(request['scene_id'],request)
    return first


def _matrix_checks(pair,calls):
    from scipy.io import loadmat
    off,on = map(_first_requests,calls); output = []
    for sid in sorted(set(off)|set(on)):
        a,b = off.get(sid),on.get(sid)
        row = {'scene_id':sid,'observed':False,'reason':'MISSING_FIRST_REQUEST_OR_LOCAL_MAT'}
        if a and b and a.get('request_number') and b.get('request_number'):
            p0 = pair/'call_off/invocation/matlab'/f"request_{a['request_number']:06d}.mat"
            p1 = pair/'call_on/invocation/matlab'/f"request_{b['request_number']:06d}.mat"
            if p0.is_file() and p1.is_file():
                row = {'scene_id':sid,**compare_model_arrays(
                    loadmat(p0,variable_names=list(core.MODEL_FIELDS)),
                    loadmat(p1,variable_names=list(core.MODEL_FIELDS)),EXPECTED[sid],
                    ((calls[0].get('model_metadata',{}).get(sid) or {}).get('model_summary') or {}).get('options'))}
                row['first_request_numbers'] = {'off':a['request_number'],'on':b['request_number']}
        row['native_options'] = compare_native_options((a or {}).get('native_options'),(b or {}).get('native_options'))
        output.append(row)
    return output


def _plot(out,calls):
    import matplotlib
    matplotlib.use('Agg',force=True)
    import matplotlib.pyplot as plt
    fig,axes = plt.subplots(1,2,figsize=(11,4.1),sharey=True,layout='constrained')
    for ax,call in zip(axes,calls):
        limit = call.get('budget_s',300)
        end = min(limit,max(0.,float((call.get('timing') or {}).get('method_elapsed_s',0))))
        if end < limit:
            ax.axvspan(end,limit,color='#888888',alpha=.12,label='Unused budget')
            ax.axvline(end,color='#777777',linestyle='-.',linewidth=.9)
        updates = [u for u in call['updates'] if u['committed_at_s'] <= end]
        if updates:
            xs = [u['committed_at_s'] for u in updates]; ys = [float(core._interval(u['energy_J'])[1]) for u in updates]
            ax.step(xs+[end],ys+[ys[-1]],where='post',color='#1764a0',label='Saved SAFE U(t)',linewidth=1.7)
            ax.scatter(xs,ys,s=20,color='#1764a0',zorder=4)
        else: ax.text(.5,.6,'No complete SAFE U',ha='center',transform=ax.transAxes)
        for key,color,style in [('L0','#555555',':'),('L_a','#2d854b','--')]:
            receipt = call['independent_bounds'].get(key)
            if receipt and receipt['formed_at_s'] <= end:
                ax.plot([receipt['formed_at_s'],end],[float(core._q(receipt['lower_bound_J']))]*2,
                        color=color,linestyle=style,label='Independent '+key,linewidth=1.5)
        if call.get('initial_energy_J') and call.get('initial_complete_at_s',limit) <= end:
            ax.plot([call['initial_complete_at_s'],end],[float(core._interval(call['initial_energy_J'])[1])]*2,
                    color='#bc6c19',linestyle=(0,(5,3)),label='Own complete init upper',linewidth=1.1)
        ax.set(title=call['label']+'; CutMaxIterations=10',xlabel='Elapsed method time (s)',xlim=(0,limit))
        ax.grid(alpha=.22)
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8,loc='best')
    axes[0].set_ylabel('Energy (J)')
    fig.suptitle('One fixed shared deployment; independent fresh 300 s budgets',fontsize=11)
    fig.savefig(out/'cumulative_bounds.png',dpi=220); fig.savefig(out/'cumulative_bounds.pdf'); plt.close(fig)


def summarize(pair_dir,out_dir):
    """Analyze terminal call_off/call_on only; write a new directory."""
    pair,out = Path(pair_dir).resolve(),Path(out_dir).resolve()
    if out.exists(): raise FileExistsError(out)
    if pair == out or pair.is_relative_to(out): raise ValueError('Output cannot contain pair input')
    declaration,run = core._read(pair/'declaration.json'),core._read(pair/'run_record.json')
    records = run.get('calls',[])
    if (run.get('state') in ('RUNNING','PROCESSING','STARTING') or len(records) != 2
            or any(row.get('state') in ('RUNNING','PROCESSING','STARTING') for row in records)):
        raise ValueError('Both calls must have terminal run records')
    calls = []
    for name,enabled in [('call_off',False),('call_on',True)]:
        record = next((row for row in records if row.get('relative_path') == name
                       or row.get('cumulative_precedence') is enabled),{})
        calls.append(_enrich(pair/name,enabled,record))
    matrices = _matrix_checks(pair,calls)
    posthoc = {'same_full_input_sha256':calls[0].get('full_input_sha256') == calls[1].get('full_input_sha256')
        if calls[0].get('full_input_sha256') else None,
        'same_config_sha256':calls[0].get('config_sha256') == calls[1].get('config_sha256') if calls[0].get('config_sha256') else None,
        'same_shared_deployment':calls[0].get('shared_deployment') == calls[1].get('shared_deployment')
            if calls[0].get('shared_deployment') is not None and calls[1].get('shared_deployment') is not None else None,
        'first_request_model_checks':matrices,
        'later_feedback_requests':{call['label']:[r for r in call['requests'] if r.get('round',1)>1] for call in calls}}
    report = {'analysis_scope':'fixed_shared_deployment_not_global16','declaration':declaration,'run_record':run,
        'calls':calls,'posthoc_pair_checks':posthoc,'expected_static_append_counts':EXPECTED,
        'postprocessor_identity':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__),Path(core.__file__))},
        'identity_scope':'posthoc read-only code identity; separate from method source freeze',
        'internal_gap_convention':'R2023b raw relativegap=100*(U-L)/(|U|+1); never substituted for independent (U-L0)/U',
        'limitations':['No K119 research result is read or used as control; only its unchanged generic reader code is reused.',
            'No complete evidence means unknown; native numfeaspoints is not a decoded/legal/SAFE certificate.',
            'No new decode, schedule, U, heat, LP, solver or post-cutoff recovery is performed.',
            'One call per setting does not establish overall performance or feedback advantage.']}
    rows = []
    for call in calls:
        timing = call.get('timing') or {}
        rows.append({'cumulative_precedence':call['cumulative_precedence'],'state':call['state'],'reason':call['reason'],
            'initial_energy_J':call.get('initial_energy_J'),'final_energy_J':call.get('final_energy_J'),
            'final_U_J':call.get('final_U_J'),'strict_improvement_certified':call.get('strict_improvement_certified'),
            'upper_bound_improved':call.get('upper_bound_improved'),'first_SAFE_at_s':call.get('first_SAFE_at_s'),
            'first_new_legal_at_s':call.get('first_new_legal_at_s'),'first_strict_improvement_at_s':call.get('first_strict_improvement_at_s'),
            'candidate_outcome':call.get('candidate_outcome'),'different_native_vector_in_budget':call.get('different_native_vector_in_budget'),
            'actual_CutMaxIterations':call.get('actual_CutMaxIterations'),'feedback_records':call.get('feedback_records'),
            'feedback_rows':call.get('feedback_rows'),'method_elapsed_s':timing.get('method_elapsed_s'),
            'cleanup_s':timing.get('cleanup_s'),'deadline_overshoot_s':timing.get('deadline_overshoot_s'),
            'model_construction_s':(timing.get('phases_exclusive_s') or {}).get('model_construction'),
            'CDF_construction':{sid:meta['CDF_construction_component'] for sid,meta in call['model_metadata'].items()},
            'native_errors':call.get('native_errors'),'receipt_errors':call.get('receipt_errors'),
            'wrapper_state':call['run_record'].get('state'),'wrapper_error':call['run_record'].get('error'),
            'source_unchanged':call['run_record'].get('source_unchanged'),
            'technical_issues':call['run_record'].get('technical_issues'),
            'cleanup_status':call['run_record'].get('cleanup_status'),
            'cleanup_error':call['run_record'].get('cleanup_error'),
            'cleanup_metadata_error':call['run_record'].get('cleanup_metadata_error')})
    out.mkdir(parents=True,exist_ok=False)
    with (out/'calls.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader()
        writer.writerows({key:json.dumps(value,ensure_ascii=False,separators=(',',':'))
            if isinstance(value,(dict,list)) else '' if value is None else value for key,value in row.items()} for row in rows)
    _plot(out,calls)
    model_summary = {'first_request_model_checks':matrices,'models':{
        call['label']:{'metadata':call['model_metadata'],
            'published_requests':[{'scene_id':r['scene_id'],'round':r.get('round'),
                'request_number':r.get('request_number'),'fingerprint':r.get('model_fingerprint')} for r in call['requests']]}
        for call in calls}}
    (out/'mat_model_summary.json').write_text(json.dumps(model_summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (out/'facts.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    strict = [call['label'] for call in calls if call.get('strict_improvement_certified') is True]
    lead = ('本次'+str(strict)+'最终能耗上端严格低于各自完整初始化下端。' if strict else
        '本次两版均未证实相对各自完整初始化的严格节能改善。')
    if any(call.get('initial_energy_J') is None or call.get('final_energy_J') is None for call in calls):
        lead = '完整初始/最终SAFE证据不足，相关能耗比较保留未知。'
    if any(call.get('native_errors') or call.get('error') or call['run_record'].get('error')
           or call['run_record'].get('technical_issues') or call['run_record'].get('cleanup_error')
           or call['run_record'].get('cleanup_metadata_error') for call in calls):
        lead += ' 调用存在技术故障；已保存SAFE与故障状态分别保留。'
    lines = [lead,'','固定共享部署H=a，CDF False/True均Cut10；K119不作为control。','',
        '| CDF | 初始U（J） | 最终U（J） | 严格改善 | 首SAFE/新legal/严格改善（s） | 方法/清理（s） | 状态 |',
        '|---|---|---|---|---|---|---|']
    for call in calls:
        timing = call.get('timing') or {}
        lines.append(f"| {call['cumulative_precedence']} | {_energy_display(call.get('initial_U_J'))} | {_energy_display(call.get('final_U_J'))} | {call.get('strict_improvement_certified')} | {_seconds_display(call.get('first_SAFE_at_s'))} / {_seconds_display(call.get('first_new_legal_at_s'))} / {_seconds_display(call.get('first_strict_improvement_at_s'))} | {_seconds_display(timing.get('method_elapsed_s'))} / {_seconds_display(timing.get('cleanup_s'))} | {call['state']} / {call['reason']} |")
    lines += ['', '表内能量和时间为舍入展示；严格改善使用facts.json保存的原始能量包络比较。', '', '首模型只读数组核对：','',
        '| 场景 | 旧A/b前缀相同 | 追加行/nnz | ±1且rhs0且仅旧y | 其他数组相同 | 其余设置相同（MaxTime单列） |',
        '|---|---|---|---|---|---|']
    for check in matrices:
        properties = [check.get(k) for k in (
            'appended_coefficients_only_plus_minus_one','appended_rhs_zero','appended_columns_only_existing_y')]
        only_cdf = None if not check['observed'] or None in properties else all(properties)
        arrays_equal = None if not check['observed'] else all(check['unchanged_components'].values())
        lines.append(f"| {check['scene_id']} | {check.get('old_A_prefix_equal')}/{check.get('old_b_prefix_equal')} | {check.get('appended_rows')}/{check.get('appended_nnz')} | {only_cdf} | {arrays_equal} | {check['native_options']['settings_equal_except_MaxTime']} |")
    for call in calls:
        lines += ['',f"{call['label']}：{call.get('candidate_outcome')}；非空原生向量对本次x0：{call.get('nonempty_native_vector_summary',{}).get('all_exactly_x0')}；反馈 {call.get('feedback_records')} 条/{call.get('feedback_rows')} 行。"]
        for error in call.get('native_errors',[]):
            lines += [f"原生错误：`{error['identifier']}`。",'```text',error.get('message') or '', '```']
    lines += ['', 'first_new_legal只由不同已解码安排与同source、预算内LEGAL完成日志核定；缺失写未知，不使用原生可行点数代替。',
        'U只引用已存预算内完整SAFE回执；曲线止于实际方法停止时刻。phase/节点/原生界/rawgap、每个非空向量对x0比较、派生MaxTime差异及CDF构模组件见facts.json。',
        '旧前缀相等/追加结构是事后数组核对；不重新认证可行域或求解。CDF行数/非零数不自动代表运行瓶颈或加速。单次配对不推断总体胜率，也不证明热反馈收益。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    result = summarize(args.run,args.out)
    print(json.dumps({'out':str(args.out.resolve()),'analysis_scope':result['analysis_scope']},ensure_ascii=False))
