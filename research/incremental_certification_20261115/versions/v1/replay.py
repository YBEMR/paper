"""One fresh process, one 300-second root, archived candidate order, no search."""
import argparse, ctypes, hashlib, json, os, platform, sys, time
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from runtime import SceneReuse,compact_receipt,count_extrema,digest,load_frozen,semantic

REL=Path('research/chapter4_scheduler/results/onp_new24_20261113')

def peak_memory():
    if os.name!='nt':
        import resource
        return {'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'kind':'process_lifetime_peak_RSS'}
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
            ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
    x=PMC();x.cb=ctypes.sizeof(x);get=ctypes.windll.kernel32.GetCurrentProcess;get.restype=ctypes.c_void_p
    ok=ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(get()),ctypes.byref(x),x.cb)
    if not ok:raise RuntimeError('memory measurement failed')
    return {'peak_rss_bytes':x.PeakWorkingSetSize,'current_rss_bytes':x.WorkingSetSize,'peak_pagefile_bytes':x.PeakPagefileUsage,'kind':'fresh_process_lifetime_peak_working_set'}

def run(cache,call,arm,out,seconds=300,max_candidates=None):
    entered=time.perf_counter();cpu_start=time.process_time();out.mkdir(parents=True,exist_ok=False)
    thermal,timing,contracts,version=load_frozen(cache)
    budget=timing.MethodBudget(seconds=seconds);budget.extremum_calls=0
    source_load_s=time.perf_counter()-entered
    setup=time.perf_counter();base=cache/REL;folder=base/'execution/calls'/call
    raw=json.loads((folder/'method/result.json').read_text(encoding='utf-8'))
    case='U'+call.split('_U')[1][:2]
    instance=json.loads((base/'execution/frozen_inputs'/f'{case}__n24'/'instance.json').read_text(encoding='utf-8'))
    config=json.loads((base/'execution/frozen_inputs'/f'{case}__n24'/'config.json').read_text(encoding='utf-8'))
    rows=[e for e in raw['evaluations'] if not e.get('cache_hit',False)]
    if max_candidates is not None:rows=rows[:max_candidates]
    assert digest(instance)==raw['input_sha256']
    assert digest(config)==raw['root_context']['config_sha256']
    assert digest(config['accuracy_targets'])==raw['root_context']['accuracy_sha256']
    if arm=='C':
        from prefix import PrefixReuse
        reuse=PrefixReuse(thermal,instance,config,budget,version)
    else:reuse=SceneReuse(thermal,instance,config,budget,version,enabled=arm!='A')
    source_hashes={str(p.relative_to(Path(__file__).parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}
    setup_s=time.perf_counter()-setup;results=[];failure=None;not_started=[];current_best=None
    with (out/'receipts.jsonl').open('w',encoding='utf-8') as stream,count_extrema(thermal,budget):
        for ordinal,old in enumerate(rows,1):
            if budget.elapsed>=budget.seconds:
                not_started=[{'ordinal':i,'candidate_sha256':e['candidate_sha256'],'state':'NOT_STARTED_BUDGET'} for i,e in enumerate(rows[ordinal-1:],ordinal)];break
            candidate=deepcopy(old['candidate']);before_panels=budget.panels;before_extrema=budget.extremum_calls;before_refine=budget.refinements
            previous_metrics=dict(reuse.metrics);start=time.perf_counter();start_elapsed=budget.elapsed
            try:
                legal_begin=time.perf_counter();legal=thermal.validate_schedule(instance,candidate);legal_s=time.perf_counter()-legal_begin
                budget.check();receipt=reuse.evaluate(candidate);core_end=time.perf_counter()
                validation_start=time.perf_counter()
                if receipt.get('legality') is not None and receipt['legality']!=legal:raise RuntimeError('LEGALITY_CHANGED')
                if contracts.technical_issues(receipt):raise RuntimeError('TECHNICAL_RECEIPT')
                if receipt['state']=='SAFE':
                    energy=contracts.safe_receipt(instance,candidate,receipt,config['accuracy_targets'],seconds)
                    # No historical timing or old candidate identity is adopted.
                    if receipt['completed_at_elapsed_s']>budget.elapsed:raise RuntimeError('FUTURE_TIMESTAMP')
                    if old['receipt']['state']=='SAFE' and semantic(receipt)!=semantic(old['receipt']):
                        raise RuntimeError('UNEXPLAINED_NUMERICAL_DIFFERENCE')
                    improves=current_best is None or F(energy['upper'])<(F(current_best['upper']) if old['phase']=='initialization' else F(current_best['lower']))
                    if old['receipt']['state']=='SAFE' and bool(old['incumbent_replaced'])!=improves:
                        raise RuntimeError('ENERGY_ORDER_CHANGED')
                    if improves:current_best=energy
                    reuse.commit(receipt)
                    if arm=='C' and improves:reuse.promote()
                else:
                    reuse.pending=[]
                    exhausted=receipt.get('budget_exhausted') or any(s.get('budget_exhausted') for s in receipt.get('scenes',{}).values())
                    if receipt['state']!='UNRESOLVED' or not exhausted:
                        raise RuntimeError('UNEXPECTED_NONSAFE')
                validation_s=time.perf_counter()-validation_start
                record={'ordinal':ordinal,'candidate_sha256':old['candidate_sha256'],'phase':old['phase'],'historical_state':old['receipt']['state'],
                    'state':receipt['state'],'start_elapsed_s':start_elapsed,'returned_elapsed_s':budget.elapsed,
                    'evaluation_wall_s':core_end-start,'outer_legality_s':legal_s,'validation_and_commit_s':validation_s,
                    'new_panels':budget.panels-before_panels,'new_extremum_calls':budget.extremum_calls-before_extrema,
                    'new_refinements':budget.refinements-before_refine,'cache_delta':{k:reuse.metrics[k]-previous_metrics[k] for k in reuse.metrics},
                    'receipt':compact_receipt(receipt)}
                record['charged_before_archive_s']=time.perf_counter()-start
                stream.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n');stream.flush();results.append(record)
            except thermal.Exhausted as exc:
                results.append({'ordinal':ordinal,'candidate_sha256':old['candidate_sha256'],'historical_state':old['receipt']['state'],
                    'state':'UNRESOLVED','reason':str(exc),'start_elapsed_s':start_elapsed,'returned_elapsed_s':budget.elapsed,
                    'new_panels':budget.panels-before_panels,'new_extremum_calls':budget.extremum_calls-before_extrema})
                stream.write(json.dumps(results[-1])+'\n');stream.flush()
            except Exception as exc:
                failure={'ordinal':ordinal,'type':type(exc).__name__,'message':str(exc),'elapsed_s':budget.elapsed}
                not_started=[{'ordinal':i,'candidate_sha256':e['candidate_sha256'],'state':'NOT_STARTED_TECHNICAL_STOP'} for i,e in enumerate(rows[ordinal:],ordinal+1)]
                (out/'failure.json').write_text(json.dumps(failure,indent=2),encoding='utf-8');break
    stopped=budget.elapsed
    summary={'call':call,'arm':arm,'root_seconds':seconds,'root_start':repr(budget.start),'root_deadline':repr(budget.deadline),
        'method_charged_s':stopped,'wall_total_s':time.perf_counter()-entered,'cpu_s':time.process_time()-cpu_start,
        'source_load_outside_root_s':source_load_s,
        'setup_inside_root_s':setup_s,'frozen_version':version,'prototype_sources':source_hashes,
        'planned_candidates':len(rows),'evaluated_candidates':len(results),'states':{s:sum(r['state']==s for r in results) for s in ['SAFE','UNRESOLVED','THERMAL_VIOLATION']},
        'not_started':not_started,'failure':failure,'physical_panels':budget.panels,'extremum_calls':budget.extremum_calls,
        'refinements':budget.refinements,'cache_metrics':reuse.metrics,'memory':peak_memory(),
        'environment':{'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),'pid':os.getpid()},
        'historical_timeouts_preserved':sum(e['receipt']['state']=='UNRESOLVED' for e in rows)}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:summary[k] for k in ['call','arm','method_charged_s','states','failure','physical_panels']}),flush=True)
    if failure:raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);p.add_argument('--call',required=True)
    p.add_argument('--arm',choices=['A','B','C'],required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=300);p.add_argument('--max-candidates',type=int)
    a=p.parse_args();run(a.cache,a.call,a.arm,a.out,a.seconds,a.max_candidates)
