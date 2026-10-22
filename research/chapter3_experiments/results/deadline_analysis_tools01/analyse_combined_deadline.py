"""Read-only K163+K164 analysis of the same original 40 deadline slots.

No scientific modules are imported. Prefix mode reads only sealed result claims
and their hash-bound artifacts. Final mode requires process_terminal.json.
The original two-slot directory is never an output destination.
"""
import argparse
from collections import Counter
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path

import analyse_deadline as a

HERE, ROOT, REPO = a.HERE, a.ROOT, a.REPO
OLD = ROOT/'results/deadline_execution01'
RESUME = ROOT/'results/deadline_resume01'
REPAIR = ROOT/'results/deadline_cutoff_repair01'
NORMAL_CUTOFF = 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'
MARKER_ERROR = 'MISSING_MATCHING_ROOT_CANCEL_FILE'


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def roster(old, continuation):
    """A continuation is exactly the unconsumed suffix, not another batch."""
    slots = old['slots']
    require(len(slots) == 40, 'Original declaration must contain 40 slots')
    require([v['ordinal'] for v in slots] == list(range(1, 41)), 'Original ordinals changed')
    require(len({v['slot_id'] for v in slots}) == 40, 'Duplicate original slots')
    require(continuation['slots'] == slots[2:], 'Continuation is not the exact original 3..40 suffix')
    require(continuation.get('prior_consumed') == 2
            and continuation.get('remaining_calls') == 38
            and continuation.get('campaign_call_limit') == 40
            and continuation.get('seconds_each') == 300
            and continuation.get('campaign_reserved_method_s') == 12000
            and continuation.get('calendar_was_not_reset') is True,
            'Changed continuation count, budget or calendar')
    return deepcopy(slots)


def corrected_old_second(record, review, post):
    """Apply only a previously saved, fully hash-checked adapter derivation.

This does not run the adapter, change the archived record, or produce any U.
File-level binding is checked by validate_repair before this pure transform.
"""
    records = record.get('records') or {}
    execution = records.get('execution') or {}
    audit = review.get('cancel_overwrite_audit') or {}
    require(review.get('protocol') == 'K163-read-only-cancel-repair-review-v1'
            and review.get('passed') is True and bool(review.get('checks'))
            and all(value is True for value in review['checks'].values())
            and review.get('slot_id') == record.get('slot_id')
            and review.get('new_research_calls') == 0
            and review.get('new_thermal_evaluations') == 0
            and review.get('new_safe_U') is False
            and review.get('original_data_modified') is False,
            'Stored read-only adapter review is incomplete')
    require(execution.get('execution_status') == 'TECHNICAL_FAILURE_CONFIRMED'
            and records.get('context', {}).get('hard_errors') == [MARKER_ERROR]
            and audit.get('protocol') == 'K163-root-cutoff-cancel-overwrite-adapter-v1'
            and audit.get('applied') is True
            and audit.get('original_execution') == execution
            and audit.get('original_context_hard_errors') == [MARKER_ERROR]
            and audit.get('derived_execution_status') == NORMAL_CUTOFF
            and audit.get('new_safe_evaluation') is False
            and audit.get('late_candidate_accepted') is False
            and (records.get('current_schedule_audit') or {}).get('passed') is True,
            'Derivation does not match this exact original cancel-only fault')
    U = records.get('usable_U_J')
    require(U is not None and U == review.get('original_U_J')
            == review.get('derived_U_J') == post.get('original_U_J'),
            'Correction must preserve the original exact safe U')
    require(post.get('state') == 'PASSED' and post.get('passed') is True
            and bool(post.get('checks')) and all(value is True for value in post['checks'].values())
            and post.get('new_U') is False and post.get('research_repeated') is False
            and post.get('delayed_original_once_only_post') is True
            and post.get('original_slot_files_unchanged') is True
            and post.get('new_safe_formation_or_U') is False,
            'Delayed post is not the once-only verification of the original U')
    view = deepcopy(record)
    view['records']['execution']['execution_status'] = NORMAL_CUTOFF
    # An explicit derived reason, never presented as a native/raw solver field.
    view['records']['execution']['reasons'] = ['HASH_BOUND_CANCEL_ADAPTER_DERIVED_CLASSIFICATION']
    view['records']['context']['hard_errors'] = []
    view['records']['cancel_overwrite_audit'] = deepcopy(audit)
    view['postcheck'] = deepcopy(post)
    return view


