"""Independent resource/event/convolution/Decimal checks; does not import experiment.py."""
from pathlib import Path
from itertools import product
from fractions import Fraction as F
from decimal import Decimal as D, localcontext
import csv, hashlib, json, time
import numpy as np

ROOT=Path(__file__).resolve().parent

def check(out):
    tic=time.perf_counter()
    cfg=json.loads((ROOT/'inputs.json').read_text())
    cases=json.loads((ROOT/'parameter_grid.json').read_text())
    by_case={c['case_id']:c for c in cases}
    L=F('0.11455');pre=L/20;post=L/20;window=4*L
    masks=[frozenset(x) for x in cfg['masks']]
    d=[[F(str(v))/1000 for v in row] for row in cfg['isolated_latency_ms_by_width']]
    catalogs={}
    timeline_checks=0;gene_checks=0;max_finish_error=0.0
    for sigma in cfg['concurrent_slowdown_sigma']:
        cat=json.loads((out/f'catalog_sigma_{sigma}.json').read_text())
        gene_map={tuple(e['gene']):e['sid'] for e in cat['gene_to_sid']}
        independently_legal={}
        # Distinct loop structure and exact rational event progression.
        for order in [0,1]:
            for a,b in product(range(5),repeat=2):
                da,db=d[0][len(masks[a])-1],d[1][len(masks[b])-1]
                ds=[da,db]
                for u,v in product(range(4),repeat=2):
                    for anchor in [0,1]:
                        delay=[F(0),F(1,4),F(1,2),F(1)]
                        starts=[F(0),F(0)]
                        starts[order]=pre+L*delay[u]
                        starts[1-order]=starts[order]+anchor*ds[order]+L*delay[v]
                        overlap=max(starts)<min(starts[0]+da,starts[1]+db)
                        gene=(a,b,order,anchor,u,v)
                        legal=not (overlap and masks[a]&masks[b])
                        assert (gene in gene_map)==legal
                        gene_checks+=1
                        if not legal:continue
                        independently_legal[gene]=(a,b,*starts)
        assert len(independently_legal)==cat['legal_genes']
        assert len(set(independently_legal.values()))==cat['unique_schedules']
        for row in cat['rows']:
            a,b=row['a'],row['b']
            starts=[F(round(row['sa']/1e-7),10_000_000),F(round(row['sb']/1e-7),10_000_000)]
            left=[d[0][len(masks[a])-1],d[1][len(masks[b])-1]]
            done=[False,False];ends=[None,None];clock=min(starts)
            while not all(done):
                active=[j for j in range(2) if not done[j] and starts[j]<=clock]
                factor=F(1)+F(str(sigma)) if len(active)==2 else F(1)
                events=[clock+left[j]*factor for j in active]
                events.extend(starts[j] for j in range(2) if not done[j] and starts[j]>clock)
                next_time=min(events)
                for j in active:
                    left[j]-=(next_time-clock)/factor
                    if left[j]==0:done[j]=True;ends[j]=next_time
                clock=next_time
            err=max(abs(float(ends[0])-row['fa']),abs(float(ends[1])-row['fb']))
            assert err<1e-12
            max_finish_error=max(max_finish_error,err)
            assert starts[0]>=pre and starts[1]>=pre
            if masks[a]&masks[b]:assert ends[0]<=starts[1] or ends[1]<=starts[0]
            assert max(ends)+post <= window
            timeline_checks+=1
        catalogs[sigma]=cat
    raw=np.load(out/'all_candidates.npz',allow_pickle=False)
    summary_rows=list(csv.DictReader((out/'cases.csv').open(encoding='utf-8')))
    method_rows=list(csv.DictReader((out/'methods.csv').open(encoding='utf-8')))
    computed_peak={};computed_energy={};max_convolution_error=0.;max_energy_error=0.
    full_candidate_checks=0;deadline_checks=0;reference_checks=0
    for k,cid in enumerate(raw['case_ids']):
        case=by_case[str(cid)];cat=catalogs[case['concurrent_slowdown_sigma']]
        rows=cat['rows'];n=len(rows)
        sa=np.array([r['sa'] for r in rows]);sb=np.array([r['sb'] for r in rows])
        fa=np.array([r['fa'] for r in rows]);fb=np.array([r['fb'] for r in rows])
        pa=np.array([[1,case['p2_over_p1'],case['p2_over_p1']*case['p3_over_p2']][len(masks[r['a']])-1] for r in rows])
        pb=np.array([[1,case['p2_over_p1'],case['p2_over_p1']*case['p3_over_p2']][len(masks[r['b']])-1] for r in rows])
        t=np.sort(np.column_stack((np.zeros(n),sa,sb,fa,fb,np.full(n,float(window)))),axis=1)
        tau=float(L)*case['tau_over_time_unit'];gain=case['single_power_steady_theta_gain']
        decay=np.exp(-t/tau)
        # Independent superposition, not segment recursion.
        theta=case['entry_theta']*decay+gain*.2*(1-decay)
        for starts,ends,p in [(sa,fa,pa),(sb,fb,pb)]:
            theta+=gain*p[:,None]*(np.exp(-np.maximum(t-ends[:,None],0)/tau)-np.exp(-np.maximum(t-starts[:,None],0)/tau))
        peaks=25+20*np.max(theta,axis=1)
        delta=float(np.max(np.abs(peaks-raw['peak_C'][k])))
        assert delta<1e-10;max_convolution_error=max(max_convolution_error,delta)
        # Complete system event integral including CPU work and idle tail.
        event=np.sort(np.column_stack((np.zeros(n),np.full(n,float(pre)),sa,sb,fa,fb,fa+float(post),fb+float(post),np.full(n,float(window)))),axis=1)
        mid=(event[:,1:]+event[:,:-1])/2
        p=np.ones(mid.shape)
        p+=((mid<float(pre))*1.0)
        p+=.5*((mid>=fa[:,None]) & (mid<(fa+float(post))[:,None]))
        p+=.5*((mid>=fb[:,None]) & (mid<(fb+float(post))[:,None]))
        p+=pa[:,None]*((mid>=sa[:,None]) & (mid<fa[:,None]))
        p+=pb[:,None]*((mid>=sb[:,None]) & (mid<fb[:,None]))
        en=np.sum(p*np.diff(event,axis=1),axis=1)
        delta=float(np.max(np.abs(en-raw['energy_J'][k])))
        assert delta<1e-12;max_energy_error=max(max_energy_error,delta)
        safe=peaks<45-1e-8;ambiguous=np.abs(peaks-45)<=1e-8
        assert np.array_equal(raw['thermal_state'][k],np.where(ambiguous,2,np.where(safe,0,1)))
        deadline=(.1+case['deadline_npu_allowance_over_time_unit'])*float(L)
        ontime=(fa+float(post)<=deadline+1e-11)&(fb+float(post)<=deadline+1e-11)
        summary=summary_rows[k];assert cid==summary['case_id']
        assert int(summary['deadline_feasible'])==int(ontime.sum())
        assert int(summary['safe_feasible'])==int((ontime&safe).sum())
        feasible=en[ontime&safe]
        if len(feasible):assert abs(float(summary['E_J'])-float(feasible.min()))<1e-10
        else:assert summary['E_J']==''
        computed_peak[str(cid)]=peaks;computed_energy[str(cid)]=en
        full_candidate_checks+=n;deadline_checks+=n;reference_checks+=1
    for row in method_rows:
        if not row['sid']:continue
        sid=int(row['sid']);cid=row['case_id'];case=by_case[cid]
        assert abs(float(row['energy_J'])-computed_energy[cid][sid])<1e-12
        assert abs(float(row['peak_C'])-computed_peak[cid][sid])<1e-10
        if row['status']=='SAFE':
            assert computed_peak[cid][sid] < 45-1e-8
            assert float(row['completion_A_ms'])<=float(row['deadline_ms'])+1e-8
            assert float(row['completion_B_ms'])<=float(row['deadline_ms'])+1e-8
            assert float(row['gap_to_E_percent'])>=-1e-8
        else:assert row['gap_to_E_percent']==''
    # High precision checks cover every returned schedule; cache identical physics
    # across deadline variants, not across different input states/powers.
    checked={};max_decimal_error=0.;decimal_count=0
    with localcontext() as ctx:
        ctx.prec=60
        for line in (out/'selected_trajectories.jsonl').open(encoding='utf-8'):
            tr=json.loads(line);case=by_case[tr['case_id']];r=tr['schedule']
            key=tuple(case[x] for x in ['p2_over_p1','p3_over_p2','concurrent_slowdown_sigma','entry_theta','tau_over_time_unit','single_power_steady_theta_gain'])+(tr['sid'],)
            if key not in checked:
                # Independently sorted endpoints; exact decimal recurrence.
                times=sorted([D(0),D(str(r['sa'])),D(str(r['sb'])),D(str(r['fa'])),D(str(r['fb'])),D(str(float(window)))])
                theta=D(str(case['entry_theta']));peak=theta;path=[theta]
                power=[D(1),D(str(case['p2_over_p1'])),D(str(case['p2_over_p1']))*D(str(case['p3_over_p2']))]
                tau=D('0.11455')*D(str(case['tau_over_time_unit']))
                gain=D(str(case['single_power_steady_theta_gain']))
                for t0,t1 in zip(times,times[1:]):
                    mid=(t0+t1)/2;heat=D('.2')
                    if D(str(r['sa']))<=mid<D(str(r['fa'])):heat+=power[len(masks[r['a']])-1]
                    if D(str(r['sb']))<=mid<D(str(r['fb'])):heat+=power[len(masks[r['b']])-1]
                    equilibrium=gain*heat
                    theta=equilibrium+(theta-equilibrium)*(-(t1-t0)/tau).exp()
                    path.append(theta);peak=max(peak,theta)
                checked[key]=[float(D(25)+D(20)*q) for q in path]
                decimal_count+=1
            err=max(abs(x-y) for x,y in zip(checked[key],tr['temperature_C']))
            assert err<1e-10;max_decimal_error=max(max_decimal_error,err)
    frozen=json.loads((ROOT/'freeze.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in frozen['files'].items())
    result=dict(status='PASS',independence='separate implementation by same assistant; no external reviewer',
                raw_gene_legality_checks=gene_checks,independent_event_timelines=timeline_checks,
                all_candidate_thermal_and_energy_checks=full_candidate_checks,deadline_checks=deadline_checks,
                independent_reference_minimum_checks=reference_checks,method_records_checked=len(method_rows),
                high_precision_unique_trajectories=decimal_count,decimal_digits=60,
                max_finish_error_s=max_finish_error,max_convolution_peak_error_K=max_convolution_error,
                max_energy_event_integral_error_J=max_energy_error,max_decimal_path_error_K=max_decimal_error,
                frozen_inputs_unchanged=True,wall_s=time.perf_counter()-tic)
    (out/'independent_verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2),flush=True)
    return result

if __name__=='__main__':
    import sys
    check(Path(sys.argv[1]))
