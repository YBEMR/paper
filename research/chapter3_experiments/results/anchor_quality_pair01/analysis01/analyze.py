"""K151 terminal saved-evidence analysis. No optimizer or physical reevaluation.

Run only after the pair is terminal. Imports only archived JSON/Fraction audit
helpers; does not import current experiment modules. Refuses completed outputs.
"""
from collections import Counter, defaultdict
from datetime import datetime
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
REPO = next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
HELPER = REPO/'research/chapter3_experiments/results/linked_five_open_pair01/analysis01/analyze.py'
spec = importlib.util.spec_from_file_location('K151_saved_K148_audit', HELPER)
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)
k.ROOT, k.OUT = ROOT, OUT
k.EXPECTED = ('old_linked4', 'anchor_linked4')
EXPECTED = k.EXPECTED
h, read, save, sha, interval, digest = k.h, k.read, k.save, k.sha, k.interval, k.digest


def phase_report(result, jid, updates, clocks):
    rows = k.k.phase_report(result, 'linked_n1', updates, clocks)
    for row in rows:
        row.update(job=jid, phase_name='N1_local_main_post' if row['phase_index']==1 else
            'linked_4_open_2_closed_anchor_filter_on' if jid==EXPECTED[1] else
            'linked_4_open_2_closed_anchor_filter_off')
    return rows


k.phase_report = phase_report


def keyed(rows):
    return {r['stage_id']:(r['unit'],r['opp'],F(r['start_ms'])) for r in rows}


def native_details(result, jid, instance, native_rows):
    rows, candidates = [], []
    folder = ROOT/jid
    for nr in native_rows:
        number = nr['request_number']
        response_path = folder/'matlab'/f'request_{number:06d}.response.json'
        if not response_path.is_file():
            rows.append(dict(nr, stored_response_present=False))
            continue
        response = read(response_path)
        init = next((c for c in response.get('callbacks',[]) if c.get('state')=='init'),{})
        roots = [c for c in response.get('callbacks',[]) if c.get('values',{}).get('phase')=='rootlp']
        root = roots[0] if roots else {}
        row = dict(nr, stored_response_present=True, response_sha256=sha(response_path),
            rootlp_native_cumulative_s=root.get('values',{}).get('time'),
            init_to_rootlp_request_wall_s=(root['request_wall_seconds']-init['request_wall_seconds'])
                if root and init else None,
            final_output=response.get('output'),
            phase_seconds=response.get('phase_seconds'),
            callback_timeline=[{key:c.get(key) for key in ('event_number','state','request_wall_seconds')}
                | {'native':c.get('values'),'nonempty_vector':bool(c.get('x'))}
                for c in response.get('callbacks',[])],
            rootlp_timing_scope='cumulative native callback, not exclusive LP execution time')
        rows.append(row)
    for phase in result.get('phases',[]):
        index = phase['phase_index']
        condition = phase.get('condition') or result.get('condition') or {}
        for sid, scene in phase.get('scenes',{}).items():
            warm_options = condition.get('warm_options_by_scene',condition.get('seed_options_by_scene',{})).get(sid,{})
            warm = {s:(v['unit'],v['opp'],F(v['start_ms'])) for s,v in warm_options.items()}
            evaluations = (scene.get('solver_result') or {}).get('diagnostic',{}).get('evaluations',[])
            for order, ev in enumerate(evaluations,1):
                selected = ev.get('candidate',{}).get('scenes',{}).get(sid,[])
                candidates.append({'job':jid,'phase_index':index,'scene':sid,'order':order,
                    **{key:ev.get(key) for key in ('source','accepted_safe','started_at_s','completed_at_s',
                        'evaluation_returned_at_s','within_budget','reason')},
                    'same_as_own_warm':bool(selected and warm) and keyed(selected)==warm,
                    'candidate_sha256':digest(ev.get('candidate')),
                    'saved_fields':sorted(ev),
                    'stored_evaluation':{key:val for key,val in ev.items() if key not in ('candidate','receipt','result','evaluation')},
                    'scope':'stored callback/final candidate receipts; not a new decode or thermal evaluation'})
    return rows,candidates