def provenance(row, original, view, *, segment, record_source, post_source,
               correction_source=None):
    saved = original.get('records') or {}
    stored_audit = saved.get('cancel_overwrite_audit') or {}
    stored_exec = saved.get('execution') or {}
    # K164 stores both the inherited and adapter-derived statuses itself.
    raw_exec = (stored_audit.get('original_execution') or stored_exec
                if stored_audit.get('applied') is True else stored_exec)
    row.update(segment=segment, record_source=record_source,
        raw_slot_state=original.get('state', 'NOT_STARTED'),
        raw_execution_status=raw_exec.get('execution_status', 'NO_STORED_METHOD_RETURN'),
        stored_execution_status=stored_exec.get('execution_status', 'NO_STORED_METHOD_RETURN'),
        derived_execution_status=row['execution_status'],
        raw_execution_reasons=raw_exec.get('reasons') or [],
        raw_context_hard_errors=(stored_audit.get('original_context_hard_errors')
            if stored_audit.get('applied') is True else (saved.get('context') or {}).get('hard_errors')),
        raw_post_state=(original.get('postcheck') or {}).get('state'),
        effective_post_state=(view.get('postcheck') or {}).get('state'),
        post_source=post_source,
        classification_source=correction_source or record_source,
        classification_derived=correction_source is not None or stored_audit.get('applied') is True,
        original_usable_U_preserved=(saved.get('usable_U_J')
            == (view.get('records') or {}).get('usable_U_J')),
        new_safe_U_from_analysis=False)
    return row


def summarize_counts(rows):
    """Keep declared/claimed/sealed/no-U separate, including prefixes."""
    result = {
        'declared': len(rows),
        'sealed': sum(r.get('sealed') is True for r in rows),
        'claimed': sum(r.get('claim_exists') is True for r in rows),
        'unsealed_claims': sum(r.get('claim_exists') is True and r.get('sealed') is not True for r in rows),
        'not_started': sum(r['slot_state'] == 'NOT_STARTED' for r in rows),
        'original_SAFE': sum(r['rankable_original_receipt'] for r in rows),
        'comparison_eligible_SAFE': sum(r['comparison_usable'] for r in rows),
        'normal_without_safe_U': sum(r.get('sealed') is True and r['execution_status'] in a.NORMAL
                                     and r['safe_U_J'] is None for r in rows),
        'post_not_applicable_no_U': sum(r.get('post_state') == 'NOT_APPLICABLE_NO_USABLE_U' for r in rows),
    }
    return result


def combined_cohorts(rows):
    values = a.cohorts(rows)
    for cohort in values:
        group = [r for r in rows if r['problem_id'] == cohort['problem_id']]
        counts = summarize_counts(group)
        cohort.update(sealed_calls=counts['sealed'], claimed_calls=counts['claimed'],
            unsealed_claims=counts['unsealed_claims'], normal_without_safe_U=counts['normal_without_safe_U'],
            post_not_applicable_no_U=counts['post_not_applicable_no_U'],
            SA_sealed_n=sum(r['method_kind'] == 'sa' and r.get('sealed') is True for r in group),
            SA_no_U_sealed_n=sum(r['method_kind'] == 'sa' and r.get('sealed') is True
                                and r['safe_U_J'] is None for r in group))
    return values


def validate_repair(declaration, read, old=OLD, repair=REPAIR):
    review_path, post_path = repair/'repair_review.json', repair/'post_summary.json'
    review, post = read(review_path), read(post_path)
    require(a.sha(review_path) == declaration['repair_review_sha256']
            and a.sha(post_path) == declaration['delayed_post_sha256'], 'Frozen repair/post hash mismatch')
    require(a.sha(ROOT/'deadline_resume/cancel_adapter.py') == review['adapter_sha256'],
            'Adapter source differs from the stored derivation')
    folder = old/'calls/beta_1.0__R1/anchor_linked4'
    require(a.sha(folder/'wrapper_raw_result.json') == post['original_raw_sha256']
            and a.sha(old/'declaration.json') == post['original_declaration_sha256']
            and a.sha(repair/'post01/postcheck.json') == post['postcheck_sha256']
            and a.sha(repair/'post01/postcheck.claim.json') == post['postclaim_sha256'],
            'Delayed post does not bind the original raw receipt and original declaration')
    audit = review['cancel_overwrite_audit']
    number = audit['final_native_request_number']
    for ext, key in [('cancel', 'matching_cancel_file_sha256'),
                     ('python.json', 'matching_python_file_sha256'),
                     ('input.json', 'matching_input_file_sha256')]:
        require(a.sha(folder/'matlab'/f'request_{number:06d}.{ext}') == audit[key],
                'Stored adapter native evidence hash changed')
    return review, post


