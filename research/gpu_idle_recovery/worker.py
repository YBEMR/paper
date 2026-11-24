"""One case, one 120 s budget, including selection, scheduling and certification."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import gzip,json,sys,hashlib
from time import perf_counter as clock
from dataclasses import replace
from collections import Counter
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/'config.json').read_bytes());CASE=sys.argv[1];OUT=HERE/'raw'/CASE
START=float(os.environ['RECOVERY_START']);LOG=(OUT/'events.jsonl').open('x',encoding='utf-8',newline='\n')
def save(p,x):
    b=(json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b)
def emit(kind,**data):
    LOG.write(json.dumps(dict(t_s=clock()-START,kind=kind,**data),allow_nan=False)+'\n');LOG.flush()
class Budget(Exception):pass
def check():
    if clock()-START>=CFG['admission_cutoff_s']:raise Budget()

def main():
    for name,h in json.loads((HERE/'execution_manifest.json').read_bytes()).items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    sys.path.insert(0,str(ROOT/'research/multidnn_diagnostics'))
    from instance import Instance,events
    inst=Instance(CASE);inst.bind()
    sys.path.insert(0,str(ROOT/'research/kim_multidnn_search_trial'))
    import solver
    inst.bind()
    from profiles import build_chains
    from control import Timeline
    from online_events import simulate
    from physics import certify
    from peak_selection import enumerate_bounds
    import events as base_events
    import csv
    history=ROOT/'research/multidnn_diagnostics'
    summary=next(r for r in csv.DictReader((history/'summary.csv').open()) if r['case_id']==CASE)
    Eref=float(summary['best_safe_j']);opps=summary['best_safe_opps'].split('/')
    emit('identity',case=inst.case,identity=inst.identity,domain=inst.order,config=CFG,reference=summary)
    schedules={};prepared={};originals={};new={};coverage={};band=[]
    def prepare(dep,os):
        key=(dep,tuple(os))
        if key in prepared:return prepared[key]
        chains={};requests=[];rows=[];completion={};meta={}
        for j,scene in enumerate(inst.scenes):
            sk=(dep,j,os[j])
            if sk not in schedules:schedules[sk]=events.time_scene(inst.platform,scene,dep,os[j])
            s=schedules[sk];assert s.deadline_feasible
            chains[j]=build_chains(inst.platform,inst.frozen,dep,os[j])
            requests.extend(replace(q,release_ns=q.release_ns+scene.start_ns,deadline_ns=q.deadline_ns+scene.start_ns) for q in scene.requests)
            rows.extend(replace(r,start_ns=r.start_ns+scene.start_ns,end_ns=r.end_ns+scene.start_ns) for r in s.rows)
            completion.update({rid:t+scene.start_ns for rid,t in s.completions_ns.items()})
            meta.update({q.id:(j,os[j][1]) for q in scene.requests})
        order=[(r.request,r.stage_index) for r in rows if r.resource=='GPU']
        prepared[key]=(chains,requests,rows,completion,meta,order);return prepared[key]
    def original(dep,code):
        check();key=dep,code
        if key not in originals:
            os=solver.joint.decode(code);t=clock();p=inst.replay(dep,os)
            assert p['fully_replayed'] and p['required']==p['completed']==750
            originals[key]=p;save(OUT/f'{dep}_{code}_original.json.gz',p)
            emit('original',dep=dep,code=code,opps=os,energy_j=p['energy_j'],peak_c=max(p['peak_upper_c']),status=p['thermal_status'],seconds=clock()-t)
        return originals[key]
    def idle(dep,code,reason):
        check();key=dep,code
        if key in new:return new[key]
        t=clock();os=solver.joint.decode(code);chains,requests,oldrows,oldcompletion,meta,order=prepare(dep,os)
        rows,completion,tl,audit=simulate(base_events,Timeline,requests,chains,order,meta,inst.window_ns,
             'reactive',dict(latency_ns=CFG['latency_ns'],energy_j=CFG['energy_j']),CFG['dwell_ns'],40000000,10000000000)
        features=lambda rr:{(r.request,r.stage_index):(r.resource,r.stage,r.end_ns-r.start_ns,r.activity_w) for r in rr}
        assert features(rows)==features(oldrows)
        p,times,temps=certify(inst,requests,rows,completion,tl,inst.ambient,os)
        # Shared CPU/DLA scene clocks cannot be reinterpreted if a delayed stage crosses a switch.
        valid=all(not any(max(r.start_ns,s.start_ns)<min(r.end_ns,s.end_ns) and os[meta[r.request][0]][0 if r.resource.startswith('CPU') else 2]!=os[j][0 if r.resource.startswith('CPU') else 2]
                    for j,s in enumerate(inst.scenes)) for r in rows if r.resource.startswith(('CPU','DLA')))
        p['physical']['scene_frequency_valid']=valid;p['physical']['SAFE'] &= valid
        p.update(dep=dep,code=code,opps=os,reason=reason,identity=inst.identity,initial_c=inst.initial,
                 reference_stage_features_sha=hashlib.sha256(repr(sorted(features(oldrows).items())).encode()).hexdigest())
        check();save(OUT/f'{dep}_{code}_idle.json.gz',p);save(OUT/f'{dep}_{code}_control.json.gz',audit)
        np.savez_compressed(OUT/f'{dep}_{code}_trace.npz',time_s=times,temperature_c=temps)
        check();new[key]=p['physical'];emit('idle',dep=dep,code=code,reason=reason,opps=os,physical=p['physical'],seconds=clock()-t)
        return new[key]
    # Full old-evaluator regression is paid in each case's budget.
    code=sum(solver.OPPS.index(o)*27**(3-j) for j,o in enumerate(opps))
    prior=original('D017',code);chains,req,rows,comp,meta,order=prepare('D017',opps)
    tl=Timeline(inst.window_ns);tl.changes=[(s.start_ns,opps[j][1]) for j,s in enumerate(inst.scenes)]
    reg,_,_=certify(inst,req,rows,comp,tl,25,opps)
    assert abs(prior['energy_j']-Eref)<1e-7 and abs(reg['physical']['energy_J']-Eref)<1e-7
    assert max(abs(a-b) for a,b in zip(prior['peak_upper_c'],reg['physical']['peak_upper_c']))<1e-7
    assert reg['physical']['min_slack_ms']==prior['min_slack_ms']==float(summary['best_safe_deadline_slack_ms'])
    emit('regression',status='PASS',energy_error_j=reg['physical']['energy_J']-Eref,initial_c=inst.initial)
    idle('D017',code,'D017_reference')
    builder=solver.SceneTable(inst.scenes,'M2',Counter(),inst.identity)
    old_get=builder.get
    def get(dep,j,o):check();v=old_get(dep,j,o);check();return v
    targets=[]
    for dep in inst.order:
        check()
        with np.load(history/'raw'/CASE/f'fallback_{dep}.npz') as a:
            st=a['status'].copy();e=a['energy_j'].copy()
        legal=np.isfinite(e);over=st==2
        coverage[dep]=dict(legal=int(legal.sum()),original_safe=int((st==1).sum()),original_overtemp=int(over.sum()))
        if over.any():targets.append((dep,st,e))
    emit('targets',deployments=[d for d,_,_ in targets],coverage=coverage)
    # Cover every eligible deployment before spending time on extra band sequences.
    for dep,st,e in targets:
        check();t=clock();tables=[[get(dep,j,o) for o in solver.OPPS] for j in range(4)]
        codes,L,U,E=enumerate_bounds(tables,inst.initial,check)
        assert np.array_equal(np.sort(codes),np.flatnonzero(np.isfinite(e)))
        assert np.max(np.abs(E-e[codes]))<1e-7
        e0=int(np.nanargmin(e));original(dep,e0);idle(dep,e0,'minimum_energy')
        # Refine the envelope minimizer until the original evaluator certifies
        # global min peak to its unchanged 0.0005 C numerical resolution.
        best=float('inf');bestcode=None;tested=set()
        while True:
            check();remaining=np.array([i for i in range(len(codes)) if int(codes[i]) not in tested and L[i]<best-CFG['peak_minimum_tolerance_c']],dtype=int)
            if not len(remaining):break
            i=int(remaining[np.lexsort((codes[remaining],E[remaining],U[remaining]))[0]])
            c=int(codes[i]);p=original(dep,c);peak=max(p['peak_upper_c']);tested.add(c)
            if peak<best:best,bestcode=peak,c
        assert bestcode is not None
        idle(dep,bestcode,'minimum_peak')
        eligible=(st[codes]==2)&(E<Eref)&(L<=CFG['band_upper_c'])&(U>80)
        band.extend((float(E[i]),dep,int(codes[i])) for i in np.flatnonzero(eligible))
        np.savez_compressed(OUT/f'{dep}_selection_bounds.npz',codes=codes,lower_c=L,upper_c=U,energy_j=E)
        emit('selection',dep=dep,e0=e0,min_peak_code=bestcode,min_peak_c=best,min_peak_lower_c=float(min(L)),
             minimum_peak_certified_tolerance_c=CFG['peak_minimum_tolerance_c'],refined_codes=sorted(tested),refinements=len(tested),band_candidates=int(eligible.sum()),seconds=clock()-t)
    emit('mandatory_complete',target_count=len(targets),band_candidates=len(band))
    # Optional explicit user-suggested 80–84 C / below original D017 band.
    for _,dep,c in sorted(band):
        check();p=original(dep,c)
        if 80<max(p['peak_upper_c'])<=CFG['band_upper_c'] and p['energy_j']<Eref:idle(dep,c,'80_84C_below_D017')
    emit('finished',status='complete',new_certificates=len(new))

try:main()
except Budget:emit('stopped',status='budget_unresolved')
except BaseException as exc:emit('error',type=type(exc).__name__,message=str(exc));raise
finally:LOG.close()