def model_details(result,jid):
    rows=[]
    for phase in result.get('phases',[]):
        index=phase['phase_index']
        for sid,scene in phase.get('scenes',{}).items():
            model=scene.get('model_summary') or {}
            pre=model.get('preprocessing') or {}
            filt=pre.get('closed_anchor_preelimination') or {}
            scene_index=next(i for i,s in enumerate(read(ROOT/'input_instance.json')['scenarios']) if s['id']==sid)
            base=ROOT/jid
            if index==2:
                base=base/'pass_02'
            matrixfiles=sorted((base/f'scene_{scene_index}'/'augmented_requests').glob('request_*/matrix_identities.json'))
            for path in matrixfiles:
                matrix=read(path)
                labels=read(path.parent/'labels.json')
                tags=Counter(labels.get('row_tags',[]))
                rows.append({'job':jid,'phase_index':index,'scene':sid,
                    'matrix_path':path.relative_to(ROOT).as_posix(),'matrix_sha256':sha(path),
                    'options':model.get('options'),'events':model.get('events_per_scene',{}).get(sid),
                    'constructed_variables':matrix['original']['c']['length'],
                    'native_variables':matrix['augmented']['c']['length'],
                    'native_inequalities':matrix['augmented']['A']['shape'][0],
                    'native_equalities':matrix['augmented']['Aeq']['shape'][0],
                    'native_integer_variables':matrix['augmented']['intcon']['length'],
                    'joint_groups':sum(n.startswith('w:') for n in labels['names']),
                    'thermal_energy_conditional_equation_groups':tags['thermal_propagation/upper']+tags['complete_energy/upper'],
                    'anchor_filter_enabled':bool(filt),'filter_before':filt.get('before'),
                    'filter_after':filt.get('after'),'filter_removed':filt.get('removed'),
                    'filter_complete':filt.get('complete'),'filter_passes':filt.get('passes'),
                    'filter_condition_sha256':filt.get('condition_sha256'),
                    'filter_warm_candidate_sha256':filt.get('warm_candidate_sha256'),
                    'filter_source_sha256':filt.get('filter_source_sha256'),
                    'filter_rule_counts':dict(Counter(rule for r in filt.get('removals',[])
                        for reason in r['reasons'] for rule in reason['rules'])),
                    'row_tag_counts':dict(tags)})
    return rows


def phase1_anchor_comparison(results):
    rows=[]
    left,right=results
    pleft=next((p for p in left.get('phases',[]) if p['phase_index']==2),{})
    pright=next((p for p in right.get('phases',[]) if p['phase_index']==2),{})
    a,b=pleft.get('condition',{}),pright.get('condition',{})
    for sid in sorted(set(a.get('warm_options_by_scene',{}))|set(b.get('warm_options_by_scene',{}))):
        x=a.get('warm_options_by_scene',{}).get(sid,{})
        y=b.get('warm_options_by_scene',{}).get(sid,{})
        for stage in sorted(set(x)|set(y)):
            xx,yy=x.get(stage,{}),y.get(stage,{})
            rows.append({'scene':sid,'stage':stage,'old':xx,'new':yy,
                'same_choices':bool(xx and yy) and xx['unit']==yy['unit'] and xx['opp']==yy['opp'] and
                    F(xx['start_ms'])==F(yy['start_ms']),
                'closed_in_phase2':stage not in a.get('opened_by_scene',{}).get(sid,[])})
    return {'same_phase1_warm_candidate':bool(a.get('warm_candidate_sha256')) and
                a.get('warm_candidate_sha256')==b.get('warm_candidate_sha256'),
        'old_warm_candidate_sha256':a.get('warm_candidate_sha256'),
        'new_warm_candidate_sha256':b.get('warm_candidate_sha256'),
        'same_closed_anchors':bool(rows) and all(r['same_choices'] for r in rows if r['closed_in_phase2']),
        'rows':rows}


def candidate_summary(rows):
    groups=defaultdict(list)
    for row in rows:
        groups[row['job'],row['phase_index'],row['scene']].append(row)
    return [{'job':job,'phase_index':phase,'scene':scene,'evaluated_count':len(values),
        'distinct_evaluated_candidates':len({r['candidate_sha256'] for r in values}),
        'different_from_own_warm_count':sum(not r['same_as_own_warm'] for r in values),
        'accepted_safe_count':sum(r['accepted_safe'] is True for r in values),
        'first_evaluation_returned_at_s':min((r['evaluation_returned_at_s'] for r in values
            if r.get('evaluation_returned_at_s') is not None),default=None),
        'first_new_evaluation_returned_at_s':min((r['evaluation_returned_at_s'] for r in values
            if not r['same_as_own_warm'] and r.get('evaluation_returned_at_s') is not None),default=None),
        'scope':'local scene evaluation completion; does not itself establish a complete-system SAFE update'}
        for (job,phase,scene),values in sorted(groups.items())]


