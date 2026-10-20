"""K146: compare saved evidence with stdlib only; never invoke a method."""
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import csv
import hashlib
import json

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
CODE = ROOT/'research/chapter3_experiments'
OLD = CODE/'results/fair_comparison_preparation01'
NEW = CODE/'results/heft_sa_followup01'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def iv(value):
    low,high = map(Q,value)
    assert low <= high
    return low,high

def scene_physical(receipt):
    return receipt.get('result',receipt)

def write_csv(name,values):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(values[0]));w.writeheader();w.writerows(values)

def comparison():
    linked=read(OLD/'linked_n1/result.json')
    heft=read(NEW/'heft/result.json')
    instance=read(NEW/'input_instance.json')
    declaration=read(NEW/'declaration.json')
    prior=read(CODE/'results/budget_end_review01/audit.json')
    inputs={n:sha(OLD/n) for n in ['input_raw.json','input_config.json','input_instance.json']}
    assert inputs=={n:sha(NEW/n) for n in inputs}
    assert canonical(instance)==declaration['input_sha256']==linked['condition']['source_input_sha256']==heft['input_sha256']
    assert all(sha(ROOT/n)==h for n,h in declaration['source_sha256'].items())
    assert all(sha(OLD/n)==h for n,h in prior['raw_artifact_sha256'].items())
    receipts={'linked_K142':linked['aggregation'],'HEFT_K145':heft['evaluation']}
    candidates={'linked_K142':linked['safe_candidate'],'HEFT_K145':heft['safe_candidate']}
    weights={s['id']:Q(s['weight']) for s in instance['scenarios']}
    assert sum(weights.values())==1
    energy_rows=[];components=[];schedule_rows=[];plans={};physical_summaries={}
    for name,receipt in receipts.items():
        assert receipt['state']=='SAFE' and receipt['rankable_energy']
        assert receipt['safe_upper_bound_J']==(linked if name=='linked_K142' else heft)['safe_upper_bound_J']
        assert receipt.get('safe_candidate',candidates[name])==candidates[name]
        total_low,total_high=iv(receipt['weighted_energy_J'])
        weighted_low=weighted_high=Q(0)
        plans[name]={};physical_summaries[name]={}
        for scene in instance['scenarios']:
            sid=scene['id'];physical=scene_physical(receipt['scenes'][sid])
            assert physical['state']=='SAFE' and physical['complete'] and physical['rankable_energy']
            assert Q(physical['covered_until_s'])==Q(instance['window_ms'])/1000
            assert Q(physical['trace'][-1]['time_s'])==Q(instance['window_ms'])/1000
            peaks={n:float(iv(v)[1]) for n,v in physical['peaks_degC'].items()}
            assert set(peaks)==set(instance['platform']['node_order'])
            assert all(iv(physical['peaks_degC'][n])[1]<=Q(limit) for n,limit in zip(instance['platform']['node_order'],scene['maximum_temperature_degC']))
            e_low,e_high=iv(physical['energy_J']);weighted_low+=weights[sid]*e_low;weighted_high+=weights[sid]*e_high
            energy_rows.append(dict(method=name,scene=sid,energy_low_J=str(e_low),energy_high_J=str(e_high),
                                    energy_J=float(e_high),peak_upper_degC=max(peaks.values())))
            physical_summaries[name][sid]=dict(energy_J=float(e_high),peak_upper_degC=peaks,
                                             request_completion_ms=receipt['legality']['scenes'][sid]['request_completion_ms'])
            for key,value in physical['energy_components_J'].items():
                low,high=iv(value)
                components.append(dict(method=name,scene=sid,component=key,weight=str(weights[sid]),
                                       low_J=str(low),high_J=str(high),weighted_high_J=float(weights[sid]*high)))
            by_stage={s['id']:s for s in scene['stage_instances']}
            saved={r['stage_id']:r for r in receipt['legality']['scenes'][sid]['rows']}
            plans[name][sid]={r['stage_id']:r for r in candidates[name]['scenes'][sid]}
            for row in candidates[name]['scenes'][sid]:
                stage=by_stage[row['stage_id']];r=saved[row['stage_id']]
                mode=next(m for m in instance['stage_modes'][stage['shared_stage_id']] if (m['unit_id'],m['opp_id'])==(row['unit'],row['opp']))
                assert Q(r['start_ms'])==Q(row['start_ms']) and Q(r['end_ms'])==Q(row['start_ms'])+Q(mode['duration_ms'])
                schedule_rows.append(dict(method=name,scene=sid,stage=row['stage_id'],shared_stage=stage['shared_stage_id'],
                                          unit=row['unit'],opp=row['opp'],start_ms=row['start_ms'],end_ms=r['end_ms'],
                                          duration_ms=mode['duration_ms'],deadline_ms=r['deadline_ms'],
                                          activity_energy_J=mode['activity_energy_J'],
                                          alpha=mode['alpha'],weighted_activity_J=float(weights[sid]*Q(mode['activity_energy_J']))))
        assert total_low<=weighted_low<=weighted_high<=total_high
    comp_delta=[]
    for component in sorted({r['component'] for r in components}):
        values={name:sum(Q(r['weight'])*Q(r['high_J']) for r in components if r['method']==name and r['component']==component) for name in receipts}
        comp_delta.append(dict(component=component,linked_J=float(values['linked_K142']),heft_J=float(values['HEFT_K145']),
                               linked_minus_heft_J=float(values['linked_K142']-values['HEFT_K145'])))
    changes=[];deployment=[]
    for sid in weights:
        for stage,left in plans['linked_K142'][sid].items():
            right=plans['HEFT_K145'][sid][stage]
            changes.append(dict(scene=sid,stage=stage,linked_unit=left['unit'],heft_unit=right['unit'],
                                linked_opp=left['opp'],heft_opp=right['opp'],linked_start_ms=left['start_ms'],
                                heft_start_ms=right['start_ms'],unit_changed=left['unit']!=right['unit'],
                                opp_changed=left['opp']!=right['opp'],start_changed=Q(left['start_ms'])!=Q(right['start_ms'])))
    shared_units={name:{r['shared_stage']:r['unit'] for r in schedule_rows if r['method']==name} for name in receipts}
    for key in sorted(shared_units['linked_K142']):
        deployment.append(dict(stage=key,shared_across_scenes=key.startswith('A.'),
                               linked_unit=shared_units['linked_K142'][key],heft_unit=shared_units['HEFT_K145'][key]))
    # Compare labels only; this does not construct or evaluate a new schedule.
    label_comparisons=[]
    for swap in [False,True]:
        rename={'CPU1':'CPU2','CPU2':'CPU1'} if swap else {}
        mismatched=[key for key,left in shared_units['linked_K142'].items()
                    if rename.get(left,left)!=shared_units['HEFT_K145'][key]]
        label_comparisons.append(dict(global_CPU_label_swap=swap,mismatched_stage_identities=mismatched))
    domain_rows=[];phase_rows=[]
    for phase in linked['phases']:
        condition=phase['condition'];seed=condition['seed_options_by_scene']
        anchor=condition.get('warm_options_by_scene',seed)
        for sid,scene in phase['scenes'].items():
            for stage,row in plans['HEFT_K145'][sid].items():
                causes=[]
                if row['unit']!=seed[sid][stage]['unit']:causes.append('fixed_seed_unit')
                if stage not in condition['opened_by_scene'][sid]:
                    if row['opp']!=anchor[sid][stage]['opp']:causes.append('closed_OPP')
                    if Q(row['start_ms'])!=Q(anchor[sid][stage]['start_ms']):causes.append('closed_start')
                domain_rows.append(dict(phase=phase['phase_index'],scene=sid,stage=stage,
                                        opened=stage in condition['opened_by_scene'][sid],
                                        fixed_unit=seed[sid][stage]['unit'],closed_opp=anchor[sid][stage]['opp'],
                                        closed_start_ms=anchor[sid][stage]['start_ms'],HEFT_membership=not causes,
                                        exclusion_reasons=';'.join(causes)))
            solver=scene.get('solver_result') or {};diagnostic=solver.get('diagnostic') or {};model=scene['model_summary']
            phase_rows.append(dict(phase=phase['phase_index'],scene=sid,
                                   phase_start_s=phase['started_at_s'],phase_end_s=phase['completed_at_s'],
                                   phase_complete=phase['search_sequence_complete'],model_complete_s=scene.get('model_completed_at_s'),
                                   search_start_s=scene.get('search_started_at_s'),search_return_s=scene.get('search_returned_at_s'),
                                   options=model['options'],variables=model['variables'],binary=model['binary_variables'],rows=model['rows'],
                                   solver_reason=solver.get('reason'),thermal_feedback_rows=len(solver.get('feedback') or []),
                                   actual_evaluations=len(diagnostic.get('evaluations') or []),duplicates=diagnostic.get('duplicate_receipts'),
                                   original_evaluation_row_count=(len(scene['original_scene_evaluations'])
                                       if isinstance(scene.get('original_scene_evaluations'),list) else None),
                                   original_evaluation_row_count_status=('RECORDED'
                                       if isinstance(scene.get('original_scene_evaluations'),list) else 'NOT_RECORDED_IN_PHASE')))
    path_drops=[]
    for previous,event in zip(heft['events'],heft['events'][1:]):
        path_drops.append(dict(source=event['source'],at_s=event['at_s'],
                               upper_bound_drop_J=float(Q(previous['safe_upper_bound_J'])-Q(event['safe_upper_bound_J']))))
    activity_delta=[]
    for stage in sorted({r['shared_stage'] for r in schedule_rows}):
        values={name:sum(Q(weights[r['scene']])*Q(r['activity_energy_J']) for r in schedule_rows
                         if r['method']==name and r['shared_stage']==stage) for name in receipts}
        activity_delta.append(dict(stage=stage,linked_J=float(values['linked_K142']),heft_J=float(values['HEFT_K145']),
                                   linked_minus_heft_J=float(values['linked_K142']-values['HEFT_K145'])))
    old_low,old_high=iv(linked['aggregation']['weighted_energy_J']);new_low,new_high=iv(heft['evaluation']['weighted_energy_J'])
    prior140=read(CODE/'results/linked_quality_pair01/linked_n1/result.json')
    assert prior140['condition']['source_input_sha256']==declaration['input_sha256']
    assert prior140['condition']['seed_options_by_scene']==linked['condition']['seed_options_by_scene']
    assert Q(prior140['safe_upper_bound_J'])<old_low
    log_summaries={};log_totals=Counter();seen_decodes=Counter();seen_receipts=Counter()
    second_candidates={}
    for name in ['scene_0/diagnostic_events.jsonl','scene_1/diagnostic_events.jsonl',
                 'pass_02/scene_0/diagnostic_events.jsonl','pass_02/scene_1/diagnostic_events.jsonl']:
        path=OLD/'linked_n1'/name
        entries=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        counts=Counter(e.get('event') for e in entries);log_totals.update(counts)
        for entry in entries:
            if entry.get('event')=='candidate_decoded':seen_decodes[entry['decode']['state']]+=1
            if entry.get('event')=='candidate_evaluated':seen_receipts[entry['evaluation']['state']]+=1
        log_summaries[name]=dict(events=dict(counts),sha256=sha(path))
        if name.startswith('pass_02/'):
            second_candidates[name]=sorted({e['candidate_sha256'] for e in entries if e.get('event')=='candidate_evaluated'})
    assert log_totals['candidate_decoded']==10 and log_totals['candidate_evaluated']==6
    assert dict(seen_decodes)=={'LEGAL':10} and dict(seen_receipts)=={'SAFE':6}
    with (OLD/'execution_k142/analysis01/native_timing.csv').open(encoding='utf-8-sig',newline='') as stream:
        native_records=[row for row in csv.DictReader(stream) if row['job']=='linked_n1']
    native_columns=['scene','phase_index','request_number','status','exitflag','MaxTime_used_s',
                    'actual_intlinprog_call_s','rootlp_callback_observed','first_rootlp_native_elapsed_s',
                    'rootlp_numnodes','final_numnodes','nonempty_callback_count']
    native_brief=[{k:row.get(k) for k in native_columns} for row in native_records]
    historical_attempts=[]
    for stage,path in [('K135',CODE/'results/augmented_quality_pair01/augmented_all_opp_start/result.json'),
                       ('K138',CODE/'results/staged_quality_pair01/staged_n1_all/result.json')]:
        history=read(path)
        historical_attempts.append(dict(stage=stage,source=str(path.relative_to(ROOT)),sha256=sha(path),
                                         U_J=float(Q(history['safe_upper_bound_J'])),
                                         final_state=history['state'],
                                         phase2_updates=sum(u.get('phase_index')==2 for u in history.get('global_updates',[]))))
    source_paths=['linked_method.py','linked_neighborhood.py','neighborhood.py','neighborhood_method.py',
                  'heft_method.py','staged_method.py','fixed_unit_neighborhood.py']
    input_sources={str((OLD/'linked_n1/result.json').relative_to(ROOT)):sha(OLD/'linked_n1/result.json'),
                   str((NEW/'heft/result.json').relative_to(ROOT)):sha(NEW/'heft/result.json'),
                   str((CODE/'results/linked_quality_pair01/linked_n1/result.json').relative_to(ROOT)):sha(CODE/'results/linked_quality_pair01/linked_n1/result.json'),
                   **{str((CODE/n).relative_to(ROOT)):sha(CODE/n) for n in source_paths}}
    facts=dict(stage='K146',passed=True,research_calls=0,solver_calls=0,thermal_evaluations=0,
               scope='stored JSON and source reading only; no counterfactual schedule/energy/thermal evaluation',
               input_file_sha256=inputs,input_identity=declaration['input_sha256'],source_files_unchanged=165,
               input_sources=input_sources,old301_files_unchanged=True,
               linked_U_J=float(old_high),HEFT_U_J=float(new_high),
               delta_interval_J=[str(old_low-new_high),str(old_high-new_low)],
               HEFT_lower_percent_of_linked=float((old_high-new_high)/old_high*100),
               components=comp_delta,activity_by_stage=activity_delta,physical=physical_summaries,
               domain_membership={'HEFT_full_plan_in_phase1':not any(not r['HEFT_membership'] for r in domain_rows if r['phase']==1),
                                  'HEFT_full_plan_in_phase2':not any(not r['HEFT_membership'] for r in domain_rows if r['phase']==2),
                                  'label_only_comparison':label_comparisons},
               phase_rows=phase_rows,linked_updates=[{k:v for k,v in u.items() if k in ['phase_index','committed_at_s','safe_upper_bound_J','trigger_scene']} for u in linked['global_updates']],
               linked_log_totals=dict(log_totals),linked_decode_states=dict(seen_decodes),
               linked_evaluation_states=dict(seen_receipts),linked_logs=log_summaries,
               second_pass_candidate_hashes=second_candidates,native_requests=native_brief,
               historical_full_open=historical_attempts,
               matlab_startup_s=sum(r['wall_s'] for r in linked['timing']['phase_records'] if r['phase']=='solver_startup'),
               HEFT_local_attempts=dict(Counter(a['kind'] for a in heft['search']['local_attempts'])),
               HEFT_local_accepted=dict(Counter(a['kind'] for a in heft['search']['local_attempts'] if a['accepted'])),
               historical_K140=dict(U_J=float(Q(prior140['safe_upper_bound_J'])),same_seed_units_and_choices=True,
                                    phase2_full_updates=sum(u.get('phase_index')==2 for u in prior140['global_updates'])),
               conclusions={'exact_HEFT_plan_excluded':True,'A_OPP_shared_across_scenes':False,
                            'all_gap_due_to_CPU_placement_proven':False,'thermal_rejection_explains_gap':False,
                            'more_time_would_reach_HEFT_proven':False,'new_block_gain_proven':False})
    assert all(not facts['domain_membership'][key] for key in ['HEFT_full_plan_in_phase1','HEFT_full_plan_in_phase2'])
    (OUT/'facts.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for filename,values in [('energy_by_scene.csv',energy_rows),('energy_components.csv',comp_delta),
                            ('schedules.csv',schedule_rows),('decision_changes.csv',changes),
                            ('deployment.csv',deployment),('HEFT_domain_membership.csv',domain_rows),
                            ('phase_timing.csv',phase_rows),('activity_by_stage.csv',activity_delta),
                            ('native_timing_brief.csv',native_brief),('HEFT_path_drops.csv',path_drops)]:
        write_csv(filename,values)
    print(json.dumps({k:facts[k] for k in ['passed','research_calls','linked_U_J','HEFT_U_J','HEFT_lower_percent_of_linked','components','historical_K140']},ensure_ascii=False))

if __name__=='__main__':
    comparison()
