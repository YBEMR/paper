"""Read archived logs and compute necessary-condition certificates only.

No research-module imports, candidate reconstruction, initializer, optimization,
thermal integration, candidate re-evaluation, or wall-clock counterfactual run.
"""
from bisect import bisect_right
from collections import Counter,defaultdict
from fractions import Fraction as F
import csv
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
REPO=next(p for p in OUT.parents if (p/'RESEARCH_BRIEF.md').is_file())
ARCHIVE=REPO/'research/chapter4_scheduler/results/scale24_i1_20261113'
EX=ARCHIVE/'execution'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda name,v:(OUT/name).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def csv_save(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        keys=list(dict.fromkeys(k for r in rows for k in r))
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def graph_data(ins):
    result={}
    for scene in ins['scenarios']:
        nodes={x['id']:x for x in scene['stage_instances']}
        succ={n:set() for n in nodes};pred={n:set() for n in nodes}
        for u,v in scene['dependencies']:succ[u].add(v);pred[v].add(u)
        order=[];pending=set(nodes)
        while pending:
            ready=sorted(n for n in pending if pred[n]<=set(order));assert ready
            order.extend(ready);pending.difference_update(ready)
        reach={n:set() for n in nodes}
        for n in reversed(order):
            for v in succ[n]:reach[n].add(v);reach[n].update(reach[v])
        req={r['id']:r for r in scene['requests']}
        result[scene['id']]={'nodes':nodes,'succ':succ,'pred':pred,'order':order,'reach':reach,'requests':req}
    return result


def static_bounds(ins,dag,incumbent,base):
    """DAG-only earliest and latest starts: necessary bounds, not a schedule."""
    rows={r['stage_id']:r for r in incumbent['scenes'][base['scene_id']]}
    grid=F(ins['start_grid_ms']);ceil=lambda x:-((-x)//grid)*grid;floor=lambda x:(x//grid)*grid
    affected=set(base['selected_stages'])
    for n in base['selected_stages']:affected.update(dag['reach'][n])
    duration={};earliest={};latest={};dues={}
    for n in dag['order']:
        row=rows[n];opp=base['opp_overrides'].get(n,row['opp'])
        modes=[m for m in ins['stage_modes'][dag['nodes'][n]['shared_stage_id']] if m['unit_id']==row['unit'] and m['opp_id']==opp]
        assert len(modes)==1;duration[n]=F(modes[0]['duration_ms']);assert duration[n]>0
        req=dag['requests'][dag['nodes'][n]['request_id']]
        lower=max(F(0),F(req['release_ms']))
        if base['template']=='preserve' and n not in affected:lower=max(lower,F(row['start_ms']))
        earliest[n]=ceil(max([lower]+[earliest[p]+duration[p] for p in dag['pred'][n]]))
        dues[n]=min(F(req['deadline_ms']),F(ins['window_ms']))
    for n in reversed(dag['order']):
        latest[n]=floor(min([dues[n]-duration[n]]+[latest[v]-duration[n] for v in dag['succ'][n]]))
    impossible=[n for n in dag['order'] if earliest[n]>latest[n]]
    return rows,duration,earliest,latest,impossible,ceil


def curve(raw):
    return [{'time_s':e['at_s'],'transferred_at_s':e['transferred_at_s'],
        'phase':e['phase'],'energy_upper_J':str(F(e['energy']['upper'])),
        'energy_upper_J_decimal':float(F(e['energy']['upper'])),'candidate_sha256':e['candidate_sha256']} for e in raw['events']]


def trajectories(raw):
    ev={e['candidate_sha256']:e for e in raw['evaluations']}
    current=raw['initial_safe_snapshot'];result=[]
    for i,p in enumerate(raw['graph_proposals'],1):
        if not p['strict_accepted']:continue
        new=ev[p['candidate_sha256']];assert F(new['receipt']['weighted_energy_J'][1])<F(current['receipt']['weighted_energy_J'][0])
        assert p['base_candidate_sha256']==current['candidate_sha256']
        changes=[]
        for sid,rs in new['candidate']['scenes'].items():
            old={r['stage_id']:r for r in current['candidate']['scenes'][sid]}
            for r in rs:
                if r!=old[r['stage_id']]:changes.append({'scene_id':sid,'before':old[r['stage_id']],'after':r})
        result.append({'step':len(result)+1,'proposal_index':i,'proposed_at_s':p['proposed_at_s'],
            'formed_at_s':new['receipt']['completed_at_elapsed_s'],'returned_at_s':new['returned_at_s'],
            'target':p['energy_target'],'selected_stages':p['selected_stages'],
            'extra_edges':p['additional_reversed_edges'],'base_sha256':p['base_candidate_sha256'],
            'candidate_sha256':p['candidate_sha256'],'energy_upper_J':str(F(new['receipt']['weighted_energy_J'][1])),
            'drop_J':str(F(current['receipt']['weighted_energy_J'][1])-F(new['receipt']['weighted_energy_J'][1])),
            'changes':changes})
        current=new
    assert current['candidate']==raw['safe_candidate']
    return result


def diagnose_one(slot,raw,ins,ret):
    steps=trajectories(raw);ev={e['candidate_sha256']:e for e in raw['evaluations']}
    states=[raw['initial_safe_snapshot']['candidate']]+[ev[s['candidate_sha256']]['candidate'] for s in steps]
    state_hashes=[raw['initial_safe_snapshot']['candidate_sha256']]+[s['candidate_sha256'] for s in steps]
    phases=[x for x in raw['timing']['phase_records'] if x['phase']=='blocking_graph_construct']
    starts=[x['start_s'] for x in raw['timing']['phase_records'] if x['phase']=='activity_saving_targets']
    assert len(starts)<=len(states)
    groups=[]
    for i,d in enumerate(raw['reconstruction_attempts']):
        if d['extra_resource_edge'] is None:groups.append({'base':d,'index':i,'extras':[]})
        else:
            assert groups;g=groups[-1]
            assert all(d[k]==g['base'][k] for k in ('target','scene_id','selected_stages','opp_overrides','orientation','template'))
            assert d['base_blocking_traces']==g['base']['blocking_traces']
            g['extras'].append((i,d))
    assert len(phases)-len(groups) in (0,1)
    if len(phases)>len(groups):assert phases[-1].get('exception')=='Exhausted'
    dags=graph_data(ins);domains={u['id']:u['domain_id'] for u in ins['platform']['units']}
    stats=Counter();failures=Counter();rows=[];round_rows=[];proofs=[];fail_stage=Counter();failed_targets=Counter()
    for dag in dags.values():assert all(F(r['deadline_ms'])<=F(ins['window_ms']) for r in dag['requests'].values())
    for j,g in enumerate(groups):
        phase=phases[j];round_id=bisect_right(starts,phase['start_s'])-1;assert 0<=round_id<len(states)
        base=g['base'];dag=dags[base['scene_id']]
        prior,duration,early,late,impossible,ceil=static_bounds(ins,dag,states[round_id],base)
        selected=base['selected_stages'];cycle=False
        if base['orientation']=='reverse' and len(selected)==2:
            u,v=selected;ru,rv=prior[u],prior[v]
            ou=base['opp_overrides'].get(u,ru['opp']);ov=base['opp_overrides'].get(v,rv['opp'])
            resource=ru['unit']==rv['unit'] or (domains[ru['unit']]==domains[rv['unit']] and ou!=ov)
            cycle=resource and (v in dag['reach'][u] or u in dag['reach'][v])
        if cycle:assert base['reason']=='SKELETON_DIRECTED_CYCLE'
        if impossible:assert base['state']!='COMPLETE_LEGAL_CANDIDATE'
        stats['base_static_dependency_cycle_certificates']+=cycle
        stats['base_DAG_bound_certificates']+=bool(impossible)
        stats['base_union_certificates']+=cycle or bool(impossible)
        mixed=bool(g['extras']);stats['base_count']+=1;stats['mixed_group_count']+=mixed
        stats['mixed_group_wall_s']+=phase['wall_s'] if mixed else 0
        stats['base_only_group_wall_s']+=phase['wall_s'] if not mixed else 0
        round_rows.append({'slot':slot,'round':round_id,'base_sha256':state_hashes[round_id],
            'group':j,'diag_index':g['index'],'start_s':phase['start_s'],'end_s':phase['end_s'],'wall_s':phase['wall_s'],
            'target':base['target']['stage_id'],'target_opp':base['target']['target_opp'],
            'base_reason':base['reason'],'extra_count':len(g['extras']),'base_cycle_certificate':cycle,
            'template':base['template'],'base_DAG_bound_certificate':bool(impossible)})
        all_certified=True
        for idx,d in [(g['index'],base)]+g['extras']:
            extra=d['extra_resource_edge'] is not None;kind='extra' if extra else 'base'
            failures[(kind,d['reason'] or 'LEGAL')]+=1
            timed=d['reason']=='SKELETON_DEADLINE_OR_WINDOW_EXCEEDED'
            window=timed and any(F(v['end_ms'])>F(ins['window_ms']) for v in d['deadline_violations'])
            stats[kind+'_deadline_and_window_failures']+=window
            stats[kind+'_deadline_only_failures']+=timed and not window
            for v in d['deadline_violations']:
                if timed:fail_stage[(kind,d['scene_id'],v['stage_id'])]+=1
            if d['reason']:failed_targets[(kind,d['target']['stage_id'],d['target']['target_opp'])]+=1
            if not extra:continue
            stats['extra_count']+=1;u,v=d['extra_resource_edge'];unchanged=[]
            for tr in base['blocking_traces']:
                if (u,v) not in {(e['from'],e['to']) for e in tr['edges']}:unchanged.append(tr['stage_id'])
            edge_lower=ceil(max(early[u],early[v]+duration[v]))
            bound=bool(impossible) or edge_lower>late[u]
            cert=bool(unchanged) or bound
            if cert:assert d['state']!='COMPLETE_LEGAL_CANDIDATE'
            stats['extra_unaffected_path_certificates']+=bool(unchanged)
            stats['extra_dag_edge_bound_certificates']+=bound
            stats['extra_union_certificates']+=cert
            stats['extra_legal']+=d['state']=='COMPLETE_LEGAL_CANDIDATE'
            all_certified=all_certified and cert
            item={'slot':slot,'diag_index':idx,'group':j,'round':round_id,
                'extra_edge':[u,v],'observed_state':d['state'],'observed_reason':d['reason'],
                'template':base['template'],
                'unaffected_late_stages':unchanged,'DAG_infeasible_stages':impossible,
                'reverse_edge_start_lower_ms':str(edge_lower),'latest_start_upper_ms':str(late[u]),
                'bound_reject':bound,'certified_reject':cert,'base_sha256':state_hashes[round_id]}
            proofs.append(item)
        if mixed and all_certified:
            stats['all_extra_certified_groups']+=1
            stats['all_extra_certified_mixed_wall_s']+=phase['wall_s']
    stats['unlogged_terminal_graph_wall_s']=sum(x['wall_s'] for x in phases[len(groups):])
    assert abs(stats['mixed_group_wall_s']+stats['base_only_group_wall_s']+stats['unlogged_terminal_graph_wall_s']-ret['metrics']['graph_construction_s'])<1e-6
    return {'stats':dict(stats),'reason_counts':[{'kind':k,'reason':v,'count':n} for (k,v),n in sorted(failures.items())],
        'late_task_counts':[{'kind':k,'scene':sid,'stage_id':iid,'count':n} for (k,sid,iid),n in fail_stage.most_common()],
        'failed_target_counts':[{'kind':k,'stage_id':iid,'opp':opp,'count':n} for (k,iid,opp),n in failed_targets.most_common()],
        'groups':round_rows,'certificates':proofs,'steps':steps,'curve':curve(raw)}


def initializer_comparison(on,off,onret,offret):
    a=[e for e in on['evaluations'] if e['phase']=='initialization']
    b=[e for e in off['evaluations'] if e['phase']=='initialization']
    n=0
    for x,y in zip(a,b):
        if x['candidate_sha256']!=y['candidate_sha256']:break
        assert x['receipt']['weighted_energy_J']==y['receipt']['weighted_energy_J']
        assert x['incumbent_replaced']==y['incumbent_replaced'];n+=1
    clean=lambda m:[{k:v for k,v in x.items() if k!='admitted_at_s'} for x in m['local_attempts']]
    la,lb=clean(on['initialization']),clean(off['initialization'])
    k=next((i for i,(x,y) in enumerate(zip(la,lb)) if x!=y),min(len(la),len(lb)))
    rows=[]
    ja=onret['evaluation_attempts_journal'];jb=offret['evaluation_attempts_journal']
    for i in range(max(len(a),len(b))):
        row={'ordinal':i+1}
        for label,es,js in (('ON',a,ja),('OFF',b,jb)):
            if i<len(es):
                e,j=es[i],js[i];assert e['candidate_sha256']==j['candidate_sha256']
                row.update({label+'_sha256':e['candidate_sha256'],label+'_source':e['source'],
                    label+'_admitted_s':e['evaluation_admitted_at_s'],label+'_returned_s':e['returned_at_s'],
                    label+'_evaluation_s':j['returned_at_s']-j['started_at_s'],
                    label+'_energy_upper_J':float(F(e['receipt']['weighted_energy_J'][1])),
                    label+'_replaced':e['incumbent_replaced']})
        rows.append(row)
    firstdiff=[]
    ca=on['initial_safe_snapshot']['candidate'];cb=off['initial_safe_snapshot']['candidate']
    prefix_best=next(e for e in reversed(b[:n]) if e['incumbent_replaced'])
    assert ca==prefix_best['candidate']
    assert on['initial_safe_snapshot']['receipt']['weighted_energy_J']==prefix_best['receipt']['weighted_energy_J']
    for sid,rs in ca['scenes'].items():
        other={x['stage_id']:x for x in cb['scenes'][sid]}
        firstdiff.extend({'scene':sid,'ON':x,'OFF':other[x['stage_id']]} for x in rs if x!=other[x['stage_id']])
    return {'ON_evaluations':len(a),'OFF_evaluations':len(b),'identical_candidate_and_energy_prefix':n,
        'local_attempt_identical_prefix':k,'ON_local_attempts':len(la),'OFF_local_attempts':len(lb),
        'ON_is_exact_OFF_prefix':n==len(a) and k==len(la),
        'ON_initial_equals_OFF_best_after_common_prefix':True,
        'common_prefix_best_sha256':prefix_best['candidate_sha256'],
        'common_prefix_return_time_gap_s':a[n-1]['returned_at_s']-b[n-1]['returned_at_s'],
        'ON_stop':on['initialization']['admission_stop'],'OFF_stop':off['initialization']['admission_stop'],
        'common_prefix_ON_eval_s':sum(r['ON_evaluation_s'] for r in rows[:n]),
        'common_prefix_OFF_eval_s':sum(r['OFF_evaluation_s'] for r in rows[:n]),
        'additional_OFF_local_attempts':off['initialization']['local_attempts'][k:],
        'initial_candidate_changes':firstdiff,'rows':rows}


def main():
    plan=read(EX/'plan.json');manifest=read(ARCHIVE/'files_sha256.json')
    consumed=[EX/'plan.json',EX/'summary.json']
    selected=[s for s in plan['slots'] if s['arm'] in ('ON','OFF')]
    raw={};rets={};results={}
    for s in selected:
        folder=EX/'calls'/s['id'];paths=[folder/'method/result.json',folder/'method/input_instance.json',folder/'method_return.json']
        consumed.extend(paths)
        r,ins,ret=map(read,paths);raw[s['id']]=r;rets[s['id']]=ret
        results[s['id']]=diagnose_one(s['id'],r,ins,ret)
    for p in consumed:assert sha(p)==manifest[p.relative_to(REPO).as_posix()]
    for n,h in plan['source_sha256'].items():assert sha(REPO/n)==h
    init=initializer_comparison(raw['04_U04__n24_ON_I1'],raw['05_U04__n24_OFF_I1'],rets['04_U04__n24_ON_I1'],rets['05_U04__n24_OFF_I1'])
    compact={k:{n:v for n,v in r.items() if n not in ('groups','certificates')} for k,r in results.items()}
    save('diagnostic.json',{'scope':'READ_ONLY_ARCHIVED_LOGS_AND_NECESSARY_BOUND_ARITHMETIC','source_commit':'581a77ed8dafb4099d4acd186c554db03cb23969',
        'real_method_calls':0,'thermal_evaluations':0,'new_candidate_reconstructions':0,'algorithm_changed':False,
        'unchanged_frozen_sources':len(plan['source_sha256']),'input_sha256':{p.relative_to(REPO).as_posix():sha(p) for p in consumed},
        'runs':compact,'U04_initializer':{k:v for k,v in init.items() if k!='rows'}})
    save('necessary_condition_certificates.json',[c for r in results.values() for c in r['certificates']])
    csv_save('graph_groups.csv',[g for r in results.values() for g in r['groups']])
    csv_save('U04_initialization_prefix.csv',init['rows'])
    csv_save('energy_time.csv',[{'slot':k,**x} for k,r in results.items() for x in r['curve']])
    csv_save('accepted_steps.csv',[{'slot':k,'step':x['step'],'formed_at_s':x['formed_at_s'],
        'energy_upper_J':float(F(x['energy_upper_J'])),'drop_J':float(F(x['drop_J'])),
        'target':x['target']['stage_id'],'old_opp':x['target']['old_opp'],'target_opp':x['target']['target_opp'],
        'extra_edges':json.dumps(x['extra_edges']),'candidate_sha256':x['candidate_sha256']} for k,r in results.items() for x in r['steps']])
    print(json.dumps({'runs':{k:v['stats'] for k,v in results.items()},'U04_init':{k:v for k,v in init.items() if k not in ('rows','initial_candidate_changes','additional_OFF_local_attempts')}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