def recover_rows(ledger):
    """Append-only review/one unstarted invocation; never relabel raw ledger."""
    claimpath=ROOT/'claims/remaining_recovery.json'
    if not claimpath.exists():
        return ledger['calls'],ledger['consumed'],ledger['reserved_method_budget_s'],None
    k.require((ROOT/'recovery_result.json').is_file() and (ROOT/'recovery_launcher_result.json').is_file(),
        'Continuation is still running or not fully archived')
    original=read(ROOT/'recovery_before/original_sha256.json')
    globalpath=REPO/'research/chapter3_experiments/results/anchor_quality_claim01.json'
    k.require(all(sha(globalpath if name=='GLOBAL_CLAIM' else ROOT/name)==expected
        for name,expected in original.items()),'Original frozen blocked records changed')
    claim=read(claimpath);returned=read(ROOT/'recovery_result.json')
    originalrows=ledger['calls']
    k.require(ledger['state']=='BLOCKED' and ledger['consumed']==1 and len(originalrows)==1,
        'Continuation must preserve original one-consumed blocked ledger')
    k.require(claim.get('original_consumed_calls')==1 and claim.get('cumulative_consumed_calls_after_claim')==2
        and claim.get('cumulative_reserved_method_s')==600 and claim.get('old_rerun') is False
        and claim.get('no_retry') is True,'Unexpected continuation consumption')
    k.require(returned.get('cumulative_consumed_calls')==2 and returned.get('cumulative_reserved_method_budget_s')==600
        and returned.get('old_rerun') is False and returned.get('no_retry') is True
        and returned.get('original_ledger_unchanged') is True,'Unexpected terminal continuation budget/state')
    k.require(returned['claim_sha256']==sha(claimpath)
        and returned['new_result_sha256']==sha(ROOT/'claims/anchor_linked4_result.json')
        and returned['new_artifact_manifest_sha256']==sha(ROOT/'claims/anchor_linked4_artifact_sha256.json')
        and returned['original_manifest_sha256']==sha(ROOT/'recovery_before/original_sha256.json'),
        'Continuation terminal bindings disagree')
    corrected=read(ROOT/'corrected_old_record.json')
    review=corrected.get('cutoff_audit') or {}
    k.require(review.get('applied') is True and review.get('new_safe_evaluation') is False
        and review.get('late_candidate_accepted') is False
        and corrected.get('usable_U_J')==originalrows[0].get('usable_U_J'),
        'Old cutoff review must not create or change an energy witness')
    rows=[{**originalrows[0],**corrected},read(ROOT/'claims/anchor_linked4_result.json')]
    first=read(ROOT/'launcher_result.json');second=read(ROOT/'recovery_launcher_result.json')
    firstclaim=read(ROOT/'launcher_claim.json');secondclaim=read(ROOT/'recovery_launcher_claim.json')
    active=first['process_wall_s']+second['process_wall_s']
    k.require(abs(active-second['cumulative_active_process_wall_s'])<=1e-9,'Active process sum mismatch')
    pause=(datetime.fromisoformat(secondclaim['created_at_utc'])-datetime.fromisoformat(first['completed_at_utc'])).total_seconds()
    calendar=(datetime.fromisoformat(second['completed_at_utc'])-datetime.fromisoformat(firstclaim['created_at_utc'])).total_seconds()
    return rows,2,600,{'protocol':claim.get('protocol'),'fault_free_initial_pair':False,
        'original_execution_status':originalrows[0].get('execution',{}).get('execution_status'),
        'corrected_execution_status':corrected.get('execution',{}).get('execution_status'),
        'old_rerun':False,'original_record_manifest_sha256':sha(ROOT/'recovery_before/original_sha256.json'),
        'corrected_old_record_sha256':sha(ROOT/'corrected_old_record.json'),
        'original_old_claim_sha256':sha(ROOT/'claims/old_linked4_result.json'),
        'new_result_sha256':sha(ROOT/'claims/anchor_linked4_result.json'),
        'terminal_result':returned,'original_record':k.safe_summary(originalrows[0]),
        'timing':{'first_process_wall_s':first['process_wall_s'],
            'continuation_process_wall_s':second['process_wall_s'],
            'cumulative_active_process_wall_s':active,'diagnosis_pause_calendar_s':pause,
            'full_calendar_elapsed_s':calendar,'calendar_outside_active_processes_s':calendar-active,
            'original_outer_watchdog_stopped':first['outer_watchdog_stopped'],
            'continuation_outer_watchdog_stopped':second['outer_watchdog_stopped'],
            'continuation_actual_watchdog_limit_s':secondclaim['hard_wall_s'],
            'scope':'two separately supervised active processes; pause is not method budget; each evidence cutoff remains 300s'}}


