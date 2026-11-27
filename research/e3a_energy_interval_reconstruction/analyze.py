"""Audit frozen run receipts and recover physical mechanism examples from saved candidates."""
import collections,csv,gzip,itertools,sys
from fractions import Fraction
from shared import *
from run import logs,improves,native_plan
RESULT=HERE/'results'
CASES=('D1','D2','C10')
def table(name,rows):
    if not rows:return
    with (RESULT/name).open('w',newline='',encoding='utf8') as f:
        fields=list(dict.fromkeys(k for row in rows for k in row))
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def additions(p,base,plan):
    rows,low=plan;old,flags=base
    return dict(stage_changes=[dict(request=i//3,stage=('pre','main','post')[i%3],old=a,new=b,
                    old_end=p.finish(i,a),new_end=p.finish(i,b)) for i,(a,b) in enumerate(zip(old,rows)) if a!=b],
            low_added=sorted(low-flags),low_removed=sorted(flags-low))
def compare_pairs(pool,certs):
    unique={r['plan']:r for r in pool}
    strict=0;largest=None;nties=0
    for x,y in itertools.combinations(unique.values(),2):
        a,b=certs[x['plan']],certs[y['plan']]
        if a==b:nties+=1;continue
        if a>b:x,y,a,b=y,x,b,a
        if x['bounds'][0]<=y['bounds'][1]:continue
        delta=x['J']-y['J']
        strict+=1
        if largest is None or delta>largest[0]:largest=(delta,x,y,float(b-a))
    return dict(unique_SAFE=len(unique),pairs=len(unique)*(len(unique)-1)//2,reference_ties=nties,
        reversals=strict,largest=([largest[1],largest[2],largest[3],largest[0]] if largest else None))
