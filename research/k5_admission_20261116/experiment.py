"""Finite-domain K5 admission experiment. No hardware or legacy solver imports."""
from pathlib import Path
from itertools import product
import csv, hashlib, json, math, time
import numpy as np

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT/'inputs.json').read_text(encoding='utf-8'))
L = CFG['time_unit_s']
R = CFG['cpu_pre_over_time_unit']*L
POST = CFG['cpu_post_over_time_unit']*L
W = CFG['window_over_time_unit']*L
MASKS = CFG['masks']
BITS = [sum(1 << c for c in m) for m in MASKS]
DUR = np.array(CFG['isolated_latency_ms_by_width'])/1000
WIDTH = np.array([len(m)-1 for m in MASKS])
TIME_EPS = CFG['time_tolerance_s']
TEMP_EPS = CFG['thermal_margin_tolerance_K']
ENERGY_EPS = CFG['energy_equality_tolerance_J']
LIMIT = CFG['ambient_C']+CFG['temperature_scale_K']
BASE_E = CFG['system_common_baseline_W']*W
CPU_E = CFG['cpu_active_increment_per_stage_W']*2*(R+POST)

def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def write_csv(path, rows):
    if not rows: return
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def finish_pair(sa, sb, da, db, sigma):
    if sa > sb:
        fb, fa, overlap = finish_pair(sb, sa, db, da, sigma)
        return fa, fb, overlap
    if sa+da <= sb+TIME_EPS:
        return sa+da, sb+db, 0.0
    remaining_a = da-(sb-sa)
    common_work = min(remaining_a, db)
    overlap = (1+sigma)*common_work
    stop = sb+overlap
    return stop+max(0.0, remaining_a-db), stop+max(0.0, db-remaining_a), overlap

class Catalog:
    def __init__(self, sigma):
        self.sigma = sigma
        self.genes = {}
        self.rows = []
        keys = {}
        raw = 0
        rejected = 0
        delays = CFG['start_delay_over_time_unit']
        lags = CFG['second_start_lag_over_time_unit']
        for a,b,order,anchor,u,v in product(range(5),range(5),range(2),range(2),range(4),range(4)):
            raw += 1
            gene = (a,b,order,anchor,u,v)
            ds = [float(DUR[0, WIDTH[a]]), float(DUR[1, WIDTH[b]])]
            first = order
            second = 1-first
            starts = [0.0, 0.0]
            starts[first] = R+delays[u]*L
            starts[second] = starts[first]+anchor*ds[first]+lags[v]*L
            sa, sb = starts
            if (BITS[a] & BITS[b]) and max(sa,sb) < min(sa+ds[0],sb+ds[1])-TIME_EPS:
                rejected += 1
                continue
            # Starts are exact multiples of 100 ns in this frozen protocol.
            key = (a,b,round(sa/1e-7),round(sb/1e-7))
            if key not in keys:
                fa, fb, overlap = finish_pair(sa,sb,*ds,sigma)
                assert max(fa,fb)+POST < W+TIME_EPS
                sid = len(self.rows)
                keys[key] = sid
                self.rows.append(dict(sid=sid,a=a,b=b,sa=sa,sb=sb,fa=fa,fb=fb,
                                      overlap_s=overlap,representative_gene=gene))
            self.genes[gene] = keys[key]
        self.raw_count=raw; self.conflicting_gene_count=rejected
        self.n=len(self.rows)
        self.a=np.array([x['a'] for x in self.rows],int)
        self.b=np.array([x['b'] for x in self.rows],int)
        self.sa=np.array([x['sa'] for x in self.rows])
        self.sb=np.array([x['sb'] for x in self.rows])
        self.fa=np.array([x['fa'] for x in self.rows])
        self.fb=np.array([x['fb'] for x in self.rows])
        self.completion=np.column_stack((self.fa+POST,self.fb+POST))
        self.points=np.sort(np.column_stack((np.zeros(self.n),self.sa,self.sb,self.fa,self.fb,np.full(self.n,W))),axis=1)
        self.dt=np.diff(self.points,axis=1)
        mid=(self.points[:,:-1]+self.points[:,1:])/2
        self.active_a=(mid>=self.sa[:,None]) & (mid<self.fa[:,None])
        self.active_b=(mid>=self.sb[:,None]) & (mid<self.fb[:,None])
        self.by_pair={(a,b):np.where((self.a==a)&(self.b==b))[0] for a,b in product(range(5),repeat=2)}

