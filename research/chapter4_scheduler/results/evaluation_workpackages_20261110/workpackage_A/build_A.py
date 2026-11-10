"""Read-only extraction of the seven explicitly selected archived schedules.

Authoritative bytes come from the specified commit. No optimizer, evaluator,
constructor, model builder, or numerical propagation module is imported.
"""
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

REPO=Path('/workspace/paper')
OUT=Path(__file__).resolve().parent
COMMIT='4339bdcc7dc6d37adf42963ed731f78d5f8ff63e'
IDS=['t50_milp','t50_heft']+[f't50_sa{s}' for s in range(101,106)]
ROOT='research/chapter3_experiments/results/chapter3_closure_execution01'
ANALYSIS='research/chapter3_experiments/results/chapter3_closure_analysis01/summary.json'
PREP='research/chapter3_experiments/results/chapter3_closure_preparation01/t50_full'
started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
sources={};commands=[];checks=[];missing=[]
log=(OUT/'A_log.jsonl').open('x')

def emit(value):
    log.write(json.dumps(value,ensure_ascii=False)+'\n');log.flush()

def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')

def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def check(label,value):
    checks.append({'name':label,'passed':bool(value)})
    if not value:raise AssertionError(label)

def source(path):
    if path in sources:return sources[path]['value']
    argv=['git','show',COMMIT+':'+path];t=time.monotonic()
    proc=subprocess.run(argv,cwd=REPO,capture_output=True)
    commands.append({'argv':argv,'exit_code':proc.returncode,'wall_s':time.monotonic()-t})
    if proc.returncode:
        missing.append({'path':path,'reason':'MISSING_AT_SELECTED_COMMIT'});raise FileNotFoundError(path)
    historical=proc.stdout;current=(REPO/path).read_bytes() if (REPO/path).is_file() else None
    try:value=json.loads(historical);json_value=True
    except (json.JSONDecodeError,UnicodeDecodeError):value=None;json_value=False
    equal=current==historical
    semantic=json_value and current is not None and json.loads(current)==value
    record={'path':path,'specified_commit':COMMIT,'historical_sha256':hashlib.sha256(historical).hexdigest(),
        'current_sha256':hashlib.sha256(current).hexdigest() if current is not None else None,
        'byte_equal':equal,'json_semantic_equal':semantic if json_value else None,
        'size_bytes':len(historical),'value':value,'historical_bytes':historical}
    sources[path]=record;emit({k:v for k,v in record.items() if k not in ('value','historical_bytes')})
    check('specified commit matches current bytes: '+path,equal)
    return value

def interval(value):return [F(value[0]),F(value[1])]

def write_csv(name,rows):
    with (OUT/name).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

