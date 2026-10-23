"""K176 independent terminal-only stored analysis; standard library only.

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


def strict_improvement(old, new):
    a,b=interval(old),interval(new)
    if a is None or b is None:return {'state':'UNAVAILABLE'}
    return {'state':'STRICT_IMPROVEMENT' if b[1]<a[0] else 'STRICTLY_WORSE' if a[1]<b[0] else 'OVERLAPPING_INTERVALS',
        'old_energy_J':old,'new_energy_J':new,
        'improvement_J_lower':str(a[0]-b[1]),'improvement_J_upper':str(a[1]-b[0]),
        'improvement_percent_at_upper':float(100*(a[1]-b[1])/a[1]) if a[1]>0 else None}


def extended_details(batch,slot):
    data=extract_slot(batch,slot);r=read(batch/'calls'/slot['slot_id']/'result.json',True)
    rawphases=phase_records(r,slot['variant']);p2=next((p for p in rawphases if p.get('phase_index')==2),{})
    cond=p2.get('condition') or {};release=r.get('conditional_release') or {}
    selection=release.get('selection') or {};receipt=selection.get('receipt') or {}
    data['conditional_release']=release
    data['S1']={'candidate':cond.get('warm_candidate'), 'candidate_sha256':cond.get('warm_candidate_sha256'),
        'receipt_sha256':cond.get('warm_receipt_sha256'),
        'energy_J':(cond.get('warm_receipt') or {}).get('weighted_energy_J')}
    if not data['S1']['candidate']:
        snap=release.get('frozen_first_pass_safe_snapshot') or {}
        if snap:data['S1']={'candidate':snap.get('safe_candidate'),
            'candidate_sha256':snap.get('candidate_sha256'), 'receipt_sha256':snap.get('receipt_sha256'),
            'energy_J':snap.get('weighted_energy_J') or (snap.get('aggregation') or {}).get('weighted_energy_J')}
    data['final_candidate']=r.get('safe_candidate')
    data['final_candidate_sha256']=canonical(r['safe_candidate']) if isinstance(r.get('safe_candidate'),dict) else None
    data['row']['selection_state']=release.get('selection_state','NOT_APPLICABLE_OR_NOT_ENTERED')
    data['row']['selection_started_s']=release.get('selection_started_at_s')
    data['row']['selection_completed_s']=release.get('selection_completed_at_s')
    data['row']['selection_elapsed_s']=duration(release.get('selection_started_at_s'),release.get('selection_completed_at_s'))
    data['row']['second_phase_energy_change']=strict_improvement(data['S1']['energy_J'],data['row']['comparison_energy_J'])
    request_map={}
    for p in rawphases:
        for sid,s in (p.get('scenes') or {}).items():
            for n in (s.get('solver_result') or {}).get('rounds') or []:
                if isinstance(n,dict) and type(n.get('request_number')) is int:
                    request_map[n['request_number']]={'phase_index':p.get('phase_index'),'scene_id':sid}
    for n in data['native']['requests']:
        path=batch/'calls'/slot['slot_id']/'method/matlab'/(n['request_prefix']+'.response.json')
        raw=read(path,True);py=read(path.with_name(n['request_prefix']+'.python.json'),True)
        req=py.get('request_number');n.update(request_map.get(req,{'phase_index':None,'scene_id':None}))
        callbacks=raw.get('callbacks') or py.get('callbacks') or []
        compact=[{'state':c.get('state'),'request_wall_s':c.get('request_wall_seconds'),
            **{k:(c.get('values') or {}).get(k) for k in ('phase','time','fval','lowerbound','numnodes','numfeaspoints','relativegap')}}
            for c in callbacks if isinstance(c,dict)]
        roots=[c for c in compact if c.get('phase')=='rootlp']
        n.update(rootlp_first_solver_time_s=roots[0].get('time') if roots else None,
            rootlp_first_fval=roots[0].get('fval') if roots else None,
            rootlp_observation='first rootlp callback only; not a full LP profiler or independent lower-bound certificate',
            callbacks=compact,native_exitflag=raw.get('exitflag'),native_output=raw.get('output'))
    data['release_receipt_keys']=list(receipt)
    return data


def analyse(batch,output):
    if output.exists():raise FileExistsError('append-only analysis output')
    terminal=read(batch/'batch_terminal.json')
    if terminal.get('state') in (None,'DECLARED','RUNNING'):raise ValueError('terminal required')
    d=read(batch/'declaration.json');ledger=read(batch/'ledger.json')
    expected=[('base__R3','C'),('base__R3','conditional_release')]
    if [(s['case_id'],s['variant']) for s in d['slots']]!=expected:raise ValueError('two-slot protocol/order mismatch')
    details=[extended_details(batch,s) for s in d['slots']];rows=[v['row'] for v in details]
    c,n=details;a,b=c['row'],n['row']
    seeds=[a.get('seed_label_hash'),b.get('seed_label_hash')]
    anchors=[c['S1'].get('candidate_sha256'),n['S1'].get('candidate_sha256')]
    same_seed=bool(all(seeds) and len(set(seeds))==1)
    same_anchor=bool(all(anchors) and len(set(anchors))==1)
    pair={'same_fresh_seed':same_seed,'same_complete_S1':same_anchor,
        'C_S1_candidate_sha256':anchors[0],'new_S1_candidate_sha256':anchors[1],
        'end_to_end_energy':strict_improvement(a.get('comparison_energy_J'),b.get('comparison_energy_J')),
        'attribution_scope':'same full S1; one independent call per arm, includes selection/search trajectory and numerical variation'
            if same_anchor else 'end-to-end only; different/missing S1 prevents isolating conditional-release effect'}
    after={k:sha(ROOT/k) for k in HASHES};unchanged=after==HASHES
    facts={'protocol':'K176-independent-readonly-terminal-v1','terminal':terminal,'ledger':ledger,
        'rows':rows,'details':details,'comparison':pair,'read_before_sha256':dict(HASHES),
        'read_after_sha256':after,'read_files_unchanged':unchanged,'warnings':WARNINGS,
        'guard':GUARD,'models':0,'solver_calls':0,'thermal_or_post_calls':0,'new_candidate_or_U':0}
    if not unchanged:raise ValueError('stored artifacts drift during analysis')
    output.mkdir(parents=True)
    (output/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False)+'\n','utf-8')
    write_csv(output/'results2.csv',rows)
    write_csv(output/'phases.csv',[{'slot_id':v['row']['slot_id'],**{k:p[k] for k in p if k!='scenes'}} for v in details for p in v['phases']])
    write_csv(output/'models.csv',[{'slot_id':v['row']['slot_id'],'phase_index':p['phase_index'],**s} for v in details for p in v['phases'] for s in p['scenes']])
    write_csv(output/'native_requests.csv',[{'slot_id':v['row']['slot_id'],**n} for v in details for n in v['native']['requests']])
    write_csv(output/'safe_updates.csv',[{'slot_id':v['row']['slot_id'],**u} for v in details for u in v['updates']])
    schedules=[]
    for data in details:
        for name,candidate in (('S1',data['S1']['candidate']),('final',data['final_candidate'])):
            for sid,entries in (candidate or {}).get('scenes',{}).items():
                schedules.extend({'slot_id':data['row']['slot_id'],'generation':name,'scene_id':sid,**r} for r in entries)
    write_csv(output/'schedules.csv',schedules)
    lines=['# K176两次调用独立只读结论','',f"终态：{terminal.get('state')}；有效可比较SAFE：{sum(r['comparison_U_J'] is not None for r in rows)}/2。",'',
        '|版本|完整安全U/J|第一阶段后U/J|第二阶段后U/J|方法实际/s|P1/s|P2/s|MATLAB启动/s|',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:lines.append('|'+ '|'.join([r['variant'],display(r['comparison_U_J']),display(r['phase1_U_J']),display(r['phase2_U_J']),display(r['root_actual_s'],3),display(r['phase1_wall_s'],3),display(r['phase2_wall_s'],3),display(r['MATLAB_startup_s'],3)])+'|')
    lines+=['',f'同fresh S0：{same_seed}；同完整S1：{same_anchor}。',
        f"新版相对原C：{pair['end_to_end_energy']['state']}。归因范围：{pair['attribution_scope']}。",'',
        '各臂相对自身S1的净改善、选择触发/耗时、P2选项/变量/行数与过滤证据见facts、models、schedules；rootlp为已保存回调首次观测，未证明MILP全局最优。',
        'native求解时间、方法根时长、构模和传输存在嵌套，不能相加。预算后归档的response仅提取时间与内部状态，不据其x接纳新U。',
        '本次两臂各一开发调用，只能判本配对表现，不支持稳定加速或总体排名。',
        f'读取证据前后hash不变：{unchanged}；只读警告：{len(WARNINGS)}；新优化/热积分/候选评价均0。']
    (output/'summary.md').write_text('\n'.join(lines)+'\n','utf-8')
    print(json.dumps({'output':str(output),'same_seed':same_seed,'same_S1':same_anchor,'comparison':pair['end_to_end_energy'],'warnings':WARNINGS,'new_scientific_calls':0},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,default=BATCH)
    p.add_argument('--out',type=Path);p.add_argument('--inspect-slot');a=p.parse_args()
    HASHES[str(Path(__file__).relative_to(ROOT)).replace('\\','/')]=sha(Path(__file__))
    sys.addaudithook(audit);sys.setprofile(profile)
    try:
        if a.inspect_slot:
            d=read(a.batch/'declaration.json');s=next(s for s in d['slots'] if s['slot_id']==a.inspect_slot)
            print(json.dumps(extended_details(a.batch,s),ensure_ascii=False))
        else:
            if a.out is None:p.error('--out required')
            analyse(a.batch,a.out)
    finally:sys.setprofile(None)
if __name__=='__main__':main()


