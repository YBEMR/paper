"""A04 software/analytic fixtures, not hardware or scheduling research cases."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,localcontext
from copy import deepcopy
from unittest.mock import patch
import hashlib,json,sys,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluator import schedule as adapter
from evaluator.certified_segments import Budget,evaluate_piecewise
ROOT=Path(__file__).resolve().parents[1]

def need(ok,message='check failed'):
    if not ok: raise AssertionError(message)
def contain(interval,point): return Decimal(interval[0])<=point<=Decimal(interval[1])
def physical(n,c,g):
    return dict(node_order=['n'+str(i) for i in range(n)],heat_capacity_J_per_K=c,conductance_W_per_K=g,
      ambient_temperature_degC=25,reference_temperature_degC=25,power_model_temperature_range_degC=[0,100],external_common_power_W=0)
def segment(platform,b,l,duration,start=0):
    ns=platform['node_order']; base=dict(zip(ns,b)); zeros={k:0 for k in ns}
    return dict(start_ms=F(start)*1000,end_ms=(F(start)+F(duration))*1000,duration_ms=F(duration)*1000,
      baseline_by_node_W=base,activity_by_node_W=zeros,local_leakage_slope_W_per_K=dict(zip(ns,l)),node_power_constant_at_reference_W=base,
      baseline_by_power_group_W=base,external_common_power_W=0,external_common_injected_heat_W=0,reference_temperature_degC=25)
def run(output):
    started=time.perf_counter(); checks=[]; x,digest=adapter.load_frozen(); f=x['schedule_fixtures'][0]
    def check(name,fn):
        t=time.perf_counter()
        try: fn(); item=dict(name=name,passed=True)
        except Exception as e: item=dict(name=name,passed=False,error=str(e),traceback=traceback.format_exc())
        item['elapsed_s']=time.perf_counter()-t; checks.append(item)
    def events():
        for fixture in x['schedule_fixtures']:
            s,done,ends=adapter.prepare_schedule(x,fixture,Budget()); need(s[0]['start_ms']==0 and s[-1]['end_ms']==1000)
            need(all(a['end_ms']==b['start_ms'] for a,b in zip(s,s[1:]))); need(s[-1]['active_stage_ids']==[])
            need(s[-1]['domain_opps']=={'C':'L','G':'L','N':'L'}); need(sum(s[-1]['baseline_by_node_W'].values())==F('1.17'))
            need(all(v<=F('.5') for v in done.values())); need(all(sid in ends for sid in ['A.post','B.post']))
    check('two_frozen_fixtures_complete_half_open_events_and_idle_tail',events)
    def shared():
        segs,_,_=adapter.prepare_schedule(x,f,Budget()); s=next(s for s in segs if set(s['active_stage_ids'])=={'A.main','B.main'})
        need(s['activity_by_node_W']['U']==F('.88')); need(s['baseline_by_node_W']['U']==F('.65'))
        need(s['activity_by_node_W']['GPU0']==F('.4640625') and s['activity_by_node_W']['NPU0']==F('.169'))
        need(s['local_leakage_slope_W_per_K']['U']==F('.003') and s['external_common_power_W']==0)
    check('five_node_local_and_shared_power_sources',shared)
    def touching():
        y=deepcopy(f); y['entries'][3].update(mode_id='B.pre@CPU1@H',start_s=F(24,1024)); y['entries'][4]['start_s']=F(40,1024); y['entries'][5]['start_s']=F(76,1024)
        ss,_,_=adapter.prepare_schedule(x,y,Budget()); s=next(s for s in ss if s['domain_opps']['C']=='H')
        need(s['baseline_by_node_W']['CPU0']==s['baseline_by_node_W']['CPU1']==F('.16'))
        need(s['local_leakage_slope_W_per_K']['CPU0']==F('.003'))
    check('zero_gap_frequency_change_and_idle_sibling_high_OPP',touching)
    def nongrid():
        y=deepcopy(f)
        for e in y['entries']:
            if e['stage_id'].startswith('B.'): e['start_s']=F(e['start_s'])+F(1,7000)
        ss,_,_=adapter.prepare_schedule(x,y,Budget()); need(F(1,7) in [s['start_ms'] for s in ss])
    check('exact_nongrid_start_is_not_rounded',nongrid)
    for name,edit in [
      ('reject_missing_stage',lambda y:y['entries'].pop()),
      ('reject_unit_overlap',lambda y:y['entries'][3].update(mode_id='B.pre@CPU0@L')),
      ('reject_mixed_CPU_OPP',lambda y:y['entries'][3].update(mode_id='B.pre@CPU1@H')),
      ('reject_late_request',lambda y:y['entries'][-1].update(start_s='0.499')),
      ('reject_dependency',lambda y:y['entries'][1].update(start_s=0)),
      ('reject_float_as_exact_start',lambda y:y['entries'][0].update(start_s=.001))]:
        def trial(edit=edit):
            y=deepcopy(f); edit(y); r=adapter.evaluate_schedule(x,y); need(r['state']=='INVALID_SCHEDULE' and not r['rankable_energy'] and r['energy_J'] is None)
        check(name,trial)
    def accuracy():
        fake=dict(state='UNRESOLVED',reason='NUMERICAL_ERROR',complete=False,rankable_energy=False,energy_J=None,violations=[])
        with patch.object(adapter,'evaluate_piecewise',return_value=fake) as call:
            r=adapter.evaluate_schedule(x,f)
            a=call.call_args.args[5]
            need(a==dict(temperature_enclosure_width_K=F('.0001'),energy_absolute_error_J=F('.00000001'),energy_relative_error=F('.00000001')))
            need(r['technical_issue'] and r['reason']=='NUMERICAL_ERROR')
    check('accuracy_mapping_and_technical_error_not_silenced',accuracy)
    def scalar():
        plat=physical(1,[2],[[F('.2')]]); seg=segment(plat,[F('.4')],[F('.02')],1)
        r=evaluate_piecewise(plat,[35],[60],[seg],1000,budget=Budget(60)); need(r['state']=='SAFE',r.get('reason'))
        with localcontext() as ctx:
            ctx.prec=80; a=Decimal('-.09'); eq=Decimal('.4')/Decimal('.18'); theta=eq+(Decimal(10)-eq)*a.exp()
            integral=eq+(Decimal(10)-eq)*(a.exp()-1)/a; energy=Decimal('.4')+Decimal('.02')*integral
            need(contain(r['final_temperature_degC']['n0'],theta+25)); need(contain(r['energy_J'],energy))
        need(Decimal(r['energy_J'][1])-Decimal(r['energy_J'][0])<=Decimal('.000001'))
    check('scalar_closed_form_with_temperature_leakage_energy',scalar)
    def five():
        plat=physical(5,[1]*5,[[1 if i==j else 0 for j in range(5)] for i in range(5)])
        r=evaluate_piecewise(plat,[30]*5,[60]*5,[segment(plat,[0,0,0,0,1],[0]*5,F(1,8))],125,budget=Budget(60))
        need(r['state']=='SAFE'); need(contain(r['energy_J'],Decimal('.125')))
        need(r['node_injected_energy_J']['n0']==['0','0'] and contain(r['node_injected_energy_J']['n4'],Decimal('.125')))
    check('five_node_shared_only_heat_and_exact_energy',five)
    def interior():
        plat=physical(2,[1,1],[[2,-1],[-1,2]]); seg=segment(plat,[0,0],[0,0],3)
        r=evaluate_piecewise(plat,[35,25],[60,F('26.8')],[seg],3000,budget=Budget(60))
        need(r['state']=='THERMAL_VIOLATION' and r['violations'] and not r['rankable_energy'])
        need(Decimal(r['peaks_degC']['n1'][0])>Decimal('26.8'))
        need(Decimal(r['final_temperature_degC']['n1'][1])<Decimal('26.8'))
    check('interior_peak_violation_with_safe_endpoints',interior)
    def interrupted_violation():
        plat=physical(1,[1],[[1]]); seg=segment(plat,[0],[0],1)
        def hook(event,b):
            if event=='after_violation_commit': b.seconds=-1
        r=evaluate_piecewise(plat,[35],[34],[seg],1000,budget=Budget(60,hook=hook))
        need(r['state']=='THERMAL_VIOLATION' and len(r['violations'])==1 and not r['complete'] and r['energy_J'] is None)
    check('budget_expiry_preserves_already_formed_violation',interrupted_violation)
    def interrupted_final():
        plat=physical(1,[1],[[1]]); seg=segment(plat,[1],[0],F(1,8))
        def hook(event,b):
            if event=='before_scene_commit': b.seconds=-1
        r=evaluate_piecewise(plat,[30],[60],[seg],125,budget=Budget(60,hook=hook))
        need(r['state']=='UNRESOLVED' and not r['complete'] and not r['rankable_energy'] and r['energy_J'] is None)
    check('expired_final_commit_cannot_publish_safe_energy',interrupted_final)
    def empty_budget():
        r=adapter.evaluate_schedule(x,f,Budget(seconds=-1)); need(r['state']=='UNRESOLVED' and r['energy_J'] is None)
    check('no_budget_gives_no_thermal_claim',empty_budget)
    def split():
        plat=physical(1,[2],[[F('.2')]]); initial=[35]; limits=[60]
        a=evaluate_piecewise(plat,initial,limits,[segment(plat,[F('.4')],[F('.02')],1)],1000,budget=Budget(60))
        b=evaluate_piecewise(plat,initial,limits,[segment(plat,[F('.4')],[F('.02')],F(1,2)),segment(plat,[F('.4')],[F('.02')],F(1,2),F(1,2))],1000,budget=Budget(60))
        need(a['state']==b['state']=='SAFE')
        need(max(Decimal(a['energy_J'][0]),Decimal(b['energy_J'][0]))<=min(Decimal(a['energy_J'][1]),Decimal(b['energy_J'][1])))
    check('segment_split_preserves_temperature_history_and_energy',split)
    report=dict(kind='TEST_ONLY',passed=all(c['passed'] for c in checks),checks=checks,elapsed_s=time.perf_counter()-started,input_sha256=digest,research_optimizer_calls=0,scope='Analytic and software fixtures, not device-selection or hardware research')
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"A04 Python correctness checks {sum(c['passed'] for c in checks)}/{len(checks)}")
    for c in checks:
        if not c['passed']: print(c['name'],c['error'])
    if not report['passed']: raise SystemExit(1)
if __name__=='__main__':
    run(sys.argv[1] if len(sys.argv)>1 else ROOT/'evidence/a04/python_precheck_01.json')