def main():
    RESULT.mkdir(exist_ok=True)
    endrows=[];stage_rows=[];reversals=[];rankings=[];energy_rows=[];windows=[];mechanisms={};accepted=[]
    pre=read(RUN/'preflight/receipt.json')
    budget=[dict(case='all',arm='preflight',budget_s=600,charged_s=pre['wall_s']+pre['historical_inventory_reserved_s'],wall_s=pre['wall_s'],reservation_s=pre['historical_inventory_reserved_s'])]
    gate=read(RUN/'gate.json')
    for c in CASES:
        p,seed=load_native(c); case_root=RUN/c;diag=case_root/'diagnostic'
        ident=read(DATA/c/'identity.json');records=logs(diag/'candidates.jsonl')
        base=records[0]['result'];certs={};physical=diag/'physical'
        for f in (physical/'certificates').glob('*.json'):certs[f.stem]=Fraction(read(f)['exact_E35_J'])
        regionlist=read(diag/'regions.json');rby={x['id']:x for x in regionlist}
        for window in regionlist:windows.append(dict(case=c,**window))
        seeds=[r['result'] for r in records if r.get('result',{}).get('status')=='SAFE']
        pool=read(diag/'probe_pool.json')
        by_key={r['plan']:r for r in seeds}
        groups={'all_phase1':seeds,'common_probes':[by_key[z['plan']] for z in pool if z['plan']]}
        for rid in rby:
            groups['region_'+str(rid)]=[r['result'] for r in records if r.get('region')==rid and r.get('result',{}).get('status')=='SAFE']
        for label,items in groups.items():
            row=compare_pairs(items,certs)
            if row['largest']:
                x,y,refd,reald=row['largest']
                row.update(ordinary_choice=x['plan'],thermal_choice=y['plan'],ref_penalty_J=refd,true_saving_J=reald)
                if label in ['all_phase1','common_probes']:
                    mechanisms[c+'_'+label+'_reversal']=dict(reference_preferred=x,thermal_preferred=y,
                        reference_difference_J=refd,thermal_difference_J=reald,
                        accounting_delta_J={k:y[k]-x[k] for k in ['activity','base','switch','temperature','external']},
                        witness_rows=[{k:v for k,v in r.items() if k not in ('result','solver')} for h in (x['plan'],y['plan']) for r in [next(r for r in records if r.get('result',{}).get('plan')==h)]])
            del row['largest'];reversals.append(dict(case=c,pool=label,**row))
        for arm in ['diagnostic']+(list('ABCD') if gate['open'] else []):
            folder=case_root/arm;receipt=read(folder/'receipt.json');allrows=logs(folder/'candidates.jsonl')
            assert receipt['status']=='COMPLETE' and receipt['wall_s']<=receipt['budget_s']
            assert all(x.get('solver',{}).get('local_wall_s',0)<=30 for x in allrows)
            assert all(r['wall_s']<=receipt['budget_s'] for r in allrows)
            assert receipt['initial']==base
            best=receipt['best'];results=[x['result'] for x in allrows if x.get('result',{}).get('status')=='SAFE']
            assert all(not improves(x,best) for x in results)
            budget.append(dict(case=c,arm=arm,budget_s=receipt['budget_s'],charged_s=receipt['wall_s'],
                               wall_s=receipt['wall_s'],cpu_s=receipt['cpu_s'],single_cpu=receipt['core'][0],
                               local_calls=sum('solver' in r for r in allrows),max_local_s=max((r['solver']['local_wall_s'] for r in allrows if 'solver'in r),default=0)))
            running=base
            for row in allrows:
                x=row.get('result',{})
                if x.get('status')!='SAFE' or not improves(x,running):continue
                accepted.append(dict(case=c,arm=arm,seq=row['seq'],wall_s=row['wall_s'],mode=row['kind'],
                    region=row.get('region'),request_ids=row.get('requests'),before=running['plan'],after=x['plan'],
                    saving_J=running['J']-x['J'],baseline_saving_J=base['J']-x['J'],
                    reference_saving_J=running['E35']-x['E35'],correction_saving_J=running['temperature']-x['temperature']))
                running=x
            assert running['plan']==best['plan']
            baseline_plan=native_plan(folder/'physical/plans'/(base['plan']+'.json.gz'))
            final_plan=native_plan(folder/'physical/plans'/(best['plan']+'.json.gz'))
            changes=additions(p,baseline_plan,final_plan)
            endrows.append(dict(case=c,arm=arm,baseline_J=base['J'],SAFE_J=best['J'],saving_J=base['J']-best['J'],
                saving_pct=100*(base['J']-best['J'])/base['J'],unique_SAFE=len({x['plan'] for x in results}),
                config_changes=sum(x['old'][:2]!=x['new'][:2] for x in changes['stage_changes']),
                start_changes=sum(x['old'][2]!=x['new'][2] for x in changes['stage_changes']),
                idle_changes=len(changes['low_added'])+len(changes['low_removed']),peak_upper_C=80-best['margin_C'],
                slack_ms=best['slack_ms'],energy_lo=best['bounds'][0],energy_hi=best['bounds'][1],best_plan=best['plan']))
            energy_rows.append(dict(case=c,arm=arm,**{k:best[k] for k in ('E35','activity','base','switch','temperature','external','J')}))
            for kind in sorted({r['kind'] for r in allrows}-{'initial'}):
                bucket=[r for r in allrows if r['kind']==kind]
                valid=[r['result'] for r in bucket if r.get('result',{}).get('status')=='SAFE']
                winners=[x for x in valid if improves(x,base)]
                stage_rows.append(dict(case=c,arm=arm,mode=kind,attempts=len(bucket),timing_invalid=sum(r.get('result',{}).get('status')=='TIMING_INVALID' for r in bucket),
                    physical_returns=sum('result' in r and 'plan'in r['result'] for r in bucket),SAFE_calls=len(valid),
                    unique_SAFE=len({x['plan'] for x in valid}),nonseed_SAFE_unique=len({x['plan'] for x in valid}-{base['plan']}),strictly_better_unique=len({x['plan'] for x in winners}),
                    best_returned_J=min((x['J'] for x in valid),default=None),best_with_seed_J=min([base['J']]+[x['J'] for x in winners]),
                    solver_statuses=dict(collections.Counter(r['solver']['status'] for r in bucket if 'solver'in r))))
            if arm!='diagnostic' and improves(best,base):
                mechanisms[c+'_'+arm+'_end']=dict(original=base,winner=best,**changes)
            if arm=='diagnostic' and improves(best,base):
                source=next(x for x in allrows if x.get('result',{}).get('plan')==best['plan'])
                mechanisms[c+'_gain']=dict(source=source,region=rby[source['region']],original=base,winner=best,**changes,
                     energy_delta_J={k:best[k]-base[k] for k in ('activity','base','switch','temperature','external','J')})
            if arm in ('C','D'):
                ss=read(folder/'probe_scores.json')
                key='gain35' if arm=='C' else 'gainfull'
                rankings.append(dict(case=c,arm=arm,priority_order=[x['id'] for x in sorted(ss,key=lambda x:(-x[key],x['id']))],
                    actual_sequence=[x['region'] for x in allrows if x['kind']=='comparison']))
                probe_records=[(x['region'],x['result']['plan'],x['result']['J']) for x in allrows if x['kind']=='shared_probe']
                assert [h for _,h,_ in probe_records]==[z['plan'] for z in pool if z['plan']]
    assert sum(r['charged_s'] for r in budget)<=6000
    for name,vals in [('endpoints',endrows),('stage_counts',stage_rows),('budget',budget),('reversals',reversals),('regions',windows),('probe_rankings',rankings),('energy',energy_rows)]:table(name+'.csv',vals)
    table('accepted_moves.csv',accepted)
    if gate['open']:
        by={(r['case'],r['arm']):r for r in endrows}
        contrasts=[]
        for c in CASES:
            for baseline,challenger in [('A','C'),('B','C'),('C','D')]:
                a,b=by[c,baseline],by[c,challenger]
                lo=a['energy_lo']-b['energy_hi'];hi=a['energy_hi']-b['energy_lo']
                verdict='LOWER' if lo>0 else 'HIGHER' if hi<0 else 'IDENTICAL_PLAN' if a['best_plan']==b['best_plan'] else 'OVERLAPPING'
                contrasts.append(dict(case=c,baseline=baseline,challenger=challenger,
                                      saving_J=a['SAFE_J']-b['SAFE_J'],saving_lo_J=lo,saving_hi_J=hi,verdict=verdict))
        table('contrasts.csv',contrasts)
    put(RESULT/'mechanisms.json',mechanisms)
if __name__=='__main__':main()