class Evaluator:
    def __init__(self, catalog, case):
        self.cat=catalog; self.case=case
        self.deadline=(0.1+case['deadline_npu_allowance_over_time_unit'])*L
        self.p=np.array([1.0,case['p2_over_p1'],case['p2_over_p1']*case['p3_over_p2']])
        self.pa=self.p[WIDTH[catalog.a]]; self.pb=self.p[WIDTH[catalog.b]]
        self.energy=BASE_E+CPU_E+self.pa*(catalog.fa-catalog.sa)+self.pb*(catalog.fb-catalog.sb)
        self.deadline_ok=np.all(catalog.completion<=self.deadline+TIME_EPS,axis=1)
        self.tau=case['tau_over_time_unit']*L
        self.kappa=case['single_power_steady_theta_gain']
        self.theta0=case['entry_theta']
        self.calls=0

    def evaluate(self, ids, trace=False):
        ids=np.asarray(ids,dtype=int)
        cat=self.cat
        temp=np.full(len(ids),self.theta0)
        peak=temp.copy()
        history=[temp.copy()]
        heat=0.2+self.pa[ids,None]*cat.active_a[ids]+self.pb[ids,None]*cat.active_b[ids]
        for j in range(5):
            equilibrium=self.kappa*heat[:,j]
            temp=equilibrium+(temp-equilibrium)*np.exp(-cat.dt[ids,j]/self.tau)
            peak=np.maximum(peak,temp)
            history.append(temp.copy())
        self.calls += len(ids)
        peak_C=25+20*peak
        safe=(peak_C < LIMIT-TEMP_EPS)
        unresolved=np.abs(peak_C-LIMIT)<=TEMP_EPS
        if trace: return peak_C,safe,unresolved,25+20*np.stack(history,axis=1)
        return peak_C,safe,unresolved

def energy_key(ev, sid):
    cat=ev.cat
    return (float(ev.energy[sid]),float(max(cat.completion[sid])),int(sid))

def record(ev, method, sid, elapsed, evaluation_count, peak=None, note=''):
    if sid is None:
        return dict(case_id=ev.case['case_id'],method=method,sid=None,status='NO_SAFE_SOLUTION_IN_RESTRICTED_DOMAIN',
                    energy_J=None,baseline_J=None,cpu_active_J=None,npu_active_J=None,
                    completion_A_ms=None,completion_B_ms=None,deadline_ms=ev.deadline*1000,
                    peak_C=None,a_mask=None,b_mask=None,a_start_ms=None,b_start_ms=None,
                    a_finish_ms=None,b_finish_ms=None,wall_s=elapsed,thermal_evaluations=evaluation_count,
                    gap_to_E_percent=None,note=note)
    cat=ev.cat; r=cat.rows[sid]
    if peak is None: peak=float(ev.evaluate([sid])[0][0])
    deadline=bool(ev.deadline_ok[sid]); unresolved=abs(peak-LIMIT)<=TEMP_EPS
    thermal=peak < LIMIT-TEMP_EPS
    status=('SAFE' if deadline and thermal else 'UNRESOLVED' if deadline and unresolved else
            'DEADLINE_AND_THERMAL_VIOLATION' if not deadline and not thermal else
            'DEADLINE_VIOLATION' if not deadline else 'THERMAL_VIOLATION')
    return dict(case_id=ev.case['case_id'],method=method,sid=int(sid),status=status,
                energy_J=float(ev.energy[sid]),baseline_J=BASE_E,cpu_active_J=CPU_E,
                npu_active_J=float(ev.energy[sid]-BASE_E-CPU_E),
                completion_A_ms=float(cat.completion[sid,0]*1000),completion_B_ms=float(cat.completion[sid,1]*1000),
                deadline_ms=ev.deadline*1000,peak_C=peak,a_mask=str(MASKS[r['a']]),b_mask=str(MASKS[r['b']]),
                a_start_ms=r['sa']*1000,b_start_ms=r['sb']*1000,a_finish_ms=r['fa']*1000,b_finish_ms=r['fb']*1000,
                wall_s=elapsed,thermal_evaluations=evaluation_count,gap_to_E_percent=None,note=note)

def restricted_search(cat, case, method, ids):
    tic=time.perf_counter(); ev=Evaluator(cat,case)
    ids=np.asarray(ids,int)
    peaks,safe,unresolved=ev.evaluate(ids)
    valid=safe & ev.deadline_ok[ids]
    feasible=ids[valid]
    sid=min(feasible,key=lambda i:energy_key(ev,i)) if len(feasible) else None
    peak=float(peaks[np.where(ids==sid)[0][0]]) if sid is not None else None
    row=record(ev,method,sid,time.perf_counter()-tic,ev.calls,peak)
    if sid is None and np.any(unresolved & ev.deadline_ok[ids]): row['status']='UNRESOLVED'
    return row

