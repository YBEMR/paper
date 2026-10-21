"""Independent exact-rational static checks for the A03 packet.
No thermal propagation, optimizer, energy ranking or safety certification.
"""
from fractions import Fraction as F
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import argparse, hashlib, json
ROOT=Path(__file__).resolve().parents[1]

def read(path): return json.loads(path.read_text(encoding='utf-8'),parse_float=F)
def need(ok,msg):
    if not ok: raise ValueError(msg)
def unique(items): return len(items)==len(set(items))
def maps(x):
    return ({d['id']:d for d in x['frequency_domains']},{u['id']:u for u in x['execution_units']},{p['id']:p for p in x['profiles']},{s['id']:s for s in x['workload']['stages']},{m['id']:m for m in x['mode_table']})

def validate(x):
    need(x['schema']=='htp.a03.v1','schema')
    ds,us,ps,ss,ms=maps(x)
    need(len(ds)==3 and len(us)==4 and len(ss)==6 and len(ms)==36,'declared finite set size')
    for records in [x['frequency_domains'],x['execution_units'],x['profiles'],x['workload']['stages'],x['mode_table']]: need(unique([r['id'] for r in records]),'duplicate id')
    need({d['device_type']:len(d['unit_ids']) for d in ds.values()}=={'CPU':2,'GPU':1,'NPU':1},'platform scope')
    need(sorted(u for d in ds.values() for u in d['unit_ids'])==sorted(us),'domain membership')
    need(all(v['thermal_node']==v['id'] for v in us.values()),'local source must inject into its declared local node')
    for d in ds.values():
        o=d['opps']; f=[v['frequency_Hz'] for v in o]; v=[v['voltage_V'] for v in o]
        need(unique([v['id'] for v in o]) and unique(f) and f==sorted(f) and min(f)>0,'OPP set')
        need(min(v)>0 and v==sorted(v) and o[0]['id']=='L','voltage and lowest OPP')
        need(all(v['baseline_per_unit_W']>=0 and v['local_leakage_W_per_K']>=0 for v in o),'nonnegative power')
        for u in d['unit_ids']: need(us[u]['domain_id']==d['id'] and us[u]['device_type']==d['device_type'],'unit/domain type')
    e=x['execution']
    for key in ['nonpreemptive','stage_opp_fixed','unit_exclusive','cpu_domain_same_opp_during_overlap','activity_additive']: need(e[key] is True,key)
    for key in ['duration_temperature_dependence','contention_slowdown','extra_handoff_cost']: need(e[key] is False,key)
    need(e['idle_domain_policy']=='IMMEDIATE_LOWEST_OPP' and e['switch_time_s']==e['switch_energy_J']==0,'control scope')
    need(e['start_domain']=='CONTINUOUS_NONNEGATIVE','no hidden start grid')
    u=x['shared_system']; need(u['node']=='U' and u['baseline_count']==1 and u['baseline_W']>=0 and u['leakage_W_per_K']>=0,'shared baseline once')
    need(x['data_grade']=='L3_PHYSICS_CONSTRAINED_ABSTRACT' and x['model_boundary']['real_hardware_calibration'] is False,'data grade')
    need(any(p['grade']=='ASSISTANT_SELECTED_L3' for p in x['parameter_provenance']),'numerical provenance')
    requests={r['id']:r for r in x['workload']['requests']}; W=x['workload']['window_s']
    need(W>0 and len(requests)==2,'workload')
    for r in requests.values(): need(0<=r['release_s']<r['absolute_deadline_s']<=W,'release/deadline/window')
    visited=set(); active=set()
    def dfs(i):
        need(i in ss,'predecessor exists'); need(i not in active,'DAG cycle')
        if i in visited: return
        active.add(i)
        for pred in ss[i]['predecessors']: dfs(pred)
        active.remove(i); visited.add(i)
    for s in ss.values():
        need(s['request_id'] in requests and s['profile_ids'] and unique(s['profile_ids']),'stage support')
        dfs(s['id'])
    for r in requests.values():
        ids={s['id'] for s in ss.values() if s['request_id']==r['id']}
        parents={pred for s in ss.values() if s['id'] in ids for pred in s['predecessors']}
        need(set(r['terminal_stage_ids'])==ids-parents,'request terminals')
    expected=set()
    for s in ss.values():
        for pid in s['profile_ids']:
            need(pid in ps,'profile exists'); pr=ps[pid]
            dom=next(d for d in ds.values() if d['device_type']==pr['device_type'])
            r=pr['response']; need(r['freq_Hz']==[o['frequency_Hz'] for o in dom['opps']],'profile legal frequencies')
            need(len(pr['shared_activity_W'])==len(dom['opps']) and min(pr['shared_activity_W'])>=0,'shared activity shape')
            for j,o in enumerate(dom['opps']):
                f=F(o['frequency_Hz'])
                if r['kind']=='alpha':
                    a=r['sensitivity']; need(0<=a<=1 and r['fref_Hz'] in r['freq_Hz'],'alpha scope')
                    duration=r['dref_s']*((1-a)+a*F(r['fref_Hz'])/f)
                elif r['kind']=='table':
                    need(len(r['duration_s'])==len(r['freq_Hz']),'response table shape'); duration=r['duration_s'][j]
                else:
                    need(r['kind']=='cycles_pwl' and len(r['a_s'])==len(r['b_cycles'])>0,'cycle envelope shape')
                    duration=max((F(a)*f+b)/f for a,b in zip(r['a_s'],r['b_cycles']))
                a=pr['activity']
                if a['model']=='effective_capacitance': q=a['coefficient_F']*f*o['voltage_V']**2
                else:
                    need(a['model']=='utilization_scaled_capacitance','activity model')
                    need(len(a['utilization_by_opp'])==len(dom['opps']) and all(0<=v<=1 for v in a['utilization_by_opp']),'GPU activity scope')
                    q=a['capacitance_F']*a['utilization_by_opp'][j]*f*o['voltage_V']**2
                need(duration>0 and q>=0,'positive mode duration/power')
                for unit in dom['unit_ids']:
                    mid=s['id']+'@'+unit+'@'+o['id']; expected.add(mid); need(mid in ms,'mode coverage')
                    m=ms[mid]
                    need((m['stage_id'],m['profile_id'],m['unit_id'],m['domain_id'],m['opp_id'])==(s['id'],pid,unit,dom['id'],o['id']),'mode identity')
                    need(m['duration_s']==duration and m['local_activity_W']==q and m['shared_activity_W']==pr['shared_activity_W'][j],'exact mode reconstruction')
    need(set(ms)==expected,'no candidate pruning or extra modes')
    t=x['thermal']; nodes=t['node_order']; n=len(nodes); G=t['conductance_W_per_K']; ga=t['ambient_conductance_W_per_K']
    need(nodes==['CPU0','CPU1','GPU0','NPU0','U'] and len(G)==n and all(len(row)==n for row in G),'thermal shape')
    need(len(t['heat_capacity_J_per_K'])==n and min(t['heat_capacity_J_per_K'])>0,'capacity')
    need(len(ga)==n and min(ga)>0,'ambient paths')
    for i in range(n):
        need(all(G[i][j]==G[j][i] and (i==j or G[i][j]<=0) for j in range(n)),'passive symmetric conductance')
        need(sum(G[i])==ga[i],'conductance row sum')
        if nodes[i]=='U': lam=u['leakage_W_per_K']
        else: lam=max(o['local_leakage_W_per_K'] for o in ds[us[nodes[i]]['domain_id']]['opps'])
        need(ga[i]>lam,'strict diagonal dominance of G-Lambda for every OPP')
    ta=t['ambient_temperature_degC']; lo,hi=t['power_model_temperature_range_degC']
    need(t['reference_temperature_degC']==ta and lo==ta,'relative temperature reference')
    need(len(t['initial_temperature_degC'])==len(t['limit_temperature_degC'])==n,'temperature shape')
    need(all(lo<=v<=lim<=hi for v,lim in zip(t['initial_temperature_degC'],t['limit_temperature_degC'])),'declared temperature range')
    for fixture in x['schedule_fixtures']: validate_schedule(x,fixture)
    return True

