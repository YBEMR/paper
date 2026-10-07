"""Read-only audit/export of saved 76 results. No scheduling or thermal search.

High precision checks are diagnostic cross-checks, not interval certificates.
All official evidence was already saved inside each original 60 s call.
"""
from pathlib import Path
import csv, json, hashlib
from collections import Counter
import h5py
import mpmath as mp

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'research/matlab_config_value_src/thermal76_reports/frozen_20260928_163059_270'
OUT = RUN / 'postcheck'
OUT.mkdir(exist_ok=True)
mp.mp.dps = 60

def scalar(g, key):
    return float(g[key][0, 0])

def text(g, key):
    return ''.join(chr(int(x)) for x in g[key][()].flat)

def getrows(name):
    with (RUN / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def writecsv(name, fields, rows):
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields);w.writeheader();w.writerows(rows)

audit={'scope':'saved-evidence audit, no new search or budget extension','cases':{}}
for cid in ['P_high_D6_cold', 'P_high_D6_hot']:
    rows=getrows(cid+'_schedules.csv')
    assert len(rows)==288
    configs=Counter(tuple(r[f'choice_{i}'] for i in range(1,9)) for r in rows)
    safe_configs={tuple(r[f'choice_{i}'] for i in range(1,9)) for r in rows if r['thermal_status']=='safe'}
    data={'state_counts':dict(Counter(r['thermal_status'] for r in rows)),
          'arrangements':len(rows),'label_orbits':len({r['orbit_id'] for r in rows}),
          'configurations':len(configs),'safe_configurations':len(safe_configs)}
    with h5py.File(RUN/(cid+'.mat'),'r') as f:
        r=f['r'];cols=r['columns'][()].T
        options=[f[ref[0]][()].T for ref in r['trial']['case']['options'][()]]
        traces=[]
        for rr in rows:
            work=[]
            for i in range(8):
                unit,freq,duration,q=options[i][int(rr[f'choice_{i+1}'])-1]
                start=int(rr[f'start_tick_{i+1}'])*4
                duration_units=round(duration*4000)
                assert abs(duration-duration_units/4000)<1e-12
                work.append((int(unit),start,start+duration_units,q))
            events=sorted({0,80,*[x for w in work for x in w[1:3]]})
            parts=[]
            for a,b in zip(events,events[1:]):
                pc=.2+sum(w[3] for w in work if w[0]<3 and w[1]<=a<w[2])
                pn=.3+sum(w[3] for w in work if w[0]==3 and w[1]<=a<w[2])
                if parts and parts[-1][2:]==(pc,pn):parts[-1]=(parts[-1][0],b,pc,pn)
                else:parts.append((a,b,pc,pn))
            traces.append(tuple(parts))
        data['distinct_injection_traces']=len(set(traces))
        data['violating_injection_traces']=len({t for t,rr in zip(traces,rows) if rr['thermal_status']=='violation'})
        data['timing_s']={k:scalar(r['timing'],k) for k in r['timing']}
        data['elapsed_s']=scalar(r,'elapsed_s')
        data['max_peak_enclosure_C']=max(scalar(f[ref[0]],'enclosure_width') for ref in r['thermal'][()])
        if cid.endswith('hot'):
            certs=[];coefs=[];unique=[];seen=set();excluded_union=set();removed_traces=[]
            highprec_ok=True;min_coef_margin=mp.inf;min_source_margin=mp.inf
            for cutref in r['cuts'][()]:
                cut=f[cutref[0]];row=cut['row'];node=int(scalar(row,'node'));t=mp.mpf(scalar(row,'time_s'))
                baseline=row['baseline_interval'][()].ravel();bound=scalar(row,'rhs_upper')
                coef=row['coefficient_lower'][()].ravel();pulse=row['pulse_interval'][()].T
                source=int(scalar(cut,'source_row'));excluded=[int(x) for x in cut['excluded_rows'][()].ravel()]
                excluded_union.update(excluded)
                assert source in excluded and all(rows[x-1]['thermal_status']=='violation' for x in excluded)
                trajectory_count=len({traces[x-1] for x in excluded});removed_traces.append(trajectory_count)
                key=(node,float(t),tuple(coef),bound)
                if key not in seen:
                    seen.add(key);uid=len(unique)+1
                    M=5+(53-5)*mp.exp(-20*t)
                    D=-mp.mpf('.5')+mp.mpf('.5')*mp.exp(-40*t)
                    base=25+M+(D if node==1 else -D)
                    assert mp.mpf(float(baseline[0]))<=base<=mp.mpf(float(baseline[1]))
                    assert mp.mpf(bound)>=80+mp.mpf('.000001')-mp.mpf(float(baseline[0]))
                    for j,col in enumerate(cols):
                        stage,choice,ss,ee,unit,_,_=map(int,col)
                        q=mp.mpf(float(options[stage-1][choice-1,3]));s=mp.mpf(ss)/4000;e=mp.mpf(ee)/4000
                        u=max(mp.mpf(0),min(t,e)-s);lag=max(mp.mpf(0),t-e)
                        a=10*(1-mp.exp(-20*u))*mp.exp(-20*lag)
                        b=5*(1-mp.exp(-40*u))*mp.exp(-40*lag)
                        kind=1 if unit<3 else 2;v=q*(a+b if kind==node else a-b)
                        assert mp.mpf(float(pulse[j,0]))<=v<=mp.mpf(float(pulse[j,1]))
                        assert mp.mpf(float(coef[j]))<=v
                        min_coef_margin=min(min_coef_margin,v-mp.mpf(float(coef[j])))
                        coefs.append(dict(cut_id=uid,option_id=j+1,stage=stage,choice=choice,
                            start_quarter_ms=ss,end_quarter_ms=ee,unit=unit,
                            coefficient_lower_C=float(coef[j]),response_upper_C=float(pulse[j,1])))
                    unique.append(dict(cut_id=uid,node=node,time_s=float(t),baseline_lower_C=float(baseline[0]),
                        baseline_upper_C=float(baseline[1]),rhs_upper_C=bound,
                        excluded_rows=excluded,excluded_injection_traces=trajectory_count))
                source_lhs=cut['source_lhs_interval'][()].ravel()
                min_source_margin=min(min_source_margin,mp.mpf(float(source_lhs[0]))-mp.mpf(bound))
                certs.append(dict(source_row=source,node=node,time_ms=float(t)*1000,
                    source_lhs_lower_C=float(source_lhs[0]),rhs_upper_C=bound,
                    excluded_raw=len(excluded),excluded_orbits=len(set(rows[x-1]['orbit_id'] for x in excluded)),
                    excluded_injection_traces=trajectory_count))
            writecsv('cut_details.csv',list(certs[0]),certs)
            writecsv('unique_cut_coefficients.csv',list(coefs[0]),coefs)
            (OUT/'unique_cuts.json').write_text(json.dumps(unique,indent=2),encoding='utf-8')
            data.update(unique_cut_rows=len(unique),excluded_union=len(excluded_union),
                coverage_histogram=dict(Counter(x['excluded_raw'] for x in certs)),
                excluded_trace_histogram=dict(Counter(removed_traces)),
                high_precision_crosscheck=True,min_source_strict_margin_C=float(min_source_margin),
                min_coefficient_lower_slack_C=float(min_coef_margin))
    audit['cases'][cid]=data

protected=json.loads((ROOT/'research/thermal76_design/protected_before.json').read_text(encoding='utf-8'))
changes=[]
for rec in protected:
    p=ROOT/rec['path']
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=rec['sha256']:changes.append(rec['path'])
experimental_changes=[x for x in changes if not x.startswith('research/latex/')]
assert not experimental_changes,experimental_changes
audit['historical_hashes']={'count':len(protected),'unchanged_count':len(protected)-len(changes),
    'experimental_inputs_sources_results_unchanged':True,'observed_latex_changes_not_written_by_this_task':changes}
(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
