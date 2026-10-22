"""K159: stored R4 arithmetic and domain analysis; stdlib only, no solver/heat imports."""
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'AGENTS.md').is_file())
EXP=REPO/'research/chapter3_experiments'
SOURCES={}


def read(path):
    data=path.read_bytes();SOURCES[path.relative_to(REPO).as_posix()]=hashlib.sha256(data).hexdigest()
    return json.loads(data.decode('utf-8'))


def write(name,value):
    with (OUT/name).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def csv_write(name,rows):
    with (OUT/name).open('x',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)


def iv(value):return tuple(map(F,value))
def encoded(value):return [str(x) for x in value]
def diff(a,b):return a[0]-b[1],a[1]-b[0]
def overlap(a,b):return max(a[0],b[0])<=min(a[1],b[1])
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def membership(condition,candidate,phase,*,ignore_unit=False,swap_cpu=False):
    violations=[]
    for sid,rows in candidate['scenes'].items():
        for row in rows:
            seed=condition['seed_options_by_scene'][sid][row['stage_id']]
            fixed=seed if phase==1 else condition['warm_options_by_scene'][sid][row['stage_id']]
            unit={'CPU1':'CPU2','CPU2':'CPU1'}.get(row['unit'],row['unit']) if swap_cpu else row['unit']
            causes=[]
            if not ignore_unit and unit!=seed['unit']:causes.append('fixed_unit')
            if row['stage_id'] not in condition['opened_by_scene'][sid]:
                if row['opp']!=fixed['opp']:causes.append('closed_opp')
                if F(row['start_ms'])!=F(fixed['start_ms']):causes.append('closed_start')
            if causes:violations.append({'scene':sid,'stage':row['stage_id'],'causes':causes,
                'tested':{'unit':unit,'opp':row['opp'],'start_ms':row['start_ms']},'unit_anchor':seed['unit'],'closed_anchor':fixed})
    return {'member':not violations,'violations':violations,'ignore_unit_for_diagnosis':ignore_unit,
            'CPU_label_swap_only':swap_cpu,'new_safe_witness_claimed':False}


def mode_of(instance,sid,row):
    scene=next(s for s in instance['scenarios'] if s['id']==sid)
    st=next(s for s in scene['stage_instances'] if s['id']==row['stage_id'])
    return st,next(m for m in instance['stage_modes'][st['shared_stage_id']]
                   if m['unit_id']==row['unit'] and m['opp_id']==row['opp'])


