"""K173 independent terminal-only stored analysis; standard library only.

--inspect-slot reads one completed slot without creating a final analysis.
Final outputs require the authoritative batch_terminal.json and a fresh out.
"""
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys


ROOT=Path(__file__).resolve().parents[5]
BATCH=Path(__file__).resolve().parent.parent
HASHES={}
WARNINGS=[]
GUARD={'scientific_import':0,'scientific_code_entry':0,'process_launch':0}


class GuardViolation(BaseException):pass


def audit(event,args):
    if event=='import' and args[0].split('.')[-1] in {'numpy','scipy','milp','thermal','inputs',
        'matlab_bridge','schedules','initial_point','initial_schedule','neighborhood_method',
        'linked_method','worker','post_worker'}:
        GUARD['scientific_import']+=1;raise GuardViolation('forbidden scientific import')
    if event=='subprocess.Popen' or event=='os.system' or event.startswith('os.spawn'):
        GUARD['process_launch']+=1;raise GuardViolation('forbidden process')


def profile(frame,event,arg):
    if event=='call':
        filename=frame.f_code.co_filename.replace('\\','/')
        if '/research/chapter3_experiments/' in filename and '/results/' not in filename:
            GUARD['scientific_code_entry']+=1;raise GuardViolation('forbidden scientific code')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read(path,optional=False):
    path=Path(path)
    if not path.is_file():
        if optional:return {}
        raise FileNotFoundError(path)
    data=path.read_bytes();HASHES[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(data).hexdigest()
    try:return json.loads(data)
    except (ValueError,UnicodeDecodeError) as error:
        if not optional:raise
        WARNINGS.append({'path':str(path),'read_error':str(error),'raw_hash_preserved':True})
        return {}


def number(v):
    if isinstance(v,bool) or v is None:return None
    try:return float(F(str(v)))
    except (ValueError,TypeError,ZeroDivisionError):return None


def duration(start,end):
    a,b=number(start),number(end)
    return None if a is None or b is None else b-a


def interval(v):
    if not isinstance(v,list) or len(v)!=2:return None
    try:
        a,b=map(F,v)
        return (a,b) if 0<=a<=b else None
    except (ValueError,TypeError,ZeroDivisionError):return None


def phase_records(result,variant):
    phases=result.get('phases')
    if isinstance(phases,list) and phases:return [p for p in phases if isinstance(p,dict)]
    if result and variant=='A':
        timing=result.get('timing') or {}
        return [{'phase_index':1,'name':'single_N1','synthetic_record':True,
            'started_at_s':timing.get('invocation_started_at_s'),
            'completed_at_s':timing.get('invocation_stopped_at_s',timing.get('method_elapsed_s')),
            'condition':result.get('condition') or {},'scenes':result.get('scenes') or {}}]
    return []


def update_phase(update,variant,phases):
    value=update.get('phase_index')
    if type(value) is int and value in (0,1,2):return value,'explicit'
    if variant=='A':return 1,'implicit_single_N1'
    stamp=number(update.get('committed_at_s'))
    if stamp is not None:
        first=next((number(p.get('started_at_s')) for p in phases if p.get('phase_index')==1),None)
        if first is not None and stamp<first:return 0,'inferred_seed_before_phase1'
        matches=[p.get('phase_index') for p in phases if type(p.get('phase_index')) is int
            and number(p.get('started_at_s')) is not None and number(p.get('completed_at_s')) is not None
            and number(p['started_at_s'])<=stamp<=number(p['completed_at_s'])]
        if len(matches)==1:return matches[0],'inferred_from_saved_phase_time'
    return None,'unresolved_original_null_or_missing'


def native_timing(folder):
    native=folder/'method/matlab';rows=[]
    session=read(native/'session.json',optional=True);closed=read(native/'closed.json',optional=True)
    prefixes=sorted({p.name.split('.')[0] for pattern in ('request_*.python.json','request_*.response.json') for p in native.glob(pattern)})
    for prefix in prefixes:
        py=read(native/(prefix+'.python.json'),optional=True)
        raw=read(native/(prefix+'.response.json'),optional=True)
        n=raw or py
        phase=n.get('phase_seconds') or {}
        admitted=(py.get('status')=='SOLVED' and py.get('budget_valid') is True)
        rows.append({'request_prefix':prefix,'request_number':py.get('request_number'),
            'python_status':py.get('status'),'python_budget_valid':py.get('budget_valid'),
            'raw_native_status':raw.get('status'),'native_response_exists':bool(raw),
            'timing_only_late_or_unadmitted':not admitted,
            'native_intlinprog_s':phase.get('intlinprog_call'),
            'native_load_s':phase.get('request_and_mat_load'),
            'native_option_preparation_s':phase.get('options_preparation'),
            'native_archive_s':phase.get('native_result_archive'),
            'native_request_wall_s':n.get('matlab_request_wall_seconds'),
            'python_transport_wall_s':py.get('wall_seconds'),
            'solver_max_time_declared_s':n.get('solver_max_time_s_declared'),
            'solver_max_time_allocated_s':n.get('solver_max_time_s_allocated'),
            'solver_max_time_used_s':n.get('solver_max_time_s_used'),
            'native_timing_is_not_new_candidate_or_U':True})
    known=[number(x['native_intlinprog_s']) for x in rows if number(x['native_intlinprog_s']) is not None]
    admitted=[number(x['native_intlinprog_s']) for x in rows if not x['timing_only_late_or_unadmitted'] and number(x['native_intlinprog_s']) is not None]
    return {'session_startup_s':session.get('startup_wall_seconds'),
        'cleanup_s':closed.get('cleanup_wall_seconds'),'cleanup_status':closed.get('cleanup_status'),
        'native_intlinprog_observed_total_s':sum(known) if known else None,
        'native_intlinprog_python_in_budget_views_s':sum(admitted) if admitted else None,
        'native_request_count':len(rows),'native_timing_missing_count':sum(number(x['native_intlinprog_s']) is None for x in rows),
        'requests':rows,'scope':'native request timings include late cleanup-time raw responses; never admit their candidate or U'}


def extract_slot(batch,slot):
    folder=batch/'calls'/slot['slot_id'];a=read(folder/'audit.json',True);result=read(folder/'result.json',True)
    pa=read(folder/'post_audit.json',True);pr=read(folder/'post_return.json',True)
    wi=read(folder/'worker_identity.json',True);wr=read(folder/'worker_return.json',True)
    mp=read(folder/'method_process.json',True);pp=read(folder/'post_process.json',True)
    timing=result.get('timing') or {};exclusive=timing.get('phases_exclusive_s') or {}
    phases=phase_records(result,slot['variant']);updates=[]
    for index,u in enumerate(result.get('global_updates') or []):
        if not isinstance(u,dict):continue
        phase,normalisation=update_phase(u,slot['variant'],phases)
        updates.append({'update_index':index,'phase_index_original':u.get('phase_index'),
            'phase_index_field_present':'phase_index' in u,'phase_index':phase,
            'phase_normalisation':normalisation,'formed_at_s':u.get('committed_at_s'),
            'transferred_at_s':u.get('transferred_at_s'),'U_J':u.get('safe_upper_bound_J'),
            'energy_J':u.get('weighted_energy_J'),'strict_improvement_original':u.get('strict_energy_improvement_certified')})
    seed=a.get('initial_seed') or {};seed_i=interval(seed.get('energy_J'))
    build_frames=[(i,v) for i,v in enumerate(timing.get('phase_records') or []) if v.get('phase')=='model_construction']
    phase_details=[]
    for p in phases:
        index=p.get('phase_index');end=number(p.get('completed_at_s'))
        prior=[u for u in updates if type(u['phase_index']) is int and type(index) is int
            and u['phase_index']<=index and number(u['formed_at_s']) is not None
            and 0<=number(u['formed_at_s'])<300 and (end is None or number(u['formed_at_s'])<=end)]
        last=prior[-1] if prior else None;condition=p.get('condition') or {};scenes=[];closed=[]
        fixed=condition.get('warm_options_by_scene') or condition.get('seed_options_by_scene') or {}
        opened=condition.get('opened_by_scene') or {}
        for sid,by_copy in fixed.items():
            for copy,row in by_copy.items():
                if copy not in (opened.get(sid) or []):closed.append({'scene_id':sid,'stage_id':copy,**row})
        for sid,s in (p.get('scenes') or {}).items():
            summary=s.get('model_summary') or {};pre=s.get('preprocessing') or {};construction=s.get('construction') or {}
            completed=number(s.get('model_completed_at_s'))
            candidates=[(abs(number(f.get('end_s'))-completed),i,f) for i,f in build_frames
                        if completed is not None and number(f.get('end_s')) is not None]
            matched=min(candidates,key=lambda z:z[0]) if candidates else None
            if matched is not None and matched[0]>.05:matched=None
            anchor=pre.get('closed_anchor_preelimination') or {}
            initial=s.get('initialisation') or {}
            scenes.append({'scene_id':sid,'options':summary.get('options'),'variables':summary.get('variables'),
                'binary_variables':summary.get('binary_variables'),'logical_binary_variables':summary.get('logical_binary_variables'),
                'rows':summary.get('rows'),'events_per_scene':summary.get('events_per_scene'),
                'model_completed_at_s':s.get('model_completed_at_s'),
                'build_phase_record_index':None if matched is None else matched[1],
                'build_wall_s':None if matched is None else matched[2].get('wall_s'),
                'build_exclusive_s':None if matched is None else matched[2].get('exclusive_s'),
                'observer_stage_times_s':construction.get('phase_wall_seconds'),
                'construction_nonzeros':construction.get('nonzeros_in_rows'),
                'search_started_at_s':s.get('search_started_at_s'),'search_returned_at_s':s.get('search_returned_at_s'),
                'search_wall_s':duration(s.get('search_started_at_s'),s.get('search_returned_at_s')),
                'scene_slice_s':s.get('scene_slice_s'),'reason':s.get('reason'),
                'closed_anchor_filter':{k:anchor.get(k) for k in ('before','after','removed','input_options_sha256','output_options_sha256','by_scene_stage')},
                'actual_x0_source':initial.get('source'),'actual_x0_snapshot_hash':initial.get('snapshot_candidate_sha256'),
                'actual_x0_local_candidate_hash':canonical(initial['candidate']) if isinstance(initial.get('candidate'),dict) else None,
                'x0_injected':s.get('x0_injected')})
        phase_details.append({'phase_index':index,'name':p.get('name'),'synthetic_record':p.get('synthetic_record',False),
            'started_at_s':p.get('started_at_s'),'completed_at_s':p.get('completed_at_s'),
            'wall_s':duration(p.get('started_at_s'),p.get('completed_at_s')),
            'U_after_J':None if last is None else last['U_J'],
            'energy_after_J':None if last is None else last['energy_J'],
            'best_update_source_index':None if last is None else last['update_index'],
            'warm_candidate_hash':condition.get('warm_candidate_sha256'),
            'condition_sha256':condition.get('condition_sha256'),'closed_labels':closed,
            'closed_labels_sha256':canonical(sorted(closed,key=lambda z:(z['scene_id'],z['stage_id']))) if closed else None,
            'opened_by_scene':opened,'scenes':scenes})
    native=native_timing(folder)
    method_ok=(a.get('passed') is True and a.get('eligible_for_post') is True
        and mp.get('returncode')==0 and mp.get('watchdog_stop') is None)
    post_ok=(pa.get('passed') is True and pa.get('new_U') is False and pr.get('passed') is True
        and pp.get('returncode')==0 and pp.get('watchdog_stop') is None)
    admitted=a.get('usable_U_J') if method_ok and post_ok else None
    if admitted is not None and pa.get('comparison_eligible_U_J')!=admitted:
        WARNINGS.append({'slot_id':slot['slot_id'],'error':'method/post eligible U mismatch'});admitted=None
    energy=result.get('weighted_energy_J') if admitted is not None else None
    strict=[number(u['formed_at_s']) for u in updates if seed_i and interval(u['energy_J'])
        and interval(u['energy_J'])[1]<seed_i[0] and number(u['formed_at_s']) is not None
        and number(u['formed_at_s'])<300]
    p1=next((p for p in phase_details if p['phase_index']==1),{})
    p2=next((p for p in phase_details if p['phase_index']==2),{})
    row={'slot_id':slot['slot_id'],'case_id':slot['case_id'],'variant':slot['variant'],
        'classification':a.get('classification','MISSING_AUDIT'),'state':result.get('state'),
        'method_audit_passed':a.get('passed'),'post_audit_passed':pa.get('passed'),
        'reported_U_J':result.get('safe_upper_bound_J'),'verified_method_U_J':a.get('usable_U_J'),
        'comparison_U_J':admitted,'comparison_energy_J':energy,
        'root_actual_s':timing.get('method_elapsed_s'),'root_overshoot_s':timing.get('deadline_overshoot_s'),
        'cleanup_s':timing.get('cleanup_s'),'cleanup_native_record_s':native['cleanup_s'],
        'method_process_wall_s':mp.get('process_wall_seconds'),
        'worker_dispatch_inclusive_s':wr.get('method_elapsed_s'),
        'worker_root_until_entry_return_s':wi.get('wrapper_root_elapsed_at_method_return_s'),
        'worker_archival_s':wr.get('wrapper_archival_elapsed_s'),
        'common_support_import_s':wi.get('common_support_import_elapsed_s'),
        'arm_specific_import_s':exclusive.get('worker_selected_arm_imports'),
        'MATLAB_startup_s':exclusive.get('solver_startup'),'MATLAB_session_startup_s':native['session_startup_s'],
        'native_intlinprog_observed_total_s':native['native_intlinprog_observed_total_s'],
        'native_intlinprog_python_in_budget_views_s':native['native_intlinprog_python_in_budget_views_s'],
        'native_request_count':native['native_request_count'],'native_timing_missing_count':native['native_timing_missing_count'],
        'first_SAFE_s':result.get('first_safe_at_s'),'first_strict_improvement_s':min(strict) if strict else None,
        'seed_label_hash':seed.get('candidate_sha256'),'seed_U_J':seed.get('U_J'),'seed_energy_J':seed.get('energy_J'),
        'phase1_U_J':p1.get('U_after_J'),'phase2_U_J':p2.get('U_after_J'),
        'phase1_wall_s':p1.get('wall_s'),'phase2_wall_s':p2.get('wall_s'),
        'phase2_entered':bool(p2),'phase2_anchor_hash':p2.get('warm_candidate_hash'),
        'phase2_closed_labels_hash':p2.get('closed_labels_sha256'),
        'post_evaluation_s':pr.get('evaluation_elapsed_s'),'post_return_wall_s':pr.get('return_wall_s'),
        'post_process_wall_s':pp.get('process_wall_seconds')}
    return {'slot':slot,'row':row,'phases':phase_details,'updates':updates,
        'native':native,'timing_exclusive':exclusive,'original_reason':result.get('reason'),
        'pending_last_request':a.get('pending_last_request'),'method_hard_errors':a.get('hard_errors'),
        'method_aggregate_issues':a.get('aggregate_issues'),'post_issues':pa.get('issues')}


def write_csv(path,rows):
    columns=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('x',encoding='utf-8-sig',newline='') as stream:
        out=csv.DictWriter(stream,fieldnames=columns);out.writeheader()
        for row in rows:out.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def display(value,digits=9):
    v=number(value)
    return '—' if v is None else f'{v:.{digits}f}'


def analyse(batch,output):
    if output.exists():raise FileExistsError('final analysis is append-only')
    terminal=read(batch/'batch_terminal.json')
    if terminal.get('state') in (None,'DECLARED','RUNNING'):raise ValueError('authoritative batch terminal required')
    declaration=read(batch/'declaration.json');ledger=read(batch/'ledger.json')
    details=[extract_slot(batch,s) for s in declaration['slots']]
    rows=[v['row'] for v in details];pairs=[]
    for case in ('base__R1','base__R3'):
        by_arm={v['row']['variant']:v['row'] for v in details if v['row']['case_id']==case}
        seeds=[v['seed_label_hash'] for v in by_arm.values()]
        same_seed=len(seeds)==3 and all(seeds) and len(set(seeds))==1
        b,c=by_arm.get('B',{}),by_arm.get('C',{})
        same_anchor=bool(b.get('phase2_anchor_hash') and b['phase2_anchor_hash']==c.get('phase2_anchor_hash'))
        comparisons=[]
        for left,right in (('A','B'),('B','C'),('A','C')):
            x,y=by_arm.get(left,{}),by_arm.get(right,{})
            a,z=interval(x.get('comparison_energy_J')),interval(y.get('comparison_energy_J'))
            state=('MISSING_ACCEPTED_PAIR' if a is None or z is None else right+'_STRICTLY_LOWER' if z[1]<a[0]
                else left+'_STRICTLY_LOWER' if a[1]<z[0] else 'OVERLAPPING_INTERVALS')
            comparisons.append({'left':left,'right':right,'state':state})
        pairs.append({'case_id':case,'same_fresh_seed_labels':same_seed,'B_C_same_full_warm_anchor':same_anchor,
            'B_C_same_closed_labels':bool(b.get('phase2_closed_labels_hash') and b['phase2_closed_labels_hash']==c.get('phase2_closed_labels_hash')),
            'comparisons':comparisons,'attribution_scope':'same saved full anchor' if same_anchor else 'end-to-end calls; not isolated same-anchor preelimination'})
    after={name:sha(ROOT/name) for name in HASHES}
    unchanged=after==HASHES
    facts={'protocol':'K173-independent-readonly-final-v1','terminal':terminal,'ledger_state':ledger.get('state'),
        'rows':rows,'details':details,'pairs':pairs,'read_before_sha256':dict(HASHES),
        'read_after_sha256':after,'read_files_unchanged':unchanged,'warnings':WARNINGS,
        'guard':GUARD,'models':0,'solver_calls':0,'thermal_or_post_calls':0,'new_candidate_or_U':0}
    if not unchanged:raise ValueError('read artifacts changed during final analysis')
    output.mkdir(parents=True,exist_ok=False)
    (output/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    write_csv(output/'results6.csv',rows)
    write_csv(output/'phases.csv',[{'slot_id':v['row']['slot_id'],**{k:p[k] for k in p if k!='scenes'}} for v in details for p in v['phases']])
    write_csv(output/'models.csv',[{'slot_id':v['row']['slot_id'],'phase_index':p['phase_index'],**s} for v in details for p in v['phases'] for s in p['scenes']])
    write_csv(output/'native_requests.csv',[{'slot_id':v['row']['slot_id'],**n} for v in details for n in v['native']['requests']])
    write_csv(output/'safe_updates.csv',[{'slot_id':v['row']['slot_id'],**u} for v in details for u in v['updates']])
    lines=['# K173六槽终态独立只读汇总','',
        f"终态{terminal['state']}；已消费{terminal.get('consumed')}/6，方法预留{terminal.get('reserved_method_budget_s')}s，post消费{terminal.get('post_consumed')}。缺失不填0。",'',
        '|题目|臂|终态分类|post可比较U/J|根实耗/s|清理/s|MATLAB启动/s|native求解观测/s|',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for x in rows:lines.append('|'+ '|'.join([x['case_id'],x['variant'],x['classification'],display(x['comparison_U_J']),display(x['root_actual_s'],3),display(x['cleanup_s'],3),display(x['MATLAB_startup_s'],3),display(x['native_intlinprog_observed_total_s'],3)])+'|')
    lines+=['','|题目|臂|S0 U/J|P1后U/J|P2后U/J|P1时长/s|P2时长/s|首严格改善/s|',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for x in rows:lines.append('|'+ '|'.join([x['case_id'],x['variant'],display(x['seed_U_J']),display(x['phase1_U_J']),display(x['phase2_U_J']),display(x['phase1_wall_s'],3),display(x['phase2_wall_s'],3),display(x['first_strict_improvement_s'],3)])+'|')
    lines+=['','根实耗、清理、子进程总时长与native intlinprog耗时分别记录，存在嵌套／重叠，不能相加当方法时长。native观测总量可包含预算后才归档的response，仅读其时间，绝不据其x补SAFE或U。每request的预算接纳状态与时间证据见native_requests.csv。','',
        'A原记录没有phases且更新可能缺／空phase_index，按单N1标1；B／C仅用明确阶段或可唯一定位的原时间作标注，原空值仍保留，不能比较None与整数。未进入第二阶段与进入后未更新U分开。','']
    for pair in pairs:lines.append(f"- {pair['case_id']}：同fresh seed={pair['same_fresh_seed_labels']}；B/C同完整warm锚={pair['B_C_same_full_warm_anchor']}；同关闭标签={pair['B_C_same_closed_labels']}；{pair['attribution_scope']}。")
    lines+=['','A/B比较搜索组织，B/C按冻结的同锚归因边界；两题单次开发调用不构成总体／稳定性排名。历史HEFT不进入这六槽配对。模型规模／构模时间、关闭标签、实际x0来源及安全U更新均见facts和分表。','',
        f"读取证据hash前后不变={unchanged}；只读警告数={len(WARNINGS)}；科学调用全部0。"]
    (output/'summary.md').write_text('\n'.join(lines)+'\n','utf-8')
    print(json.dumps({'terminal_analysis':str(output),'comparison_eligible':sum(v['comparison_U_J'] is not None for v in rows),
        'new_scientific_calls':0,'warnings':len(WARNINGS)},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path,default=BATCH)
    parser.add_argument('--out',type=Path);parser.add_argument('--inspect-slot');args=parser.parse_args()
    HASHES[str(Path(__file__).relative_to(ROOT)).replace('\\','/')]=sha(Path(__file__))
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        if args.inspect_slot:
            declaration=read(args.batch/'declaration.json')
            slot=next(s for s in declaration['slots'] if s['slot_id']==args.inspect_slot)
            data=extract_slot(args.batch,slot)
            print(json.dumps({'probe_only_no_final_output':True,'row':data['row'],
                'phases':[{k:p[k] for k in ('phase_index','name','wall_s','U_after_J')} for p in data['phases']],
                'native_requests':data['native']['requests'],'guard':GUARD,'warnings':WARNINGS},ensure_ascii=False))
        else:
            if args.out is None:parser.error('--out required for terminal analysis')
            analyse(args.batch,args.out)
    finally:sys.setprofile(None)


if __name__=='__main__':main()
