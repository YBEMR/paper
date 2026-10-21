"""Terminal-only P1 analysis: no solver or thermal calls."""
import csv
from fractions import Fraction as F
import json
from pathlib import Path
import statistics
import sys
REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
sys.path.insert(0,str(REPO/'research/chapter3_experiments/p1_batch'))
import p1_controller as r
def num(value):
    return None if value is None else float(F(str(value)))

def feedback_count(raw):
    total=len(raw.get('feedback') or [])
    for phase in raw.get('phases') or []:
        for scene in (phase.get('scenes') or {}).values():
            total+=len((scene.get('solver_result') or {}).get('feedback') or [])
    return total

def one(slot,row,segment):
    root=r.OLD if segment=='K155' else r.OUT
    folder=root/'calls'/slot['problem_id']/slot['id']
    raw=r.read(folder/'wrapper_raw_result.json');rec=row['records'];metrics=rec['completion_metrics']
    receipt=raw.get('aggregation') if slot['method']=='linked_fixed_unit_opp_start' else raw.get('evaluation')
    receipt=receipt or {}
    post=r.read(folder/'postcheck.json') if (folder/'postcheck.json').exists() else {}
    lower=raw.get('certified_lower_bound_J')
    if lower is None:lower=((raw.get('deployment_bounds') or {}).get('L0') or {}).get('lower_bound_J')
    if (folder/'independent_bounds.json').exists():lower=r.read(folder/'independent_bounds.json')['L0']['lower_bound_J']
    interval=receipt.get('weighted_energy_J') or [None,None]
    upper=num(rec.get('usable_U_J'));L0=num(lower)
    post_safe=post.get('state')=='SAFE' and post.get('rankable_energy') is True
    phases=[]
    carried=raw.get('initial_global_safe_upper_bound_J')
    for phase in raw.get('phases') or []:
        updates=[u for u in raw.get('global_updates') or [] if u.get('phase_index')==phase['phase_index']]
        if updates:carried=updates[-1]['safe_upper_bound_J']
        phases.append({'phase':phase['phase_index'],'start_s':phase['started_at_s'],
            'end_s':phase.get('completed_at_s'),'U_J':num(carried),
            'new_strict_improvement':any(u.get('strict_energy_improvement_certified') is True for u in updates)})
    out={'ordinal':slot['ordinal'],'problem_id':slot['problem_id'],'method':slot['id'],'seed':slot.get('seed'),
        'segment':segment,'method_state':rec['execution']['execution_status'],
        'original_wrapper_archive_failure':segment=='K155' and slot['id']=='heft',
        'safe_U_J':upper,'safe_U_exact':rec.get('usable_U_J'),
        'safe_energy_lo_J':num(interval[0]),'safe_energy_hi_J':num(interval[1]),
        'safe_energy_lo_exact':interval[0],
        'post_SAFE':post_safe,'comparison_usable':upper is not None and post_safe,
        'independent_L0_J':L0,'certified_gap_fraction':(upper-L0)/upper if upper and L0 is not None else None,
        'independent_bound_inconsistent':upper is not None and lower is not None and F(lower)>F(rec['usable_U_J']),
        'first_SAFE_s':metrics.get('first_complete_SAFE_at_s'),
        'first_strict_improvement_s':metrics.get('first_strict_improvement_at_s'),
        'method_root_s':(raw.get('timing') or {}).get('method_elapsed_s'),
        'return_inclusive_s':row.get('method_return_inclusive_wall_s'),
        'matlab_startup_s':(metrics.get('matlab_startup') or {}).get('wall_s'),
        'post_evaluator_s':post.get('elapsed_s'),'feedback_saved_rows':feedback_count(raw),
        'violation_saved_rows':len(raw.get('violations') or []),
        'independently_proven_optimal':rec['execution'].get('independently_proven_optimal'),
        'independently_proven_infeasible':rec['execution'].get('independently_proven_infeasible'),
        'phase1_U_J':phases[0]['U_J'] if phases else None,
        'phase2_U_J':phases[1]['U_J'] if len(phases)>1 else None,'phases':phases,
        'safe_curve':metrics.get('complete_SAFE_receipts') or []}
    return out

