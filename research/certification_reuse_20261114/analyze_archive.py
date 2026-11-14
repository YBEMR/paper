"""Read archived U07-U10 JSON only. No frozen module imports or evaluator calls."""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path
from statistics import mean, median
import time

COMMIT = '0de4d191966294dc673c21ed244616f1b5a6a85c'
REL = Path('research/chapter4_scheduler/results/onp_new24_20261113')
PROTOCOL = 'directed-decimal60-taylor18-scaled100-v1'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def normalized(value):
    if isinstance(value,dict): return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,list): return [normalized(v) for v in value]
    if isinstance(value,str):
        try: return str(F(value))
        except (ValueError,ZeroDivisionError): return value
    assert not isinstance(value,float), 'No binary floating physical scalar'
    return value

def powers(segments,window):
    full=[]; merged=[]
    for s in segments:
        a,b=F(s['start_ms']),F(s['end_ms'])
        assert b>a and F(s['duration_ms'])==b-a
        assert a==(full[-1][1] if full else 0)
        physics={k:v for k,v in s.items() if k not in ('start_ms','end_ms','duration_ms','active_stage_ids')}
        signature=json.dumps(normalized(physics),sort_keys=True,separators=(',',':'))
        full.append((a,b,signature))
        if merged and merged[-1][2]==signature:
            merged[-1]=(merged[-1][0],b,signature)
        else: merged.append((a,b,signature))
    assert full[-1][1]==window
    return {'segments':full,'merged':merged,'key':tuple(full)}

def common(old,new,window):
    a,b=old['segments'],new['segments']; pre=suf=0
    for x,y in zip(a,b):
        if x!=y: break
        pre+=1
    for x,y in zip(reversed(a),reversed(b)):
        if x!=y: break
        suf+=1
    pt=b[pre-1][1] if pre else F(0)
    st=b[len(b)-suf][0] if suf else window
    fp=F(0); fs=window
    for x,y in zip(old['merged'],new['merged']):
        if x[2]!=y[2]: break
        fp=min(x[1],y[1])
        if x[1]!=y[1]: break
    for x,y in zip(reversed(old['merged']),reversed(new['merged'])):
        if x[2]!=y[2]: break
        fs=max(x[0],y[0])
        if x[0]!=y[0]: break
    return dict(same=a==b,function_same=old['merged']==new['merged'],prefix_segments=pre,suffix_segments=suf,
                prefix_ms=pt,suffix_start_ms=st,function_prefix_ms=fp,function_suffix_start_ms=fs)

def temp_at(scene,entry,when_ms,nodes):
    if when_ms==0: return {n:[str(entry[i]),str(entry[i])] for i,n in enumerate(nodes)}
    matches=[p['temperature_degC'] for p in scene.get('trace',[]) if F(p['time_s'])*1000==when_ms]
    return matches[-1] if matches else None

def order_relation(old,new,nodes):
    if old is None or new is None: return 'boundary_not_archived'
    if old==new: return 'same_interval_box_only'
    if all(Decimal(new[n][1])<=Decimal(old[n][0]) for n in nodes): return 'new_box_colder'
    if all(Decimal(old[n][1])<=Decimal(new[n][0]) for n in nodes): return 'new_box_warmer'
    return 'no_componentwise_box_dominance'

def write_csv(path,rows):
    assert rows
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def describe(values):
    return {'n':len(values),'min':min(values) if values else None,'median':median(values) if values else None,
            'mean':mean(values) if values else None,'max':max(values) if values else None}

