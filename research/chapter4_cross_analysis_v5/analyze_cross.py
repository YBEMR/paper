"""Read-only post-run audit of the 24 registered C/D cells and historical A/B.
No optimizer is called. A v3 probe is a parser/mechanism test, never a formal result.
"""
from pathlib import Path
from fractions import Fraction
from types import SimpleNamespace
from collections import defaultdict
from statistics import median
import argparse, csv, gzip, hashlib, json, math, sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'formal_runner'))
from run_cross import roster, check_bundle, identities, ENDPOINTS_SHA, LOCK_BLOB, PIN, CASES, SEEDS, RESULT_PIN
from feedback_frozen import virtual
FEEDBACK_SHA='1f5e570cea491c97f6d1091bc195163bdcd5a4168115a2ebe0e52fc27241b815'
N={'D1':160,'D2':160,'F1':120,'F2':130}

def req(cond, msg):
    if not cond: raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def raw_sorted(o):return json.dumps(o,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def csvread(p):
    with Path(p).open(encoding='utf8',newline='') as f:return list(csv.DictReader(f))
def write(p,o):Path(p).write_text(json.dumps(o,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def table(path,rows):
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
def finite(x):return isinstance(x,(float,int)) and math.isfinite(x)
def close(a,b,tol=1e-9):return finite(a) and finite(b) and abs(a-b)<=tol
def bounds(s):
    b=s['bounds'];req(len(b)==2 and all(finite(x) for x in b) and b[0]<=s['J']<=b[1],'invalid energy interval');return b
def safe(s):return s is not None and s.get('status')=='SAFE'
def delta(a,b):
    if not(safe(a) and safe(b)):return (None,None,None,'UNAVAILABLE')
    x,y=bounds(a),bounds(b);lo=x[0]-y[1];hi=x[1]-y[0]
    return (1000*(a['J']-b['J']),1000*lo,1000*hi,'A_HIGHER' if lo>0 else 'B_HIGHER' if hi<0 else 'INTERVAL_OVERLAP')
def score(m,k):return {'plan':k,'status':m['status'],'J':m['E_J'],'bounds':m['E_bounds']}
def check_metrics(m):
    s=score(m,'');bounds(s)
    req(m['status']=='SAFE','not SAFE');req(max(m['peak_hi'])<=80 and min(m['minimum_lo'])>=20,'thermal interval');req(m['min_deadline_slack_ms']>=0,'deadline violation')
    req(m['E_bounds'][1]-m['E_bounds'][0]<=2.00001e-6,'energy interval too wide')
def read_e():
    e=read(ROOT/'E_reference.json');ids=identities()
    for c in CASES:
        r=e[c];k=r['plan_sha256'];p=r['plan'];cert=r['certificate'];m=cert['metrics']
        req(sha(raw_sorted(p))==k==cert['plan_sha256'] and p['case']==c and len(p['rows'])==3*N[c],f'E plan mismatch {c}')
        check_metrics(m);req(close(r['J'],m['E_J']) and r['bounds']==m['E_bounds'] and r['initial_v1_sha256']==ids[c,'Q4']['v1_plan_sha256'],f'E origin mismatch {c}')
    return e

class Store:
    def __init__(self,folder,case):self.root=Path(folder)/'evidence';self.case=case;self.cache={}
    def get(self,k):
        req(isinstance(k,str) and len(k)==64 and all(x in '0123456789abcdef' for x in k),'invalid plan id')
        if k not in self.cache:
            payload=gzip.decompress((self.root/'plans'/(k+'.json.gz')).read_bytes());req(sha(payload)==k,'plan digest mismatch '+k)
            p=json.loads(payload);req(p['case']==self.case and len(p['rows'])==3*N[self.case],'plan case/stage mismatch')
            cert=read(self.root/'certificates'/(k+'.json'));req(cert['plan']==k and cert['case']==self.case,'certificate identity mismatch')
            m=cert['metrics'];bounds(score(m,k));req((self.root/'certificates'/(k+'.npz')).is_file(),'missing thermal trace '+k)
            if m['status']=='SAFE':check_metrics(m)
            self.cache[k]=(p,cert)
        return self.cache[k]
    def verify_score(self,s):
        req(s is not None and s.get('plan'),'missing score plan')
        p,c=self.get(s['plan']);m=c['metrics']
        req(s['status']==m['status'] and close(s['J'],m['E_J']) and s['bounds']==m['E_bounds'],'score/certificate disagreement')
        return p,m

def model_for(repo,case):
    # Minimal immutable-data adapter used ONLY for the original feedback.virtual function.
    req(sha((ROOT/'feedback_frozen.py').read_bytes())==FEEDBACK_SHA,'feedback source drift')
    root=Path(repo)/'research/chapter3_final_evaluation';path=root/'instances'/(case+'.csv');lock=read(root/'execution_lock.json')
    req(sha(path.read_bytes())==lock['files']['instances/'+case+'.csv'],'request input drift')
    rr=csvread(path);req(len(rr)==N[case],'wrong request count')
    src=ROOT/'formal_runner/v1/p1/config';duration={}
    for name in ('gpu_profiles.csv','cpu_npu_profiles.csv'):
        for r in csvread(src/name):
            u=(2,) if name.startswith('gpu') else (3,) if r['domain']=='npu' else (0,1)
            for i in u:duration[r['stage'],i,int(r['k'])]=int(r['ticks'])
    pre=[];t=0;dt=[];q=[];d=[];sc=[]
    for r in rr:
        kind=r['kind'];t=max(t,int(r['release_tick']))+duration[kind+'.pre',0,0];pre.append(t)
        dt.append({(u,k):v for (s,u,k),v in duration.items() if s==kind+'.main'});q.append(duration[kind+'.post',1,0]);d.append(int(r['deadline_tick']));sc.append(int(r['scene']))
    return SimpleNamespace(f=SimpleNamespace(pre=pre),dt=dt,q=q,d=d,n=len(rr),scenes=sc)

def deficit(m,base,target):
    cfg=list(map(tuple,base))
    for i,op in target:cfg[int(i)]=tuple(op)
    total,late,_,_=virtual(m,cfg)
    return dict(deficit_max_ms=max((x[0] for x in late),default=0)/10,deficit_total_ms=total/10,late_count=len(late))
def actual_remote(r,scenes):
    changed={x[0] for x in r.get('real_changes',r.get('changed',[]))};selected={x['selected'] for x in r.get('feedback',[]) if x.get('selected') is not None}
    targets={x[0] for x in r.get('target',[])};real=selected&changed
    across={i for i in real if any(scenes[i]!=scenes[j] for j in targets)} if scenes else set()
    return dict(selected_compensators=len(selected),realized_compensators=len(real),cross_scene_realized=len(across),changed_main=len(changed),real_ids=sorted(real))
def matched(a,b):
    if isinstance(a['before'],dict):ka,kb=a['before']['plan'],b['before']['plan'];sa,sb=a['after'],b['after']
    else:ka,kb=a['before'],b['before'];sa,sb={'J':a['after_J']},{'J':b['after_J']}
    if ka!=kb or a.get('target')!=b.get('target') or len(a.get('scope',[]))!=len(b.get('scope',[])):return None
    real=actual_remote(b,None)['real_ids'];outside=sorted(set(real)-set(a['scope']))
    return dict(delta_mJ=1000*(sa['J']-sb['J']),ordinary_solver=a['solver']['status'],feedback_solver=b['solver']['status'],realized_outside_ordinary=';'.join(map(str,outside)),both_exact_reference=a['solver']['status']==b['solver']['status']=='EXACT_REFERENCE')

def audit_cell(folder,case,method,seed,expect,m,official=None,expected_charge=None):
    folder=Path(folder);rec=read(folder/'receipt.json');res=read(folder/'result.json');store=Store(folder,case)
    req(rec['status']=='COMPLETE','noncomplete receipt');req(rec['case']==case and rec['method']==method and rec['seed']==seed and rec['mode']=='T3','receipt identity')
    req(rec['budget_s']==900 and rec['subject']==PIN,'receipt budget/protocol mismatch')
    req(0<=rec['prior_charge_s']<=rec['charged_s']<=900 and 0<=res['elapsed_s']<=900,'outside budget')
    if expected_charge is not None:req(close(rec['prior_charge_s'],expected_charge,1e-6),'pool charge mismatch')
    req(res['case']==case and res['method']==method and res['seed']==seed and res['mode']=='T3' and res['budget_s']==900 and res['status']=='SAFE','result identity/status')
    i=res['initial'];req(safe(i) and i['plan']==expect['original_plan_sha256'] and close(i['J'],expect['energy_J']),'initial identity mismatch');store.verify_score(i)
    req(safe(res['configuration']) and safe(res['selected']) and safe(res['final']),'non-SAFE terminal')
    req(res['selected']['plan']==res['final']['plan'],'selected/final plan mismatch')
    for s in [res['configuration'],res['selected'],res['final']]:store.verify_score(s)
    if official is not None:
        req(official['receipt']=='COMPLETE' and official['actual_status']=='SAFE' and official['initial_plan']==i['plan'] and official['plan']==res['final']['plan'] and close(float(official['SAFE_J']),res['final']['J']) and close(float(official['configuration_J']),res['configuration']['J']) and close(float(official['charged_s']),rec['charged_s'],1e-6),'historical raw cell does not match publication')
    log=folder/'rounds.jsonl';rs=[json.loads(x) for x in log.read_text(encoding='utf8').splitlines() if x.strip()] if log.exists() else []
    cur=i;config=[];timing=[];prev_time=-1;phase_origin=None;rows=[]
    for r in rs:
        ph=r['phase'];req(ph in ('configuration','timing'),'unknown phase');req(r['elapsed_s']>=prev_time and r['elapsed_s']<=900,'round time/order');prev_time=r['elapsed_s']
        req(r['before']['plan']==cur['plan'],'incumbent chain mismatch');store.verify_score(r['before'])
        for cand in r['candidates']:
            if cand is None:continue
            store.verify_score(cand)
            if cand.get('eligible') and cand.get('in_time') and cand['status']=='SAFE' and bounds(cand)[1]<bounds(cur)[0]:cur=cand
        req(cur['plan']==r['after']['plan'],'strict SAFE acceptance chain mismatch');store.verify_score(r['after'])
        if ph=='configuration':
            req(not timing and r['turn']==len(config),'configuration round order');p,_=store.get(r['before']['plan']);q,_=store.get(r['after']['plan']);base=[x[:2] for x in p['rows'][1::3]];after=[x[:2] for x in q['rows'][1::3]]
            req(r['real_changes']==[[j,a,b] for j,(a,b) in enumerate(zip(base,after)) if a!=b],'real_changes mismatch')
            df=deficit(m,base,r['target']);rf=actual_remote(r,m.scenes)
            if r.get('feedback'):req(close(r['feedback'][0]['deficit_ticks']/10,df['deficit_max_ms']) and close(r['feedback'][0]['total_violation']/10,df['deficit_total_ms']),'virtual deficit mismatch')
            if phase_origin is None:phase_origin=r['elapsed_s']-r['round_s']
            rows.append(dict(round=r['turn']+1,elapsed_config_s=r['elapsed_s']-phase_origin,before_J=r['before']['J'],after_J=r['after']['J'],target_type=r['target_type'],scope=len(r['scope']),solver=r['solver']['status'],**df,**rf));config.append(r)
        else:
            if not timing:req(r['before']['plan']==res['configuration']['plan'],'configuration endpoint mismatch')
            req(r['turn']==len(timing),'timing round order');timing.append(r)
    req((config[-1]['after'] if config else i)['plan']==res['configuration']['plan'],'configuration endpoint mismatch');req(cur['plan']==res['final']['plan'],'final incumbent mismatch')
    req(len(config)==res['configuration_details']['rounds'] and len(timing)==res['post']['rounds'],'round count mismatch')
    return dict(initial=i,configuration=res['configuration'],final=res['final'],receipt=rec,configuration_rounds=config,mechanism=rows,phase_origin=phase_origin,phase_elapsed=rows[-1]['elapsed_config_s'] if rows else 0,plan_certificates_checked=len(store.cache),post_rounds=len(timing))

def hist_scores(r):
    return dict(initial={'J':float(r['initial_J']),'plan':r['initial_plan'],'status':'SAFE'},configuration={'J':float(r['configuration_J']),'plan':r['configuration_plan'],'status':'SAFE'},final={'J':float(r['SAFE_J']),'plan':r['plan'],'status':'SAFE','bounds':[float(r['actual_lo']),float(r['actual_hi'])]})

def checkpoint(arm,t=None,rounds=None):
    rs=arm['mechanism'];raw=arm['configuration_rounds']
    if rounds is not None:
        if len(rs)<rounds:return None
        return raw[rounds-1]['after'] if rounds else arm['initial']
    if not rs or t>arm['phase_elapsed']:return None
    valid=[j for j,x in enumerate(rs) if x['elapsed_config_s']<=t]
    return raw[valid[-1]]['after'] if valid else arm['initial']

def compare_pair(a,b,c,d,e):
    out={}
    for phase in ('configuration','final'):
        aa,bb,cc,dd=(x[phase] for x in (a,b,c,d));out.update({f'{phase}_{k}_mJ':1000*(p['J']-q['J']) for k,p,q in [('A_B',aa,bb),('C_D',cc,dd),('A_C',aa,cc),('B_D',bb,dd)]});out[f'{phase}_interaction_mJ']=out[f'{phase}_A_B_mJ']-out[f'{phase}_C_D_mJ']
    for k,p,q in [('A_B',a['final'],b['final']),('C_D',c['final'],d['final']),('A_C',a['final'],c['final']),('B_D',b['final'],d['final']),('D_E',d['final'],e)]:
        value,lo,hi,verdict=delta(p,q);out[f'final_{k}_mJ']=value;out[f'final_{k}_lo_mJ']=lo;out[f'final_{k}_hi_mJ']=hi;out[f'final_{k}_verdict']=verdict
    out.update(A_J=a['final']['J'],B_J=b['final']['J'],C_J=c['final']['J'],D_J=d['final']['J'],E_J=e['J'])
    out['final_interaction_lo_mJ']=out['final_A_B_lo_mJ']-out['final_C_D_hi_mJ'];out['final_interaction_hi_mJ']=out['final_A_B_hi_mJ']-out['final_C_D_lo_mJ']
    return out

def main(a):
    bundle=check_bundle();es=read_e();repo=Path(a.repo).resolve();root=repo/'research/chapter3_final_evaluation';run=Path(a.run).resolve();out=Path(a.out).resolve();req(out!=run and not out.is_relative_to(run) and not out.is_relative_to(repo),'analysis output must be separate');out.mkdir(parents=True,exist_ok=False)
    req(blob((root/'execution_lock.json').read_bytes())==LOCK_BLOB and sha((root/'results/endpoints.csv').read_bytes())==ENDPOINTS_SHA,'historical source drift')
    hist={(x['case'],x['method'],int(x['seed'])):x for x in csvread(root/'results/endpoints.csv') if x['mode']=='T3' and x['case'] in CASES and x['method'] in ('AB','Proposed')};req(len(hist)==24,'historical A/B incomplete')
    check=read(run/'check.json');req(check['bundle_sha256']==bundle and check['versions_match'] and not check['runtime_errors'] and check['formal_protocol']==PIN and check['result_reference']==RESULT_PIN,'unverified execution environment')
    begin=read(run/'batch_start.json');req(begin['roster']==roster(),'batch roster drift');end=read(run/'batch_end.json');pool_receipts=read(run/'pool_receipts.json');ids=identities();valid={};historical={};inventory=[];mechanism=[];matches=[];paired=[];time_points=[]
    for case in CASES:
        m=model_for(repo,case);pool=pool_receipts.get(case,{})
        req(pool.get('status')=='COMPLETE','missing verified Q4 pool '+case);p=read(run/'pools'/case/'result.json');req(p['plan']==ids[case,'Q4']['original_plan_sha256'] and p['status']=='SAFE','wrong Q4 pool')
        for seed in SEEDS:
            for arm,method in [('C','AB'),('D','Proposed'),('A','AB'),('B','Proposed')]:
                folder=(run if arm in ('C','D') else Path(a.ab_root or root/'formal'))/'cells'/f'{case}_{method}_T3_{seed}';h=hist[case,method,seed] if arm in ('A','B') else None
                if h:
                    req(h['receipt']=='COMPLETE' and h['actual_status']=='SAFE' and h['initial_plan']==ids[case,'G2']['original_plan_sha256'],'historical row invalid');historical[case,seed,arm]=hist_scores(h)
                try:
                    v=audit_cell(folder,case,method,seed,ids[case,'Q4' if arm in ('C','D') else 'G2'],m,h,pool['charged_s'] if not h else None);valid[case,seed,arm]=v
                    inventory.append(dict(case=case,seed=seed,arm=arm,status='AUDITED_SAFE',charged_s=v['receipt']['charged_s'],configuration_rounds=len(v['configuration_rounds']),post_rounds=v['post_rounds'],certificates_checked=v['plan_certificates_checked']))
                    for x in v['mechanism']:mechanism.append(dict(case=case,seed=seed,arm=arm,**x))
                except Exception as exc:
                    inventory.append(dict(case=case,seed=seed,arm=arm,status='RAW_AUDIT_UNAVAILABLE' if h else 'UNVERIFIED',reason=f'{type(exc).__name__}: {exc}'))
            for x,y in [('A','B'),('C','D')]:
                u,v=valid.get((case,seed,x)),valid.get((case,seed,y))
                if not(u and v):continue
                for rr,ss in zip(u['configuration_rounds'],v['configuration_rounds']):
                    match=matched(rr,ss)
                    if match is not None:matches.append(dict(case=case,seed=seed,pair=x+y,round=rr['turn']+1,**match))
            c,d=valid.get((case,seed,'C')),valid.get((case,seed,'D'));aa=historical[case,seed,'A'];bb=historical[case,seed,'B'];
            if c and d:
                paired.append(dict(case=case,seed=seed,**compare_pair(aa,bb,c,d,es[case])))
            arms=[valid.get((case,seed,k)) for k in ('A','B','C','D')]
            if all(arms):
                # Complete-round snapshots only; no extrapolation after last recorded configuration round.
                for r in range(1,min(len(z['mechanism']) for z in arms)+1):
                    vals=[checkpoint(z,rounds=r) for z in arms];x,y,z,w=[v['J'] for v in vals];time_points.append(dict(case=case,seed=seed,axis='round',checkpoint=r,A_B_mJ=1000*(x-y),C_D_mJ=1000*(z-w),interaction_mJ=1000*(x-y-z+w)))
                for t in [30,60,120,300,600]:
                    vals=[checkpoint(z,t=t) for z in arms]
                    if any(v is None for v in vals):time_points.append(dict(case=case,seed=seed,axis='config_elapsed_s',checkpoint=t,status='CENSORED'));continue
                    x,y,z,w=[v['J'] for v in vals];time_points.append(dict(case=case,seed=seed,axis='config_elapsed_s',checkpoint=t,status='OBSERVED',A_B_mJ=1000*(x-y),C_D_mJ=1000*(z-w),interaction_mJ=1000*(x-y-z+w)))
    summary=[]
    for case in CASES:
        rr=[r for r in paired if r['case']==case];row={'case':case,'valid_pairs':len(rr),'registered_pairs':3}
        if rr:
            for k in ('configuration_A_B_mJ','configuration_C_D_mJ','configuration_interaction_mJ','final_A_B_mJ','final_C_D_mJ','final_interaction_mJ','final_D_E_mJ'):
                v=[x[k] for x in rr];row.update({k+'_median':median(v),k+'_min':min(v),k+'_max':max(v)})
        summary.append(row)
    for name,rs in [('inventory',inventory),('paired',paired),('paired_summary',summary),('round_mechanisms',mechanism),('matched_rounds',matches),('common_checkpoints',time_points)]:table(out/(name+'.csv'),rs)
    n=sum(x['arm'] in ('C','D') and x['status']=='AUDITED_SAFE' for x in inventory);ab=sum(x['arm'] in ('A','B') and x['status']=='AUDITED_SAFE' for x in inventory)
    status={'outcome':'PASS' if n==24 and end['outcome']=='FINISHED' and end['completed_receipts']==24 else 'INCOMPLETE_OR_UNVERIFIED','audited_CD':n,'registered_CD':24,'audited_AB_raw':ab,'historical_AB_rows':len(hist),'complete_pairs':len(paired),'checkpoint_scope':'Configuration-round end snapshots, censored after last logged round; no exact first SAFE timestamp claim. Historical/new batch comparison descriptive even with environment declaration. E is one deterministic archived endpoint per case, not independent repeated seeds.','limitations':'No rerun of original thermal kernel here; audit stored plan hashes, certificate consistency and candidate acceptance. Cross-machine speedup prohibited.'};write(out/'audit.json',status);print(json.dumps(status,ensure_ascii=False));return 0 if status['outcome']=='PASS' else 2

def test_probe(path):
    # Exercise shared mechanism and identity logic on real v3 logs. This is not a fake formal receipt test.
    p=Path(path);read_e();check_bundle();n=0;exact=0;remote=[];rows=0
    for case in CASES:
        aa=read(p/'run'/case/'AB.json');bb=read(p/'run'/case/'Proposed.json');req(aa['status']==bb['status']=='SAFE' and aa['initial']==bb['initial']==identities()[case,'Q4']['v1_plan_sha256'],'probe initial drift')
        for x,y in zip(aa['rounds'],bb['rounds']):
            rows+=2;r=matched(x,y)
            if r is not None:
                n+=1;exact+=r['both_exact_reference']
                if r['realized_outside_ordinary']:remote.append(dict(case=case,round=x['round'],**r))
    print(json.dumps(dict(status='PASS',scope='v3 archived short probe parser and v1 E identity; not a 900s formal run',round_records=rows,matched=n,both_exact=exact,remote=remote),ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo');p.add_argument('--run');p.add_argument('--out');p.add_argument('--ab-root');p.add_argument('--probe');a=p.parse_args()
    if a.probe:test_probe(a.probe)
    else:
        if not all((a.repo,a.run,a.out)):p.error('--repo, --run, --out required (or --probe)')
        raise SystemExit(main(a))