def plot(jobs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7.5,4.2),layout='constrained')
    for job,color in zip(jobs,('#31658b','#d37c29')):
        points=job.get('complete_updates') or []
        if not points:
            continue
        xs=[p['at_s'] for p in points];ys=[float(F(p['energy_J'][1])) for p in points]
        actual_stop=float((job.get('completion_metrics') or {}).get('root_stop_at_s',300))
        stopped=min(actual_stop,300)
        ax.step(xs+[stopped],ys+[ys[-1]],where='post',color=color,label=job['id'])
        ax.scatter(xs,ys,color=color,s=15)
        ax.scatter([stopped],[ys[-1]],color=color,marker='X',s=45,zorder=4)
        if stopped<300:
            ax.plot([stopped,300],[ys[-1],ys[-1]],color=color,linestyle=':',linewidth=1.2)
        ax.annotate(f'stop {actual_stop:.3f}s',(stopped,ys[-1]),xytext=(-6,-15),
            textcoords='offset points',ha='right',fontsize=7,color=color)
        for p in job.get('phase_attribution',[]):
            if p['phase_index']==2 and p['entered']:
                ax.axvline(p['started_at_s'],color=color,linestyle='--',alpha=.5,linewidth=.8)
    ax.set(xlim=(0,300),xlabel='Full method time (s)',ylabel='Complete SAFE energy upper (J)')
    ax.set_title('X: method stop; dotted tail retains existing U, no further search',fontsize=9)
    ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(OUT/'safe_energy_progress.png',dpi=170);plt.close(fig)