def summarize_pairs(rows):
    groups=defaultdict(list)
    for r in rows: groups[(r['reference'],r['phase'])].append(r)
    result=[]
    for (reference,phase),rr in sorted(groups.items()):
        changed=[r for r in rr if not r['same_scene']]
        result.append({'reference':reference,'phase':phase,'scene_pairs':len(rr),
            'unchanged_scenes':sum(r['same_scene'] for r in rr),'changed_scenes':len(changed),
            'changed_with_prefix':sum(r['prefix_segments']>0 for r in changed),
            'changed_with_suffix':sum(r['suffix_segments']>0 for r in changed),
            'changed_prefix_ms':describe([float(F(r['prefix_ms'])) for r in changed]),
            'changed_suffix_ms':describe([float(F(r['suffix_ms'])) for r in changed]),
            'changed_prefix_window_fraction':describe([r['prefix_fraction'] for r in changed]),
            'changed_suffix_window_fraction':describe([r['suffix_fraction'] for r in changed]),
            'changed_function_prefix_window_fraction':describe([r['function_prefix_fraction'] for r in changed]),
            'changed_function_suffix_window_fraction':describe([r['function_suffix_fraction'] for r in changed]),
            'changed_segments':sum(r['current_segments'] for r in changed),
            'changed_prefix_segments':sum(r['prefix_segments'] for r in changed),
            'changed_suffix_segments':sum(r['suffix_segments'] for r in changed),
            'changed_committed_panels':sum(r['current_committed_panels'] for r in changed),
            'changed_prefix_panels':sum(r['prefix_committed_panels'] for r in changed),
            'changed_suffix_panels':sum(r['suffix_committed_panels'] for r in changed),
            'changed_suffix_state_relations':dict(Counter(r['suffix_state_relation'] for r in changed)),
            'functional_vs_event_prefix_difference':sum(r['function_prefix_ms']!=r['prefix_ms'] for r in changed),
            'functional_vs_event_suffix_difference':sum(r['function_suffix_ms']!=r['suffix_ms'] for r in changed)})
    return result