def validate_schedule(x,fixture):
    ds,us,ps,ss,ms=maps(x); entries=fixture['entries']
    need(len(entries)==len(ss) and unique([e['stage_id'] for e in entries]),'schedule stage coverage')
    requests={r['id']:r for r in x['workload']['requests']}; times={}; chosen={}
    for e in entries:
        sid=e['stage_id']; need(sid in ss and e['mode_id'] in ms,'schedule identifier'); m=ms[e['mode_id']]
        need(m['stage_id']==sid,'mode belongs to stage')
        a=e['start_s']; b=a+m['duration_s']; r=requests[ss[sid]['request_id']]
        need(a>=r['release_s'] and b<=r['absolute_deadline_s'] and b<=x['workload']['window_s'],'release/deadline/window violation')
        times[sid]=(a,b); chosen[sid]=m
    for sid,(a,b) in times.items():
        for pred in ss[sid]['predecessors']: need(times[pred][1]<=a,'dependency')
        for sid2,(c,d) in times.items():
            if sid>=sid2 or not (max(a,c)<min(b,d)): continue
            m,n=chosen[sid],chosen[sid2]
            need(m['unit_id']!=n['unit_id'],'resource overlap')
            if m['domain_id']==n['domain_id']: need(m['opp_id']==n['opp_id'],'same-domain mixed OPP')
    return times

