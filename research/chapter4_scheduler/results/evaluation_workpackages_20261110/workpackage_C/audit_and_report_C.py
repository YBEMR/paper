"""Read-only receipt arithmetic audit and result tables, no new propagation."""
from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime,timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[4]
sys.path[:0]=[str(OUT),str(REPO/'research/chapter3_experiments')]
import periodic_core as core
from run_C import verify
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def write_csv(path,rows):
    with path.open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

checks=[];started=datetime.now(timezone.utc).isoformat();plan=read(OUT/'plan.json');identity=read(OUT/'plan_identity.json')['sha256'];summary=read(OUT/'real_run01/summary.json');config=read(OUT/'frozen/input_config.json');instance=read(OUT/'frozen/input_instance.json');nodes=instance['platform']['node_order'];limits=[F(80)]*4
def check(name,value):
    checks.append({'name':name,'passed':bool(value)})
    if not value:raise AssertionError(name)
def deny(*args,**kwargs):raise AssertionError('READ_ONLY_AUDIT_FORBIDS_NEW_PROPAGATION_OR_SEARCH')
cycle_rows=[];mean_rows=[];difference_rows=[]
with ExitStack() as stack:
    for target in ('thermal.evaluate_candidate','thermal.evaluate_piecewise','heft_method.run_heft','heft_method.build_heft_candidate','sa_method.run_sa'):
        stack.enter_context(patch(target,side_effect=deny))
    verify(plan,identity)
    check('all exactly nine slots processed',summary['completed_all_nine'] and [r['slot'] for r in summary['results']]==plan['slots'])
    check('bounded wall and no scheduling calls',summary['wall_s']<1800 and summary['new_scheduling_search_calls']==0)
    for row in summary['results']:
        slot=row['slot'];name=slot['id'];folder=OUT/'real_run01'/name;spec=read(OUT/'frozen'/(name+'.json'));r=row['result'];check(name+': no technical or unresolved result',row['error'] is None and row['classification'] in ('SAFE_ALL_ROUNDS','THERMAL_VIOLATION'))
        check(name+': one frozen config budget',row['actual_original_kernel_calls']<=259 and row['wall_s']<180 and r['checked_round_count']<=128)
        check(name+': stable same4D norm',r['contractivity']==core.contraction(instance['platform'],spec['segments'],slot['period_ms']))
        receipts={};calls={}
        events=[json.loads(line) for line in (folder/'calls.jsonl').read_text().splitlines()]
        check(name+': all calls returned',sum(e['event']=='START' for e in events)==sum(e['event']=='RETURN' for e in events)==row['actual_original_kernel_calls'])
        for c in row['calls']:
            v=read(folder/c['receipt_file']);receipts[c['label']]=v;calls[c['label']]=c
            check(name+': complete valid original receipt '+str(c['ordinal']),v['complete'] and F(v['covered_until_s'])==F(slot['period_ms'])/1000 and v['reason'] in ('COMPLETE_CONTINUOUS_ENCLOSURE','POINT_WITNESS'))
            check(name+': timely original receipt '+str(c['ordinal']),0<=v['completed_at_elapsed_s']<180)
        nominal=receipts['fixed_point_residual'];xhat=calls['fixed_point_residual']['entry_degC'];residual,radius=core.residual_radius(xhat,[nominal['final_temperature_degC'][n] for n in nodes],r['contractivity']['q_rational_upper'])
        check(name+': fixedpoint interval residual and radius',str(residual)==r['fixed_point_residual_infinity_K'] and str(radius)==r['fixed_point_initial_error_radius_K'])
        box=[[str(F(x)-radius),str(F(x)+radius)] for x in xhat]
        check(name+': periodic initial box',box==r['periodic_entry_box_degC'])
        check(name+': two periodic bound paths started at endpoints',calls['steady_lower']['entry_degC']==[v[0] for v in box] and calls['steady_upper']['entry_degC']==[v[1] for v in box])
        steady=core.combine_paths(receipts['steady_lower'],receipts['steady_upper'],instance['platform'],slot['period_ms']);check(name+': all periodic bounds reproduced',steady==r['periodic_bounds'])
        periodic_peak=max(F(v[1]) for v in steady['peak_by_node_degC'].values());periodic_min=min(F(v[0]) for v in steady['minimum_by_node_degC'].values());entry=[['50','50'] for _ in nodes];prefix_upper=None;all_earlier_safe=True
        for item in r['startup_rounds']:
            n=item['round'];label=f'round_{n:03d}_lower';lo=receipts[label];hi=receipts.get(f'round_{n:03d}_upper',lo)
            check(name+': inherited actual entry box '+str(n),item['entry_box_degC']==entry and calls[label]['entry_degC']==[v[0] for v in entry])
            if f'round_{n:03d}_upper' in calls:check(name+': upper entry '+str(n),calls[f'round_{n:03d}_upper']['entry_degC']==[v[1] for v in entry])
            else:check(name+': reused identical entry only '+str(n),[v[0] for v in entry]==[v[1] for v in entry])
            bound=core.combine_paths(lo,hi,instance['platform'],slot['period_ms']);check(name+': actual bound reproduced '+str(n),bound==item['bound'])
            distance=core.box_distance(bound['end_temperature_degC'],box);check(name+': conservative tail arithmetic '+str(n),F(item['distance_after_round_to_periodic_box_K'])==distance and F(item['tail_all_future_upper_degC'])==periodic_peak+distance and F(item['tail_all_future_lower_degC'])==periodic_min-distance)
            peak_hi=max(F(v[1]) for v in bound['peak_by_node_degC'].values());prefix_upper=peak_hi if prefix_upper is None else max(prefix_upper,peak_hi)
            if n<r['checked_round_count']:all_earlier_safe=all_earlier_safe and peak_hi<=80
            entry=bound['end_temperature_degC']
        check(name+': first-round data reused',r['first_round']==r['startup_rounds'][0]['bound'])
        last=r['startup_rounds'][-1]
        if row['classification']=='SAFE_ALL_ROUNDS':
            check(name+': all checked prefixes continuously safe',prefix_upper<=80)
            check(name+': full future tail safe and model-valid',last['tail_model_range_certified'] and F(last['tail_all_future_upper_degC'])<=80 and F(last['tail_all_future_lower_degC'])>=20)
            check(name+': allround bound is conservative max',F(r['all_rounds_conservative_upper_degC'])==max(prefix_upper,F(last['tail_all_future_upper_degC'])))
            check(name+': no diagnostic-only energy flag',not r['periodic_energy_is_diagnostic_only'])
        else:
            witness=r['violation_witness'];actual=receipts[f"round_{witness['round']:03d}_lower"]
            check(name+': actual low-path point witness',any(all(v.get(k)==witness.get(k) for k in ('node','time_s','temperature_degC','limit_degC')) for v in actual['violations']) and F(witness['temperature_degC'][0])>80)
            check(name+': earliest unsafe only after safe prefix',all_earlier_safe and r['earlier_rounds_all_safe'] and r['first_unsafe_round']==witness['round'])
            check(name+': global witness time',F(witness['global_time_s'])==(witness['round']-1)*F(slot['period_ms'])/1000+F(witness['time_s']))
            check(name+': unsafe energy explicitly diagnostic',r['periodic_energy_is_diagnostic_only'] and r['all_rounds_conservative_upper_degC'] is None)
        old=spec['reference_CSV_row'];difference={'id':name,'template':slot['template'],'scene':slot['scene_id'],'period_ms':slot['period_ms'],'old_classification':old['classification'],'new_classification':row['classification'],
            'old_periodic_peak_lower_degC':old['periodic_peak_lower_degC'],'old_periodic_peak_upper_degC':old['periodic_peak_upper_degC'],'new_periodic_peak_lower_degC':r['periodic_peak_degC'][0],'new_periodic_peak_upper_degC':r['periodic_peak_degC'][1],
            'new_upper_minus_old_upper_degC':str(F(r['periodic_peak_degC'][1])-F(old['periodic_peak_upper_degC'])),'old_all_rounds_conservative_upper_degC':old['all_rounds_upper_degC'],'new_all_rounds_conservative_upper_degC':r['all_rounds_conservative_upper_degC'],
            'bound_comparison_note':'Conservative bounds are not actual peaks; differing valid bounds are not trajectory errors.','old_first_unsafe_round':old['first_unsafe_round'],'new_first_unsafe_round':r['first_unsafe_round'],'new_witness_global_time_s':r['violation_witness']['global_time_s'] if r['violation_witness'] else '',
            'first_energy_upper_minus_old_J':str(F(r['first_round']['energy_J'][1])-F(old['first_energy_J'])),'periodic_energy_upper_minus_old_J':str(F(steady['energy_J'][1])-F(old['periodic_energy_J_diagnostic_if_unsafe']))}
        difference_rows.append(difference)
        cycle_rows.append({'id':name,'template':slot['template'],'scene':slot['scene_id'],'period_ms':slot['period_ms'],'makespan_ms':slot['makespan_ms'],'classification':row['classification'],
            'periodic_peak_lower_degC':r['periodic_peak_degC'][0],'periodic_peak_upper_degC':r['periodic_peak_degC'][1],'periodic_peak_upper_node':r['periodic_peak_node_upper'],'all_rounds_conservative_upper_degC':r['all_rounds_conservative_upper_degC'],
            'first_cycle_energy_lower_J':r['first_round']['energy_J'][0],'first_cycle_energy_upper_J':r['first_round']['energy_J'][1],'periodic_cycle_energy_lower_J':steady['energy_J'][0],'periodic_cycle_energy_upper_J':steady['energy_J'][1],
            'periodic_energy_diagnostic_only':r['periodic_energy_is_diagnostic_only'],'checked_startup_rounds':r['checked_round_count'],'first_unsafe_round_if_certified':r['first_unsafe_round'],
            'fixedpoint_residual_inf_K':r['fixed_point_residual_infinity_K'],'fixedpoint_error_radius_K':r['fixed_point_initial_error_radius_K'],'alpha_per_s':r['contractivity']['alpha_per_s'],'q_rational_upper':r['contractivity']['q_rational_upper'],
            'rho_float_diagnostic_only':r['floating_guide']['spectral_radius_float_diagnostic'],'kernel_calls':row['actual_original_kernel_calls'],'wall_s':row['wall_s']})
        for node in nodes:mean_rows.append({'id':name,'scene':slot['scene_id'],'period_ms':slot['period_ms'],'node':node,'first_cycle_mean_lower_degC':r['first_round']['mean_by_node_degC'][node][0],'first_cycle_mean_upper_degC':r['first_round']['mean_by_node_degC'][node][1],
            'periodic_cycle_mean_lower_degC':steady['mean_by_node_degC'][node][0],'periodic_cycle_mean_upper_degC':steady['mean_by_node_degC'][node][1],'energy_status':'diagnostic_unsafe' if r['periodic_energy_is_diagnostic_only'] else 'safe_fixed_template_cycle'})
    verify(plan,identity)
    check('exact9 cycle and36 mean rows',len(cycle_rows)==9 and len(mean_rows)==36)