def main(cache,out):
    started=time.perf_counter(); base=cache/REL; out.mkdir(parents=True,exist_ok=True)
    candidate_rows=[]; pair_rows=[]; run_rows=[]; phase_rows=[]; checks=[]
    for call in sorted((base/'execution/calls').iterdir()):
        if not call.is_dir(): continue
        raw=read(call/'method/result.json'); ret=read(call/'method_return.json')
        case='U'+call.name.split('_U')[1][:2]; arm=call.name.split('__n24_')[1]
        inp=read(base/'execution/frozen_inputs'/f'{case}__n24'/'instance.json')
        cfg=read(base/'execution/frozen_inputs'/f'{case}__n24'/'config.json')
        context=raw['root_context']; window=F(inp['window_ms']); nodes=inp['platform']['node_order']
        assert context['input_sha256']==digest(inp)==raw['input_sha256']
        assert context['config_sha256']==digest(cfg)
        assert context['accuracy_sha256']==digest(cfg['accuracy_targets'])
        scenes={s['id']:s for s in inp['scenarios']}; assert len(scenes)==2
        journal=[json.loads(l) for l in (call/'method_evaluation_journal.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
        js=[j for j in journal if j['event']=='START']; jr={j['ordinal']:j for j in journal if j['event']=='RETURN'}
        evaluated=[e for e in raw['evaluations'] if not e.get('cache_hit',False)]
        assert len(js)==len(evaluated)==ret['counts']['evaluation_attempts']
        assert [j['candidate_sha256'] for j in js]==[e['candidate_sha256'] for e in evaluated]
        by_sha={}; prior_scene={sid:{} for sid in scenes}; previous=None; incumbent=None
        proposals={p['candidate_sha256']:p for p in raw['graph_proposals']}
        last_panels=last_refinements=0; phase_counter=Counter(); committed_total=0; safe_durations=[]
        for ordinal,(e,j) in enumerate(zip(evaluated,js),1):
            receipt=e['receipt']; phase=e['phase']; phase_counter[phase]+=1
            assert e['context']==context and digest(e['candidate'])==e['candidate_sha256']
            assert receipt['evidence_identity']=={'input_sha256':digest(inp),'candidate_sha256':e['candidate_sha256']}
            assert receipt['numerical_protocol']==PROTOCOL
            assert receipt['control_policy']=={'idle_policy':'auto_low_immediate_v1','idle_delay_ms':'0'}
            assert receipt['legality']['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED'
            if phase=='refinement':
                parent=by_sha[proposals[e['candidate_sha256']]['base_candidate_sha256']]
            else: parent=incumbent
            info={'e':e,'power':{},'ordinal':ordinal}
            panels=receipt['panels']-last_panels; refinements=receipt['refinements']-last_refinements
            assert panels>=0 and refinements>=0
            last_panels=receipt['panels'];last_refinements=receipt['refinements']
            total_segments=committed=whole_scenes=whole_segments=whole_panels=parent_prefix_segments=parent_prefix_panels=0
            changed_counts={}; parent_cert_before=True
            for sid,sc in scenes.items():
                ps=powers(receipt['legality']['scenes'][sid]['segments'],window); info['power'][sid]=ps
                trace=receipt['scenes'].get(sid,{}).get('trace',[])
                nseg=len(ps['segments']); ntrace=len(trace);total_segments+=nseg;committed+=ntrace
                history=prior_scene[sid].get(ps['key'])
                if history is not None:
                    assert history['e']['receipt']['completed_at_elapsed_s']<j['started_at_s']
                    whole_scenes+=1;whole_segments+=nseg;whole_panels+=ntrace
                    old_full=history['e']['receipt']['scenes'][sid]
                    current_full=receipt['scenes'].get(sid,{})
                    if current_full.get('state')=='SAFE':
                        semantic=lambda s:{k:v for k,v in s.items() if k not in ('elapsed_s','completed_at_elapsed_s')}
                        assert semantic(old_full)==semantic(current_full), 'Identical power history has different certified data'
                for label,ref in [('adjacent',previous),('incumbent',parent)]:
                    if ref is None: continue
                    assert ref['ordinal']<ordinal
                    cp=common(ref['power'][sid],ps,window)
                    changed_counts[label]=changed_counts.get(label,0)+(not cp['same'])
                    pp=sum(t['segment']<cp['prefix_segments'] for t in trace)
                    sp=sum(t['segment']>=nseg-cp['suffix_segments'] for t in trace)
                    suffix_start=cp['suffix_start_ms']
                    old_scene=ref['e']['receipt']['scenes'].get(sid,{})
                    cur_scene=receipt['scenes'].get(sid,{})
                    old_trace={t['time_s']:t['temperature_degC'] for t in old_scene.get('trace',[])}
                    for t in trace:
                        if t['segment']<cp['prefix_segments']:
                            assert old_trace[t['time_s']]==t['temperature_degC'], 'Same prefix differs at archived temperature checkpoint'
                    relation='no_common_suffix'
                    if cp['suffix_segments']:
                        relation=order_relation(temp_at(old_scene,sc['entry']['temperature_degC'],suffix_start,nodes),
                            temp_at(cur_scene,sc['entry']['temperature_degC'],suffix_start,nodes),nodes)
                    pair_rows.append(dict(run=call.name,case=case,arm=arm,ordinal=ordinal,phase=phase,state=receipt['state'],
                        reference=label,reference_ordinal=ref['ordinal'],scene_id=sid,same_scene=cp['same'],function_same=cp['function_same'],
                        current_segments=nseg,current_committed_panels=ntrace,prefix_segments=cp['prefix_segments'],suffix_segments=cp['suffix_segments'],
                        prefix_committed_panels=pp,suffix_committed_panels=sp,prefix_ms=str(cp['prefix_ms']),suffix_ms=str(window-suffix_start),
                        prefix_fraction=float(cp['prefix_ms']/window),suffix_fraction=float((window-suffix_start)/window),
                        function_prefix_ms=str(cp['function_prefix_ms']),function_suffix_ms=str(window-cp['function_suffix_start_ms']),
                        function_prefix_fraction=float(cp['function_prefix_ms']/window),function_suffix_fraction=float((window-cp['function_suffix_start_ms'])/window),
                        suffix_state_relation=relation,prefix_temperature_trace_identical=True))
                    if label=='incumbent':
                        assert ref['e']['accepted_safe'] and ref['e']['receipt']['state']=='SAFE'
                        assert ref['e']['receipt']['completed_at_elapsed_s']<j['started_at_s']
                        if history is None:
                            parent_prefix_segments+=cp['prefix_segments'];parent_prefix_panels+=pp
            duration=jr[ordinal]['returned_at_s']-j['started_at_s']; assert duration>=0
            if receipt['state']=='SAFE': safe_durations.append(duration)
            assert panels>=committed
            candidate_rows.append(dict(run=call.name,case=case,arm=arm,ordinal=ordinal,phase=phase,state=receipt['state'],
                candidate_sha256=e['candidate_sha256'],actual_cache_hit=e.get('cache_hit',False),accepted=e['incumbent_replaced'],
                start_s=j['started_at_s'],return_s=jr[ordinal]['returned_at_s'],evaluation_wall_s=duration,
                panel_attempts=panels,committed_panels=committed,uncommitted_panel_attempts=panels-committed,refinements=refinements,
                segments=total_segments,adjacent_changed_scenes=changed_counts.get('adjacent'),incumbent_changed_scenes=changed_counts.get('incumbent'),
                prior_certified_scene_hits=whole_scenes,whole_scene_segments=whole_segments,whole_scene_panels=whole_panels,
                extra_incumbent_prefix_segments=parent_prefix_segments,extra_incumbent_prefix_panels=parent_prefix_panels))
            if receipt['state']=='SAFE':
                assert e['accepted_safe'] and receipt['completed_at_elapsed_s']<context['root_seconds']
                for sid in scenes: prior_scene[sid][info['power'][sid]['key']]=info
            if e['incumbent_replaced']: incumbent=info
            by_sha[e['candidate_sha256']]=info;previous=info;committed_total+=committed
        assert ret['counts']['cache_hits']==raw['cache_hits']==0
        timing=raw['timing']; handoff=ret['metrics']['initialization_completed_at_s']
        search_evaluation=sum(p['exclusive_s'] for p in timing['phase_records'] if p['phase']=='complete_continuous_evaluation' and p['start_s']>=handoff)
        search_time=ret['metrics']['search_s']
        run_rows.append(dict(run=call.name,case=case,arm=arm,evaluations=len(evaluated),initialization_evaluations=phase_counter['initialization'],
            refinement_evaluations=phase_counter['refinement'],safe_evaluations=len(safe_durations),unresolved_evaluations=len(evaluated)-len(safe_durations),
            cache_hits=raw['cache_hits'],method_s=timing['method_elapsed_s'],evaluation_s=timing['phases_exclusive_s']['complete_continuous_evaluation'],
            external_legality_and_power_s=timing['phases_exclusive_s']['complete_legality'],unattributed_s=timing['unattributed_s'],
            search_s=search_time,search_evaluation_s=search_evaluation,search_evaluation_fraction=search_evaluation/search_time if search_time else None,
            mean_SAFE_evaluation_s=mean(safe_durations),attempted_panels=last_panels,committed_panels=committed_total,refinements=last_refinements))
        for name,seconds in timing['phases_exclusive_s'].items():phase_rows.append(dict(run=call.name,case=case,arm=arm,phase=name,seconds=seconds))
        checks.append({'run':call.name,'journal_order_and_counts':True,'candidate_and_input_identity':True,'context_constant':True,
            'safe_sources_precede_use':True,'cumulative_counters_differenced':True,'same_power_complete_scene_semantics_equal':True,
            'same_prefix_temperature_traces_equal':True,'raw_rows':len(raw['evaluations'])})
        print(f"{call.name}: {len(evaluated)} archived evaluations",flush=True)
    assert len(candidate_rows)==855 and sum(r['state']=='SAFE' for r in candidate_rows)==845
    aggregates=[]
    for phase in ['all','initialization','refinement']:
        rows=[r for r in candidate_rows if phase=='all' or r['phase']==phase]
        item={'phase':phase,'evaluations':len(rows),'SAFE':sum(r['state']=='SAFE' for r in rows),'UNRESOLVED':sum(r['state']=='UNRESOLVED' for r in rows)}
        for key in ('segments','panel_attempts','committed_panels','uncommitted_panel_attempts','refinements','prior_certified_scene_hits','whole_scene_segments','whole_scene_panels','extra_incumbent_prefix_segments','extra_incumbent_prefix_panels'):
            item[key]=sum(r[key] for r in rows)
        for key in ('adjacent_changed_scenes','incumbent_changed_scenes'):
            item[key]=dict(Counter(str(r[key]) for r in rows))
        item['scene_query_count']=2*len(rows)
        item['whole_scene_panel_fraction']=item['whole_scene_panels']/item['committed_panels']
        item['whole_plus_prefix_panel_fraction']=(item['whole_scene_panels']+item['extra_incumbent_prefix_panels'])/item['committed_panels']
        aggregates.append(item)
    incumbent_coverage=[]
    group_keys=[('all',p) for p in ['all','initialization','refinement']]+[(c,p) for c in ['U07','U08','U09','U10'] for p in ['initialization','refinement']]
    for case,phase in group_keys:
        cc=[r for r in candidate_rows if (case=='all' or r['case']==case) and (phase=='all' or r['phase']==phase)]
        pp=[r for r in pair_rows if r['reference']=='incumbent' and (case=='all' or r['case']==case) and (phase=='all' or r['phase']==phase)]
        denom=sum(r['committed_panels'] for r in cc)
        whole=sum(r['current_committed_panels'] for r in pp if r['same_scene'])
        prefix=sum(r['prefix_committed_panels'] for r in pp if not r['same_scene'])
        incumbent_coverage.append(dict(case=case,phase=phase,evaluations=len(cc),committed_panels=denom,
            whole_scene_panels=whole,changed_scene_prefix_panels=prefix,combined_panel_fraction=(whole+prefix)/denom,
            zero_reusable_panel_candidates=sum(not any(p['ordinal']==r['ordinal'] and p['run']==r['run'] and p['prefix_committed_panels']>0 for p in pp) for r in cc)))
    cost={'method_s':sum(r['method_s'] for r in run_rows),'evaluation_s':sum(r['evaluation_s'] for r in run_rows),
        'external_legality_and_power_s':sum(r['external_legality_and_power_s'] for r in run_rows),
        'unattributed_s':sum(r['unattributed_s'] for r in run_rows),
        'search_s':sum(r['search_s'] for r in run_rows),'search_evaluation_s':sum(r['search_evaluation_s'] for r in run_rows)}
    summary={'status':'ANALYZED_READ_ONLY_NOT_SPEED_BENCHMARK','commit':COMMIT,'runs':16,'aggregates':aggregates,
        'pair_summary':summarize_pairs(pair_rows),'incumbent_coverage':incumbent_coverage,'cost':cost,'actual_full_hash_cache_hits':0,
        'new_scientific_calls':0,'wall_speedup':None,'thermal_subphase_timings':None,
        'candidate_archive_sha_verified_separately':True,'analysis_wall_s':time.perf_counter()-started}
    write_csv(out/'candidates.csv',candidate_rows);write_csv(out/'scene_pairs.csv',pair_rows)
    write_csv(out/'runs.csv',run_rows);write_csv(out/'timing_phases.csv',phase_rows)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'consistency_checks.json').write_text(json.dumps({'status':'PASS_STATIC_ARCHIVE_CONSISTENCY','runs':checks,
        'new_scientific_calls':0,'frozen_code_imported':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'evaluations':len(candidate_rows),'scene_pair_rows':len(pair_rows),'wall_s':summary['analysis_wall_s']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--cache',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();main(args.cache,args.out)
