"""Readable publication tables from sealed A/B/C data; no physical replay."""
from collections import Counter
from datetime import datetime,timezone
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
REPO=ROOT.parents[3]
IDS=['t50_milp','t50_heft']+[f't50_sa{s}' for s in range(101,106)]
LABELS={'t50_milp':'MILP（完整）','t50_heft':'HEFT（增强）',**{f't50_sa{s}':f'SA{s}' for s in range(101,106)}}
started=datetime.now(timezone.utc).isoformat();began=time.monotonic();sources={};checks=[];log=(OUT/'generation_log.jsonl').open('x')

def note(value):log.write(json.dumps(value,ensure_ascii=False)+'\n');log.flush()
def source(relative,kind='json'):
    path=ROOT/relative;raw=path.read_bytes()
    sources[relative]={'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'path_from_tables':'../../'+relative}
    note({'event':'READ_SEALED_SOURCE','path':relative,**sources[relative]})
    if kind=='json':return json.loads(raw)
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))
def save(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def check(label,value):
    checks.append({'name':label,'passed':bool(value)})
    if not value:raise AssertionError(label)
def fixed_integer(value,digits,upper):
    x=F(value)*10**digits
    return -((-x.numerator)//x.denominator) if upper else x.numerator//x.denominator
def formatted(q,digits):
    sign='-' if q<0 else '';q=abs(q);scale=10**digits
    return sign+str(q//scale)+'.'+str(q%scale).zfill(digits)
def bound(value,digits,upper=True):
    q=fixed_integer(value,digits,upper);result=formatted(q,digits)
    check('outward display '+str(value)[:30],F(result)>=F(value) if upper else F(result)<=F(value))
    return result
def bracket(value,digits):return '['+bound(value[0],digits,False)+', '+bound(value[1],digits,True)+']'
def timing(value):return '' if value is None else f'{value:.3f}'
def csvfile(name,rows):
    with (OUT/name).open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def mdfile(name,lines):
    with (OUT/name).open('x',encoding='utf-8') as stream:stream.write('\n'.join(lines)+'\n')

a=source('workpackage_A/A_results.json');b=source('workpackage_B/B_metrics.json')
c=source('workpackage_C/C_cycle_results.csv','csv');means=source('workpackage_C/C_cycle_node_mean_temperatures.csv','csv')
a_audit=source('workpackage_A/A_execution_record.json');b_audit=source('workpackage_B/B_audit.json');c_audit=source('workpackage_C/C_read_only_audit.json')
check('A existing extraction passed',a_audit['passed'] and a['checks_passed'])
check('C existing readonly audit passed',c_audit['passed'])
check('exact seven A schemes',[row['id'] for row in a['rows']]==IDS)
check('exact seven B schemes',set(row['scheme'] for row in b['scheme_summary'])==set(IDS))
check('exact nine C configurations',len(c)==9 and len({row['id'] for row in c})==9 and [row['id'][:2] for row in c]==[f'{i:02d}' for i in range(1,10)])
check('exact36 cycle/node rows',len(means)==36)

main=[];main_md=[];timing_md=[];components=[];component_md=[];main_exact=[]
for row in a['rows']:
    ident=row['id'];br=next(v for v in b['scheme_summary'] if v['scheme']==ident);t=row['timing']
    check(ident+': A B candidate identity',row['candidate_sha256']==br['candidate_canonical_sha256'])
    check(ident+': A B input identity',row['input_canonical_sha256']==br['input_canonical_sha256'])
    check(ident+': complete same-candidate SAFE',row['method_state']==row['post_state']==br['original_method_SAFE']==br['saved_post_SAFE']=='SAFE')
    check(ident+': fixed600s cap',t['method_budget_s']==600)
    peak=row['maximum_posterior_peak_upper_degC'];meanlo=br['worst_node_scene_time_mean_lower_degC'];meanhi=br['worst_node_scene_time_mean_upper_degC']
    short_scene=br['upper_max_scene'].split('_')[0];location=short_scene+'/'+br['upper_max_node']
    check(ident+': bounded means',F(meanlo)<=F(meanhi)<=F(peak))
    energy=bound(row['stored_method_energy_interval_J'][1],9);peak_display=bound(peak,6);mean_display=bound(meanhi,6)
    main.append({'方案':LABELS[ident],'方案ID':ident,'400ms完整系统能耗上界_J':energy,'最坏连续峰温上界_degC':peak_display,
        '最坏节点400ms时间均温下界_degC':bound(meanlo,6,False),'最坏节点400ms时间均温上界_degC':mean_display,
        '均温上界最大场景节点':location,'原方法SAFE':'SAFE','后验SAFE':'SAFE','方法根预算_s':t['method_budget_s'],
        '方法根耗时_s_近似':timing(t['method_root_s']),'方法进程耗时_s_近似':timing(t['total_method_wall_s']),
        '首次完整SAFE_s_近似':timing(t['first_safe_s']),'最佳完整SAFE_s_近似':timing(t['best_safe_s']),
        '独立后验进程耗时_s_近似':timing(t['post_wall_s']),'MILP名义交付余量_s':t['delivery_reserve_s']})
    main_md.append('|'+ '|'.join([LABELS[ident],energy,peak_display,mean_display+' ('+location+')','SAFE/SAFE'])+'|')
    timing_md.append('|'+ '|'.join([LABELS[ident],timing(t['method_root_s']),timing(t['total_method_wall_s']),timing(t['first_safe_s']),timing(t['best_safe_s']),timing(t['post_wall_s']),'—（原null）' if t['delivery_reserve_s'] is None else str(t['delivery_reserve_s'])])+'|')
    comp=row['posterior_weighted_energy_components_J']
    components.append({'方案':LABELS[ident],'方案ID':ident,'后验基线能耗上界_J':bound(comp['baseline'][1],9),
        '后验活动能耗上界_J':bound(comp['activity'][1],9),'后验外部公共能耗上界_J':bound(comp['external_common'][1],9),
        '后验温度修正能耗上界_J':bound(comp['temperature_correction'][1],9),
        '后验完整能耗上界_J':bound(row['stored_posterior_energy_interval_J'][1],9)})
    component_md.append('|'+ '|'.join([LABELS[ident],*[components[-1][key] for key in list(components[-1])[2:]]])+'|')
    main_exact.append({'scheme_id':ident,'candidate_sha256':row['candidate_sha256'],'input_canonical_sha256':row['input_canonical_sha256'],
        'method_energy_interval_J':row['stored_method_energy_interval_J'],'posterior_energy_interval_J':row['stored_posterior_energy_interval_J'],
        'posterior_energy_components_J':comp,'continuous_peak_upper_degC':peak,
        'worst_time_mean_degC':[meanlo,meanhi],'mean_upper_max_scene':br['upper_max_scene'],'mean_upper_max_node':br['upper_max_node'],
        'timing_original_values':t,'original_method_reason':row['method_reason'],'original_execution_status':row['execution_status'],
        'source_pointers':{'A':'workpackage_A/A_results.json#/rows/'+str(IDS.index(ident)),'B':'workpackage_B/B_metrics.json#/scheme_summary[scheme='+ident+']'}})

null_reserves=a['missing_or_null_fields']
check('exact six reserve null records',len(null_reserves)==6 and all(v['field']=='delivery_reserve_s' for v in null_reserves))
check('reserve null kept in main CSV',sum(row['MILP名义交付余量_s'] is None for row in main)==6)
csvfile('main_experiment_table.csv',main);csvfile('main_energy_components.csv',components)
csvfile('main_original_null_fields.csv',[{'方案ID':v['scheme_id'],'字段':v['field'],'原值':'null','说明':'保留A标记；不补为0'} for v in null_reserves])
mdfile('main_experiment_table.md',[
    '# 表：400 ms固定方案主实验结果','',
    '|方案|完整系统能耗上界 J|最坏连续峰温上界 °C|最坏节点时间均温上界 °C（场景/节点）|方法/后验SAFE|',
    '|---|---:|---:|---:|---|',*main_md,'',
    '同一七方案的原实验计时：','',
    '|方案|方法根耗时 s≈|方法进程 s≈|首次SAFE s≈|最佳SAFE s≈|原后验进程 s≈|MILP名义交付余量 s|',
    '|---|---:|---:|---:|---:|---:|---|',*timing_md,'',
    '表注：七行均为原400 ms独立AB/AC场景、β=1、50°C入口、80°C上限及原auto-L下的完整固定终解；SA101–105全部保留。能耗是按原场景权重聚合的完整系统能耗，包含空闲尾段与温度修正。温度峰值为两场景、四节点连续包络最大上界；时间均温为每个场景/节点对完整400 ms积分后的最大值，不按场景权重平均。',
    '能耗上界按1e-9 J向上舍入，温度上界按1e-6°C向上舍入；CSV同时给出均温向外舍入区间。时间按最近0.001 s近似显示；“首次/最佳SAFE”是同次方法根中的完整SAFE形成时刻，不是终止耗时。方法进程包含启动/收尾，后验另计。所有方法根上限均600 s；MILP名义交付余量为30 s，HEFT/SA六项原delivery_reserve_s=null在CSV仍留空，见[原空字段清单](main_original_null_fields.csv)，未补成0。',
    'SAFE/SAFE指原方法凭证与同评价器独立后验进程均有完整连续安全凭证，不是第二套独立数值实现或硬件实测。此表无全局最优性、普遍胜率或一般性节能结论；保留有限预算和五种子结果的范围。温度均值/峰值为描述指标，原优化目标仍为完整系统能耗。',
    '精确来源：[A结果](../../workpackage_A/A_results.json)、[B均温](../../workpackage_B/B_metrics.json)。本目录[精确字段映射](table_data_exact.json)保存原有理数/十进制端点，来源文件SHA见[派生核查](derivation_checks.json)。输入和候选身份已逐行跨A/B核对。能量分项见[对应细表](main_energy_components.md)。'])
mdfile('main_energy_components.md',[
    '# 主实验能量分项细表','',
    '|方案|基线能耗上界 J|活动能耗上界 J|外部公共能耗上界 J|温度修正上界 J|后验完整能耗上界 J|',
    '|---|---:|---:|---:|---:|---:|',*component_md,'',
    '各列来自A中同一固定候选的原后验凭证，均按场景权重聚合并向上舍入到1e-9 J。显示列分别向上舍入，显示分项之和可略大于显示总量，不替代精确区间求和。主表完整系统能耗来自原方法凭证；本细表来自后验凭证，原两次完整能量区间重叠已在A核查。',
    '精确来源：[A结果](../../workpackage_A/A_results.json)的posterior_weighted_energy_components_J及stored_posterior_energy_interval_J；[精确字段映射](table_data_exact.json)。'])

cycles=[];cycle_md=[];cycle_exact=[]
template_names={'All-H initial':'全H初始模板','Enhanced HEFT final':'增强HEFT终解','MILP final':'MILP终解'}
for row in c:
    ident=row['id'];nodes=[v for v in means if v['id']==ident]
    check(ident+': four exact periodic mean nodes',len(nodes)==4 and len({v['node'] for v in nodes})==4)
    lower=max(F(v['periodic_cycle_mean_lower_degC']) for v in nodes)
    upper=max(F(v['periodic_cycle_mean_upper_degC']) for v in nodes)
    upper_max=next(v['node'] for v in nodes if F(v['periodic_cycle_mean_upper_degC'])==upper)
    envelope=source('workpackage_C/real_run01/'+ident+'/result.json');result=envelope['result']
    check(ident+': exact archived classification',envelope['classification']==result['classification']==row['classification'])
    unsafe=row['classification']=='THERMAL_VIOLATION';witness=result['violation_witness']
    check(ident+': diagnostic energy flag',unsafe==(row['periodic_energy_diagnostic_only']=='True')==result['periodic_energy_is_diagnostic_only'])
    peak=[row['periodic_peak_lower_degC'],row['periodic_peak_upper_degC']]
    check(ident+': csv exact periodic peak matches result',list(map(F,peak))==list(map(F,result['periodic_peak_degC'])))
    conservative=row['all_rounds_conservative_upper_degC']
    check(ident+': conservative is separate safety envelope',not conservative if unsafe else F(conservative)>=F(peak[1]))
    if unsafe:
        check(ident+': actual startup point witness',witness is not None and F(witness['temperature_degC'][0])>80 and result['earlier_rounds_all_safe'])
        check(ident+': first unsafe round consistent',int(row['first_unsafe_round_if_certified'])==witness['round']==result['first_unsafe_round'])
    else:check(ident+': safe all-round upper<=80',F(conservative)<=80 and witness is None)
    first_energy=[row['first_cycle_energy_lower_J'],row['first_cycle_energy_upper_J']]
    steady_energy=[row['periodic_cycle_energy_lower_J'],row['periodic_cycle_energy_upper_J']]
    peak_text=bracket(peak,6);mean_text=bracket([str(lower),str(upper)],6)
    conservative_text='—（无安全界）' if not conservative else bound(conservative,6)
    first_text=bound(first_energy[1],9);steady_text=bound(steady_energy[1],9)
    globaltime='' if not witness else str(F(witness['global_time_s']))
    classification='全轮连续SAFE' if not unsafe else '实际启动超温'
    state_text=classification if not unsafe else f"超温：第{witness['round']}轮@{float(F(globaltime)):.3f}s/{witness['node']}"
    label=template_names[row['template']];short_scene=row['scene'].split('_')[0]
    cycles.append({'配置ID':ident,'模板':label,'场景':short_scene,'周期P_ms':row['period_ms'],'固定模板完成时刻_ms':row['makespan_ms'],
        '周期稳态峰温下界_degC':bound(peak[0],6,False),'周期稳态峰温上界_degC':bound(peak[1],6),'周期稳态峰温上界最大节点':row['periodic_peak_upper_node'],
        '全轮保守安全界上界_degC':None if not conservative else bound(conservative,6),
        '最坏节点周期均温下界_degC':bound(str(lower),6,False),'最坏节点周期均温上界_degC':bound(str(upper),6),'周期均温上界最大节点':upper_max,
        '首轮周期能耗上界_J每周期':first_text,'稳态周期能耗上界_J每周期':steady_text,'能耗仅诊断':unsafe,
        '分类':classification,'原分类':row['classification'],'首个确证超温轮':None if not witness else witness['round'],
        '确证超温全局时刻_s_精确':globaltime,'确证超温节点':'' if not witness else witness['node'],
        '已查启动轮数':row['checked_startup_rounds'],'后验耗时_s_近似':timing(float(row['wall_s'])),'原热核调用次数':row['kernel_calls']})
    cycle_md.append('|'+ '|'.join([label+'/'+short_scene+'/'+row['period_ms'],peak_text+' ('+row['periodic_peak_upper_node']+')',
        conservative_text,mean_text+' ('+upper_max+')',first_text+'/'+steady_text+(' †' if unsafe else ''),state_text,timing(float(row['wall_s']))])+'|')
    cycle_exact.append({'id':ident,'period_ms':row['period_ms'],'scene':row['scene'],'template':row['template'],'periodic_peak_degC':peak,
        'all_rounds_conservative_upper_degC':conservative or None,'worst_node_periodic_time_mean_degC':[str(lower),str(upper)],
        'mean_upper_max_node':upper_max,'first_cycle_energy_J':first_energy,'periodic_cycle_energy_J':steady_energy,
        'periodic_energy_diagnostic_only':unsafe,'violation_witness':witness,'classification':row['classification'],
        'original_posterior_wall_s':row['wall_s'],'sources':{'csv':'workpackage_C/C_cycle_results.csv','node_mean_csv':'workpackage_C/C_cycle_node_mean_temperatures.csv','raw':'workpackage_C/real_run01/'+ident+'/result.json'}})

check('exact main table7 rows',len(main)==7 and [v['方案ID'] for v in main]==IDS)
check('exact periodic table9 rows',len(cycles)==9 and [v['配置ID'] for v in cycles]==[v['id'] for v in c])
check('seven safe and two certified violated configurations',Counter(v['原分类'] for v in cycles)=={'SAFE_ALL_ROUNDS':7,'THERMAL_VIOLATION':2})
csvfile('periodic_supplement_table.csv',cycles)
mdfile('periodic_supplement_table.md',[
    '# 表：九个固定模板周期配置补充结果','',
    '|模板/场景/P(ms)|周期稳态峰温区间 °C（节点）|全轮保守安全界上界 °C|最坏节点周期均温区间 °C（节点）|首轮/稳态周期能耗上界 J/周期|判定与原记录越限见证|后验耗时 s≈|',
    '|---|---|---:|---|---:|---|---:|',*cycle_md,'',
    '表注：这些是给定时间表按P重复的后验周期评价，场景分别运行并继承本场景轮末温度；AB与AC不串接。P为75/80/85/90ms，不是主表400ms评价窗口。首轮从原50°C状态启动；稳态周期采用已包围的固定点入口，二者能耗为J/周期，不与主表400ms加权系统能耗直接相减比较。',
    '稳态峰温是周期极限轨迹的连续峰温包围；全轮保守安全界是启动前缀及尾界组成的安全上界，不是实际峰温估计，也不是稳态峰温的替代值。最坏节点周期均温为max_i(1/P∫T_i dt)，给出原36行四节点均温中最大值的包围；它不等于峰温或多节点平均。',
    '科学区间下端按1e-6°C向下舍入，上端按1e-6°C向上舍入；能耗上界按1e-9 J向上舍入，时间近似到0.001s。完整精确端点、点见证与源映射见[精确字段](table_data_exact.json)。',
    '† 两个超温配置的能耗均仅为诊断量，不作为安全方案能耗或优化性能；“第21/29轮”与时刻来自实际启动下入口路径的有效域内点温度下界>80°C，并结合此前各轮连续安全证明。稳态辅助上/下路径返回的超温数量不等于实际配置数量。SAFE表示给定模板全轮连续安全界成立，无全局最优性或普遍性收益含义。',
    '第21/29轮为原凭证确证的首个违规轮；所列1.575/2.315s是原记录点见证，既不是精确首次穿越，也不一定是更密采样能找到的最早越限点。','',
    '全H初始模板为MILP原始全H时间表(c212a952…04b126)，并非HEFT首次构造(de42dc29…4d356f)。另两模板为封存增强HEFT/MILP终解。',
    '精确来源：[周期结果](../../workpackage_C/C_cycle_results.csv)、[36行节点周期均温](../../workpackage_C/C_cycle_node_mean_temperatures.csv)、[C结论和证明边界](../../workpackage_C/C_summary.md)、[原核辅助轨迹计数说明](../../workpackage_C/C_summary_addendum.md)。逐配置原始result.json的相对路径和SHA记录在[派生核查](derivation_checks.json)。'])

save(OUT/'table_data_exact.json',{'schema':'paper-table-exact-source-map-v1','main':main_exact,'periodic':cycle_exact,
    'rounding':{'temperature_digits':6,'energy_digits':9,'rule':'Each physical lower rounded downward, each upper upward using Fraction integer arithmetic; times approximate nearest0.001s.'},
    'important_original_null_fields':null_reserves,'new_searches':0,'new_thermal_evaluations':0})
record={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-began,
    'passed':True,'main_rows':len(main),'periodic_rows':len(cycles),'energy_component_rows':len(components),'original_null_records':len(null_reserves),
    'source_files':sources,'checks':checks,'assertion_count':len(checks),'all_scientific_displays_outward':True,
    'csv_encoding':'utf-8-sig (UTF-8 with BOM)','sources_modified':False,'new_search_calls':0,'new_thermal_evaluations':0,
    'execution':{'argv':['python','-B',str(Path(__file__).relative_to(REPO))],'cwd':str(REPO),'python':sys.version,'platform':platform.platform()},
    'limits':'Derived presentation only. Original SAFE evidence reused, not independent kernel validation; no general optimization claim; periodic unsafe energy diagnostic.'}
save(OUT/'derivation_checks.json',record);note({'event':'COMPLETE','utc':record['ended_utc'],'main':7,'periodic':9,'checks':len(checks)});log.close()
manifest={p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='tables_manifest.json'}
save(OUT/'tables_manifest.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'files_sha256':manifest,'source_files':sources})
print(json.dumps({'passed':True,'main_rows':7,'periodic_rows':9,'checks':len(checks),'sources':len(sources),'wall_s':time.monotonic()-began},ensure_ascii=False),flush=True)
