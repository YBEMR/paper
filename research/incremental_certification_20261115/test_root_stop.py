"""Regression for non-wall exhaustion; one real warm cache plus mock controls."""
import argparse,importlib.util,json,time
from copy import deepcopy
from pathlib import Path
from runtime import SceneReuse,RootClosed,load_frozen,semantic

def main(cache,out):
    t,timing,c,version=load_frozen(cache);base=cache/'research/chapter4_scheduler/results/onp_new24_20261113'
    raw=json.loads((base/'execution/calls/04_U07__n24_ON_P_I1/method/result.json').read_text())
    inp=json.loads((base/'execution/frozen_inputs/U07__n24/instance.json').read_text());cfg=json.loads((base/'execution/frozen_inputs/U07__n24/config.json').read_text())
    initial=raw['initial_safe_snapshot'];nxt=next(e for e in raw['evaluations'] if e['phase']=='refinement')
    checks=[];start=time.perf_counter()
    def check(name,v):
        checks.append({'name':name,'passed':bool(v)})
        if not v:raise AssertionError(name)
    b=timing.MethodBudget(seconds=30);r=SceneReuse(t,inp,cfg,b,version)
    a=r.evaluate(initial['candidate']);c.safe_receipt(inp,initial['candidate'],a,cfg['accuracy_targets'],30);r.commit(a)
    computed=b.panels;b.panels=b.panel_limit  # TEST_ONLY: simulate already consumed physical count.
    stopped=r.evaluate(nxt['candidate'])
    check('nonwall_exhaustion_returns_original_UNRESOLVED',stopped['state']=='UNRESOLVED' and b.elapsed<30)
    try:r.evaluate(initial['candidate']);ok=False
    except RootClosed:ok=True
    check('warm_cache_cannot_issue_new_certificate_after_root_stop',ok)
    check('previous_complete_SAFE_remains_auditable',bool(c.safe_receipt(inp,initial['candidate'],a,cfg['accuracy_targets'],30)))
    # Demonstrate the old control gap with the same already certified component;
    # no new propagation, no cache transfer across a numerical root.
    spec=importlib.util.spec_from_file_location('old_runtime',Path(__file__).parent/'versions/v1/runtime.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    legacy=old.SceneReuse(t,inp,cfg,b,version);legacy.cache=deepcopy(r.cache)
    legacy_again=legacy.evaluate(initial['candidate'])
    check('v1_gap_reproduced_in_same_test_root',legacy_again['state']=='SAFE' and b.panels>b.panel_limit)
    # Original deterministic numerical certificate is unchanged: this is a
    # root lifecycle violation, not an incorrect thermal enclosure.
    check('v1_gap_not_hidden_as_numerical_difference',semantic(legacy_again)==semantic(a))
    from types import SimpleNamespace
    for enabled in [False,True]:
        for reason in ['panel_limit','peak_refinement_limit','wall_time_limit','ENERGY_ERROR_TARGET']:
            budget=timing.MethodBudget(seconds=10);calls=[]
            def evaluator(*args):
                calls.append(1);return {'state':'UNRESOLVED','reason':'NOT_ALL_SCENES_COMPLETE_AND_SAFE',
                  'scenes':{'C1':{'state':'UNRESOLVED','reason':reason,'budget_exhausted':reason!='ENERGY_ERROR_TARGET'}}}
            fake=SimpleNamespace(evaluate_piecewise=lambda *a,**k:None,evaluate_candidate=evaluator)
            item=SceneReuse(fake,{}, {'accuracy_targets':{}},budget,'test-only',enabled=enabled)
            item.evaluate({})
            try:item.evaluate({});ok=False
            except RootClosed:ok=True
            check(('B' if enabled else 'A')+'_closed_after_'+reason,ok and len(calls)==1)
    result={'status':'PASS','checks':checks,'check_count':len(checks),'wall_s':time.perf_counter()-start,
      'actual_completed_panels_before_injected_counter':computed,'injected_counter':b.panel_limit,
      'v1_issue':'New aggregate SAFE could be formed after an earlier panel-limit UNRESOLVED; its numerical enclosure remained correct. v2 latches root closure.',
      'scope':'Same isolated test root, explicit counter fault injection; no benchmark input or limit changed.'}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','check_count','wall_s']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.cache,a.out)
