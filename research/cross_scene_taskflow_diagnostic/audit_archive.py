"""Read-only validation of the finished snapshot, resource ledger, thermal/energy evidence and gate."""
import csv,gzip,hashlib,json,math,sys
from pathlib import Path
from collections import Counter
from fractions import Fraction
d=Path.cwd()
def load(path):
    p=d/path
    return json.loads(gzip.decompress(p.read_bytes()) if str(p).endswith('.gz') else p.read_bytes())
sig=load('RESULT_SHA256.json')
assert all(hashlib.sha256((d/n).read_bytes()).hexdigest()==v for n,v in sig['files'].items())
assert hashlib.sha256(json.dumps(sig['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()==sig['snapshot']
cfg=load('config/p1_frozen.json')
log=[json.loads(s) for s in Path('logs/calls.jsonl').read_text(encoding='utf8').splitlines()]
begin={(r['case'],r['method'],r['arm']):r for r in log if r['event']=='begin'}
end={(r['case'],r['method'],r['arm']):r for r in log if r['event']=='end'}
assert begin.keys()==end.keys()
assert all(r['state']=='OK' for r in end.values())
caps=sum(x['budget_s'] for x in begin.values())
assert caps<=16620
wall=max(begin[k]['elapsed_s']+end[k]['actual_s'] for k in begin)
assert wall<=18000
pats=load('config/profile_sources.json')
assert len(pats['files'])==5 and all(x['expected']==x['actual'] for x in pats['history']+pats['files'])
assert sum(len(x['selected']) for x in pats['files'])==40
rows=list(csv.DictReader(open('summary.csv',encoding='utf8')))
cs={r['case']:r for r in rows}
result_counts=Counter()
max_peak_width=max_energy_halfwidth=energy_diff=0
for file in Path('certificates').glob('*_continuous.json.gz'):
    c=load(file)
    cmet=c['metrics']
    raw=load('logs/plans/'+c['schedule']+'.json.gz')
    canonical={key:raw[key] for key in ('case','rows','low')}
    assert hashlib.sha256(json.dumps(canonical,separators=(',',':')).encode()).hexdigest()==c['schedule']
    s=load('certificates/'+c['schedule']+'_schedule.json.gz')
    assert len(s['rows'])==int(cs[c['case']]['requests'])*3
    assert all(item[1]==index//3 and item[0]==index for index,item in enumerate(s['rows']))
    events=c['events']
    assert events[0][0]==0 and events[-1][1]==round(float(cs[c['case']]['window_ms'])*10)
    assert all(a[1]==b[0] and max(abs(x-y) for x,y in zip(a[18:22],b[14:18]))<1e-9 for a,b in zip(events,events[1:]))
    nsum=sum(sum(e[26:30]) for e in events)+cmet['external_J']
    comps=sum(cmet[z] for z in ('base_J','activity_J','temperature_J','switch_J','external_J'))
    energy_diff=max(energy_diff,abs(nsum-cmet['E_J']),abs(comps-cmet['E_J']))
    assert max(abs(nsum-cmet['E_J']),abs(comps-cmet['E_J']))<1e-7
    result_counts[cmet['status']]+=1
    ew=(cmet['E_bounds'][1]-cmet['E_bounds'][0])/2
    pw=max(cmet['peak_hi'])-max(cmet['peak_lo'])
    max_peak_width=max(max_peak_width,pw);max_energy_halfwidth=max(max_energy_halfwidth,ew)
    if cmet['status'] in ('SAFE','HOT'):
        assert pw<=.001 and ew<=1e-6 and min(cmet['minimum_lo'])>=20 and max(cmet['peak_hi'])<=100
    if cmet['status']=='SAFE': assert max(cmet['peak_hi'])<=80
    if cmet['status']=='HOT': assert max(cmet['peak_lo'])>80
    reset=load('certificates/'+c['schedule']+'_reset.json.gz')
    assert [e[:14] for e in reset['events']]==[e[:14] for e in events]
dev=load('logs/development_gate.json') if Path('logs/development_gate.json').exists() else {}
if not dev.get('holdout_open'): assert not any(k[0].startswith('H') for k in begin)
print(json.dumps(dict(calls=len(begin),sum_call_s=sum(r['actual_s'] for r in end.values()),reserved_s=caps,wall_s=wall,
    by_status=result_counts,max_peak_width_K=max_peak_width,max_energy_halfwidth_J=max_energy_halfwidth,
    worst_energy_crosscheck_J=energy_diff,files=len(sig['files']),snapshot=sig['snapshot'],
    excess=[(k,end[k]['actual_s']-r['budget_s']) for k,r in begin.items() if end[k]['actual_s']>r['budget_s']]),
    ensure_ascii=False))