def attribution(facts):
    """Observed timelines/components only, never a counterfactual solve."""
    results={j:read(ROOT/j/'result.json') for j in EXPECTED}
    old,new=(results[j] for j in EXPECTED)
    oldphase,newphase=(r['phases'][1] for r in (old,new))
    oldac,newac=(p['scenes']['AC_offset_0ms'] for p in (oldphase,newphase))
    oldinput=read(ROOT/EXPECTED[0]/'matlab/request_000004.input.json')
    newinput=read(ROOT/EXPECTED[1]/'matlab/request_000004.input.json')
    oldresponse=read(ROOT/EXPECTED[0]/'matlab/request_000004.response.json')
    origin=300-newinput['case_budget_at_entry_s']
    updates=[u for u in facts['jobs'][1]['complete_updates'] if u['phase_index']==2
        and newac['search_started_at_s']<=u['at_s']<=newac['search_returned_at_s']]
    native=[]
    for sid in ('AB_offset_0ms','AC_offset_0ms'):
        one=next(r for r in facts['native_records'] if r['job']==EXPECTED[0] and r['phase_index']==2 and r['scene']==sid)
        two=next(r for r in facts['native_records'] if r['job']==EXPECTED[1] and r['phase_index']==2 and r['scene']==sid)
        native.append({'scene':sid,'old_rootlp_native_cumulative_s':one['first_rootlp_native_elapsed_s'],
            'new_rootlp_native_cumulative_s':two['first_rootlp_native_elapsed_s'],
            'old_wrapper_native_status':one['status'],'new_wrapper_native_status':two['status'],
            'old_accepted_final_numfeaspoints':one['final_numfeaspoints'],
            'new_accepted_final_numfeaspoints':two['final_numfeaspoints'],
            'scope':'rootlp is cumulative callback time; missing old AC final statistics are not zero'})
    components=[]
    for name in facts['jobs'][0]['components_J']:
        x,y=(interval(j['components_J'][name]) for j in facts['jobs'])
        components.append({'component':name,'old_lower_J':str(x[0]),'old_upper_J':str(x[1]),
            'new_lower_J':str(y[0]),'new_upper_J':str(y[1]),
            'old_lower_minus_new_upper_J':str(x[0]-y[1]),
            'observed_energy_decrease_J':float(x[0]-y[1])})
    return {'source':'saved K151 results, receipts, request input/response and completed facts only',
        'new_research_calls':0,'new_thermal_evaluations':0,'native_second_pass':native,
        'startup_old_s':facts['exclusive_totals_s'][EXPECTED[0]]['solver_startup'],
        'startup_new_s':facts['exclusive_totals_s'][EXPECTED[1]]['solver_startup'],
        'model_construction_old_s':facts['exclusive_totals_s'][EXPECTED[0]]['model_construction'],
        'model_construction_new_s':facts['exclusive_totals_s'][EXPECTED[1]]['model_construction'],
        'old_phase2_remaining_s':next(p for p in facts['phases'] if p['job']==EXPECTED[0] and p['phase_index']==2)['root_remaining_at_entry_s'],
        'new_phase2_remaining_s':next(p for p in facts['phases'] if p['job']==EXPECTED[1] and p['phase_index']==2)['root_remaining_at_entry_s'],
        'old_AC_scene_slice_s':oldac['scene_slice_s'],'new_AC_scene_slice_s':newac['scene_slice_s'],
        'old_AC_remaining_at_native_request_entry_s':oldinput['case_budget_at_entry_s'],
        'old_AC_effective_native_MaxTime_s':oldresponse.get('options',{}).get('MaxTime'),
        'new_AC_native_request_entry_root_s':origin,
        'new_AC_full_SAFE_updates':[{'at_s':u['at_s'],'U_J':u['energy_J'][1],
            'after_AC_search_entry_s':u['at_s']-newac['search_started_at_s'],
            'after_AC_native_request_entry_s':u['at_s']-origin,
            'after_phase2_entry_s':u['at_s']-newphase['started_at_s'],
            'before_old_AC_native_entry_remaining':u['at_s']-origin<oldinput['case_budget_at_entry_s'],
            'before_old_total_phase2_remaining':u['at_s']-newphase['started_at_s']<
                next(p for p in facts['phases'] if p['job']==EXPECTED[0] and p['phase_index']==2)['root_remaining_at_entry_s']}
            for u in updates],
        'energy_components':components,
        'causal_scope':'same phase1 warm and fewer original-impossible options support an implementation benefit; '
            'startup and phase2 budgets differed, so no pure causal share or same-budget counterfactual is established'}