def main(name='analysis01'):
    terminal=r.read(r.OUT/'process_terminal.json');ledger=r.read(r.OUT/'ledger.json')
    rows=[]
    for slot in r.slots():
        file=r.OUT/'claims'/(slot['slot_id']+'_result.json')
        if not file.exists():file=r.OUT/'claims'/(slot['slot_id']+'_method_return.json')
        if file.exists():rows.append(one(slot,r.read(file),'K158'))
    rows.sort(key=lambda x:x['ordinal'])
    assert len({row['ordinal'] for row in rows})==len(rows)
    cohorts=[]
    for pid in r.p.PROBLEMS:
        group=[x for x in rows if x['problem_id']==pid]
        safe=[x for x in group if x['comparison_usable']]
        indexed={x['method']:x for x in safe}
        heft=indexed.get('heft');linked=indexed.get('anchor_linked4')
        sa=[x for x in safe if x['seed'] is not None]
        for row in group:
            row['normalized_to_HEFT']=row['safe_U_J']/heft['safe_U_J'] if heft and row['comparison_usable'] else None
            row['strictly_lower_than_HEFT']=bool(heft and row['comparison_usable'] and F(row['safe_U_exact'])<F(heft['safe_energy_lo_exact']))
        cohorts.append({'problem_id':pid,'observed_calls':len(group),'safe_calls':len(safe),
            'linked_vs_HEFT_reduction_fraction':(heft['safe_U_J']-linked['safe_U_J'])/heft['safe_U_J'] if heft and linked else None,
            'linked_strictly_lower_than_HEFT':bool(heft and linked and F(linked['safe_U_exact'])<F(heft['safe_energy_lo_exact'])),
            'SA_n':len(sa),'SA_mean_J':statistics.mean(x['safe_U_J'] for x in sa) if sa else None,
            'SA_median_J':statistics.median(x['safe_U_J'] for x in sa) if sa else None,
            'SA_min_J_descriptive_only':min((x['safe_U_J'] for x in sa),default=None),
            'SA_max_J':max((x['safe_U_J'] for x in sa),default=None),
            'SA_stdev_J':statistics.stdev(x['safe_U_J'] for x in sa) if len(sa)>1 else None})
    out=r.OUT/name;out.mkdir(exist_ok=False)
    if rows:
        fields=[k for k in rows[0] if k not in ('phases','safe_curve')]
        with (out/'results40.csv').open('x',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    facts={'protocol':'K158-P1-response-R-terminal-analysis-v1','process_terminal':terminal,
        'observed_rows':len(rows),'consumed_total':ledger['consumed_total'],
        'reserved_total_method_s':ledger['reserved_total_method_s'],'cohorts':cohorts,'rows':rows,
        'method_root_sum_s':sum(x['method_root_s'] or 0 for x in rows),
        'all_formed_SAFE_post_verified':all(x['post_SAFE'] for x in rows if x['safe_U_J'] is not None),
        'independent_bound_anomalies':sum(x['independent_bound_inconsistent'] for x in rows),
        'scope':'P1 distinct response_R inputs; no historical candidates/initialisation; SA5 descriptive, not best-of-five ranking'}
    r.write_new(out/'facts.json',facts)
    fmt=lambda x:'—' if x is None else f'{x:.9f}'
    lines=['# K158：P1 response_R结果','',f"状态：{terminal['state']}；消费{ledger['consumed_total']}／40次。",'',
        '| 输入 | 整体MILP/J | 联动/J | HEFT/J | SA中位数/J | 最终安全输出 |',
        '|---|---:|---:|---:|---:|---:|']
    for c in cohorts:
        indexed={x['method']:x for x in rows if x['problem_id']==c['problem_id'] and x['comparison_usable']}
        vals=[fmt((indexed.get(k) or {}).get('safe_U_J')) for k in ('whole_milp','anchor_linked4','heft')]
        lines.append('|'+c['problem_id']+'|'+'|'.join(vals)+'|'+fmt(c['SA_median_J'])+f"|{c['safe_calls']}/{c['observed_calls']}|")
    lines+=['','每次300秒包含启动、构模、求解和内部完整热复核；事后核查另列，不补预算内U。',
        '','P1只是把共同真实响应输入由H改为R，不是让某规划器误用模型。与P0跨条件比较按各自问题解释。SA逐次与分布保留，五次最优不是一次等预算竞争者。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print({'analysis':str(out),'rows':len(rows),'terminal':terminal['state']})

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'analysis01')