def earliest(cat,case):
    tic=time.perf_counter();ev=Evaluator(cat,case)
    sid=min(range(cat.n),key=lambda i:(max(cat.completion[i]),sum(cat.completion[i]),ev.energy[i],i))
    peak=float(ev.evaluate([sid])[0][0])
    return record(ev,'C',sid,time.perf_counter()-tic,ev.calls,peak)

def list_seed(cat,ev,order):
    first=order;second=1-order
    options=[]
    for m in range(5):
        d=float(DUR[first,WIDTH[m]])
        tardy=max(0.0,R+d+POST-ev.deadline)
        options.append(((tardy>TIME_EPS,tardy,ev.p[WIDTH[m]]*d,R+d,m),m))
    chosen=min(options)[1]
    options=[]
    for m in range(5):
        a,b=(chosen,m) if order==0 else (m,chosen)
        anchor=int(bool(BITS[a]&BITS[b]))
        gene=(a,b,order,anchor,0,0)
        sid=cat.genes[gene]
        tardy=float(np.maximum(cat.completion[sid]-ev.deadline,0).sum())
        options.append(((tardy>TIME_EPS,tardy,ev.p[WIDTH[m]]*DUR[second,WIDTH[m]],
                         max(cat.completion[sid]),m),gene))
    return min(options)[1]

def lists_and_local(cat,case):
    tic=time.perf_counter(); ev=Evaluator(cat,case)
    seeds=[list_seed(cat,ev,o) for o in range(2)]
    list_sid=min((cat.genes[g] for g in seeds),key=lambda i:(not ev.deadline_ok[i],
                 float(np.maximum(cat.completion[i]-ev.deadline,0).sum()),ev.energy[i],max(cat.completion[i]),i))
    list_peak=float(ev.evaluate([list_sid])[0][0])
    list_row=record(ev,'D_list',list_sid,time.perf_counter()-tic,ev.calls,list_peak)
    # This evaluator has its own cache, never populated by E/F or other methods.
    cache={}
    def fill(ids):
        todo=sorted(set(ids)-set(cache))
        if todo:
            peaks,_,_=ev.evaluate(todo)
            cache.update(zip(todo,map(float,peaks)))
    def score(gene):
        sid=cat.genes[gene]; peak=cache[sid]
        late=np.maximum(cat.completion[sid]-ev.deadline-TIME_EPS,0)
        thermal=max(0.0,(peak-LIMIT+TEMP_EPS)/20)
        return (int(np.count_nonzero(late))+int(thermal>0),
                float(late.sum()/L+thermal),float(ev.energy[sid]),float(max(cat.completion[sid])),gene)
    finals=[]; steps=[]; capped=False
    for seed in seeds:
        state=seed
        for step in range(CFG['local_search_max_steps_per_seed']):
            neighbors={state}
            for axis,size in enumerate((5,5,2,2,4,4)):
                for val in range(size):
                    g=list(state);g[axis]=val;g=tuple(g)
                    if g in cat.genes:neighbors.add(g)
            fill([cat.genes[g] for g in neighbors])
            best=min(neighbors,key=score)
            if score(best)>=score(state):break
            state=best
        else:capped=True
        finals.append(state);steps.append(step+1)
    best=min(finals,key=score);sid=cat.genes[best]
    row=record(ev,'D',sid,time.perf_counter()-tic,ev.calls,cache[sid],
               note=json.dumps(dict(steps=steps,step_cap_reached=capped,seeds=seeds,best_gene=best)))
    return list_row,row

def ordinary_energy_ordered_search(cat,case):
    tic=time.perf_counter();ev=Evaluator(cat,case)
    eligible=sorted(np.where(ev.deadline_ok)[0],key=lambda i:energy_key(ev,i))
    selected=None;peak=None;unresolved=False
    # Scalar complete prediction, not thermal table lookup from the reference.
    for sid in eligible:
        t=ev.theta0;p=t
        for j,dt in enumerate(cat.dt[sid]):
            heat=.2+ev.pa[sid]*cat.active_a[sid,j]+ev.pb[sid]*cat.active_b[sid,j]
            q=ev.kappa*heat
            t=q+(t-q)*math.exp(-float(dt)/ev.tau);p=max(p,t)
        ev.calls+=1
        peak_now=25+20*p
        if abs(peak_now-LIMIT)<=TEMP_EPS:unresolved=True
        if peak_now < LIMIT-TEMP_EPS:
            selected=int(sid);peak=peak_now;break
    row=record(ev,'F_plain_search',selected,time.perf_counter()-tic,ev.calls,peak)
    if unresolved:row['note']='Earlier unresolved candidates prevent exact optimality claim'
    if selected is None:
        row['status']='UNRESOLVED' if unresolved else 'NO_SAFE_SOLUTION_IN_FULL_DOMAIN'
    return row