def report(facts):
    comp=facts['comparison'];jobs=facts['jobs']
    lines=['# K.151：固定锚预消元单次质量配对（存档只读分析）','',
        f"配对有效：**{comp['valid_quality_pair']}**；新版严格安全能量改善：**{comp['strict_new_improvement']}**。",'',
        '| 方法 | 初始U／J | 第一遍结束U／J | 最终U／J | 首个完整SAFE／s | 首次严格改善／s | 方法返回／s |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for job in jobs:
        one=next((p for p in facts['phases'] if p['job']==job['id'] and p['phase_index']==1),{})
        c=job.get('completion_metrics') or {};w=job.get('wrapper_record') or {}
        lines.append(f"|{job['id']}|{k.text_energy(job.get('initial_energy_J'))}|"
            f"{k.text_energy(one.get('final_complete_energy_J'))}|{k.text_energy(job.get('final_energy_J'))}|"
            f"{c.get('first_complete_SAFE_at_s')}|{c.get('first_strict_improvement_at_s')}|{w.get('method_return_inclusive_wall_s')}|")
    lines+=['',f"新版相对旧版保守节能差：{comp['strict_saving_vs_old_lower_percent']}%；"
        '按新区间上端与旧区间下端计算，负值表示新版能耗较高。','',
        f"两方法第一遍结束warm完全相同：{facts['anchor_comparison']['same_phase1_warm_candidate']}；"
        f"第二遍闭合锚相同：{facts['anchor_comparison']['same_closed_anchors']}。",'',
        '| 方法／场景（二遍） | 选项 | 事件 | 原生变量 | 原生不等式 | 原生等式 | 整数变量 | joint组 | 热能耗条件等式组 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    recovery=facts.get('post_audit_recovery')
    if recovery:
        clock=recovery['timing']
        lines[2:2]=['**本轮经历包装器截止分类故障及追加审计恢复。** 原旧版记录与BLOCKED账本保留；'
            '追加审计确认末请求仅因总预算截止未完成接纳，保留此前完整SAFE。旧版未重跑，新版只消费尚未开始的一次调用。'
            '这不是无故障首次完整配对。',
            f"第一进程{clock['first_process_wall_s']:.3f}s，恢复进程{clock['continuation_process_wall_s']:.3f}s，"
            f"累计活跃进程{clock['cumulative_active_process_wall_s']:.3f}s；诊断暂停{clock['diagnosis_pause_calendar_s']:.3f}s，"
            f"完整日历历时{clock['full_calendar_elapsed_s']:.3f}s。各方法证据仍独立限于300s；原wrapper_timing只含首进程。",'']
    for row in facts['matrix_records']:
        if row['phase_index']==2:
            lines.append('|'+row['job']+'/'+row['scene']+'|'+ '|'.join(str(row[k]) for k in
                ('options','events','native_variables','native_inequalities','native_equalities',
                 'native_integer_variables','joint_groups','thermal_energy_conditional_equation_groups'))+'|')
    lines+=['','根LP时间是原生回调的累计时间戳，不能当作独占LP耗时；节点数和内部界均为solver-reported。'
        '候选、阶段、独占计时及完整能量组成分别见CSV，具体原生轨迹见native_details.json。','',
        '本分析仅核对预算内已形成的完整SAFE回执、哈希、来源和精确区间关系，不重新求解、解码或计算热轨迹。'
        '原参数、auto-L、完整合法域与连续热接纳标准不变；两方法各300秒，未补跑。'
        '一次配对用于本次质量判断，不建立统计稳定性、普遍加速或全域最优结论。','',
        f"热反馈记录／行数："+'；'.join(f"{j['id']} {j.get('feedback_records')}/{j.get('feedback_rows')}" for j in jobs)+'。',
        f"原始工件前后哈希一致：{facts['raw_artifacts_unchanged']}；源快照{facts['source_count']}项一致。"]
    att=facts.get('attribution')
    if att:
        lines+=['','## 归因与实际收益','',
            '| 二遍场景 | 旧根LP累计／s | 新根LP累计／s | 旧／新非warm候选 |',
            '|---|---:|---:|---:|']
        for row in att['native_second_pass']:
            count=[next(r['different_from_own_warm_count'] for r in facts['candidate_summary']
                if r['job']==j and r['phase_index']==2 and r['scene']==row['scene']) for j in EXPECTED]
            lines.append(f"|{row['scene']}|{row['old_rootlp_native_cumulative_s']:.3f}|"
                f"{row['new_rootlp_native_cumulative_s']:.3f}|{count[0]}／{count[1]}|")
        lines+=['','AC新增方案把A的pre／main／post和C.pre从H改为L，并调整起点；具体设备与闭合C.main／post保持。'
            'AB只发生pre起点变化。全局节能主要来自AC设备工作点选择，而非热反馈：两边反馈仍为0。','',
            '| 能耗分项 | 旧减新／J |','|---|---:|']
        for row in att['energy_components']:
            lines.append(f"|{row['component']}|{row['observed_energy_decrease_J']:.12f}|")
        lines+=['',f"MATLAB启动旧／新为{att['startup_old_s']:.3f}／{att['startup_new_s']:.3f}s，"
            f"二遍进入时剩余{att['old_phase2_remaining_s']:.3f}／{att['new_phase2_remaining_s']:.3f}s。"
            f"模型构造总独占耗时反为{att['model_construction_old_s']:.3f}／{att['model_construction_new_s']:.3f}s，"
            '不能声称构模实测加速。',
            f"新增AC两次完整安全改善距该场景搜索开始分别为"
            + '／'.join(f"{u['after_AC_search_entry_s']:.3f}" for u in att['new_AC_full_SAFE_updates'])+'s；'
            '距原生请求入口分别为'+'／'.join(f"{u['after_AC_native_request_entry_s']:.3f}" for u in att['new_AC_full_SAFE_updates'])+'s，'
            f"均小于旧AC原生入口剩余{att['old_AC_remaining_at_native_request_entry_s']:.3f}s。"
            '但按整个二遍累计看，新AC改善出现在旧二遍总剩余预算之后；局部时序证据不能消除启动差异，'
            '更不能断言旧版给足60s仍一定失败或新版在任意相同阶段配额下仍优。',
            '因此：本次同300s总预算得到更低完整安全能耗，预消元准确减少了模型规模，并伴随AC候选生成改善；'
            '尚不能把5.446%全部严格归因于该变换，也不建立稳定性或普遍效率优势。','',
            '能耗图X标记方法停止；之后点线仅表示保留已有U，不表示继续搜索。']
    (OUT/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def finalize_derived():
    """Finalize display/observed attribution; preserve the first derived version."""
    facts=read(OUT/'facts.json')
    k.require(facts.get('derived_finalized') is not True,'Derived finalization already consumed')
    initial=read(OUT/'facts_initial.json')
    k.require(facts==initial and sha(OUT/'analyze_bound_at_initial_run.py')==initial['analysis_source_sha256'],
        'Initial derived version was not preserved exactly')
    k.require(h.raw_hashes(ROOT,initial['raw_hashes_before'])==initial['raw_hashes_before'],
        'A bound raw artifact changed before finalization')
    declaration=read(ROOT/'declaration.json')
    k.require(h.source_audit(ROOT,declaration)['all_match'],'Frozen source/snapshot differs')
    facts.update(derived_finalized=True,initial_analysis_source_sha256=initial['analysis_source_sha256'],
        initial_facts_sha256=sha(OUT/'facts_initial.json'),analysis_source_sha256=sha(__file__),
        attribution=attribution(facts))
    plot(facts['jobs']);report(facts)
    h.write_csv(OUT/'attribution_native.csv',facts['attribution']['native_second_pass'])
    h.write_csv(OUT/'attribution_AC_updates.csv',facts['attribution']['new_AC_full_SAFE_updates'])
    h.write_csv(OUT/'attribution_energy.csv',facts['attribution']['energy_components'])
    k.require(h.raw_hashes(ROOT,initial['raw_hashes_before'])==initial['raw_hashes_before'],
        'A bound raw artifact changed during finalization')
    save(OUT/'facts.json',facts)
    print(json.dumps({'derived_finalized':True,'raw_unchanged':True,
        'analysis_source_matches':facts['analysis_source_sha256']==sha(__file__),
        'strict_saving_percent':facts['comparison']['strict_saving_vs_old_lower_percent']}))


def main():
    k.require(not (OUT/'facts.json').exists(),'Never overwrite completed K151 analysis')
    ledger,declaration=read(ROOT/'ledger.json'),read(ROOT/'declaration.json')
    calls,consumed,reserved,recovery=recover_rows(ledger)
    k.require(ledger['state'] not in ('RUNNING','DECLARED','PREPARED'),'Pair is still running')
    k.require(all(r['state'] not in ('RUNNING','DECLARED','PREPARED') for r in calls),'Method still running')
    k.require([r['id'] for r in calls]==list(EXPECTED[:len(calls)]),'Unexpected invocation order')
    before=h.raw_hashes(ROOT)
    frozen=h.source_audit(ROOT,declaration)
    k.require(frozen['all_match'] and frozen['count']==174,'Frozen174 differs from current/snapshot')
    k.require(all(sha(ROOT/n)==v for n,v in declaration['input_file_sha256'].items()),'Frozen input bytes changed')
    jobs,native,phases,costs,schedules,rawresults,details,candidates,matrices=[],[],[],[],[],[],[],[],[]
    instance=read(ROOT/'input_instance.json')
    byid={r['id']:r for r in calls}
    for jid in EXPECTED:
        if jid not in byid:
            jobs.append({'id':jid,'final_SAFE_receipt_verified':False,'execution_status':'NOT_RUN'})
            rawresults.append({});continue
        result=read(ROOT/jid/'result.json');rawresults.append(result)
        job,nr,pr,cr,sr=k.audit_job(jid,byid[jid],declaration)
        jobs.append(job);native+=nr;phases+=pr;costs+=cr;schedules+=sr
        det,can=native_details(result,jid,instance,nr)
        details+=det;candidates+=can;matrices+=model_details(result,jid)
    old,new=jobs
    normal={'NORMAL_COMPLETION','NORMAL_TIME_LIMIT','NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'}
    valid=bool(len(calls)==2 and consumed==2 and
        all(j.get('final_SAFE_receipt_verified') and j.get('execution_status') in normal for j in jobs))
    oe=interval(old['final_energy_J']) if old.get('final_energy_J') else None
    ne=interval(new['final_energy_J']) if new.get('final_energy_J') else None
    diff=oe[0]-ne[1] if oe and ne else None
    comp={'valid_quality_pair':valid,'strict_new_improvement':bool(valid and diff is not None and diff>0),
        'criterion':'new complete SAFE energy upper < old complete SAFE energy lower',
        'old_energy_J':old.get('final_energy_J'),'new_energy_J':new.get('final_energy_J'),
        'old_lower_minus_new_upper_J':str(diff) if diff is not None else None,
        'strict_saving_vs_old_lower_percent':float(diff/oe[0]*100) if diff is not None and oe[0]>0 else None,
        'same_fresh_seed_choices':bool(old.get('seed_candidate_sha256')) and old.get('seed_candidate_sha256')==new.get('seed_candidate_sha256'),
        'separate_budget_tokens':bool(old.get('seed_budget_token') and new.get('seed_budget_token')) and old['seed_budget_token']!=new['seed_budget_token']}
    totals=defaultdict(lambda:defaultdict(F))
    for row in costs:
        totals[row['job']][row['budget_phase']]+=F(row['exclusive_seconds_exact_fraction'])
    facts={'stage':'K151','scope':'terminal stored receipts only; no new solve/decode/physical evaluation',
        'new_research_calls':0,'new_solver_calls':0,'new_thermal_evaluations':0,'new_candidate_decodes':0,
        'consumed_calls':consumed,'reserved_method_budget_s':reserved,
        'original_ledger_state_raw':ledger['state'],'original_ledger_consumed_raw':ledger['consumed'],
        'post_audit_recovery':recovery,
        'source_count':frozen['count'],'source_current_and_snapshot_match':frozen['all_match'],
        'declaration_sha256':sha(ROOT/'declaration.json'),'analysis_source_sha256':sha(__file__),
        'helper_sha256':sha(HELPER),'input_identities':declaration['input_identities'],
        'comparison':comp,'jobs':jobs,'phases':phases,'matrix_records':matrices,
        'native_records':native,'candidate_summary':candidate_summary(candidates),
        'anchor_comparison':phase1_anchor_comparison(rawresults),
        'exclusive_totals_s':{jid:{name:float(value) for name,value in values.items()} for jid,values in totals.items()},
        'wrapper_timing':read(ROOT/'wrapper_timing.json') if (ROOT/'wrapper_timing.json').exists() else None,
        'raw_hashes_before':before}
    h.write_csv(OUT/'comparison.csv',[{'id':j['id'],'final_energy_J':j.get('final_energy_J'),
        'complete_SAFE_verified':j.get('final_SAFE_receipt_verified'),**j.get('wrapper_record',{})} for j in jobs])
    for name,rows in (('phase_timing',phases),('exclusive_costs',costs),('native',native),
        ('schedules',schedules),('schedule_differences',k.compare_schedules(schedules)),
        ('energy_components',k.component_rows(jobs)),('matrix_dimensions',matrices),
        ('candidate_evaluations',candidates),('candidate_summary',facts['candidate_summary']),
        ('phase1_anchor_comparison',facts['anchor_comparison']['rows'])):
        h.write_csv(OUT/(name+'.csv'),rows)
    save(OUT/'native_details.json',details)
    plot(jobs)
    after=h.raw_hashes(ROOT,before)
    k.require(before==after,'Raw experiment artifacts changed during analysis')
    k.require(h.source_audit(ROOT,declaration)['all_match'],'Source/snapshot changed during analysis')
    facts['raw_hashes_after']=after;facts['raw_artifacts_unchanged']=True
    save(OUT/'facts.json',facts)
    report(facts)
    print(json.dumps({'valid_quality_pair':valid,'strict_new_improvement':comp['strict_new_improvement'],
        'old_U_J':old.get('final_U_J'),'new_U_J':new.get('final_U_J'),
        'same_phase1_warm':facts['anchor_comparison']['same_phase1_warm_candidate'],
        'raw_unchanged':True},ensure_ascii=False))


if __name__=='__main__':
    finalize_derived() if sys.argv[1:]==['--finalize-derived'] else main()