def compare_P0(rows, prior):
    old = {(r['problem_id'], r['method']): r for r in prior['rows']}
    result = []
    for row in rows:
        previous = old.get((row['problem_id'].replace('beta_1.0__', 'base__'), row['method']))
        if previous is None:
            continue
        p0 = previous.get('safe_U_J') if previous.get('comparison_usable') is True else None
        new = row.get('safe_U_J') if row.get('comparison_usable') is True else None
        result.append({'sample': row['problem_id'].split('__')[-1], 'method': row['method'],
            'P0_problem_id': previous['problem_id'], 'deadline_problem_id': row['problem_id'],
            'P0_safe_U_J': p0, 'deadline_safe_U_J': new,
            'deadline_minus_P0_U_J': None if p0 is None or new is None else new-p0,
            'P0_method_root_s': previous.get('method_root_s'), 'deadline_method_root_s': row['method_root_s'],
            'P0_first_SAFE_s': previous.get('first_SAFE_s'), 'deadline_first_SAFE_s': row['first_SAFE_s'],
            'P0_feedback_saved_rows': previous.get('feedback_saved_rows'),
            'deadline_feedback_saved_rows': row['feedback_saved_rows'],
            'scope': 'independent beta1.3/P0 and beta1.0 conditions; no cross-method/batch witness or time sharing'})
    return result


