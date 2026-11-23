"""Extend only OPP transition events; reuse original profiles and thermal integrator."""
from dataclasses import asdict,replace
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/"research/kim_gap_diagnostics"))
from common import make_domain,Physical,loads
from scheduler import Timeline,dispatch,predictive_calendar

DEP="X4139374";WINDOW=10_040_000_000
BASE_OPPS=["LLL","LLL","LHL","LHL"]

def save(path,data):
    raw=(json.dumps(data,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)

def prepare(load):
    domain=make_domain(ROOT)
    ev=Physical(ROOT,"forward_flat_25C",domain.stages);loads.install(ev,load)
    stages=domain.stages(DEP)
    chains={level:{app:ev._chain(app,tuple(tuple(s) for s in stages[str(app)]),ev.opp_index['L'+level+'L']) for app in ev.apps}
            for level in ["L","H"]}
    requests=[];reference=[];completion={}
    for j,scene in enumerate(ev.scenes):
        sched=ev._schedule(j,ev._signature(DEP,j),ev.opp_index[BASE_OPPS[j]])
        assert sched.deadline_feasible
        requests.extend(replace(q,release_ns=q.release_ns+scene.start_ns,deadline_ns=q.deadline_ns+scene.start_ns) for q in scene.requests)
        reference.extend(replace(r,start_ns=r.start_ns+scene.start_ns,end_ns=r.end_ns+scene.start_ns) for r in sched.rows)
        completion.update({rid:t+scene.start_ns for rid,t in sched.completions_ns.items()})
    order=[(r.request,r.stage_index) for r in reference if r.resource=="GPU"]
    return ev,stages,chains,requests,reference,completion,order

def build_policy(ev,chains,requests,order,strategy,setting,reference,high_reference):
    tau=setting['latency_ns'];energy=setting['energy_j'];dwell=100_000
    events=sys.modules['events']
    if strategy=="simple":
        return dispatch(events,requests,chains,order,WINDOW,simple=(tau,energy,dwell))
    if strategy=="kim":
        timeline=Timeline(WINDOW);timeline.switch(ev.scenes[2].start_ns,"H",tau,energy)
    elif strategy=="predictive":
        timeline=predictive_calendar(high_reference,WINDOW,tau,energy,dwell)
    elif strategy=="ideal_fixed_busy":
        assert tau==energy==0
        timeline=Timeline(WINDOW)
        for row in reference:
            if row.resource=="GPU":
                j=next(j for j,s in enumerate(ev.scenes) if s.start_ns<=row.start_ns<s.end_ns)
                if BASE_OPPS[j][1]=="H":
                    timeline.switch(row.start_ns,"H",0,0);timeline.switch(row.end_ns,"L",0,0)
    else:raise ValueError(strategy)
    rows,completion,timeline=dispatch(events,requests,chains,order,WINDOW,calendar=timeline)
    if strategy=="predictive":assert rows==high_reference,"Perfect forecast did not preserve H reference timing"
    return rows,completion,timeline

def certify(ev,requests,rows,completion,timeline,ambient):
    """Full RC evolution over every power interval with the original continuous peak bound."""
    from events import _window_activity
    from profiles import thermal_kwargs
    from thermal import evaluate_thermal
    spans=timeline.spans()
    edges={s.start_ns for s in ev.scenes}|{WINDOW}
    for a,b,mode in spans:edges.update((a,b))
    busy,start,duration,active,transfer=_window_activity(rows,WINDOW,sorted(edges))
    transition_power=np.zeros(len(start))
    for sw in timeline.switches:
        a,b=sw['start_ns'],sw['end_ns']
        if b>a:
            on=(start>=a)&(start<b)
            assert int(duration[on].sum())==b-a
            transition_power[on]+=sw['energy_j']/((b-a)*1e-9)
        else:assert sw['energy_j']==0
    assert np.all(active[:,1][transition_power>0]==0),"Switch overlaps GPU computation"
    active[:,1]+=transition_power
    previous=np.array([30.]*4);lo=previous.copy();hi=previous.copy()
    totals={k:np.zeros(4) for k in ['idle_J','activity_J','leakage_J']}
    totals.update(energy_J=0.,common_J=0.,transfer_J=0.)
    blocks=[];times=[];temperatures=[]
    for a,b,mode in spans:
        mask=(start>=a)&(start<b)
        assert duration[mask].sum()==b-a
        kw=thermal_kwargs(ev.platform,'L'+('H' if mode=='X' else mode)+'L',ambient,True,'base')
        kw['initial_C']=previous.tolist()
        out=evaluate_thermal(duration[mask]*1e-9,active[mask],transfer_W=transfer[mask],trace=True,**kw)
        for key in totals:totals[key]+=out[key]
        blocks.append(dict(start_ns=a,end_ns=b,mode=mode,entry_c=previous.tolist(),final_c=out['final_C'],
            peak_lower_c=out['peak_lower_C'],peak_upper_c=out['peak_upper_C'],energy_j=out['energy_J']))
        times.extend((a*1e-9+out.pop('trace_time_s')).tolist());temperatures.extend(out.pop('trace_C').tolist())
        previous=np.array(out['final_C']);lo=np.maximum(lo,out['peak_lower_C']);hi=np.maximum(hi,out['peak_upper_C'])
    ledger=[dict(request_id=q.id,app_id=q.app,release_ns=q.release_ns,deadline_ns=q.deadline_ns,
                 completion_ns=completion[q.id],slack_ns=q.deadline_ns-completion[q.id]) for q in requests]
    late=[r['request_id'] for r in ledger if r['slack_ns']<0]
    thermal_status='VIOLATION' if lo.max()>80 else 'SAFE' if hi.max()<=80 else 'UNRESOLVED'
    physical={k:(v.tolist() if isinstance(v,np.ndarray) else float(v)) for k,v in totals.items()}
    physical.update(thermal_status=thermal_status,SAFE=not late and thermal_status=='SAFE',deadline_ok=not late,
        late_ids=late,required=len(requests),completed=len(completion),min_slack_ms=min(r['slack_ns'] for r in ledger)/1e6,
        peak_lower_c=lo.tolist(),peak_upper_c=hi.tolist(),final_c=previous.tolist(),
        switch_energy_j=sum(x['energy_j'] for x in timeline.switches),switch_count=len(timeline.switches),
        gpu_busy_s=busy['GPU']/1e9,gpu_idle_s=(WINDOW-busy['GPU'])/1e9,
        gpu_low_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='L'),
        gpu_high_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='H'),
        gpu_transition_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='X'))
    assert abs(physical['energy_J']-(physical['common_J']+physical['transfer_J']+sum(physical['idle_J'])+sum(physical['activity_J'])+sum(physical['leakage_J'])))<1e-8
    return dict(physical=physical,completions=ledger,rows=[asdict(r) for r in rows],switches=timeline.switches,
                clock_spans=spans,thermal_blocks=blocks),np.array(times),np.array(temperatures)
