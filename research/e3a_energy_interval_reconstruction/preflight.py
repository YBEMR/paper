import json, os, subprocess, sys, time
from shared import *
def calculate(case,side):
    p,plan=load_native(case,side)
    from model import event_arrays,independent_events
    from heat import evaluate
    import numpy as np
    a,sw,_=event_arrays(p,*plan);b,sw2=independent_events(p,*plan)
    assert sw==sw2 and np.array_equal(a,b)
    m=evaluate(p,plan,cert=True,trace=True)
    arr=np.asarray(m.pop('events')); historical=read(DATA/case/'original_certificate.json')
    delta={k:float(np.max(np.abs(np.array(m[k])-np.array(v)))) for k,v in historical['metrics'].items() if k!='status'}
    assert m['status']==historical['metrics']['status']=='SAFE' and max(delta.values())<1e-7,delta
    assert sw==[tuple(x) for x in historical['switches']]
    assert a[0,0]==0 and a[-1,1]==p.horizon and np.array_equal(a[:-1,1],a[1:,0])
    assert p.horizon==int((p.boundaries[-1]+(p.boundaries[0] if p.boundaries else 0))+3010)
    facts=dict(input=sha(request_bytes(p)),events=sha(a.tobytes()),trace=sha(arr.tobytes()),metrics=m,
               horizon=p.horizon,segments=len(arr),initial=p.initial.tolist(),cap=p.cap.tolist(),G=p.G.tolist(),options=[list(p.options[i]) for i in range(3)],historical_maximum_absolute_difference=max(delta.values()))
    where=RUN/'preflight'/case
    put(where/(side+'.json'),facts)
    if side=='chapter3':
        from construct import assemble,idle_plan
        cfg=[r[:2] for r in plan[0][1::3]]; rebuilt=assemble(p,cfg)
        try:
            alt=idle_plan(p,rebuilt);altm=evaluate(p,alt,cert=True)
            alt_info=dict(status=altm['status'],energy_J=altm['E_J'],switches_equal=event_arrays(p,*alt)[1]==sw,low_equal=alt[1]==plan[1])
        except ValueError as e:alt_info=dict(error=str(e))
        put(where/'fifo.json',dict(rows_equal=rebuilt==plan[0],row_differences=sum(x!=y for x,y in zip(rebuilt,plan[0])),**alt_info))
        np.savez_compressed(where/'original_events.npz',events=arr)
def main():
    if len(sys.argv)>1:return calculate(*sys.argv[1:])
    start=time.monotonic();end=start+540
    hashes={}
    for f in ['model.py','heat.py','profiles.py','config/p1_frozen.json','config/gpu_profiles.csv','config/cpu_npu_profiles.csv']:
        a,b=[sha((root/f).read_bytes()) for root in [THREE/P1PATH,NT/NTPATH]]
        hashes[f]=[a,b];assert f=='profiles.py' or a==b
    for c in ['D1','D2','C10']:
        for s in ['chapter3','NT']:
            subprocess.run([sys.executable,__file__,c,s],check=True,timeout=end-time.monotonic())
        folder=RUN/'preflight'/c
        assert read(folder/'NT.json')==read(folder/'chapter3.json')
    put(RUN/'preflight'/'receipt.json',dict(status='PASS',single_core=list(os.sched_getaffinity(0)),wall_s=time.monotonic()-start,historical_inventory_reserved_s=60,hashes=hashes))
if __name__=='__main__': main()
