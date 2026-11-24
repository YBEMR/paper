"""Offline audit, causal decision attribution and predeclared follow-up gate."""
from pathlib import Path
from collections import defaultdict,Counter
import csv,gzip,hashlib,json
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/'config.json').read_bytes())
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def save(name,x):(HERE/name).write_bytes((json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode())
def csv_out(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in r.items()})
def main():
    for name,h in read(HERE/'execution_manifest.json').items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    rows=[];states=[];decisions=[];summary=[];counts=Counter();gate=[]
    for case in CFG['cases']:
        out=HERE/'raw'/case;receipt=read(out/'receipt.json')
        assert receipt['returncode']==0 and not receipt['hard_timeout'] and receipt['wall_s']<=CFG['case_budget_s']
        for name,h in receipt['files'].items():assert hashlib.sha256((out/name).read_bytes()).hexdigest()==h,name
        logs=[json.loads(s) for s in (out/'events.jsonl').read_text().splitlines()]
        assert logs[-1]['kind']=='finished' and logs[-1]['t_s']<=CFG['case_budget_s']
        identity=next(r for r in logs if r['kind']=='identity');initial=identity['case']['initial_c']
        assert sum(r['kind']=='regression' and r['status']=='PASS' for r in logs)==2
        stream=read(ROOT/'research/multidnn_model_review'/identity['case']['input_stream'])
        for r in [r for r in logs if r['kind']=='decision']:
            choices=r['options'];heat=r['method']=='current_heat';entry=r['observed_entry_C'] if heat else CFG['common_reference_C']
            assert r['decision_entry_C']==entry
            valid=[o for o in choices if not heat or o['status']==1]
            expected=None
            if valid:
                lowest=min(o['energy_J'] for o in valid)
                expected=min(o['index'] for o in valid if o['energy_J']<=lowest+1e-9)
            assert r['selected']==expected
            ref=r['common_reference_SAFE_choice'];selected=r['selected']
            decisions.append(dict(case_id=case,regime=r['regime'],method=r['method'],scene=r['scene'],entry_C=entry,
                observed_entry_C=r['observed_entry_C'],selected=selected,reference_SAFE_selected=ref,
                same_scene_path_changed_with_entry=(None if selected is None or ref is None else selected//27!=ref//27),
                selected_path=None if selected is None else CFG['paths'][selected//27]))
        results=read(out/'results.json');assert len(results)==10
        for r in results:
            c=dict(case_id=case,**r);proof=c.pop('certificate')
            c.update(optimal_or_infeasible_certified=proof.get('finite_domain_optimal'),legal_sequences=proof.get('legal_sequences'),
                     checked_in_energy_order=proof.get('tested_by_energy_order'),unresolved=proof.get('unresolved_before'),
                     valid_lower_bound_J=proof.get('valid_lower_bound_J'),proven_no_safe=proof.get('proven_no_safe',False))
            if 'proof' not in r:
                assert not r['SAFE'];rows.append(c);continue
            p=read(out/r['proof']);assert p['identity']==identity['identity']
            assert abs(p['energy_J']-r['energy_J'])<1e-9 and p['SAFE']==r['SAFE']
            assert len(p['ledger'])==len({q['id'] for q in p['ledger']})==500
            assert {q[0]:(q[1],q[2],q[3]) for q in stream['requests']}=={q['id']:(q['app'],q['release_ns'],q['deadline_ns']) for q in p['ledger']}
            groups=defaultdict(list);units=defaultdict(list)
            for v in p['rows']:groups[v['request']].append(v);units[v['resource']].append(v)
            for q in p['ledger']:
                rr=sorted(groups[q['id']],key=lambda v:v['stage_index'])
                assert rr[0]['start_ns']>=q['release_ns'] and rr[-1]['end_ns']==q['completion_ns']
                assert all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
                assert q['completion_ns']<=q['deadline_ns']
            for rr in units.values():
                rr.sort(key=lambda v:v['start_ns']);assert all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
            T=initial;energy=0.;peak=np.array(initial)
            for j,s in enumerate(p['scenes']):
                assert s['entry_C']==T and s['path']==r['paths'][j] and s['opp']==r['opps'][j]
                previous=T;subtotal=0.
                for part in s['parts']:
                    assert part['entry_C']==previous;previous=part['final_C'];subtotal+=part['energy_J']
                assert previous==s['final_C'] and abs(subtotal-s['energy_J'])<1e-8
                assert abs(s['energy_J']-sum([s['common_J'],s['transfer_J'],sum(s['idle_J']),sum(s['activity_J']),sum(s['leakage_J'])]))<1e-8
                T=s['final_C'];energy+=s['energy_J'];peak=np.maximum(peak,s['peak_upper_C'])
                states.append(dict(case_id=case,regime=r['regime'],method=r['method'],scene=j,name=s['scene'],path=s['path'],opp=s['opp'],
                    entry_CPU_C=s['entry_C'][0],entry_GPU_C=s['entry_C'][1],entry_DLA0_C=s['entry_C'][2],entry_DLA1_C=s['entry_C'][3],
                    exit_CPU_C=T[0],exit_GPU_C=T[1],exit_DLA0_C=T[2],exit_DLA1_C=T[3],
                    energy_J=s['energy_J'],peak_C=max(s['peak_upper_C']),min_slack_ms=s['min_slack_ms'],thermal_status=s['thermal_status']))
            assert abs(energy-p['energy_J'])<1e-8 and max(peak)==p['peak_c']
            assert p['SAFE']==all(s['thermal_status']=='SAFE' for s in p['scenes'])
            with np.load(out/r['proof'].replace('.json.gz','_trace.npz')) as tr:
                assert np.all(tr['temperature_C'][0]==initial) and abs(tr['time_s'][-1]-10.04)<1e-8
                assert np.all(np.max(tr['temperature_C'],axis=0)<=np.array(p['peak_by_node_C'])+1e-8)
            if r['method'].startswith('fixed') or r['method']=='joint':
                assert proof['finite_domain_optimal'] and p['SAFE'] and abs(p['energy_J']-proof['safe_energy_J'])<1e-7
            c['leakage_J']=sum(sum(s['leakage_J']) for s in p['scenes'])
            c['nominal_path_changes']=sum(a!=b for a,b in zip(r['paths'],r['paths'][1:]))
            rows.append(c);counts['certificates']+=1;counts['requests']+=500;counts['SAFE']+=int(p['SAFE'])
        for regime in CFG['regimes']:
            d={r['method']:r for r in rows if r['case_id']==case and r['regime']==regime}
            j=d['joint'];g=d['current_heat'];l=d['load_only'];fixed=[d[k] for k in ['fixed_D038','fixed_D040'] if d[k]['SAFE']]
            f=min(fixed,key=lambda r:r['energy_J']) if fixed else None
            fixed_gain=None if f is None else 100*(f['energy_J']-j['energy_J'])/f['energy_J']
            greedy_gain=None if not g['SAFE'] else 100*(g['energy_J']-j['energy_J'])/g['energy_J']
            total_extra=None if f is None else f['energy_J']-j['energy_J']
            row=dict(case_id=case,regime=regime,best_fixed=None if f is None else f['method'],best_fixed_J=None if f is None else f['energy_J'],
                load_only_J=l.get('energy_J'),load_only_SAFE=l['SAFE'],greedy_J=g.get('energy_J'),greedy_SAFE=g['SAFE'],joint_J=j['energy_J'],
                joint_peak_C=j.get('peak_C'),joint_paths=j.get('paths'),joint_opps=j.get('opps'),
                joint_saving_vs_fixed_pct=fixed_gain,joint_saving_vs_greedy_pct=greedy_gain,
                extra_path_cost_total_break_even_J=total_extra,
                extra_path_resident_power_break_even_W=None if total_extra is None else max(0,total_extra)/10.04,
                extra_per_nominal_change_J=total_extra/j['nominal_path_changes'] if total_extra is not None and j['nominal_path_changes'] else None,
                wall_s=receipt['wall_s'])
            summary.append(row)
            if regime=='idle_zero':
                trigger=(j['SAFE'] and not g['SAFE']) or any(v is not None and v>=CFG['nonzero_trigger_gap_pct'] for v in [fixed_gain,greedy_gain])
                gate.append(dict(case_id=case,trigger=trigger,gap_fixed_pct=fixed_gain,gap_greedy_pct=greedy_gain,greedy_failed=not g['SAFE']))
    csv_out('comparison.csv',rows);csv_out('scene_states.csv',states);csv_out('decisions.csv',decisions);csv_out('summary.csv',summary)
    save('summary.json',summary);save('followup_gate.json',dict(run_nonzero=any(r['trigger'] for r in gate),cases=gate,rule=CFG['nonzero_trigger_gap_pct']))
    save('verification.json',dict(status='PASS',counts=dict(counts),methods=40,regression_witnesses=8,scope='full archive audit and decision rules; no additional physical replay'))
    print(json.dumps(summary,ensure_ascii=False,indent=2));print('NONZERO GATE',any(r['trigger'] for r in gate))
if __name__=='__main__':main()