summary=source(ANALYSIS);plan=source('research/chapter3_experiments/results/chapter3_closure_preparation01/plan.json')
base=source(PREP+'/input_instance.json');config=source(PREP+'/input_config.json')
input_sha=canonical(base);config_sha=canonical(config)
check('400ms full window',base['window_ms']=='400')
check('exact AB AC scenario membership',[s['id'] for s in base['scenarios']]==['AB_offset_0ms','AC_offset_0ms'])
check('six executions and independent scenes',sum(len(s['stage_instances']) for s in base['scenarios'])==6 and 'independent' in base['execution_rules']['scenario_entry'])
check('fixed50C/80C',all(s['entry']['temperature_degC']==['50']*4 and s['maximum_temperature_degC']==['80']*4 for s in base['scenarios']))
check('original auto-L',base['execution_rules'].get('idle_policy')=='auto_low_immediate_v1')
check('weights sum1',sum(F(s['weight']) for s in base['scenarios'])==1)
check('specified plan subject',summary['execution_subject_commit']=='a30d0c6d778924eea252f2033c18b78282f99147')
(OUT/'fixed_input_instance.json').write_bytes(sources[PREP+'/input_instance.json']['historical_bytes'])
(OUT/'fixed_input_config.json').write_bytes(sources[PREP+'/input_config.json']['historical_bytes'])
(OUT/'fixed_schedules').mkdir(exist_ok=False)
rows=[];csv_rows=[];schedule_rows=[];peak_rows=[];energy_rows=[];initial_candidates={}
for scheme in IDS:
    method=f'{ROOT}/slots/{scheme}__method/worker'
    paths={'raw':method+'/raw_result.json','input':method+'/method/input_instance.json',
        'config':method+'/method/input_config.json','post':f'{ROOT}/slots/{scheme}__post/worker/post_result.json',
        'method_slot':f'{ROOT}/slots/{scheme}__method/slot_result.json','post_slot':f'{ROOT}/slots/{scheme}__post/slot_result.json'}
    raw=source(paths['raw']);instance=source(paths['input']);conf=source(paths['config']);post=source(paths['post'])
    method_slot=source(paths['method_slot']);post_slot=source(paths['post_slot'])
    archived=next(x for x in summary['methods'] if x['id']==scheme)
    candidate=raw['safe_candidate'];candidate_sha=canonical(candidate);evaluation=raw['evaluation'];posterior=post['evaluation']
    check(scheme+': exact common instance/config',instance==base and conf==config)
    check(scheme+': archived candidate exact',candidate==archived['final_candidate'])
    identity={'input_sha256':input_sha,'candidate_sha256':candidate_sha}
    check(scheme+': method/post evidence identities',evaluation['evidence_identity']==posterior['evidence_identity']==identity)
    check(scheme+': method and post SAFE',evaluation['state']==posterior['state']==post['state']=='SAFE' and post['same_candidate'] and post['safe']['preserved'])
    lo,hi=interval(evaluation['weighted_energy_J']);plo,phi=interval(posterior['weighted_energy_J'])
    check(scheme+': method/post energy overlap',max(lo,plo)<=min(hi,phi))
    for scene in base['scenarios']:
        sid=scene['id'];receipt=posterior['scenes'][sid]
        check(scheme+': full400ms '+sid,receipt['complete'] and receipt['state']=='SAFE' and F(receipt['covered_until_s'])==F(2,5))
        check(scheme+': four nodes '+sid,set(receipt['peaks_degC'])==set(base['platform']['node_order']))
        for node,bound in receipt['peaks_degC'].items():
            check(scheme+': continuous peak upper safe '+sid+'/'+node,F(bound[1])<=80)
            peak_rows.append({'scheme_id':scheme,'scene_id':sid,'node':node,'peak_lower_degC':bound[0],'peak_upper_degC':bound[1],
                'minimum_lower_degC':receipt['minimum_degC'][node][0],'minimum_upper_degC':receipt['minimum_degC'][node][1],
                'source':paths['post'],'source_pointer':'/evaluation/scenes/'+sid,'continuous_certificate_state':receipt['state']})
        for item in posterior['legality']['scenes'][sid]['rows']:
            schedule_rows.append({'scheme_id':scheme,'scene_id':sid,**{k:item.get(k) for k in ['stage_id','shared_stage_id','request_id','unit','opp','domain_id','thermal_node_id','start_ms','end_ms','duration_ms','activity_power_W','release_ms','deadline_ms']}})
            check(scheme+': exact start duration end '+item['stage_id'],F(item['start_ms'])+F(item['duration_ms'])==F(item['end_ms']))
    weights={s['id']:F(s['weight']) for s in base['scenarios']}
    weighted={key:[str(sum(weights[sid]*F(receipt['energy_components_J'][key][j]) for sid,receipt in posterior['scenes'].items())) for j in (0,1)]
        for key in ('baseline','activity','external_common','temperature_correction')}
    for key,bounds in weighted.items():energy_rows.append({'scheme_id':scheme,'component':key,'lower_J':bounds[0],'upper_J':bounds[1],'source':paths['post']})
    method_bound=evaluation['weighted_energy_J']
    max_peak=max(F(v[1]) for s in posterior['scenes'].values() for v in s['peaks_degC'].values())
    timing_keys=['method_budget_s','delivery_reserve_s','total_method_wall_s','method_root_s','first_safe_s','best_safe_s','first_planning_SAFE_s','best_planning_SAFE_s','post_wall_s','SAFE_time_scope']
    timing={k:archived.get(k) for k in timing_keys}
    for key,value in timing.items():
        if value is None:missing.append({'scheme_id':scheme,'field':key,'reason':'ARCHIVED_FIELD_NULL_NOT_INFERRED'})
    row={'id':scheme,'method':archived['method'],'seed':archived['seed'],'problem_id':base['id'],
        'source_commit':COMMIT,'paths':paths,'raw_file_sha256':sources[paths['raw']]['historical_sha256'],
        'input_file_sha256':sources[paths['input']]['historical_sha256'],'input_canonical_sha256':input_sha,
        'prepared_input_file_sha256':sources[PREP+'/input_instance.json']['historical_sha256'],'config_canonical_sha256':config_sha,
        'candidate_sha256':candidate_sha,'candidate':candidate,'method_state':raw['state'],'method_reason':raw['reason'],
        'execution_status':archived['execution_status'],'post_state':post['state'],'post_execution_status':archived['post_execution_status'],
        'stored_method_energy_interval_J':method_bound,'stored_method_upper_J':raw['safe_upper_bound_J'],
        'stored_posterior_energy_interval_J':posterior['weighted_energy_J'],'posterior_weighted_energy_components_J':weighted,
        'maximum_posterior_peak_upper_degC':str(max_peak),'timing':timing,'new_search_calls':0,'new_thermal_evaluations':0,
        'physical_source':'Existing posterior receipt; method energy and timings retained separately'}
    rows.append(row)
    csv_rows.append({'id':scheme,'method':archived['method'],'seed':archived['seed'],'input_canonical_sha256':input_sha,
        'candidate_sha256':candidate_sha,'method_energy_lower_J':method_bound[0],'method_energy_upper_J':method_bound[1],
        'display_method_upper_J':float(F(method_bound[1])),'posterior_energy_lower_J':posterior['weighted_energy_J'][0],
        'posterior_energy_upper_J':posterior['weighted_energy_J'][1],'maximum_posterior_peak_upper_degC':str(max_peak),
        'continuous_SAFE':True,'execution_status':archived['execution_status'],**{k:timing[k] for k in timing_keys if k!='SAFE_time_scope'},'raw_path':paths['raw'],'post_path':paths['post']})
    save(OUT/'fixed_schedules'/f'{scheme}.json',{'scheme_id':scheme,'source_commit':COMMIT,'input_canonical_sha256':input_sha,
        'config_canonical_sha256':config_sha,'candidate_sha256':candidate_sha,'candidate':candidate,
        'original_method_receipt':evaluation,'posterior_receipt':posterior,'source_paths':paths,
        'reuse_only':'Saved archive payload; no replay, optimization, repair or changed input'})
    if scheme=='t50_milp':initial_candidates['MILP_all_H_template']={'candidate':raw['initialisation']['witness']['candidate'],'energy_upper_J':raw['initial_safe_upper_bound_J'],'pointer':paths['raw']+'#/initialisation/witness/candidate'}
    else:
        first=raw['evaluations'][0]
        initial_candidates[scheme+'_first_construction']={'candidate':first['candidate'],'energy_interval_J':first['evaluation']['weighted_energy_J'],'source':first['source'],'pointer':paths['raw']+'#/evaluations/0/candidate'}
