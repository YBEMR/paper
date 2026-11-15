"""Exact checkpoint resume and fail-closed boundary tests; no search."""
import argparse,json,time
from copy import deepcopy
from pathlib import Path
from prefix import PrefixReuse,plain
from runtime import IdentityError,RootClosed,digest,load_frozen,semantic,count_extrema

def main(cache,out):
    t,timing,c,version=load_frozen(cache);base=cache/'research/chapter4_scheduler/results/onp_new24_20261113'
    raw=json.loads((base/'execution/calls/04_U07__n24_ON_P_I1/method/result.json').read_text())
    inp=json.loads((base/'execution/frozen_inputs/U07__n24/instance.json').read_text());cfg=json.loads((base/'execution/frozen_inputs/U07__n24/config.json').read_text())
    initial=raw['initial_safe_snapshot'];nxt=next(e for e in raw['evaluations'] if e['phase']=='refinement')
    checks=[];begin=time.perf_counter();out.parent.mkdir(parents=True,exist_ok=True)
    def check(name,v):
        checks.append({'name':name,'passed':bool(v)})
        if not v:raise AssertionError(name)
    b=timing.MethodBudget(seconds=60);b.extremum_calls=0;r=PrefixReuse(t,inp,cfg,b,version)
    with count_extrema(t,b):
        a=r.evaluate(initial['candidate']);c.safe_receipt(inp,initial['candidate'],a,cfg['accuracy_targets'],60);r.commit(a);r.promote()
        check('cold_checkpoint_capture_exact_original',semantic(a)==semantic(initial['receipt']))
        saved_source=deepcopy(r.incumbent);before=b.panels
        z=r.evaluate(nxt['candidate']);c.safe_receipt(inp,nxt['candidate'],z,cfg['accuracy_targets'],60);r.commit(z)
        check('both_scene_and_prefix_used',r.metrics['scene_hits']==1 and r.metrics['prefix_hits']==1)
        check('all_endpoints_integrals_peaks_trace_exact',semantic(z)==semantic(nxt['receipt']))
        check('coverage_counts_add_up',b.panels-before+r.metrics['avoided_scene_panels']+r.metrics['avoided_prefix_panels']==sum(len(s['trace']) for s in z['scenes'].values()))
        source_event=next(p for p in z['reuse_provenance'] if p['kind']=='prefix');sid=source_event['scene_id']
        point=next(q for q in saved_source[sid]['checkpoints'] if q['state']['next_segment']==source_event['next_segment'])
        check('state_has_directed_interval_objects',all(isinstance(x,t.I) for x in point['state']['theta']))
        (out.parent/'checkpoint_example.json').write_text(json.dumps({'provenance':source_event,'checkpoint':plain(point,t.I)},indent=2)+'\n',encoding='utf-8')
        (out.parent/'generated_piecewise.py.txt').write_text(r.generated_source,encoding='utf-8')
        # Force the same changed scene to use its committed prefix again.
        r.cache={k:v for k,v in r.cache.items() if v['candidate_sha256']!=nxt['candidate_sha256']}
        r.incumbent=deepcopy(saved_source)
        item=next(q for q in r.incumbent[sid]['checkpoints'] if q['state']['next_segment']==source_event['next_segment'])
        saved=deepcopy(item);item['state']['theta'][0]=t.I(0)
        try:r.evaluate(nxt['candidate']);ok=False
        except IdentityError:ok=True
        check('corrupted_internal_interval_rejected',ok);item.clear();item.update(saved)
        oldpath=r.incumbent[sid]['physical'][0]['end_ms'];r.incumbent[sid]['physical'][0]['end_ms']='1'
        try:r.evaluate(nxt['candidate']);ok=False
        except IdentityError:ok=True
        r.incumbent[sid]['physical'][0]['end_ms']=oldpath;check('power_path_tamper_rejected',ok)
        oldroot=r.incumbent[sid]['root'];r.incumbent[sid]['root']=('foreign_root',)
        try:r.evaluate(nxt['candidate']);ok=False
        except IdentityError:ok=True
        r.incumbent[sid]['root']=oldroot;check('cross_root_checkpoint_rejected',ok)
        bad=deepcopy(nxt['candidate']);bad['scenes']['C1'].pop();before_q=r.metrics['prefix_queries'];reject=r.evaluate(bad)
        check('invalid_schedule_cannot_resume_prefix',reject['state']=='INVALID_SCHEDULE' and r.metrics['prefix_queries']==before_q)
        # A terminated root cannot be reopened, so exercise fallback before expiry.
        r.incumbent={};before_hits=r.metrics['prefix_hits'];fresh=r.evaluate(nxt['candidate'])
        c.safe_receipt(inp,nxt['candidate'],fresh,cfg['accuracy_targets'],60)
        check('no_checkpoint_fallback_exact',r.metrics['prefix_hits']==before_hits and semantic(fresh)==semantic(nxt['receipt']))
        r.incumbent=deepcopy(saved_source)
        oldclock=b.clock
        def expire(event,budget):
            if event=='before_panel':budget.clock=lambda:budget.deadline+1
        b.hook=expire;before_hits=r.metrics['prefix_hits'];stopped=r.evaluate(nxt['candidate'])
        check('expiry_after_restore_no_SAFE',r.metrics['prefix_hits']>before_hits and stopped['state']=='UNRESOLVED' and stopped.get('completed_at_elapsed_s') is None)
        b.clock=oldclock;b.hook=None
        check('partial_restore_not_promoted',r.incumbent[sid]['candidate_sha256']==initial['candidate_sha256'])
        try:r.evaluate(initial['candidate']);ok=False
        except RootClosed:ok=True
        check('C_terminated_root_cannot_be_reopened',ok)
    # Original certified entry violation survives expiry; test-only limit, never benchmark.
    badinp=deepcopy(inp)
    for s in badinp['scenarios']:s['maximum_temperature_degC']=['49']*4
    vbudget=timing.MethodBudget(seconds=10);vbudget.extremum_calls=0
    def stop_on_witness(event,budget):
        if event=='after_violation_commit':budget.clock=lambda:budget.deadline+1
    vbudget.hook=stop_on_witness;vr=PrefixReuse(t,badinp,cfg,vbudget,version)
    violated=vr.evaluate(initial['candidate'])
    check('complete_point_violation_survives_interrupt',violated['state']=='THERMAL_VIOLATION' and bool(c.thermal_witness(badinp,violated,10)))
    check('violation_never_cached_or_ranked',not vr.cache and not violated['rankable_energy'])
    result={'status':'PASS','checks':checks,'check_count':len(checks),'wall_s':time.perf_counter()-begin,
      'new_panels':b.panels+vbudget.panels,'new_extremum_calls':b.extremum_calls,'metrics':r.metrics,
      'scope':'Test-only corruption/expiry/entry-limit mutations; original benchmark parameters unchanged.'}
    out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:result[k] for k in ['status','check_count','wall_s','new_panels']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();main(a.cache,a.out)
