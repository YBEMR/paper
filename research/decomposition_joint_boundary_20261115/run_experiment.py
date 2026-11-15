from pathlib import Path
import argparse,csv,hashlib,itertools,json,time,platform,sys
import numpy as np
from model import enumerate_pool,transitions,evaluate_pool,METRICS
ROOT=Path(__file__).resolve().parent
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csvwrite(path,rows):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def best(mask,cost):
    ids=np.flatnonzero(mask)
    if len(ids)==0:return None
    low=np.min(cost[ids]);return int(ids[np.flatnonzero(cost[ids]<=low+1e-10)[0]])
def representatives(pool,configs,legal):
    result=[]
    for cid in np.unique(pool[legal,0]):
        ids=np.flatnonzero(legal&(pool[:,0]==cid))
        rid=min(ids,key=lambda k:(pool[k,5]+configs[cid,11],*pool[k,2:6]))
        result.append(int(rid))
    return np.array(result,dtype=int)

def choose(pool,configs,m,shared,heat_limit):
    legal=np.isfinite(m[:,0]);valid=legal&(m[:,6]<100)&(m[:,7]>20)
    safe=valid&(m[:,6]<=80) if heat_limit else valid
    uncertain=valid&(m[:,5]<=80)&(m[:,6]>80) if heat_limit else np.zeros(len(pool),bool)
    J=best(safe,m[:,0]);NT=best(legal,m[:,1]+m[:,2]+m[:,4])
    picks={'J':J,'NT':NT};retained={};rep=representatives(pool,configs,legal)
    if NT is not None:
        samecfg=pool[:,0]==pool[NT,0];samemap=pool[:,1]==pool[NT,1]
        eligible=safe&samecfg&np.all(pool[:,2:6]>=pool[NT,2:6],axis=1)
        ids=np.flatnonzero(eligible)
        picks['DelayRepair']=int(min(ids,key=lambda k:(pool[k,5]+configs[pool[k,0],11],m[k,0],k))) if len(ids) else None
        picks['D_C']=best(safe&samecfg,m[:,0]);picks['D_M']=best(safe&samemap,m[:,0])
    scores=[]
    for mid in sorted(set(pool[:,1])):
        ids=[int(k) for k in rep if pool[k,1]==mid and safe[k]]
        if ids:
            k=min(ids,key=lambda k:(m[k,0],k));scores.append((float(m[k,0]),int(mid),k))
    scores.sort()
    for K in [1,2,4]:
        maps=[q[1] for q in scores[:K]];retained['TC'+str(K)]=maps
        picks['TC'+str(K)]=best(safe&np.isin(pool[:,1],maps),m[:,0])
    stats=dict(legal=int(legal.sum()),valid_model=int(valid.sum()),safe=int(safe.sum()),
        unsafe=int((valid&(m[:,5]>80)).sum()) if heat_limit else 0,unresolved=int(uncertain.sum()),
        configurations=int(len(rep)),mapping_count=int(len(set(pool[legal,1]))),safe_representative_mappings=len(scores))
    conditional=[]
    for mid in sorted(set(pool[legal,1])):
        k=best(safe&(pool[:,1]==mid),m[:,0])
        score=next((x[0] for x in scores if x[1]==mid),None)
        conditional.append(dict(mapping_id=int(mid),best_candidate=k,energy_J=None if k is None else float(m[k,0]),
            representative_score_J=score,all_representatives_rejected=score is None))
    return picks,retained,stats,conditional,safe

