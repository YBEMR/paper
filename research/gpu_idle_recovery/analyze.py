"""Offline certificate audit and matched recovery tables. No physical reruns."""
from pathlib import Path
from collections import defaultdict,Counter
from bisect import bisect_right
import csv,gzip,json,hashlib
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
CFG=json.loads((HERE/'config.json').read_bytes())
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,x):(HERE/name).write_bytes((json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode())
def csv_out(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,separators=(',',':')) if isinstance(v,(dict,list)) else v for k,v in r.items()})

def main():
    for n,h in read(HERE/'execution_manifest.json').items():assert sha(ROOT/n)==h,n
    allrows=[];summaries=[];coverage_rows=[];counts=Counter();ignored=[]
    for case in CFG['cases']:
        out=HERE/'raw'/case;receipt=read(out/'receipt.json')
        for n,h in receipt['files'].items():assert sha(out/n)==h,n
        log=[]
        for line in (out/'events.jsonl').read_text().splitlines():
            try:r=json.loads(line)
            except json.JSONDecodeError:ignored.append(case+':truncated_line');continue
            if r['t_s']<=CFG['budget_s']:log.append(r)
            else:ignored.append(case+':late_record')
        identity=next(r for r in log if r['kind']=='identity');casecfg=identity['case'];initial=casecfg['initial_c']
        assert any(r['kind']=='regression' and r['status']=='PASS' for r in log)
        targets=next(r for r in log if r['kind']=='targets');coverage=targets['coverage']
        selected={r['dep']:r for r in log if r['kind']=='selection'}
        rows=[]
        for r in [r for r in log if r['kind']=='idle']:
            dep,code=r['dep'],r['code'];stem=f'{dep}_{code}'
            p=read(out/(stem+'_idle.json.gz'));old=read(out/(stem+'_original.json.gz'));phy=p['physical']
            assert r['physical']==phy and p['identity']==identity['identity']
            ledger=p['completions'];jobs={q['request_id']:q for q in ledger}
            assert len(jobs)==len(ledger)==750 and phy['required']==phy['completed']==750
            stream=read(ROOT/'research/multidnn_model_review'/casecfg['input_stream'])
            assert {q[0]:(q[1],q[2],q[3]) for q in stream['requests']}=={rid:(q['app_id'],q['release_ns'],q['deadline_ns']) for rid,q in jobs.items()}
            stage_by_job=defaultdict(list);units=defaultdict(list)
            for row in p['rows']:stage_by_job[row['request']].append(row);units[row['resource']].append(row)
            assert set(stage_by_job)==set(jobs)
            for rid,rr in stage_by_job.items():
                rr.sort(key=lambda v:v['stage_index']);q=jobs[rid]
                assert [v['stage_index'] for v in rr]==list(range(len(rr)))
                assert rr[0]['start_ns']>=q['release_ns'] and rr[-1]['end_ns']==q['completion_ns']
                assert all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
                assert q['slack_ns']==q['deadline_ns']-q['completion_ns']
            for rr in units.values():
                rr.sort(key=lambda v:v['start_ns']);assert all(a['end_ns']<=b['start_ns'] for a,b in zip(rr,rr[1:]))
            features={(v['request'],v['stage_index']):(v['resource'],v['stage'],v['end_ns']-v['start_ns'],v['activity_w']) for v in p['rows']}
            assert hashlib.sha256(repr(sorted(features.items())).encode()).hexdigest()==p['reference_stage_features_sha']
            spans=p['clock_spans'];starts=[s[0] for s in spans]
            assert spans[0][0]==0 and spans[-1][1]==CFG['window_ns'] and all(a[1]==b[0] for a,b in zip(spans,spans[1:]))
            audit=read(out/(stem+'_control.json.gz'))
            required={e['rid']:e['required'] for e in audit['controller_log'] if e['kind']=='release'}
            for row in units.get('GPU',[]):
                span=spans[bisect_right(starts,row['start_ns'])-1]
                assert span[2]==required[row['request']]
                assert all(mode==required[row['request']] for a,b,mode in spans if max(a,row['start_ns'])<min(b,row['end_ns']))
            for sw in p['switches']:
                assert sw['end_ns']-sw['start_ns']==CFG['latency_ns'] and sw['energy_j']==CFG['energy_j']
                assert all(max(v['start_ns'],sw['start_ns'])>=min(v['end_ns'],sw['end_ns']) for v in units.get('GPU',[]))
            assert phy['min_slack_ms']==min(q['slack_ns'] for q in ledger)/1e6
            assert phy['deadline_ok']==all(q['slack_ns']>=0 for q in ledger)
            assert phy['SAFE']==(phy['deadline_ok'] and max(phy['peak_upper_c'])<=80 and phy['scene_frequency_valid'])
            previous=initial;total=0.
            for b,s in zip(p['thermal_blocks'],spans,strict=True):
                assert [b['start_ns'],b['end_ns'],b['mode']]==s and b['entry_c']==previous
                previous=b['final_c'];total+=b['energy_j']
            assert previous==phy['final_c'] and abs(total-phy['energy_J'])<1e-8
            assert abs(phy['energy_J']-sum([sum(phy['idle_J']),sum(phy['activity_J']),sum(phy['leakage_J']),phy['common_J'],phy['transfer_J']]))<1e-8
            with np.load(out/(stem+'_trace.npz')) as a:
                assert a['temperature_c'].shape==(len(a['time_s']),4) and a['temperature_c'][0].tolist()==initial
                assert abs(a['time_s'][-1]-10.04)<1e-8 and np.all(np.max(a['temperature_c'],axis=0)<=np.array(phy['peak_upper_c'])+1e-8)
            z=dict(case_id=case,dep=dep,code=code,opps=r['opps'],reason=r['reason'],original_energy_J=old['energy_j'],
                 original_peak_c=max(old['peak_upper_c']),original_thermal_status=old['thermal_status'],
                 original_safe_frequency_count=coverage[dep]['original_safe'],energy_J=phy['energy_J'],peak_c=max(phy['peak_upper_c']),
                 min_slack_ms=phy['min_slack_ms'],SAFE=phy['SAFE'],deadline_ok=phy['deadline_ok'],thermal_status=phy['thermal_status'],
                 restored_sequence=old['thermal_status']=='VIOLATION' and phy['SAFE'],
                 recovered_deployment=coverage[dep]['original_safe']==0 and phy['SAFE'],
                 idle_J=sum(phy['idle_J']),leakage_J=sum(phy['leakage_J']),compute_J=sum(phy['activity_J'])-phy['switch_energy_j'],
                 switch_J=phy['switch_energy_j'],switches=phy['switch_count'],gpu_low_s=phy['gpu_low_s'],
                 gpu_medium_s=phy['gpu_medium_s'],gpu_high_s=phy['gpu_high_s'],elapsed_s=r['t_s'],proof=(out/(stem+'_idle.json.gz')).relative_to(ROOT).as_posix())
            rows.append(z);counts['certificates']+=1;counts['requests']+=750;counts['stages']+=len(p['rows']);counts['SAFE']+=int(phy['SAFE'])
        # Audit all declared min-peak certificates against the archived bounds.
        for dep,s in selected.items():
            with np.load(out/f'{dep}_selection_bounds.npz') as a:
                codes,L=a['codes'],a['lower_c'];tested=set(s['refined_codes']);best=s['min_peak_c']
                assert all(l>=best-CFG['peak_minimum_tolerance_c'] for c,l in zip(codes,L) if int(c) not in tested)
                peaks=[max(read(out/f'{dep}_{c}_original.json.gz')['peak_upper_c']) for c in tested]
                assert min(peaks)==best
        baseline=next(r for r in rows if r['reason']=='D017_reference');safe=[r for r in rows if r['SAFE']]
        best=min(safe,key=lambda r:(r['energy_J'],r['dep'],r['code']))
        for r in rows:
            r['extra_saving_vs_D017_idle_pct']=100*(baseline['energy_J']-r['energy_J'])/baseline['energy_J'] if r['SAFE'] and baseline['SAFE'] else None
        recovered=sorted({r['dep'] for r in rows if r['recovered_deployment']})
        for dep,v in coverage.items():
            tested=[r for r in rows if r['dep']==dep]
            coverage_rows.append(dict(case_id=case,dep=dep,**v,selected_minima_completed=dep in selected,
                idle_sequences=len(tested),safe_sequences=sum(r['SAFE'] for r in tested),recovered=dep in recovered,
                min_peak_original_c=selected.get(dep,{}).get('min_peak_c'),band_candidates=selected.get(dep,{}).get('band_candidates')))
        summaries.append(dict(case_id=case,original_D017_J=float(identity['reference']['best_safe_j']),original_D017_peak_c=float(identity['reference']['best_safe_peak_c']),
            D017_idle_J=baseline['energy_J'],D017_idle_peak_c=baseline['peak_c'],D017_idle_slack_ms=baseline['min_slack_ms'],
            best_dep=best['dep'],best_code=best['code'],best_J=best['energy_J'],best_peak_c=best['peak_c'],best_slack_ms=best['min_slack_ms'],
            extra_saving_pct=best['extra_saving_vs_D017_idle_pct'],recovered_count=len(recovered),recovered_deployments=recovered,
            restored_sequence_count=sum(r['restored_sequence'] for r in rows),target_deployments=len(targets['deployments']),
            min_peak_certified_deployments=len(selected),new_certificates=len(rows),SAFE_certificates=len(safe),
            deadline_failed=sum(not r['deadline_ok'] for r in rows),thermal_failed=sum(r['thermal_status']!='SAFE' for r in rows),
            completed=any(r['kind']=='finished' for r in log),wall_s=receipt['wall_s'],hard_timeout=receipt['hard_timeout']))
        allrows.extend(rows)
    csv_out('comparison.csv',allrows);csv_out('summary.csv',summaries);csv_out('coverage.csv',coverage_rows)
    save('summary.json',summaries);save('verification.json',dict(status='PASS',counts=dict(counts),ignored=ignored,
       scope='hashes, all archived new witnesses, original min-peak coverage, no additional physical evaluation'))
    print(json.dumps(summaries,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