def collect(*, old=OLD, resume=RESUME, repair=REPAIR, prefix=False):
    old, resume, repair = map(lambda p: Path(p).resolve(), (old, resume, repair))
    hashes = {}
    def read(path):
        path = Path(path); relative = path.relative_to(REPO).as_posix()
        hashes[relative] = a.sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    require(prefix or (resume/'process_terminal.json').is_file(),
            'Final analysis requires the continuation process terminal')
    terminal = read(resume/'process_terminal.json') if (resume/'process_terminal.json').is_file() else {
        'state': 'ACTIVE_SEALED_PREFIX_ONLY', 'no_terminal_claim': True}
    prior_terminal = read(old/'process_terminal.json')
    declaration, continuation = read(old/'declaration.json'), read(resume/'declaration.json')
    slots = roster(declaration, continuation)
    require(a.sha(old/'declaration.json') == continuation['prior_declaration_sha256'],
            'Original declaration binding changed')
    require(len(declaration['source_sha256']) == 240
            and len(continuation['source_sha256']) == 248, 'Unexpected source counts')
    for name, digest in continuation['source_sha256'].items():
        snapshot = old/'source_snapshot'/name if name in declaration['source_sha256'] else resume/'source_snapshot'/name
        require(a.sha(REPO/name) == digest == a.sha(snapshot), 'Current/snapshot source mismatch: '+name)
    # The original stopped directory includes its preserved analysis01/02.
    # All were bound by K164 before continuation; none can be silently replaced.
    for name, digest in continuation['prior_artifact_sha256'].items():
        require(a.sha(REPO/name) == digest, 'Original frozen artifact changed: '+name)
    review, post = validate_repair(continuation, read, old, repair)
    rows = []
    for slot in slots:
        campaign = old if slot['ordinal'] <= 2 else resume
        segment = 'original_1_2' if slot['ordinal'] <= 2 else 'continuation_3_40'
        folder = campaign/'calls'/slot['problem_id']/slot['id']
        result_path = campaign/'claims'/(slot['slot_id']+'_result.json')
        claim_exists = (campaign/'claims'/(slot['slot_id']+'.json')).is_file()
        artifact_path = campaign/'claims'/(slot['slot_id']+'_artifact_sha256.json')
        sealed = result_path.is_file() and artifact_path.is_file()
        # Snapshot this decision once. No reads from raw files of active calls,
        # method_return partials, or the growing continuation ledger.
        if sealed:
            original = read(result_path)
            require(all(original.get(k) == slot.get(k) for k in slot), 'Sealed slot identity mismatch')
            artifact_hashes = read(artifact_path)
            for name, digest in artifact_hashes.items():
                require(a.sha(folder/name) == digest, 'Sealed artifact drift: '+str(folder/name))
            raw = read(folder/'wrapper_raw_result.json')
            instance = read(folder/'input_instance.json')
            require(a.canonical(instance) == declaration['inputs'][slot['problem_id']]['input_sha256'],
                    'Stored call instance is not the original frozen deadline input')
            view = corrected_old_second(original, review, post) if slot['ordinal'] == 2 else deepcopy(original)
        else:
            original = {'state': 'CLAIMED_UNSEALED_NOT_READ' if claim_exists else 'NOT_STARTED'}
            raw, instance, view = {}, {}, original
        summary_folder = folder if sealed else HERE/'_not_a_source'/slot['slot_id']
        row = a.summary_row(slot, view, raw, summary_folder, instance, read)
        row['source_folder'] = folder.relative_to(REPO).as_posix()
        correction_source = (repair/'repair_review.json').relative_to(REPO).as_posix() if sealed and slot['ordinal'] == 2 else None
        post_source = ((repair/'post_summary.json') if sealed and slot['ordinal'] == 2 else
                       folder/'postcheck.json' if sealed and (folder/'postcheck.json').is_file() else
                       result_path if sealed and original.get('postcheck') else None)
        record_source = result_path.relative_to(REPO).as_posix() if sealed else None
        provenance(row, original, view, segment=segment, record_source=record_source,
            post_source=post_source.relative_to(REPO).as_posix() if post_source else None,
            correction_source=correction_source)
        row.update(sealed=sealed, claim_exists=claim_exists)
        rows.append(row)
    for row in rows:
        heft = next(r for r in rows if r['problem_id'] == row['problem_id'] and r['method'] == 'heft')
        paired = (row['comparison_usable'] and heft['comparison_usable']
                  and row['safe_U_J'] is not None and heft['safe_U_J'] is not None and heft['safe_U_J'] > 0)
        row['normalised_to_HEFT'] = row['safe_U_J']/heft['safe_U_J'] if paired else None
        row['strictly_lower_than_HEFT'] = a.strictly_lower(row['safe_energy_interval_J'], heft['safe_energy_interval_J']) if paired else None
    counts = summarize_counts(rows)
    facts = {'protocol': 'K164-combined-original40-read-only-analysis-v1',
        'prefix_only': prefix, 'campaign': resume.relative_to(REPO).as_posix(),
        'original_campaign': old.relative_to(REPO).as_posix(),
        'process_terminal': terminal, 'original_process_terminal': prior_terminal,
        'declared_slots': 40, 'sealed_calls': counts['sealed'],
        'consumed_total': counts['claimed'], 'count_detail': counts,
        'reserved_total_method_s': counts['claimed']*300,
        'ledger_state': 'NOT_READ_PREFIX_OR_TERMINAL',
        'frozen_source_count': 248, 'frozen_sources_verified': True,
        'prior_artifacts_verified': len(continuation['prior_artifact_sha256']),
        'original_calendar_deadline_utc': continuation['original_calendar_deadline_utc'],
        'cohorts': combined_cohorts(rows), 'rows': rows,
        'execution_status_counts': dict(Counter(r['execution_status'] for r in rows)),
        'raw_execution_status_counts': dict(Counter(r['raw_execution_status'] for r in rows)),
        'method_root_sum_s': sum(r['method_root_s'] for r in rows if r['method_root_s'] is not None),
        'safe_original_receipts': counts['original_SAFE'],
        'post_verified_safe_receipts': sum(r['rankable_original_receipt'] and r['post_passed'] is True for r in rows),
        'comparison_usable_calls': counts['comparison_eligible_SAFE'],
        'normal_without_safe_U': counts['normal_without_safe_U'],
        'bound_anomalies': [r['problem_id']+'__'+r['method'] for r in rows if r['L0_above_U_anomaly'] is True],
        'final_deadline_anomalies': [r['problem_id']+'__'+r['method'] for r in rows if r['final_deadline_anomaly']],
        'safe_curve_final_U_anomalies': [r['problem_id']+'__'+r['method'] for r in rows if r['safe_curve_minimum_matches_final_U'] is False],
        'method_SAFE_counts': {method: {
            'declared': sum(r['method'] == method for r in rows),
            'observed': sum(r['method'] == method and r.get('claim_exists') is True for r in rows),
            'sealed': sum(r['method'] == method and r.get('sealed') is True for r in rows),
            'comparison_usable_SAFE': sum(r['method'] == method and r['comparison_usable'] for r in rows)}
            for method in sorted({r['method'] for r in rows})},
        'P0_deadline_separate_conditions': compare_P0(rows, read(a.P0_FACTS)),
        'source_sha256': hashes, 'analysis_script_sha256': a.sha(Path(__file__)),
        'base_analysis_script_sha256': a.sha(HERE/'analyse_deadline.py'),
        'new_scientific_evaluations': 0, 'new_solver_calls': 0, 'new_post_calls': 0,
        'scope': 'original 2 plus exact unconsumed 38; immutable sealed results only; derived statuses and once-delayed post kept separate; no new U'}
    return facts