def full_reference(cat,case):
    tic=time.perf_counter();ev=Evaluator(cat,case)
    peaks,safe,undecided=ev.evaluate(np.arange(cat.n))
    feasible=safe & ev.deadline_ok
    ids=np.where(feasible)[0]
    sid=int(min(ids,key=lambda i:energy_key(ev,i))) if len(ids) else None
    row=record(ev,'E',sid,time.perf_counter()-tic,ev.calls,float(peaks[sid]) if sid is not None else None)
    if sid is None:row['status']='UNRESOLVED' if np.any(undecided&ev.deadline_ok) else 'NO_SAFE_SOLUTION_IN_FULL_DOMAIN'
    noheat=np.where(ev.deadline_ok)[0]
    sid0=int(min(noheat,key=lambda i:energy_key(ev,i))) if len(noheat) else None
    e0=record(ev,'E0_no_thermal_constraint',sid0,0.0,0,float(peaks[sid0]) if sid0 is not None else None,
              note='Diagnostic ablation, not a safe energy-savings baseline')
    if sid0 is None:e0['status']='NO_DEADLINE_FEASIBLE_SOLUTION_IN_FULL_DOMAIN'
    optids=ids[np.abs(ev.energy[ids]-ev.energy[sid])<=ENERGY_EPS] if sid is not None else np.array([],int)
    opt0=noheat[np.abs(ev.energy[noheat]-ev.energy[sid0])<=ENERGY_EPS] if sid0 is not None else np.array([],int)
    maps=lambda ii:sorted(set((int(cat.a[i]),int(cat.b[i])) for i in ii))
    mapT=maps(optids);map0=maps(opt0)
    summary=dict(**case,catalog_size=cat.n,raw_genes=cat.raw_count,
                 deadline_feasible=int(ev.deadline_ok.sum()),safe_feasible=int(feasible.sum()),
                 deadline_thermal_violations=int(np.sum(ev.deadline_ok & ~safe & ~undecided)),
                 unresolved=int(undecided.sum()),reference_sid=sid,noheat_reference_sid=sid0,
                 E_J=row['energy_J'],E0_J=e0['energy_J'],
                 thermal_constraint_cost_J=float(ev.energy[sid]-ev.energy[sid0]) if sid is not None and sid0 is not None else None,
                 all_optimal_maps=json.dumps(mapT),all_noheat_optimal_maps=json.dumps(map0),
                 optimal_map_sets_disjoint=bool(mapT and map0 and not set(map(tuple,mapT))&set(map(tuple,map0))),
                 min_threshold_distance_K=float(np.min(np.abs(peaks-LIMIT))),
                 max_peak_C=float(peaks.max()))
    return row,e0,summary,ev.energy,peaks,np.where(undecided,2,np.where(safe,0,1)).astype(np.uint8)