audit={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'assertion_count':len(checks),'checks':checks,'new_original_kernel_calls':0,'new_scheduling_calls':0,'shared_original_kernel_not_independent_certificate':True}
save(OUT/'C_read_only_audit.json',audit);write_csv(OUT/'C_cycle_results.csv',cycle_rows);write_csv(OUT/'C_cycle_node_mean_temperatures.csv',mean_rows);write_csv(OUT/'C_original_CSV_differences.csv',difference_rows)
lines=['# C：九个固定模板周期配置后验复核','',
    '恰九配置完成：7个全轮连续安全界成立、2个实际启动路径超温点成立、0未决/技术错误。没有新调度搜索、改时间表、改参数、补跑或扩例。原CSV只随附数据/纪要未随附生成脚本，本轮按冻结合同实现最小后验复核；共享原热核，不称独立实现证书。','',
    f"计划SHA `{identity}`。真实批次 {summary['started_utc']}–{summary['ended_utc']}，{summary['wall_s']:.6f}秒，原piecewise核调用{summary['actual_original_kernel_calls']}次，0搜索；每配置180秒/128启动轮/最多259核调用、总1800秒，无预算触及。15项原人工检查和2项汇总-schema回放通过。随后{len(checks)}项只读断言通过，新增原热核调用0。",'',
    '|模板|场景|P ms|周期稳态峰温近似显示 °C（严格包围见CSV）|全轮保守上界 °C|判定|启动检查轮|',
    '|---|---|---:|---|---:|---|---:|']
