"""One frozen case: two common-control regimes, no algorithm tuning."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS']:os.environ[k]='1'
import sys,json,gzip,hashlib
from pathlib import Path
from time import perf_counter as clock
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/'config.json').read_bytes());CASE=sys.argv[1];OUT=HERE/'raw'/CASE
START=float(os.environ['MULTIPATH_START']);LOG=(OUT/'events.jsonl').open('x',encoding='utf-8',newline='\n')
def save(p,x):
    b=(json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix=='.gz' else b)
def emit(kind,**kw):LOG.write(json.dumps(dict(t_s=clock()-START,kind=kind,**kw),allow_nan=False)+'\n');LOG.flush()
class Budget(Exception):pass
def check():
    if clock()-START>=CFG['admission_cutoff_s']:raise Budget()
def main():
    for n,h in json.loads((HERE/'execution_manifest.json').read_bytes()).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
    import numpy as np
    from model import Instance,events,Table,certificate
    from search import exact,greedy_current
    inst=Instance(CASE);inst.bind();builder=Table(inst,check)
    emit('identity',case=inst.case,identity=inst.identity,config=CFG)
    results=[]
    for regime in CFG['regimes']:
        t=clock();tables=[[builder.get(j,d,o,regime) for d in CFG['paths'] for o in events.OPPS] for j in range(4)]
        emit('tables',regime=regime,seconds=clock()-t,legal_per_scene=[sum(k is not None for k in tab) for tab in tables],
             constructed=builder.calls,cache_hits=builder.hits,parts=sum(len(k.parts) for k in builder.cache.values()))
        if regime=='constant':
            # Match two fixed historical full certificates, including unsafe ones.
            old={}
            for line in gzip.open(ROOT/'research/multidnn_diagnostics/raw'/CASE/'events.jsonl.gz','rt'):
                r=json.loads(line)
                if r['kind']=='physical_certificate' and r['data']['deployment'] in CFG['paths']:
                    old.setdefault(r['data']['deployment'],r['data'])
            for d,p in old.items():
                indices=[CFG['paths'].index(d)*27+events.OPPS.index(o) for o in p['opps']]
                observed,_,_=certificate(inst,tables,indices);prior=p['physical']
                err=observed['energy_J']-prior['energy_j'];peakerr=np.max(np.abs(np.array(observed['peak_by_node_C'])-prior['peak_upper_c']))
                assert abs(err)<1e-7 and peakerr<1e-7 and observed['min_slack_ms']==prior['min_slack_ms']
                emit('regression',path=d,energy_error_J=err,peak_error_C=float(peakerr),status='PASS')
        choices={};certificates={}
        for name,allowed in [('fixed_D038',range(27)),('fixed_D040',range(27,54)),('joint',range(54))]:
            indices,proof=exact(tables,inst.initial,allowed,check,lambda kind,**x:emit(kind,regime=regime,method=name,**x))
            choices[name]=indices;certificates[name]=proof
        for name,heat in [('load_only',False),('current_heat',True)]:
            T=inst.initial;indices=[]
            for j,tab in enumerate(tables):
                check();reference=T if heat else CFG['common_reference_C']
                i,records=greedy_current(tab,reference,heat)
                # A paired current-state probe uses only the current scene at
                # actual/ref entry; it never feeds back to the policy.
                probe,_=greedy_current(tab,CFG['common_reference_C'],True)
                emit('decision',regime=regime,method=name,scene=j,observed_entry_C=T,decision_entry_C=reference,
                     selected=i,common_reference_SAFE_choice=probe,options=records)
                if i is None:break
                indices.append(i);_,end=tab[i].affine(np.array(T));T=end.tolist()
            choices[name]=indices if len(indices)==4 else None
            certificates[name]=dict(completed_scenes=len(indices),partial_indices=indices,reason='no_current_SAFE_action' if heat and len(indices)<4 else 'completed')
        for name,indices in choices.items():
            check()
            if indices is None:
                result=dict(regime=regime,method=name,SAFE=False,status='NO_SAFE_PLAN',certificate=certificates[name])
            else:
                p,t,T=certificate(inst,tables,indices);proof=certificates[name]
                if name.startswith('fixed') or name=='joint':
                    assert p['SAFE'] and abs(p['energy_J']-proof['safe_energy_J'])<1e-7
                p.update(case_id=CASE,regime=regime,method=name,indices=indices,identity=inst.identity,search_certificate=proof)
                stem=regime+'_'+name;save(OUT/(stem+'.json.gz'),p)
                np.savez_compressed(OUT/(stem+'_trace.npz'),time_s=t,temperature_C=T)
                result=dict(regime=regime,method=name,SAFE=p['SAFE'],status='SAFE' if p['SAFE'] else 'UNSAFE',
                    energy_J=p['energy_J'],peak_C=p['peak_c'],min_slack_ms=p['min_slack_ms'],
                    paths=[CFG['paths'][i//27] for i in indices],opps=[events.OPPS[i%27] for i in indices],certificate=proof,
                    proof=stem+'.json.gz')
            results.append(result);emit('result',**result)
    save(OUT/'results.json',results);emit('finished',count=len(results))
try:main()
except Budget:emit('stopped',reason='budget_unresolved')
except BaseException as exc:emit('error',type=type(exc).__name__,detail=str(exc));raise
finally:LOG.close()
