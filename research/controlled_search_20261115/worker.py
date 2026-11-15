"""Exactly one ON-P invocation with a fresh original 300-second root."""
import argparse,json,platform,sys,time
from pathlib import Path
from support import HERE,INPUTS,paths,read,save,verify_sources,peak_memory,integration_identity,sha

def run(case,arm,out,freeze):
    entered=time.monotonic();cpu=time.process_time();paths()
    from timing import MethodBudget
    budget=MethodBudget(300);budget.start,budget.deadline=entered,entered+300;budget.extremum_calls=0
    root=(budget.start,budget.deadline,budget.seconds,budget.panel_limit,budget.refinement_limit)
    out.mkdir(parents=True,exist_ok=False)
    with budget.phase('frozen_identity_and_scientific_imports'):
        manifest=read(freeze)
        assert manifest['protocol']=='SIC20261115-fixed-ONP-ABC-4x300-v1'
        for name,h in manifest['code_sha256'].items():assert sha(HERE/name)==h,name
        source_status=verify_sources()
        import thermal
        from research.chapter4_scheduler.blocking import method as blocking,core
        from research.chapter4_scheduler.onp import method as onp
        from research.chapter4_scheduler.i1.initializer import run_heft_i1
        from runtime import count_extrema,digest
        from adapter import Bridge,installed
        from archive import write_result
        from h02_pair_preflight.receipts import safe_receipt
    constructions={'base_started':0,'extra_started':0,'base_returned':0,'extra_returned':0,
      'base_exceptions':0,'extra_exceptions':0,'base_wall_s':0.0,'extra_wall_s':0.0}
    original_build=core.reconstruct;original_save=blocking.original._save
    loads=[]
    with (out/'journal.jsonl').open('x',encoding='utf-8') as stream:
        bridge=Bridge(thermal,budget,arm,stream)
        def loader(active):
            assert active is budget and not loads
            config=read(HERE/'frozen'/INPUTS/case/'config.json');instance=read(HERE/'frozen'/INPUTS/case/'instance.json')
            assert digest(instance)==manifest['inputs'][case]['instance'] and digest(config)==manifest['inputs'][case]['config']
            bridge.configure(instance,config);loads.append((instance,config));return config,instance
        def measured(*args,**kwargs):
            key='extra' if kwargs.get('extra_resource_edge') is not None else 'base'
            constructions[key+'_started']+=1;start=time.perf_counter()
            try:
                result=original_build(*args,**kwargs);constructions[key+'_returned']+=1;return result
            except BaseException:
                constructions[key+'_exceptions']+=1;raise
            finally:constructions[key+'_wall_s']+=time.perf_counter()-start
        core.reconstruct=measured;blocking.original._save=write_result
        try:
            with installed(thermal,blocking,onp,bridge),count_extrema(thermal,budget):
                raw=onp.execute_reconstruction(loader,out/'method',bindings=blocking.Bindings(run_heft_i1,bridge,'REAL_I1'),
                    budget=budget,seconds=300,allow_blocking_edges=True,prefilter_enabled=True)
        finally:core.reconstruct=original_build;blocking.original._save=original_save
    # Read-only audit of already formed certificates. No post-budget physics.
    audit_start=time.perf_counter();checks=[];seen={};final_energy=None
    assert root==(budget.start,budget.deadline,budget.seconds,budget.panel_limit,budget.refinement_limit)
    instance,config=loads[0]
    for row in raw.get('evaluations',[]):
        receipt=row['receipt'];key=row['candidate_sha256']
        assert key==digest(row['candidate'])
        if row.get('accepted_safe'):
            energy=safe_receipt(instance,row['candidate'],receipt,config['accuracy_targets'],300)
            assert energy==row['energy'] and receipt['completed_at_elapsed_s']<300
            for source in receipt.get('reuse_provenance',[]):
                assert source['source_candidate'] in seen
                assert source['source_complete_at_s']==seen[source['source_candidate']]
                assert source['source_complete_at_s']<=source['reused_at_s']<300
            seen[key]=receipt['completed_at_elapsed_s']
    if raw.get('evaluation'):
        final_energy=safe_receipt(instance,raw['safe_candidate'],raw['evaluation'],config['accuracy_targets'],300)
        assert digest(raw['safe_candidate']) in seen
    assert len([r for r in raw.get('evaluations',[]) if not r.get('cache_hit')])==len([r for r in bridge.records if r['state']!='INTERRUPTED'])
    for row in raw.get('evaluations',[]):
        if 'evaluation_admitted_at_s' in row:assert row['evaluation_admitted_at_s']<180
    status=raw.get('run_terminal');normal=status in ['BUDGET_EXHAUSTED','SEARCH_COMPLETED','NORMAL_NO_SAFE']
    summary={'case':case,'arm':arm,'normal_stop':normal,'terminal':status,'reason':raw.get('reason'),
      'error':raw.get('error'),'final_SAFE':final_energy is not None,'usable_as_research_evidence':raw.get('usable_as_research_evidence'),
      'final_energy':final_energy,'final_candidate_sha256':digest(raw['safe_candidate']) if final_energy else None,
      'final_formed_s':raw['evaluation']['completed_at_elapsed_s'] if final_energy else None,
      'initial_energy':(raw.get('initial_safe_snapshot') or {}).get('energy'),
      'initial_candidate_sha256':(raw.get('initial_safe_snapshot') or {}).get('candidate_sha256'),
      'first_safe_s':raw.get('first_safe_at_s'),'initialization':{k:v for k,v in (raw.get('initialization') or {}).items() if k in
        ['admission_limit_s','fallback_used','quality_stages_completed','stop_reason','status','returned_at_s','remaining_method_s','local_accepted']},
      'method_charged_s':raw['timing']['method_elapsed_s'],'timing':raw['timing'],
      'physical_panels':budget.panels,'extremum_calls':budget.extremum_calls,'refinements':budget.refinements,
      'evaluation_attempts':len(bridge.records),'returned_states':{s:sum(r['state']==s for r in bridge.records) for s in ['SAFE','THERMAL_VIOLATION','UNRESOLVED','INTERRUPTED']},
      'full_hash_hits':raw.get('cache_hits'),'strict_search_improvements':raw.get('graph_strict_improvements'),
      'cache_metrics':bridge.reuse.metrics,'cache_accept_callback_s':bridge.accept_cache_s,'observer_s':bridge.observer_s,
      'constructions':constructions,'read_only_audit_s':time.perf_counter()-audit_start,
      'root_unchanged':True,'sources_verified':source_status,'code_identity':integration_identity(),
      'frozen_plan_sha256':sha(freeze),'input_loads':len(loads),'post_physical_evaluations':0,
      'worker_wall_s':time.monotonic()-entered,'cpu_s':time.process_time()-cpu,'memory':peak_memory(),
      'environment':{'python':sys.version,'platform':platform.platform(),'processor':platform.processor()}}
    save(out/'summary.json',summary)
    save(out/'numerical_calls.json',bridge.records)
    print(json.dumps({k:summary[k] for k in ['case','arm','terminal','final_SAFE','final_energy','method_charged_s','evaluation_attempts']},ensure_ascii=False),flush=True)
    if not normal:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True,choices=['U07__n24','U08__n24','U09__n24','U10__n24'])
    p.add_argument('--arm',required=True,choices=['A','B','C']);p.add_argument('--out',required=True,type=Path);p.add_argument('--freeze',required=True,type=Path)
    a=p.parse_args();run(a.case,a.arm,a.out,a.freeze)