for row in cycle_rows:
    display=lambda value:f'{float(F(value)):.9f}'
    lines.append(f"|{row['template']}|{row['scene'].split('_')[0]}|{row['period_ms']}|[{display(row['periodic_peak_lower_degC'])}, {display(row['periodic_peak_upper_degC'])}]|{display(row['all_rounds_conservative_upper_degC']) if row['all_rounds_conservative_upper_degC'] else '未给安全界'}|{row['classification']}|{row['checked_startup_rounds']}|")
lines+=['',
    '全H AB75于第21轮、1.575 s、NPU0点下界80.092269397577°C；AB80于第29轮、2.315 s、NPU0下界80.145587867910°C。所有更早轮次上包络均<=80°C，因此可称首个超温轮。仅下入口路径点用于实际违例结论，上路径越限单独不作实际违例。','',
    'AB85周期稳态峰温约79.112397°C，全轮保守上界约79.929731°C；后者由34轮前缀及尾界组成，不是实际峰温估计。旧CSV相应保守上界79.202348°C；两种保守界不要求相等。所有九行周期稳态峰温与旧CSV的六位小数舍入区间相容，两个原违例轮/点时间一致。其它全轮界差异单列，不能当温度轨迹误差。','',
    '`C_cycle_results.csv`含原周期/首轮能量区间、稳定性q/浮点rho诊断、固定点残差与初态误差半径、起始检查轮及核调用成本；`C_cycle_node_mean_temperatures.csv`含36行四节点首轮/周期均温区间；`C_original_CSV_differences.csv`逐项对应原九行。均温采用Ta+温升积分/P，周期能量单位J/周期，不冒充原400ms单轮能量；unsafe周期能量明确仅诊断。','',
    '三模板来自4339bdcc：全H c212a952...04b126（MILP原始H模板，非HEFT首解de42...）、增强HEFT终解58e9d449...8b6531、MILP终解bbbdf365...70bac1。原输入400ms/β1/50°C/80°C与原期限90/100/90ms保持；在原400ms做完整合法性检查，仅截取原功率时间表[0,P]，makespan<=P，保留周期内闲尾。各场景分别重复，轮末温度继承，不把AB和AC串接。','',
    '证明口径：4维温度块每段Metzler、行和<=-alpha，同一无权∞范数q<=1/(1+alpha·P)<1。浮点只提出固定点候选；原区间核一周期残差R给入口误差R/(1-q)，再以该盒上下入口原核传播夹整个周期轨迹/均温/能量。启动轮上下路径末温区间端点直接继承，不取中点；全部路径在20–100°C有效域内。检查N轮后以周期峰温上界+dN约束全部未来，dN为实际轮末盒与周期入口盒的最远∞距离；同时用周期最小温度下界-dN保证未来模型域。完整SAFE前缀+安全且有效尾界才标SAFE_ALL_ROUNDS。','',
    '实际命令及起止：`run01_command_started.json`/`run01_command_return.json`；总日志`run01_stdout.log`、`run01_stderr.log`。逐配置`real_run01/<id>/result.json`、`calls.jsonl`、`receipt_*.json`保留全部原核输出，`real_run01/comparison_to_original_CSV.json`保留初始自动差异。无重新热积分的审计见`C_read_only_audit.json`。','',
    '这是给定模板的后验周期安全/能量评价，不是周期调度优化、真实芯片测量或一般性结论。原CSV的source_commit是输入模型谱系，不能当其生成程序证书。原CSV/既有结果均未修改，未推送或合并。','']
with (OUT/'C_summary.md').open('x') as f:f.write('\n'.join(lines))
manifest={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='C_manifest.json'}
save(OUT/'C_manifest.json',{'completed_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':identity,'files_sha256':manifest,'actual_original_kernel_calls':summary['actual_original_kernel_calls'],'new_scheduling_search_calls':0,'read_only_audit_assertions':len(checks),'classifications':dict(Counter(r['classification'] for r in summary['results'])),'pushed':False,'merged':False})
print({'passed':True,'assertions':len(checks),'manifest_files':len(manifest),'states':dict(Counter(r['classification'] for r in summary['results']))},flush=True)
