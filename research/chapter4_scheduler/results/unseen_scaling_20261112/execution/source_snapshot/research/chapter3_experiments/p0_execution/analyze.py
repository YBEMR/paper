"""Stored P0 results only; never search, solve, reevaluate heat or replace U."""
import csv
from fractions import Fraction as F
from pathlib import Path
import statistics
import batch as b


def number(value):
    try:return float(F(str(value))) if value is not None else None
    except (ValueError,ZeroDivisionError,TypeError):return None


def rows():
    ledger=b.read(b.OUT/'ledger.json');answer=[]
    for entry in ledger['calls']:
        folder=b.OUT/'calls'/entry['problem_id']/entry['id']
        records=entry.get('records') or {};metrics=records.get('completion_metrics') or {}
        file=folder/'wrapper_raw_result.json'
        raw=b.read(file) if file.exists() else {}
        receipt=raw.get('aggregation') if entry['method']=='linked_fixed_unit_opp_start' else raw.get('evaluation')
        receipt=receipt or {}
        lower=raw.get('certified_lower_bound_J')
        if lower is None:lower=((raw.get('deployment_bounds') or {}).get('L0') or {}).get('lower_bound_J')
        if (folder/'independent_bounds.json').exists():
            lower=(b.read(folder/'independent_bounds.json').get('L0') or {}).get('lower_bound_J')
        upper=number(records.get('usable_U_J'));L0=number(lower)
        startup=metrics.get('matlab_startup') or {}
        feedback=len(raw.get('feedback') or [])
        for phase in raw.get('phases') or []:
            for scene in (phase.get('scenes') or {}).values():
                feedback+=len((scene.get('solver_result') or {}).get('feedback') or [])
        phases=raw.get('phases') or []
        answer.append({'problem_id':entry['problem_id'],'method':entry['id'],'seed':entry.get('seed'),
            'ordinal':entry['ordinal'],'execution_status':(records.get('execution') or {}).get('execution_status'),
            'post_passed':(entry.get('postcheck') or {}).get('passed'),
            'usable_U_J':upper,'certified_L0_J':L0,
            'certified_gap_fraction':(upper-L0)/upper if upper and L0 is not None else None,
            'energy_low_J':number((receipt.get('weighted_energy_J') or [None,None])[0]),
            'energy_high_J':number((receipt.get('weighted_energy_J') or [None,None])[1]),
            'first_complete_SAFE_s':metrics.get('first_complete_SAFE_at_s'),
            'first_strict_improvement_s':metrics.get('first_strict_improvement_at_s'),
            'root_stop_s':metrics.get('root_stop_at_s'),'matlab_startup_s':startup.get('wall_s'),
            'return_inclusive_s':entry.get('method_return_inclusive_wall_s'),
            'post_s':entry.get('postcheck_wall_s'),'slot_s':entry.get('slot_wall_s'),
            'feedback_saved_rows':feedback,'saved_violation_rows':len(raw.get('violations') or []),
            'phase1_U_J':number(phases[0].get('safe_upper_bound_J')) if phases else None,
            'phase2_U_J':number(phases[1].get('safe_upper_bound_J')) if len(phases)>1 else None,
            'independently_proven_optimal':(records.get('execution') or {}).get('independently_proven_optimal'),
            'independently_proven_infeasible':(records.get('execution') or {}).get('independently_proven_infeasible')})
    return ledger,answer


def main():
    ledger,data=rows()
    if ledger['active'] is not None:raise RuntimeError('No analysis of an active method')
    out=b.OUT/'analysis01';out.mkdir(exist_ok=False)
    if data:
        with (out/'results.csv').open('x',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    cohorts=[]
    for pid in b.p.PROBLEMS:
        selected=[r for r in data if r['problem_id']==pid]
        safe=[r for r in selected if r['usable_U_J'] is not None and r['post_passed'] is True]
        methods={r['method']:r for r in safe}
        sa=[r['usable_U_J'] for r in safe if r['seed'] is not None]
        linked,heft=methods.get('anchor_linked4'),methods.get('heft')
        cohorts.append({'problem_id':pid,'calls':len(selected),'post_verified_safe':len(safe),
            'SA_seeds_observed':len(sa),'SA_median_J':statistics.median(sa) if sa else None,
            'SA_min_J_descriptive_only':min(sa) if sa else None,'SA_max_J':max(sa) if sa else None,
            'linked_vs_heft_reduction_fraction':(heft['usable_U_J']-linked['usable_U_J'])/heft['usable_U_J'] if linked and heft else None})
    b.write_new(out/'facts.json',{'state':ledger['state'],'consumed':ledger['consumed'],
        'reserved_method_budget_s':ledger['reserved_method_budget_s'],'rows':data,'cohorts':cohorts,
        'scope':'new P0 cohort only; SA five-run distribution is not an equal-budget best-of-five competitor'})
    lines=['# K155：P0基准批结果','','状态：'+ledger['state']+'；已消费'+str(ledger['consumed'])+'/40次，预留方法预算'+str(ledger['reserved_method_budget_s'])+'秒。',
        '','| 问题 | 整体MILP U/J | 联动 U/J | HEFT U/J | SA五种子中位数/J | 完整post安全数 |',
        '|---|---:|---:|---:|---:|---:|']
    def fmt(v):return '—' if v is None else f'{v:.9f}'
    for cohort in cohorts:
        pid=cohort['problem_id'];indexed={r['method']:r for r in data if r['problem_id']==pid and r['post_passed'] is True}
        lines.append('|'+pid+'|'+ '|'.join(fmt((indexed.get(key) or {}).get('usable_U_J')) for key in ('whole_milp','anchor_linked4','heft'))+'|'+fmt(cohort['SA_median_J'])+'|'+str(cohort['post_verified_safe'])+'/8|')
    lines.extend(['','SA中位数仅描述五次独立300秒结果；不按五次中最优值作等预算排名。模型、参数、调度域和连续热接纳保持；原K152为独立先导，不并样。',
        '','完整状态、首次安全时间、MATLAB启动及方法／复核耗时见results.csv。内部界、局部界与独立L0不合并；没有可信界闭合时不宣称全域最优。预算后结果不补作预算内U。',
        '','原始调用、一次性claim、截止／隔离和post证据均保留；出现阻断时本表只统计已运行前缀，不补跑未完成槽。'])
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'analysis_dir':str(out),'calls':len(data),'state':ledger['state']}


if __name__=='__main__':print(main())