for value in initial_candidates.values():
    value['candidate_sha256']=canonical(value['candidate']);value['opp_counts']=dict(Counter(x['opp'] for rows_ in value['candidate']['scenes'].values() for x in rows_))
check('MILP H-template differs from HEFT first construction',initial_candidates['MILP_all_H_template']['candidate_sha256']!=initial_candidates['t50_heft_first_construction']['candidate_sha256'])
check('all SA initial constructions match HEFT first',all(initial_candidates[f't50_sa{s}_first_construction']['candidate_sha256']==initial_candidates['t50_heft_first_construction']['candidate_sha256'] for s in range(101,106)))
initial={'initials':initial_candidates,'identities_not_interchangeable':True,
    'interpretation':'All-H describes OPPs only. MILP template, HEFT first construction and improved HEFT final are distinct schedules. AB A.main/B.main ordering differs between first two.'}
save(OUT/'initial_identity_comparison.json',initial)
source_rows=[{k:v for k,v in record.items() if k not in ('value','historical_bytes')} for record in sources.values()]
save(OUT/'source_index.json',{'source_commit':COMMIT,'sources':source_rows})
write_csv('source_index.csv',source_rows);write_csv('A_results.csv',csv_rows);write_csv('A_complete_schedules.csv',schedule_rows)
write_csv('A_peak_temperatures.csv',peak_rows);write_csv('A_energy_components.csv',energy_rows)
result={'schema':'workpackage-A-selected-seven-fixed-archive-v1','source_commit':COMMIT,'specified_selection':IDS,
    'all_sources_byte_equal_current':all(r['byte_equal'] for r in source_rows),'input_canonical_sha256':input_sha,
    'config_canonical_sha256':config_sha,'prepared_input_file_sha256':sources[PREP+'/input_instance.json']['historical_sha256'],
    'rows':rows,'missing_or_null_fields':missing,'checks':checks,'checks_passed':all(c['passed'] for c in checks),
    'new_search_calls':0,'new_thermal_evaluations':0,'scope':'Exactly specified seven final schemes;400ms independently reset AB/AC, beta1,50C/80C. Existing full continuous SAFE evidence reused; no hardware or independent numerical claim.'}
