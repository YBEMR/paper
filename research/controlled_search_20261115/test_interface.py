"""Bounded interface checks with two archived SAFE candidates, never a search."""
import argparse,json,time
from copy import deepcopy
from pathlib import Path
from support import HERE,INPUTS,paths,read,save,verify_sources

def run(archive,out):
    paths();verify_sources()
    import thermal
    from timing import MethodBudget
    from research.chapter4_scheduler.blocking import method as blocking
    from research.chapter4_scheduler.onp import method as onp
    from research.chapter4_scheduler.i1.initializer import run_heft_i1
    from research.chapter4_scheduler.i1.admission import AdmissionClosed
    from adapter import Bridge,installed
    from runtime import semantic,RootClosed,count_extrema
    raw=read(archive);first=raw['initial_safe_snapshot']
    follow=[r for r in raw['evaluations'] if r['phase']=='refinement']
    second,third=follow[:2]
    instance=read(HERE/'frozen'/INPUTS/'U07__n24/instance.json');config=read(HERE/'frozen'/INPUTS/'U07__n24/config.json')
    checks=[];begin=time.perf_counter();records=[]
    def check(name,value):
        checks.append({'name':name,'passed':bool(value)})
        save(out,{'status':'IN_PROGRESS','checks':checks,'scope':'TEST_ONLY; no search; two numerical candidates per arm plus explicit counter fault injection.'})
        assert value,name
    for arm in 'ABC':
        budget=MethodBudget(300);budget.extremum_calls=0;bridge=Bridge(thermal,budget,arm);bridge.configure(deepcopy(instance),deepcopy(config))
        with installed(thermal,blocking,onp,bridge),count_extrema(thermal,budget):
            bound=blocking.Bindings(run_heft_i1,bridge,'REAL_I1')
            rec=blocking.CompleteRecorder(bridge.reuse.instance,bridge.reuse.config,budget,bound,onp.source_identity())
            one=rec.assess(deepcopy(first['candidate']),'TEST:init')
            check(arm+'_initial_original_numerical_semantics',semantic(one)==semantic(first['receipt']))
            check(arm+'_original_safe_accepted_before_cache',bridge.commit_count==1 and rec.rows[0]['accepted_safe'])
            rec.freeze_initial();two=rec.assess(deepcopy(second['candidate']),'TEST:refinement')
            check(arm+'_refinement_original_numerical_semantics',semantic(two)==semantic(second['receipt']))
            check(arm+'_strict_acceptance_matches_archive',rec.rows[-1]['incumbent_replaced']==second['incumbent_replaced'])
            panels=budget.panels;calls=len(bridge.records)
            rec.assess(deepcopy(first['candidate']),'TEST:full_hash')
            check(arm+'_old_full_hash_cache_preserved',rec.cache_hits==1 and budget.panels==panels and len(bridge.records)==calls)
            if arm=='B':check('B_scene_reuse_participates',bridge.reuse.metrics['scene_hits']>0)
            if arm=='C':check('C_scene_and_prefix_participate',bridge.reuse.metrics['scene_hits']>0 and bridge.reuse.metrics['prefix_hits']>0)
            # Simulate a late initialization assessment at the unchanged gate.
            rec.phase='initialization';budget.clock=lambda:budget.start+180
            try:rec.assess(deepcopy(third['candidate']),'TEST:admission');caught=False
            except AdmissionClosed:caught=True
            check(arm+'_180_gate_no_numerical_call_no_root_close',caught and len(bridge.records)==calls and bridge.reuse.closed_reason is None)
            rec.phase='refinement';budget.clock=lambda:budget.start+181
            rec.assess(deepcopy(first['candidate']),'TEST:after_admission')
            check(arm+'_refinement_allowed_after_admission_stop',rec.cache_hits==2 and bridge.reuse.closed_reason is None)
            # Inject consumption only; do not compute 100000 physical panels.
            budget.panels=budget.panel_limit
            try:rec.assess(deepcopy(third['candidate']),'TEST:panel_limit');stopped=False
            except blocking.SearchStop as e:stopped=str(e)=='NUMERICAL_UNRESOLVED'
            check(arm+'_numerical_unresolved_stops_root',stopped and bridge.reuse.closed_reason is not None)
            before=len(bridge.records)
            try:rec.assess(deepcopy(first['candidate']),'TEST:closed_full_cache');blocked=False
            except RootClosed:blocked=True
            check(arm+'_closed_root_blocks_even_complete_hash_cache',blocked and len(bridge.records)==before)
            check(arm+'_previous_safe_preserved',rec.current['accepted_safe'] and rec.current['receipt']['completed_at_elapsed_s']<300)
        records.append({'arm':arm,'new_extrema':budget.extremum_calls,'actual_panels_before_counter_injection':panels,
          'numeric_calls':bridge.records,'metrics':bridge.reuse.metrics})
    save(out,{'status':'PASS','checks':checks,'check_count':len(checks),'wall_s':time.perf_counter()-begin,'arms':records,
      'scope':'TEST_ONLY. Same two archived candidates across A/B/C; no candidate generation/search. Third candidate only exercises injected panel exhaustion. Test phase/clock transitions do not change benchmark inputs, budgets or original initialization rules.'})
    print(json.dumps({'status':'PASS','checks':len(checks),'wall_s':time.perf_counter()-begin}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True);run(a.archive,a.out)