def main(out):
    start=time.perf_counter();out.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'protocol.json').read_text(encoding='utf-8'))
    frozen=json.loads((ROOT/'freeze.json').read_text())
    for name,h in frozen['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
    table_cache={};rows=[];arms=[];conditions=[];max_balance=0.;refinements=[];workcounts=[]
    for shape_id,shape in enumerate(config['work_shapes']):
        for deadline in config['deadlines_us']:
            key=f'w{shape_id}_d{deadline}'
            pool,configs,powers,config_description=enumerate_pool(config,shape,deadline)
            np.savez_compressed(out/(key+'_pool.npz'),pool=pool,configs=configs,powers=powers)
            write(out/(key+'_configs.json'),config_description)
            workcounts.append(dict(pool=key,candidates=len(pool),shared_legal=int(pool[:,6].sum())))
            for c,l,s in itertools.product([0,1],repeat=3):
                if (c,l,50) not in table_cache:table_cache[c,l,50]=transitions(config,c,l,50)
                params=table_cache[c,l,50]
                for initial in config['initial_temperatures_C']:
                    label=f'{key}_t{initial}_c{c}l{l}s{s}'
                    m=evaluate_pool(pool,configs,powers,s,float(initial),50,*params)
                    for step in [10,1]:
                        uncertain=np.isfinite(m[:,0])&(m[:,5]<=80)&(m[:,6]>80)
                        ids=np.flatnonzero(uncertain)
                        if not len(ids):break
                        if (c,l,step) not in table_cache:table_cache[c,l,step]=transitions(config,c,l,step)
                        m[ids]=evaluate_pool(pool[ids],configs,powers,s,float(initial),step,*table_cache[c,l,step])
                        refinements.append(dict(arm=label,step_ticks=step,candidates=len(ids)))
                    np.savez_compressed(out/(label+'_raw.npz'),metrics=m)
                    max_balance=max(max_balance,float(np.nanmax(abs(m[:,8]))))
                    for heat_limit in [0,1]:
                        arm=label+f'h{heat_limit}';picks,retained,stats,conditional,safe=choose(pool,configs,m,s,heat_limit)
                        j=picks['J'];jE=None if j is None else float(m[j,0])
                        arms.append(dict(arm=arm,pool=key,initial_C=initial,coupling=c,leakage=l,shared=s,heat_limit=heat_limit,**stats))
                        for q in conditional:conditions.append(dict(arm=arm,**q))
                        for method,k in picks.items():
                            feasible=k is not None and bool(safe[k])
                            row=dict(arm=arm,method=method,candidate_id=k,feasible=feasible,
                                mapping_id=None if k is None else int(pool[k,1]),config_id=None if k is None else int(pool[k,0]),
                                starts_ms=None if k is None else ';'.join(str(x*.1) for x in pool[k,2:6]),
                                retained_mappings=';'.join(map(str,retained.get(method,[]))),
                                excess_over_joint_pct=(float(m[k,0])/jE-1)*100 if feasible and jE is not None else None,
                                joint_saving_pct=(1-jE/float(m[k,0]))*100 if feasible and jE is not None else None)
                            for i,name in enumerate(METRICS):row[name]=None if k is None else float(m[k,i])
                            rows.append(row)
                    if time.perf_counter()-start>config['run_timeout_s']:raise TimeoutError('Frozen run budget exceeded')
            print(key,'complete',len(pool),'candidates',round(time.perf_counter()-start,2),'s',flush=True)
    csvwrite(out/'comparisons.csv',rows);csvwrite(out/'arms.csv',arms);csvwrite(out/'mapping_conditionals.csv',conditions)
    summary=dict(id=config['id'],evidence=config['evidence'],wall_seconds=time.perf_counter()-start,pools=workcounts,
        comparison_arms=len(arms),method_rows=len(rows),max_heat_balance_J=max_balance,refinements=refinements,
        total_unresolved=sum(x['unresolved'] for x in arms),infeasible_joint_arms=sum(x['method']=='J' and not x['feasible'] for x in rows),
        python=sys.version,platform=platform.platform(),metrics=METRICS,
        hashes={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['protocol.json','PROTOCOL.md','model.py','run_experiment.py']})
    write(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['metrics','hashes','refinements']},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'results');args=ap.parse_args();main(args.out)
