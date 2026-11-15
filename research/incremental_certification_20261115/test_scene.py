"""Correctness and adversarial contract tests, separated from timed pilots."""
import argparse,json,time
from copy import deepcopy
from pathlib import Path
from runtime import SceneReuse,IdentityError,digest,load_frozen,semantic,count_extrema

def main(cache,out):
    t,timing,c,version=load_frozen(cache)
    root=cache/'research/chapter4_scheduler/results/onp_new24_20261113'
    raw=json.loads((root/'execution/calls/04_U07__n24_ON_P_I1/method/result.json').read_text())
    inp=json.loads((root/'execution/frozen_inputs/U07__n24/instance.json').read_text())
    cfg=json.loads((root/'execution/frozen_inputs/U07__n24/config.json').read_text())
    initial=raw['initial_safe_snapshot'];nextrow=next(e for e in raw['evaluations'] if e['phase']=='refinement')
    checks=[];started=time.perf_counter()
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    b=timing.MethodBudget(seconds=60);b.extremum_calls=0;r=SceneReuse(t,inp,cfg,b,version)
    with count_extrema(t,b):
        a=r.evaluate(initial['candidate']);c.safe_receipt(inp,initial['candidate'],a,cfg['accuracy_targets'],60);r.commit(a)
        check('cold_miss_exact_archived_certificate',semantic(a)==semantic(initial['receipt']))
        panels=b.panels
        z=r.evaluate(nextrow['candidate']);c.safe_receipt(inp,nextrow['candidate'],z,cfg['accuracy_targets'],60);r.commit(z)
        check('one_unchanged_scene_reused',r.metrics['scene_hits']==1)
        check('new_candidate_identity',z['evidence_identity']['candidate_sha256']==nextrow['candidate_sha256'] and z['evidence_identity']!=a['evidence_identity'])
        check('new_aggregate_exact_archived_certificate',semantic(z)==semantic(nextrow['receipt']))
        check('new_candidate_has_own_formation',z['completed_at_elapsed_s']>=a['completed_at_elapsed_s'])
        before=b.panels;rep=r.evaluate(initial['candidate']);c.safe_receipt(inp,initial['candidate'],rep,cfg['accuracy_targets'],60);r.commit(rep)
        check('two_scene_hit_no_new_panels',b.panels==before and r.metrics['scene_hits']==3)
        check('cached_exact_enclosure',semantic(rep)==semantic(initial['receipt']))
        bad=deepcopy(initial['candidate']);bad['scenes']['C1'].pop();before=r.metrics['scene_queries']
        rejected=r.evaluate(bad)
        check('invalid_schedule_rejected_before_cache',rejected['state']=='INVALID_SCHEDULE' and r.metrics['scene_queries']==before)
        before_cfg=deepcopy(cfg);cfg['accuracy_targets']['energy_relative_error']='0.00001'
        try:r.evaluate(initial['candidate']);passed=False
        except IdentityError:passed=True
        cfg.clear();cfg.update(before_cfg);check('accuracy_drift_refused',passed)
        oldseconds=b.seconds;b.seconds+=1
        try:r.evaluate(initial['candidate']);passed=False
        except IdentityError:passed=True
        b.seconds=oldseconds;check('budget_root_drift_refused',passed)
        oldtemp=inp['platform']['ambient_temperature_degC'];inp['platform']['ambient_temperature_degC']='26'
        try:r.evaluate(initial['candidate']);passed=False
        except IdentityError:passed=True
        inp['platform']['ambient_temperature_degC']=oldtemp;check('platform_drift_refused',passed)
        key=next(iter(r.cache));saved=deepcopy(r.cache[key]);r.cache[key]['result']['energy_J'][0]='0'
        try:r.evaluate(initial['candidate']);passed=False
        except IdentityError:passed=True
        r.cache[key]=saved;check('tampered_scene_proof_refused',passed)
        original_clock=b.clock
        def expire(event,budget):
            if event=='before_aggregate_commit':budget.clock=lambda:budget.deadline+1
        b.hook=expire;late=r.evaluate(initial['candidate'])
        check('no_postdeadline_SAFE_from_cached_components',late['state']=='UNRESOLVED' and late.get('completed_at_elapsed_s') is None)
        b.clock=original_clock;b.hook=None
    limited=timing.MethodBudget(seconds=30);limited.panel_limit=1;limited.extremum_calls=0
    empty=SceneReuse(t,inp,cfg,limited,version)
    with count_extrema(t,limited):part=empty.evaluate(initial['candidate'])
    check('panel_limit_preserved',part['state']=='UNRESOLVED' and any(s.get('reason')=='panel_limit' and s.get('budget_exhausted') for s in part['scenes'].values()))
    check('partial_candidate_never_cached',len(empty.cache)==0)
    result={'stage':'SCENE_CORRECTNESS','status':'PASS','checks':checks,'check_count':len(checks),
        'wall_s':time.perf_counter()-started,'new_panels':b.panels+limited.panels,
        'new_extremum_calls':b.extremum_calls+limited.extremum_calls,
        'note':'Uses two archived complete candidates and one forced partial call; negative mutations are test-only, not benchmark inputs.'}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','check_count','wall_s','new_panels']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();main(a.cache,a.out)