save(OUT/'A_results.json',result)
lines=['# 工作包A：七份固定方案来源与结果整理','',f'来源提交 `{COMMIT}`；七份为附件明确指定的50°C完整MILP、HEFT及SA101–105终解。只读取既有记录，新增搜索/热评价均0。','',
    f'所有{len(source_rows)}份源文件均从指定提交读取，并与当前文件逐字节相等；JSON语义也相等。共同输入为AB/AC独立场景、各3次执行，共6次；400ms全窗口、β1.0、50/80°C、5ms起点和原auto-L均保持。', '',
    '|方案|完整能耗上界 J|后验峰温上界 °C|首次SAFE s|最佳SAFE s|方法进程 s|后验进程 s|',
    '|---|---:|---:|---:|---:|---:|---:|']
for row in rows:
    t=row['timing'];lines.append(f"|{row['id']}|{float(F(row['stored_method_upper_J'])):.12f}|{float(F(row['maximum_posterior_peak_upper_degC'])):.9f}|{t['first_safe_s']}|{t['best_safe_s']}|{t['total_method_wall_s']}|{t['post_wall_s']}|")
lines+=['','SA五种子全部保留，不以最优种子代替一次方法。所有方法及原80°C后验完整SAFE；均无全局最优证明。MILP与SA的600秒预算及HEFT自然结束的实际耗时保留，首次/最佳SAFE不是进程结束时间。', '',
    '## 身份与证据口径','',
    f'运行实例canonical SHA256 `{input_sha}`；准备输入文件字节SHA256 `{sources[PREP+"/input_instance.json"]["historical_sha256"]}`。两种哈希编码对象不同，数值不同不代表科学输入漂移。七份运行实例/config逐字典完全一致。','',
    f'原MILP全H模板 `{initial_candidates["MILP_all_H_template"]["candidate_sha256"]}`，初始上界1.042737729699 J；HEFT首次构造 `{initial_candidates["t50_heft_first_construction"]["candidate_sha256"]}`，首次上界1.042838516887 J。两者均6个H但AB NPU次序不同：前者A.main10ms/B.main40ms，后者A.main35ms/B.main0ms。增强HEFT终解也不同于二者。SA五种子的首次构造分别与HEFT首构造相同，不能混称MILP模板或增强HEFT终解。完整身份及时间表见 `initial_identity_comparison.json`。','',
    '原方法能量区间和耗时保留为方法指标；各节点峰温、温度积分、能量分项引用已有同评价器后验凭证，两次区间重叠已核对。后验不是独立数值实现。峰温是连续包络证据，trace仅为已有分段末点，不把插值图当连续峰温证明。','',
    '## 产物与缺项','',
    '`source_index.json/csv`逐文件保存指定提交和当前字节SHA、语义相等性；`A_results.json/csv`保存身份、完整能量与计时；`A_complete_schedules.csv`保存42条精确时间表及结束时刻；`A_peak_temperatures.csv`保存56个场景/节点峰温和最小温度区间；`A_energy_components.csv`保存28个加权分项。`fixed_schedules/`保存七份候选及原方法/后验完整凭证，`fixed_input_*.json`是指定提交准备输入的原字节副本。','',
    f'缺项/空字段共{len(missing)}条，逐项见 `A_results.json.missing_or_null_fields`；不把不适用的MILP交付余量或未记录字段猜成0。来源或关键科学字段缺失会停止，当前全部关键字段存在。', '',
    f'本次{len(checks)}条身份/覆盖/区间/时间表等只读断言通过。所有温度和能量均为原模型内数值证据，不是实测；不改旧结果、不推送或合并。工作包C/B另外执行，A不预先声称完成。','']
with (OUT/'A_summary.md').open('x') as stream:stream.write('\n'.join(lines))
ended=datetime.now(timezone.utc).isoformat()
save(OUT/'A_execution_record.json',{'started_utc':started,'ended_utc':ended,'wall_s':time.monotonic()-clock,
    'argv':['python','-B',str(Path(__file__).relative_to(REPO))],'cwd':str(REPO),'python':sys.version,'platform':platform.platform(),
    'actual_read_commands':commands,'source_commit':COMMIT,'source_file_count':len(sources),'fixed_schemes':7,'schedule_rows':len(schedule_rows),
    'peak_rows':len(peak_rows),'new_search_calls':0,'new_thermal_evaluations':0,'passed':True})
emit({'event':'COMPLETE','utc':ended,'schemes':7,'checks':len(checks),'missing_or_null':len(missing)});log.close()
manifest={p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='A_manifest.json'}
save(OUT/'A_manifest.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'source_commit':COMMIT,'file_sha256':manifest})
print(json.dumps({'passed':True,'schemes':7,'sources_verified':len(sources),'checks':len(checks),'schedule_rows':len(schedule_rows),
    'peak_rows':len(peak_rows),'missing_or_null_fields':len(missing),'wall_s':time.monotonic()-clock},ensure_ascii=False))