def figures(out, facts):
    """Static saved-evidence plots; missing/unsealed energy has no zero point."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import statistics
    for family in ('Microsoft YaHei','SimHei','Noto Sans CJK SC'):
        try:
            font_manager.findfont(font_manager.FontProperties(family=family),fallback_to_default=False)
            plt.rcParams['font.family']=family
            break
        except ValueError:
            pass
    plt.rcParams['axes.unicode_minus']=False
    colors={'whole_milp':'#555555','anchor_linked4':'#1f77b4','heft':'#ff7f0e',
        **dict(zip(('sa'+str(i) for i in range(101,106)),('#2ca02c','#9467bd','#8c564b','#e377c2','#17becf')))}
    names={'whole_milp':'整体MILP','anchor_linked4':'联动MILP','heft':'HEFT',
        **{'sa'+str(i):'SA'+str(i) for i in range(101,106)}}
    label=(f"（封存前缀{facts['sealed_calls']}/40）" if facts['prefix_only'] else
           f"（停批{facts['sealed_calls']}/40）" if facts['sealed_calls'] < 40 else
           f"（终态封存{facts['sealed_calls']}/40）")
    fig,axes=plt.subplots(1,5,figsize=(17,4),constrained_layout=True)
    fig.suptitle('期限β=1.0：已存完整安全U与独立L0'+label)
    for ax,cohort in zip(axes,facts['cohorts']):
        group=[r for r in facts['rows'] if r['problem_id']==cohort['problem_id']]
        if cohort['sealed_calls']==0:
            ax.text(.5,.5,'尚无封存结果',transform=ax.transAxes,ha='center',va='center')
            ax.set_title(cohort['problem_id'].split('__')[-1]);ax.set_axis_off();continue
        for row in group:
            curve=row['safe_curve_running_minimum']
            if curve:
                t=[v['at_s'] for v in curve];u=[v['saved_running_min_U_J'] for v in curve]
                end=min(300,row['method_root_s'] if row['method_root_s'] is not None else t[-1])
                ax.step(t+[max(t[-1],end)],u+[u[-1]],where='post',color=colors[row['method']],
                    linewidth=1.15,alpha=.85,ls='-' if row['comparison_usable'] else '--',
                    label=names[row['method']]+('（未接纳）' if not row['comparison_usable'] else ''))
            L0,at=row.get('certified_L0_J'),row.get('certified_L0_formed_at_s')
            if L0 is not None and isinstance(at,(float,int)) and 0<=at<300:
                ax.plot([at,300],[L0,L0],color=colors[row['method']],ls='--',linewidth=.6,alpha=.5,
                    label='独立L0' if row['method']=='whole_milp' else None)
        ax.text(.03,.98,f"封存{cohort['sealed_calls']}/8\nSAFE {cohort['comparison_usable_calls']}/8",
            transform=ax.transAxes,va='top',fontsize=8)
        ax.set(title=cohort['problem_id'].split('__')[-1],xlabel='方法时间/s',ylabel='完整窗口能量/J',xlim=(0,300))
        ax.grid(alpha=.2)
    legend={}
    for ax in axes:
        handles,labels=ax.get_legend_handles_labels();legend.update(zip(labels,handles))
    if legend:fig.legend(list(legend.values()),list(legend),loc='lower center',bbox_to_anchor=(.5,-.06),ncol=9,fontsize=8)
    fig.savefig(out/'best_safe_upper_bound_and_L0.png',dpi=180,bbox_inches='tight');plt.close(fig)

    fig,axes=plt.subplots(1,5,figsize=(17,3.8),constrained_layout=True)
    fig.suptitle('原响应/50°C/80°C：两种期限条件的安全能耗'+label)
    pairs=facts['P0_deadline_separate_conditions']
    for ax,sample in zip(axes,('R1','R2','R3','R4','R5')):
        group=[r for r in pairs if r['sample']==sample]
        for method in ('whole_milp','anchor_linked4','heft'):
            value=next((r for r in group if r['method']==method),{})
            points=[(beta,value[field]) for beta,field in ((1.0,'deadline_safe_U_J'),(1.3,'P0_safe_U_J'))
                    if value.get(field) is not None]
            if points:ax.plot(*zip(*points),marker='o',color=colors[method],label=names[method],linewidth=1.1)
        points=[]
        for beta,field in ((1.0,'deadline_safe_U_J'),(1.3,'P0_safe_U_J')):
            values=[r[field] for r in group if r['method'].startswith('sa') and r.get(field) is not None]
            if values:
                median=statistics.median(values);points.append((beta,median))
                ax.annotate(f'{len(values)}/5',(beta,median),xytext=(0,6),textcoords='offset points',ha='center',fontsize=7)
        if points:ax.plot(*zip(*points),marker='s',ls=':',color='#2ca02c',label='SA成功中位数',linewidth=1.1)
        ax.set(title=sample,xlabel='期限系数β',ylabel='安全能量/J',xticks=[1.,1.3],xlim=(.96,1.34));ax.grid(alpha=.2)
    legend={}
    for ax in axes:
        handles,labels=ax.get_legend_handles_labels();legend.update(zip(labels,handles))
    if legend:fig.legend(list(legend.values()),list(legend),loc='lower center',bbox_to_anchor=(.5,-.07),ncol=4,fontsize=8)
    fig.savefig(out/'P0_deadline_two_level_energy.png',dpi=180,bbox_inches='tight');plt.close(fig)


def markdown(facts):
    def num(value): return '—' if value is None else f'{value:.9f}'
    lines = ['# K163/K164：原40槽期限组联合存档分析', '',
        f"{'封存前缀，尚未宣告整批完成' if facts['prefix_only'] else '监督终态：'+facts['process_terminal'].get('state','未知')}。"
        f"声明40槽；已认领{facts['consumed_total']}槽；封存{facts['sealed_calls']}槽；"
        f"可比较SAFE {facts['comparison_usable_calls']}份。", '',
        '原始2槽与续接38槽属于同一预声明批次，顺序、每次300秒和原日历截止均保留；P0仅为另一期限条件参照。', '',
        '|输入|封存/8|整体MILP/J|联动/J|HEFT/J|SA成功中位数/J|SA成功/声明；封存|',
        '|---|---:|---:|---:|---:|---:|---|']
    for cohort in facts['cohorts']:
        by = {r['method']:r for r in facts['rows'] if r['problem_id'] == cohort['problem_id']}
        lines.append('|'+cohort['problem_id']+'|'+str(cohort['sealed_calls'])+'/8|'
            +'|'.join(num(by[m]['comparison_safe_U_J']) for m in ('whole_milp','anchor_linked4','heft'))
            +'|'+num(cohort['SA_median_J'])+'|'
            +f"{cohort['SA_safe_n']}/5；{cohort['SA_sealed_n']}|")
    lines += ['', '|输入/方法|原始状态|派生/接纳状态|原U/J|可比较U/J|post来源|最小期限裕量/ms|',
              '|---|---|---|---:|---:|---|---:|']
    for row in facts['rows']:
        if not row.get('sealed'):
            continue
        lines.append('|'+row['problem_id']+'/'+row['method']+'|'+row['raw_execution_status']+'|'
            +row['derived_execution_status']+' / '+row['accepted_status']+'|'+num(row['safe_U_J'])+'|'
            +num(row['comparison_safe_U_J'])+'|'+str(row['effective_post_state'])
            +('（原预定延迟复核）' if row['classification_source'] != row['record_source'] else '')+'|'
            +str(row['min_deadline_margin_exact_ms'] or '—')+'|')
    lines += ['', f"正常完成/截止但未取得安全U：{facts['normal_without_safe_U']}次；"
        f"NOT_APPLICABLE_NO_USABLE_U：{facts['count_detail']['post_not_applicable_no_U']}次，均不计SAFE。",
        '', '原第二槽仅采用hash绑定的cancel_adapter只读审查派生正常截止；原始故障记录、原U、形成时刻与原post缺失均保留。外部一次延迟post只复核既有U，不生成新U。',
        '', '期限裕量从已保存Stage起点和合法模式时长用精确有理数计算；不重新积分或接受新方案。无U、未封存、未启动不填0能耗，SA中位数只对成功种子计算并同时保留5个声明分母。',
        '', 'SAFE/L0曲线、两阶段实际时间和改善、求解器内部界、逐场景能耗和峰温分别输出。内部界不升级为独立证明；P0两点条件对照不解释为一般单调趋势。',
        '', f"新求解/热评价/post均0次；封存方法根时钟合{facts['method_root_sum_s']:.3f}秒。", '']
    return '\n'.join(lines)


def write_outputs(out, facts, plots=True):
    out = Path(out).resolve(); out.relative_to(REPO)
    require(not out.is_relative_to(OLD.resolve()), 'Original stopped directory is frozen read-only')
    out.mkdir(parents=True, exist_ok=False)
    (out/'facts.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')
    skip = {'safe_candidate','safe_curve','safe_curve_running_minimum','solver_reported_records','feedback_records',
            'method_phases','scene_slices','accounting_phases','native_requests','final_scene_data','evaluation_record_index'}
    a.write_csv(out/'results40.csv', ({k:v for k,v in row.items() if k not in skip} for row in facts['rows']))
    a.write_csv(out/'cohorts.csv', facts['cohorts'])
    a.write_csv(out/'P0_deadline_separate_conditions.csv', facts['P0_deadline_separate_conditions'])
    for name, field in [('method_phases','method_phases'), ('accounting_phases','accounting_phases'),
                        ('scene_slices','scene_slices'), ('native_requests','native_requests'),
                        ('solver_reported','solver_reported_records'), ('thermal_feedback','feedback_records')]:
        a.write_csv(out/(name+'.csv'), ({'problem_id':r['problem_id'],'method':r['method'],**p}
            for r in facts['rows'] for p in r[field]))
    a.write_csv(out/'scene_energy.csv', ({'problem_id':r['problem_id'],'method':r['method'],'scene':sid,
        'energy_J':s.get('energy_J'),'energy_components_J':s.get('energy_components_J')}
        for r in facts['rows'] for sid,s in r['final_scene_data'].items()))
    a.write_csv(out/'scene_peak_temperature.csv', ({'problem_id':r['problem_id'],'method':r['method'],
        'scene':sid,'node':node,'peak_lo_degC':pair[0],'peak_hi_degC':pair[1]}
        for r in facts['rows'] for sid,s in r['final_scene_data'].items()
        for node,pair in (s.get('peaks_degC') or {}).items()))
    a.write_csv(out/'request_deadline_margins.csv', ({'problem_id':r['problem_id'],'method':r['method'],
        'comparison_usable':r['comparison_usable'],**item}
        for r in facts['rows'] for item in r['deadline_audit']['requests']))
    a.write_csv(out/'method_SAFE_counts.csv', ({'method':m,**v} for m,v in facts['method_SAFE_counts'].items()))
    a.write_csv(out/'SA_seed_results25.csv', ({k:v for k,v in r.items() if k not in skip}
        for r in facts['rows'] if r['method_kind']=='sa'))
    (out/'summary.md').write_text(markdown(facts),encoding='utf-8')
    if plots:
        figures(out, facts)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--prefix', action='store_true', help='Only sealed results; no live ledger/active raw file reads')
    parser.add_argument('--no-plots', action='store_true')
    args=parser.parse_args(argv)
    facts=collect(prefix=args.prefix)
    write_outputs(args.out, facts, plots=not args.no_plots)
    print({k:facts[k] for k in ('prefix_only','declared_slots','sealed_calls','consumed_total','comparison_usable_calls','normal_without_safe_U','new_scientific_evaluations')})
    return 0


if __name__=='__main__':
    raise SystemExit(main())