def main():
    checks={};cohorts={};schedules=[];components=[];phases=[];anchors=[];members={};profiles=[]
    for label,folder,pid in [('P0','p0_resume01','base__R4'),('P1','p1_execution01','response_R__R4')]:
        root=EXP/'results'/folder
        facts=read(root/'analysis01/facts.json')
        records={m:read(root/'calls'/pid/m/'wrapper_raw_result.json') for m in ['anchor_linked4','heft']}
        posts={m:read(root/'calls'/pid/m/'postcheck.json') for m in records}
        inputs={m:read(root/'calls'/pid/m/'input_instance.json') for m in records}
        instance=inputs['anchor_linked4'];linked=records['anchor_linked4'];heft=records['heft']
        checks[label+'/methods_same_input']=inputs['anchor_linked4']==inputs['heft']
        checks[label+'/two_final_posts_SAFE']=all(p['state']=='SAFE' and p['rankable_energy'] for p in posts.values())
        checks[label+'/weights_sum_one']=sum(F(s['weight']) for s in instance['scenarios'])==1
        checks[label+'/two_phases']=len(linked['phases'])==2
        receipt=lambda m:records[m]['aggregation'] if m=='anchor_linked4' else records[m]['evaluation']
        total_delta=diff(iv(receipt('anchor_linked4')['weighted_energy_J']),iv(receipt('heft')['weighted_energy_J']))
        weighted=[F(0),F(0)];weighted_components={k:[F(0),F(0)] for k in ['baseline','activity','external_common','temperature_correction']}
        scenes={};shared={};opp_counts={}
        for m,result in records.items():
            by_shared={}
            opp_counts[m]=dict(Counter(row['opp'] for rows in result['safe_candidate']['scenes'].values() for row in rows))
            for sid,rows in result['safe_candidate']['scenes'].items():
                for row in rows:
                    stage,mode=mode_of(instance,sid,row)
                    request=next(q for sc in instance['scenarios'] if sc['id']==sid for q in sc['requests'] if q['id']==stage['request_id'])
                    start=F(row['start_ms']);end=start+F(mode['duration_ms'])
                    schedules.append({'condition':label,'method':m,'scene':sid,'stage':stage['shared_stage_id'],
                        'stage_instance':row['stage_id'],'unit':row['unit'],'opp':row['opp'],'start_ms':str(start),
                        'duration_ms':mode['duration_ms'],'end_ms_exact':str(end),'end_ms':float(end),
                        'request_deadline_ms':str(F(request['deadline_ms'])),
                        'stage_end_to_request_deadline_ms':float(F(request['deadline_ms'])-end),
                        'activity_energy_J_exact':mode['activity_energy_J']})
                    if stage['shared_stage_id'].startswith('A.'):
                        by_shared.setdefault(stage['shared_stage_id'],set()).add(row['unit'])
            checks[label+'/'+m+'/shared_A_unit_consistent']=all(len(v)==1 for v in by_shared.values())
            shared[m]={k:next(iter(v)) for k,v in by_shared.items()}
        for scene in instance['scenarios']:
            sid,w=scene['id'],F(scene['weight']);l,h=[posts[m]['scenes'][sid] for m in records]
            delta=diff(iv(l['energy_J']),iv(h['energy_J']))
            weighted=[a+w*b for a,b in zip(weighted,delta)]
            scenes[sid]={'weight':str(w),'linked_J':l['energy_J'],'HEFT_J':h['energy_J'],
                'difference_J':encoded(delta),'weighted_difference_J':encoded(w*x for x in delta),
                'linked_peak_upper_degC':max(float(F(v[1])) for v in l['peaks_degC'].values()),
                'HEFT_peak_upper_degC':max(float(F(v[1])) for v in h['peaks_degC'].values())}
            summed=[F(0),F(0)]
            for k in weighted_components:
                d=diff(iv(l['energy_components_J'][k]),iv(h['energy_components_J'][k]))
                for j in (0,1):weighted_components[k][j]+=w*d[j];summed[j]+=d[j]
                components.append({'condition':label,'scene':sid,'component':k,
                    'linked_J':float(F(l['energy_components_J'][k][1])),
                    'HEFT_J':float(F(h['energy_components_J'][k][1])),
                    'delta_lo_exact_J':str(d[0]),'delta_hi_exact_J':str(d[1]),
                    'weighted_delta_J':float(w*(d[0]+d[1])/2)})
            checks[label+'/'+sid+'/components_match_scene_delta']=overlap(summed,delta)
            checks[label+'/'+sid+'/original_receipts_overlap_post']=all(overlap(
                iv((receipt(m)['scenes'][sid].get('result') or receipt(m)['scenes'][sid])['energy_J']),
                iv(posts[m]['scenes'][sid]['energy_J'])) for m in records)
        checks[label+'/weighted_scene_delta_matches_receipt']=overlap(weighted,total_delta)
        checks[label+'/weighted_component_delta_matches_receipt']=overlap(
            [sum(v[j] for v in weighted_components.values()) for j in (0,1)],total_delta)
        for ph in linked['phases']:
            index=ph['phase_index'];c=ph['condition']
            anchor=c['seed_candidate'] if index==1 else c['warm_candidate']
            checks[f'{label}/phase{index}/own_anchor_is_member']=membership(c,anchor,index)['member']
            for label2,kw in [('original',{}),('CPU_swap',{'swap_cpu':True}),('ignore_unit',{'ignore_unit':True})]:
                members[f'{label}/phase{index}/HEFT_{label2}']=membership(c,heft['safe_candidate'],index,**kw)
            for sid,opts in c['seed_options_by_scene'].items():
                fixed=opts if index==1 else c['warm_options_by_scene'][sid]
                for stage_id,row in fixed.items():
                    anchors.append({'condition':label,'phase':index,'scene':sid,'stage':stage_id.split('::')[-1],
                        'unit_fixed':opts[stage_id]['unit'],'opp_anchor':row['opp'],'start_anchor_ms':row['start_ms'],
                        'opp_and_start_open':stage_id in c['opened_by_scene'][sid]})
            for sid,s in ph['scenes'].items():
                rs=s['solver_result'];rounds=[]
                for q in rs['rounds']:
                    op=q.get('output') or {};rounds.append({'request_number':q.get('request_number'),
                        'native_exitflag':q.get('exitflag'),'objective_J':q.get('fval'),
                        'MaxTime_s':q.get('solver_max_time_s_used'),
                        'native_call_s':(q.get('phase_seconds') or {}).get('intlinprog_call'),
                        'relativegap':op.get('relativegap'),'absolutegap':op.get('absolutegap'),
                        'nodes':op.get('numnodes'),'feasible_points':op.get('numfeaspoints'),
                        'message':op.get('message'),'solver_reported_only':True})
                phases.append({'condition':label,'phase':index,'scene':sid,'phase_start_s':ph['started_at_s'],
                    'phase_end_s':ph['completed_at_s'],'phase_wall_s':ph['completed_at_s']-ph['started_at_s'],
                    'model_complete_s':s['model_completed_at_s'],'search_start_s':s['search_started_at_s'],
                    'search_return_s':s['search_returned_at_s'],'scene_cap_s':s['scene_slice_s'],
                    'reason':s['reason'],'rounds':rounds})
        checks[label+'/final_linked_in_phase2']=membership(linked['phases'][1]['condition'],linked['safe_candidate'],2)['member']
        for shared_stage,modes in instance['stage_modes'].items():
            for mode in modes:
                if mode['unit_id']=='CPU2':continue
                profiles.append({'condition':label,'stage':shared_stage,'unit':mode['unit_id'],'opp':mode['opp_id'],
                    **{k:mode[k] for k in ['alpha','d_ref_ms','frequency_GHz','duration_ms','activity_power_W','activity_energy_J']}})
        fact={m:next(v for v in facts['rows'] if v['problem_id']==pid and v['method']==m) for m in records}
        cohorts[label]={'problem_id':pid,'weighted_delta_J':encoded(total_delta),
            'weighted_component_differences_J':{k:encoded(v) for k,v in weighted_components.items()},
            'linked_relative_to_HEFT_percent':100*float(total_delta[1]/F(heft['safe_upper_bound_J'])),
            'scenes':scenes,'opp_counts':opp_counts,'shared_A_units':shared,
            'linked_root_s':linked['timing']['method_elapsed_s'],
            'linked_unused_root_s':linked['timing']['limit_s']-linked['timing']['method_elapsed_s'],
            'linked_timing_categories_s':linked['timing']['phases_exclusive_s'],
            'HEFT_root_s':heft['timing']['method_elapsed_s'],
            'phase1_U_J':fact['anchor_linked4']['phase1_U_J'],'phase2_U_J':fact['anchor_linked4']['phase2_U_J'],
            'initial_U_J':linked['initial_global_safe_upper_bound_J'],
            'first_strict_improvement_s':fact['anchor_linked4']['first_strict_improvement_s'],
            'global_updates':[{'phase':u['phase_index'],'committed_at_s':u['committed_at_s'],
                'U_J':u['safe_upper_bound_J']} for u in linked['global_updates']],
            'independent_optimal':linked['independently_proven_optimal'],'feedback_count':sum(
                len(s['solver_result']['feedback']) for p in linked['phases'] for s in p['scenes'].values())}
        cohorts[label]['_instance']=instance
        cohorts[label]['_linked_candidate']=linked['safe_candidate']
        cohorts[label]['_linked_phases']=linked['phases']
    a,b=[cohorts[k]['_instance'] for k in ['P0','P1']]
    for k in ['platform','execution_rules','units','window_ms','start_grid_ms','duration_scale','scenarios']:
        checks['P0_P1_same_'+k]=a[k]==b[k]
    changed={}
    for st,modes in a['stage_modes'].items():
        changes=set()
        for m,n in zip(modes,b['stage_modes'][st]):
            checks['same_mode_identity/'+m['mode_id']]=m['mode_id']==n['mode_id']
            changes|={k for k in m if m[k]!=n[k]}
        changed[st]=sorted(changes)
    checks['only_response_derived_mode_fields_changed']=all(set(v)<={'alpha','duration_ms','activity_energy_J'} for v in changed.values())
    c1=cohorts['P1']['_linked_phases'][1]['condition']
    checks['P1_phase2_warm_is_original_seed']=c1['warm_candidate']==c1['seed_candidate']
    checks['P0_phase2_warm_changed_from_seed']=cohorts['P0']['_linked_phases'][1]['condition']['warm_candidate']!=cohorts['P0']['_linked_phases'][1]['condition']['seed_candidate']
    checks['P0_activity_and_baseline_delta_zero']=all(iv(cohorts['P0']['weighted_component_differences_J'][k])[0]<=0<=iv(cohorts['P0']['weighted_component_differences_J'][k])[1] for k in ['activity','baseline'])
    checks['P1_even_ignoring_units_HEFT_outside_phase2']=not members['P1/phase2/HEFT_ignore_unit']['member']
    ac_key='AC_offset_0ms';ab_key='AB_offset_0ms'
    share=F(cohorts['P1']['scenes'][ac_key]['weighted_difference_J'][1])/F(cohorts['P1']['weighted_delta_J'][1])
    # Necessary timing inequality only, not a new schedule/evaluation or proof of model infeasibility.
    bm=lambda inst,sid,unit,opp:next(m for m in inst['stage_modes'][sid] if m['unit_id']==unit and m['opp_id']==opp)
    earliest=min(F(m['duration_ms']) for sid in ['A.pre','B.pre'] for m in b['stage_modes'][sid])
    low_sum=sum(F(bm(b,sid,'NPU0','L')['duration_ms']) for sid in ['A.main','B.main'])
    ab_scene=next(s for s in b['scenarios'] if s['id']==ab_key)
    latest=max(F(q['deadline_ms']) for q in ab_scene['requests'])
    timing_bound={'scope':'AB, both main stages fixed to NPU0 and both L; even before post stages',
        'earliest_NPU_start_ms':str(earliest),'sum_L_NPU_durations_ms':str(low_sum),
        'second_main_finish_lower_bound_ms':str(earliest+low_sum),'latest_request_deadline_ms':str(latest),
        'strictly_impossible_for_this_two_L_NPU_mapping':earliest+low_sum>latest,
        'not_global_infeasibility':True,'not_thermal_evaluation':True}
    checks['P1_AB_two_L_NPU_necessary_bound_exceeds_latest_deadline']=earliest+low_sum>latest
    cfg=read(EXP/'config_v01.json');p2=next(v for v in cfg['conditions'] if v['id']=='initial_78')
    checks['P2_only_existing_initial78_override']=p2['overrides']=={'initial_temperature_degC':'78'}
    for k in cohorts:
        for hidden in ['_instance','_linked_candidate','_linked_phases']:cohorts[k].pop(hidden)
    checks['source_bytes_unchanged']=all(hashlib.sha256((REPO/n).read_bytes()).hexdigest()==h for n,h in SOURCES.items())
    diagnosis={'material_passport':{'stage':'K159','date':'2026-10-22','status':'ANALYZED_STORED_RECORDS',
        'scope':'P0/P1 R4 linked and HEFT; no reproduction run'},
        'research_calls':0,'solver_calls':0,'new_thermal_evaluations':0,'algorithm_or_inputs_modified':False,
        'cohorts':cohorts,'mode_fields_changed':changed,'P1_AC_share_of_gap':float(share),
        'P1_AB_two_L_NPU_timing_bound':timing_bound,'source_sha256':SOURCES,
        'P2_status':{'condition':p2,'execution_authorised':False,'prepared_or_run':False,
            'intended_one_factor_reference':'P0/base with original response H; not P1/R plus high initial temperature'},
        'unresolved':'Why phase1 native root reports zero-gap without improvement is not independently established; no claim that all low-OPP schedules are infeasible, no solver defect claim, no new LP/MILP/thermal calls.'}
    csv_write('r4_schedules.csv',schedules);csv_write('r4_components.csv',components)
    csv_write('r4_closed_anchors.csv',anchors);csv_write('r4_response_profiles.csv',profiles)
    write('r4_membership.json',members);write('r4_phase_search.json',phases);write('diagnosis.json',diagnosis)
    write('checks.json',{'passed':all(checks.values()),'count':len(checks),'checks':checks,
        'scope':'Stored identities, exact arithmetic and saved-domain membership, not new optimisation or physical verification',
        'research_calls':0,'new_thermal_evaluations':0})
    assert all(checks.values()),[k for k,v in checks.items() if not v]
    print({'passed':True,'checks':len(checks),'P1_extra_J':float(F(cohorts['P1']['weighted_delta_J'][1])),
        'P1_AC_share':float(share),'P1_components':{k:float(F(v[1])) for k,v in cohorts['P1']['weighted_component_differences_J'].items()},
        'no_new_research_or_thermal_calls':True})


if __name__=='__main__':main()