def run(output):
    start=time.perf_counter()
    output.mkdir(parents=True,exist_ok=False)
    frozen=json.loads((ROOT/'freeze.json').read_text())
    for path,digest in frozen['files'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    cases=json.loads((ROOT/'parameter_grid.json').read_text())
    catalogs={s:Catalog(s) for s in CFG['concurrent_slowdown_sigma']}
    for sigma,cat in catalogs.items():
        write_json(output/f'catalog_sigma_{sigma}.json',dict(raw_genes=cat.raw_count,
                   conflicting_genes=cat.conflicting_gene_count,legal_genes=len(cat.genes),
                   unique_schedules=cat.n,rows=cat.rows,
                   gene_to_sid=[dict(gene=k,sid=v) for k,v in cat.genes.items()]))
    preprocessing=time.perf_counter()-start
    methods=[];summaries=[];energies=[];peaks=[];states=[]
    tracefile=(output/'selected_trajectories.jsonl').open('w',encoding='utf-8')
    progress=(output/'progress.jsonl').open('w',encoding='utf-8')
    for index,case in enumerate(cases):
        if time.perf_counter()-start>440:
            write_json(output/'unresolved_cases.json',cases[index:]);break
        cat=catalogs[case['concurrent_slowdown_sigma']]
        rows=[]
        rows.append(restricted_search(cat,case,'A',cat.by_pair[(0,1)]))
        rows.append(restricted_search(cat,case,'B',cat.by_pair[(4,4)]))
        c=earliest(cat,case);rows.append(c)
        cr=cat.rows[c['sid']]
        rows.append(restricted_search(cat,case,'C_repair',cat.by_pair[(cr['a'],cr['b'])]))
        dl,d=lists_and_local(cat,case);rows.extend((dl,d))
        rows.append(ordinary_energy_ordered_search(cat,case))
        # Reference and diagnostic results are unavailable to the preceding methods.
        er,e0,summary,energy,peak,state=full_reference(cat,case);rows.extend((er,e0))
        if er['status']=='SAFE':
            for row in rows:
                if row['status']=='SAFE':row['gap_to_E_percent']=100*(row['energy_J']/er['energy_J']-1)
        f=rows[6]
        if er['status']=='SAFE':
            assert f['status']=='SAFE'
            assert abs(f['energy_J']-er['energy_J'])<=ENERGY_EPS
        else:assert f['status']!='SAFE'
        summary.update(D_status=d['status'],D_gap_percent=d['gap_to_E_percent'],
                       F_status=f['status'],F_wall_s=f['wall_s'],E_wall_s=er['wall_s'])
        summary['strong_simple_matches_E']=(er['status']!='SAFE' or abs(f['energy_J']-er['energy_J'])<=ENERGY_EPS)
        summaries.append(summary);methods.extend(rows)
        energies.append(energy);peaks.append(peak);states.append(state)
        # Store every returned complete schedule, including unsafe/late proposals.
        ev=Evaluator(cat,case)
        returned=sorted(set(row['sid'] for row in rows if row['sid'] is not None))
        _,_,_,temps=ev.evaluate(returned,trace=True)
        for i,sid in enumerate(returned):
            tr=dict(case_id=case['case_id'],sid=sid,methods=[r['method'] for r in rows if r['sid']==sid],
                    times_s=cat.points[sid].tolist(),temperature_C=temps[i].tolist(),
                    schedule=cat.rows[sid],cpu_pre=[0,R],cpu_post_A=[cat.fa[sid],cat.fa[sid]+POST],
                    cpu_post_B=[cat.fb[sid],cat.fb[sid]+POST],complete_window_s=W)
            tracefile.write(json.dumps(tr,ensure_ascii=True)+'\n')
        if index%100==0 or index==len(cases)-1:
            status=dict(completed=index+1,total=len(cases),elapsed_s=time.perf_counter()-start)
            progress.write(json.dumps(status)+'\n');progress.flush();print(json.dumps(status),flush=True)
    tracefile.close();progress.close()
    write_csv(output/'cases.csv',summaries)
    write_csv(output/'methods.csv',methods)
    # Full enumeration retained, with catalog row index as the second axis.
    np.savez_compressed(output/'all_candidates.npz',case_ids=np.array([s['case_id'] for s in summaries]),
                        energy_J=np.array(energies),peak_C=np.array(peaks),thermal_state=np.array(states),
                        thermal_state_legend=np.array(['SAFE=0','VIOLATION=1','UNRESOLVED=2']))
    feasible=[s for s in summaries if s['E_J'] is not None]
    gaps=[s['D_gap_percent'] for s in feasible if s['D_status']=='SAFE']
    result=dict(completed=len(summaries),planned=len(cases),preprocessing_s=preprocessing,
                experiment_wall_s=time.perf_counter()-start,feasible_cases=len(feasible),
                no_deadline_feasible_cases=sum(s['deadline_feasible']==0 for s in summaries),
                thermal_infeasible_cases=sum(s['deadline_feasible']>0 and s['safe_feasible']==0 for s in summaries),
                unresolved_candidates=sum(s['unresolved'] for s in summaries),
                positive_thermal_cost_cases=sum((s['thermal_constraint_cost_J'] or 0)>ENERGY_EPS for s in summaries),
                necessary_optimal_map_change_cases=sum(s['optimal_map_sets_disjoint'] for s in summaries),
                D_safe_cases=sum(s['D_status']=='SAFE' for s in summaries),
                D_gap_max_percent=max(gaps,default=0),
                D_missed_feasible_cases=sum(s['D_status']!='SAFE' for s in feasible),
                F_matches_E_all=all(s['strong_simple_matches_E'] for s in summaries),
                min_threshold_distance_K=min(s['min_threshold_distance_K'] for s in summaries),
                max_peak_C=max(s['max_peak_C'] for s in summaries),
                catalog_counts={str(s):dict(raw=c.raw_count,legal_genes=len(c.genes),unique=c.n) for s,c in catalogs.items()})
    write_json(output/'summary.json',result)
    return result

if __name__=='__main__':
    import sys
    print(json.dumps(run(Path(sys.argv[1])),ensure_ascii=False,indent=2))
