"""Generalize existing complete certificate to frozen scene OPPs and supplied initial state."""
from dataclasses import asdict
import numpy as np
WINDOW=10_040_000_000
def certify(ev,requests,rows,completion,timeline,ambient,opps):
    """Full RC evolution over every power interval with the original continuous peak bound."""
    from events import _window_activity
    from profiles import thermal_kwargs
    from thermal import evaluate_thermal
    spans=[]
    for a,b,mode in timeline.spans():
        cuts=sorted({a,b}|{s.start_ns for s in ev.scenes if a<s.start_ns<b})
        spans.extend((x,y,mode) for x,y in zip(cuts,cuts[1:]))
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
    previous=np.array(ev.initial,dtype=float);lo=previous.copy();hi=previous.copy()
    totals={k:np.zeros(4) for k in ['idle_J','activity_J','leakage_J']}
    totals.update(energy_J=0.,common_J=0.,transfer_J=0.)
    blocks=[];times=[];temperatures=[]
    for a,b,mode in spans:
        mask=(start>=a)&(start<b)
        assert duration[mask].sum()==b-a
        j=max(j for j,s in enumerate(ev.scenes) if s.start_ns<=a)
        gpu=mode
        if mode=='X':
            sw=next(s for s in timeline.switches if s['start_ns']<=a<s['end_ns'])
            gpu=max([sw['source'],sw['target']],key='LMH'.index)
        kw=thermal_kwargs(ev.platform,opps[j][0]+gpu+opps[j][2],ambient,True,'base')
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
        gpu_medium_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='M'),
        gpu_high_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='H'),
        gpu_transition_s=sum((b-a)/1e9 for a,b,mode in spans if mode=='X'))
    assert abs(physical['energy_J']-(physical['common_J']+physical['transfer_J']+sum(physical['idle_J'])+sum(physical['activity_J'])+sum(physical['leakage_J'])))<1e-8
    return dict(physical=physical,completions=ledger,rows=[asdict(r) for r in rows],switches=timeline.switches,
                clock_spans=spans,thermal_blocks=blocks),np.array(times),np.array(temperatures)
