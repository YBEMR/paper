"""JSON/Fraction-only K139 design audit; no production import or optimizer."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').is_file())
REF=ROOT/'research/chapter3_experiments/results/staged_quality_pair01'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main(out):
    out=out.resolve();out.relative_to(ROOT);out.mkdir(parents=True,exist_ok=False)
    d=read(REF/'declaration.json');instance=read(REF/'input_instance.json');old=read(REF/'old_n1/result.json')
    assert all(sha(REF/n)==h for n,h in d['input_file_sha256'].items())
    assert old['state']=='SAFE' and old['identity']['full_input_sha256']==d['input_sha256']
    seed=old['condition']['seed_candidate'];warm=old['safe_candidate']
    grid,window=F(instance['start_grid_ms']),F(instance['window_ms'])
    assert grid==5 and window==400 and len(instance['scenarios'])==2
    proposed=deepcopy(warm);scopes={};rows=[];totals={'warm_activity_J':F(0),'linked_independent_activity_floor_J':F(0),'all_fixed_unit_activity_floor_J':F(0)}
    for scene in instance['scenarios']:
        sid=scene['id'];stages=scene['stage_instances'];requests={r['id']:r for r in scene['requests']}
        assert len(stages)==6 and len(requests)==2
        a=[s for s in stages if s['application']=='A'];local=[s for s in stages if s['application']!='A']
        assert len(a)==len(local)==3
        assert {s['chain_position'] for s in a}=={0,1,2}
        opened=sorted(s['id'] for s in a+[s for s in local if s['chain_position']==0])
        assert len(opened)==4
        initial={r['stage_id']:r for r in seed['scenes'][sid]};anchor={r['stage_id']:r for r in warm['scenes'][sid]}
        proposed_rows={r['stage_id']:r for r in proposed['scenes'][sid]}
        all_events={F(0),window};linked_events={F(0),window};all_count=linked_count=0
        for stage in stages:
            tid=stage['id'];fixed=anchor[tid];unit=initial[tid]['unit'];request=requests[stage['request_id']]
            assert fixed['unit']==unit
            modes=[m for m in instance['stage_modes'][stage['shared_stage_id']] if m['unit_id']==unit]
            choices=[]
            for mode in modes:
                duration=F(mode['duration_ms']);assert F(mode['activity_energy_J'])==F(mode['activity_power_W'])*duration/1000
                lo=max(0,(F(request['release_ms'])/grid).__ceil__())
                hi=min(int((window-duration)//grid),int((F(request['deadline_ms'])-duration)//grid))
                for index in range(lo,hi+1):
                    start=index*grid;choices.append((mode,start,start+duration))
            retained=[c for c in choices if tid in opened or
                (c[0]['opp_id']==fixed['opp'] and c[1]==F(fixed['start_ms']))]
            assert choices and retained
            warm_mode=next(m for m in modes if m['opp_id']==fixed['opp'])
            warm_energy=F(warm_mode['activity_energy_J'])
            all_floor=min(F(c[0]['activity_energy_J']) for c in choices)
            linked_floor=min(F(c[0]['activity_energy_J']) for c in retained)
            weight=F(scene['weight'])
            for key,value in [('warm_activity_J',warm_energy),('linked_independent_activity_floor_J',linked_floor),('all_fixed_unit_activity_floor_J',all_floor)]:totals[key]+=weight*value
            all_count+=len(choices);linked_count+=len(retained)
            for _,start,end in choices:all_events.update((start,end))
            for _,start,end in retained:linked_events.update((start,end))
            rows.append({'scene':sid,'stage_id':tid,'shared_stage_id':stage['shared_stage_id'],
                'opened':tid in opened,'seed_unit':unit,'warm_opp':fixed['opp'],'warm_start_ms':fixed['start_ms'],
                'all_fixed_unit_local_options_after_deadline':len(choices),'linked_local_options_after_deadline':len(retained),
                'warm_activity_J':str(warm_energy),'linked_activity_floor_J':str(linked_floor),'all_activity_floor_J':str(all_floor)})
        scopes[sid]={'opened_by_scene':opened,'closed_by_scene':sorted(set(anchor)-set(opened)),
            'opened_count':4,'closed_count':2,'all_options_after_deadline':all_count,'linked_options_after_deadline':linked_count,
            'all_candidate_start_end_events':len(all_events),'linked_candidate_start_end_events':len(linked_events)}
        # One predeclared constructive illustration, no search or repair:
        # all four opened stages use legal L, pre at release, A successors at
        # the next original grid point after the true predecessor finish.
        finish=None
        for stage in sorted(a,key=lambda s:s['chain_position'])+[s for s in local if s['chain_position']==0]:
            tid=stage['id'];row=proposed_rows[tid]
            mode=next(m for m in instance['stage_modes'][stage['shared_stage_id']] if m['unit_id']==row['unit'] and m['opp_id']=='L')
            release=F(requests[stage['request_id']]['release_ms'])
            start=(release/grid).__ceil__()*grid if stage['chain_position']==0 else (finish/grid).__ceil__()*grid
            row.update(opp='L',start_ms=str(start))
            if stage['application']=='A':finish=start+F(mode['duration_ms'])
    errors=[];timelines={}
    for scene in instance['scenarios']:
        sid=scene['id'];stages={s['id']:s for s in scene['stage_instances']};records={r['stage_id']:r for r in proposed['scenes'][sid]}
        requests={r['id']:r for r in scene['requests']};times={}
        assert set(records)==set(stages)
        for tid,row in records.items():
            mode=next(m for m in instance['stage_modes'][stages[tid]['shared_stage_id']] if m['unit_id']==row['unit'] and m['opp_id']==row['opp'])
            start=F(row['start_ms']);end=start+F(mode['duration_ms']);times[tid]=(start,end,mode['domain_id'])
            request=requests[stages[tid]['request_id']]
            if start< F(request['release_ms']) or (start/grid).denominator!=1 or end>window:errors.append([sid,tid,'release_grid_window'])
            if row['unit']!=next(r['unit'] for r in seed['scenes'][sid] if r['stage_id']==tid):errors.append([sid,tid,'unit_changed'])
            if tid in scopes[sid]['closed_by_scene'] and row!=next(r for r in warm['scenes'][sid] if r['stage_id']==tid):errors.append([sid,tid,'closed_changed'])
        for before,after in scene['dependencies']:
            if times[before][1]>times[after][0]:errors.append([sid,before,after,'dependency'])
        for request in requests.values():
            if max(times[t][1] for t in request['stage_instance_ids'])>F(request['deadline_ms']):errors.append([sid,request['id'],'deadline'])
        ids=list(records)
        for i,one in enumerate(ids):
            for two in ids[i+1:]:
                a,b=records[one],records[two];s1,e1,d1=times[one];s2,e2,d2=times[two]
                if max(s1,s2)<min(e1,e2) and (a['unit']==b['unit'] or d1==d2 and a['opp']!=b['opp']):errors.append([sid,one,two,'resource_or_frequency'])
        timelines[sid]={tid:{'start_ms':str(start),'true_end_ms':str(end),'domain':domain} for tid,(start,end,domain) in times.items()}
    totals['activity_only_optimistic_difference_J']=totals['warm_activity_J']-totals['linked_independent_activity_floor_J']
    report={'stage':'K139','scope':'JSON-only reference design audit, never runtime initialization or SAFE/quality evidence',
        'reference_input_sha256':d['input_sha256'],'reference_files':{n:sha(REF/n) for n in ['input_instance.json','old_n1/result.json']},
        'reference_runtime_parameters_changed':False,'scopes':scopes,'local_option_rows':rows,
        'weighted_activity_facts':{k:str(v) for k,v in totals.items()},
        'linked_and_all_fixed_unit_activity_floors_equal':totals['linked_independent_activity_floor_J']==totals['all_fixed_unit_activity_floor_J'],
        'demonstration':{'construction_attempts':1,'rule':'opened L; pre at request release; A successor at next original grid after true finish; closed warm unchanged',
            'candidate':proposed,'timelines':timelines,'structurally_legal':not errors,'errors':errors,
            'thermal_state':'NOT_EVALUATED','system_energy_state':'NOT_EVALUATED','used_as_method_initialization':False},
        'native_calls':0,'research_calls':0,'thermal_evaluations':0,'original_scale_models':0}
    save(out/'reference_scope.json',report)
    lines=['# 原输入联动块静态核查','',
        '仅复核归档JSON中的明确范围、局部选项及活动项代数；不构模、求解或评价原规模温度，不能当作系统节能结果。','',
        '| 场景 | 开放／闭合Stage | 全Stage固定设备选项→联动块 | 候选起止事件→联动块 |','|---|---:|---:|---:|']
    for sid,s in scopes.items():lines.append(f"| {sid} | 4／2 | {s['all_options_after_deadline']}→{s['linked_options_after_deadline']} | {s['all_candidate_start_end_events']}→{s['linked_candidate_start_end_events']} |")
    lines+=['',f"归档安排活动项为{float(totals['warm_activity_J']):.12f} J，联动块独立活动项下界为{float(totals['linked_independent_activity_floor_J']):.12f} J，与全Stage固定设备域的该下界相同。这只说明最低活动代价模式仍在局部选项中，不证明联合可实现、系统最优相同或实际可省这些能量。",'',
        f"一次事前规定的L档结构演示：结构合法={not errors}。不搜索、修复或再试；真实结束时刻不取整，只将后继起点选到原5 ms格点。全过程热安全及系统能耗均未评价，演示不进入任何方法初始化。",'',
        '完整IDs、精确时刻、活动项及检查结果见[reference_scope.json](reference_scope.json)。']
    (out/'summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'reference_scope_written':True,'scenes':scopes,'activity_floors_equal':report['linked_and_all_fixed_unit_activity_floors_equal'],'structurally_legal':not errors},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    main(parser.parse_args().out)