def vectors(x,mode_ids):
    ds,us,ps,ss,ms=maps(x); nodes=x['thermal']['node_order']; modes=[ms[k] for k in mode_ids]
    base={}; slope={}; activity={k:F(0) for k in nodes}
    for d in ds.values():
        ks={m['opp_id'] for m in modes if m['domain_id']==d['id']}; need(len(ks)<=1,'mixed OPP')
        k=next(iter(ks)) if ks else 'L'; o=next(o for o in d['opps'] if o['id']==k)
        for u in d['unit_ids']:
            base[u]=o['baseline_per_unit_W']; slope[u]=o['local_leakage_W_per_K']
    base['U']=x['shared_system']['baseline_W']; slope['U']=x['shared_system']['leakage_W_per_K']
    for m in modes:
        activity[m['unit_id']]+=m['local_activity_W']; activity['U']+=m['shared_activity_W']
    return base,activity,slope

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path); args=ap.parse_args(); x=read(ROOT/'inputs/a03_minimal_v1.json'); checks=[]
    def check(name,fn):
        try: fn(); checks.append(dict(name=name,passed=True))
        except Exception as exc: checks.append(dict(name=name,passed=False,error=str(exc)))
    check('exact_reconstruction_complete_domain_physical_and_workload_contract',lambda:validate(x))
    def mapping():
        b,a,l=vectors(x,['A.main@GPU0@M','B.main@NPU0@M'])
        need(a['U']==F('.30')+F('.58'),'shared activity sum'); need(a['CPU0']==a['CPU1']==0,'no misplaced shared power')
        need(b['U']==F('.65') and l['U']==F('.003'),'shared baseline and slope counted once')
        need(a['GPU0']==F('.55')*F('0.000000003')*500000000*F('.75')**2,'GPU local activity')
    check('local_heat_and_shared_power_boundary',mapping)
    def onebusy():
        b,a,l=vectors(x,['A.pre@CPU0@H']); need(b['CPU0']==b['CPU1']==F('.16') and l['CPU1']==F('.003'),'idle sibling follows busy domain')
        b,a,l=vectors(x,[]); need(b['CPU0']==b['CPU1']==F('.10') and sum(b.values())==F('1.17'),'whole-domain idle returns L')
    check('shared_CPU_domain_and_auto_L_accounting',onebusy)
    def touch():
        fixture=deepcopy(x['schedule_fixtures'][0]); fixture['entries'][3]['mode_id']='B.pre@CPU0@L'; fixture['entries'][3]['start_s']=F(24,1024)
        fixture['entries'][4]['start_s']=F(48,1024); fixture['entries'][5]['start_s']=F(84,1024)
        validate_schedule(x,fixture)
    check('half_open_touching_noninteger_ms_endpoints_are_legal',touch)
    def diversity():
        _,_,ps,_,_=maps(x)
        need(ps['matrix_C']['response']['sensitivity']!=ps['memory_C']['response']['sensitivity'],'CPU stage response differs')
        g=ps['matrix_G']['response']['duration_s']; h=ps['memory_G']['response']['duration_s']; need(len({a/b for a,b in zip(g,h)})>1,'GPU not a fixed speed factor')
        r=ps['matrix_N']['response']; winning=[max(range(len(r['a_s'])),key=lambda j:r['a_s'][j]*f+r['b_cycles'][j]) for f in r['freq_Hz']]
        need(len(set(winning))==2,'NPU envelope branch changes')
    check('declared_stage_hardware_response_structure_present',diversity)
    def reject(name,mutator,scope='input'):
        def trial():
            y=deepcopy(x if scope=='input' else x['schedule_fixtures'][0]); mutator(y)
            try:
                if scope=='input': validate(y)
                else: validate_schedule(x,y)
            except (ValueError,KeyError): return
            raise AssertionError('Invalid mutation was accepted')
        check(name,trial)
    reject('reject_missing_legal_mode',lambda y:y['mode_table'].pop())
    reject('reject_duplicate_stage',lambda y:y['workload']['stages'].append(deepcopy(y['workload']['stages'][0])))
    reject('reject_forged_mode_duration',lambda y:y['mode_table'][0].update(duration_s=F(1,3)))
    reject('reject_nonpassive_heat_path',lambda y:y['thermal']['conductance_W_per_K'][0].__setitem__(1,F('.03')))
    reject('reject_wrong_temperature_reference',lambda y:y['thermal'].update(reference_temperature_degC=30))
    reject('reject_duplicated_shared_baseline',lambda y:y['shared_system'].update(baseline_count=2))
    reject('reject_misplaced_local_heat',lambda y:y['execution_units'][0].update(thermal_node='U'))
    reject('reject_unit_overlap',lambda y:y['entries'][3].update(mode_id='B.pre@CPU0@L'),scope='schedule')
    reject('reject_hidden_start_grid',lambda y:y['execution'].update(start_domain='GRID_1_MS'))
    reject('reject_same_domain_mixed_frequency',lambda y:y['entries'][3].update(mode_id='B.pre@CPU1@H'),scope='schedule')
    reject('reject_request_deadline_violation',lambda y:y['entries'][-1].update(start_s=F('.499')),scope='schedule')
    reject('reject_dependency_violation',lambda y:y['entries'][1].update(start_s=0),scope='schedule')
    reject('reject_mode_of_another_stage',lambda y:y['entries'][0].update(mode_id='B.pre@CPU0@L'),scope='schedule')
    report=dict(kind='STATIC_INPUT_PRECHECK',created_utc=datetime.now(timezone.utc).isoformat(),passed=all(v['passed'] for v in checks),checks=checks,mode_count=len(x['mode_table']),schedule_fixtures=len(x['schedule_fixtures']),research_calls=0,thermal_propagations=0,continuous_safety_implemented=False,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'inputs/a03_minimal_v1.json',Path(__file__)]})
    if args.output: args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"A03 exact static checks: {sum(c['passed'] for c in checks)}/{len(checks)}; modes {len(x['mode_table'])}; research calls 0")
    for c in checks:
        if not c['passed']: print('FAILED',c)
    if not report['passed']: raise SystemExit(1)
if __name__=='__main__': main()
