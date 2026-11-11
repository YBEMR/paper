"""Extract the one full-domain comparison from saved evidence only."""
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(folder):
    from completion_metrics import build_completion_metrics
    folder=Path(folder);batch=read(folder/'batch.json');rows=[]
    for name in ('whole_milp','heft','sa101'):
        slot=folder/'slots'/(name+'__method');path=slot/'worker/raw_result.json'
        if not path.exists():
            record=read(slot/'slot_result.json') if (slot/'slot_result.json').exists() else {}
            rows.append({'id':name,'execution_status':'NOT_RUN' if name in batch['not_run'] else record.get('status','NO_RAW_RECEIPT'),
                         'error':record.get('error'),'rankable':False})
            continue
        raw=read(path);meta=read(slot/'slot_result.json');metrics=build_completion_metrics(raw,uses_matlab=name=='whole_milp',seconds=300)
        postslot=folder/'slots'/(name+'__post')
        post=read(postslot/'worker/post_result.json') if (postslot/'worker/post_result.json').exists() else {}
        postmeta=read(postslot/'slot_result.json') if (postslot/'slot_result.json').exists() else {}
        if post:assert post['method_receipt_sha256']==sha(path)
        u=raw.get('safe_upper_bound_J');ev=raw.get('evaluation') or {}
        safes=metrics['complete_SAFE_receipts']
        best=[v['completed_at_s'] for v in safes if u is not None and Q(v['safe_upper_bound_J'])==Q(u)]
        initial=metrics['initial_complete_SAFE_energy_interval_J']
        bound=raw.get('independent_lower_bound')
        if (slot/'worker/method/independent_bounds.json').exists():
            bound=read(slot/'worker/method/independent_bounds.json').get('L0')
        row={'id':name,'execution_status':meta['status'],'method_state':raw.get('state'),'reason':raw.get('reason'),
             'error':raw.get('error') or meta.get('error'),'raw_sha256':sha(path),
             'initial_energy_J':initial[1] if initial else raw.get('initial_safe_upper_bound_J'),
             'final_energy_J':u,'weighted_energy_interval_J':ev.get('weighted_energy_J'),
             'first_safe_s':metrics['first_complete_SAFE_at_s'],
             'best_safe_s':min(best) if best else ev.get('completed_at_elapsed_s'),
             'method_elapsed_s':(raw.get('timing') or {}).get('method_elapsed_s'),
             'total_method_wall_s':meta['total_wall_s'],'post_state':post.get('state'),
             'post_wall_s':postmeta.get('total_wall_s'),'post_execution_status':postmeta.get('status'),
             'rankable':meta['status'] in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT','NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST','NORMAL_UNRESOLVED') and post.get('state')=='SAFE' and postmeta.get('status')=='NORMAL_COMPLETION',
             'independent_lower_bound':bound,'model_summary':raw.get('model_summary'),
             'construction':raw.get('construction'),'timing':raw.get('timing'),'completion_metrics':metrics,
             'independently_proven_optimal':raw.get('independently_proven_optimal',False),
             'initial_candidate':((raw.get('initialisation') or {}).get('witness') or {}).get('candidate'),
             'final_candidate':raw.get('safe_candidate')}
        if row['initial_candidate'] is None:
            accepted=[r for r in raw.get('evaluations',[]) if r.get('accepted_safe')]
            if accepted:row['initial_candidate']=accepted[0]['candidate']
        if ev.get('scenes'):
            scenes=ev['scenes']; row.update(
                schedule_with_exact_ends=(ev.get('legality') or {}).get('scenes'),
                maximum_peak_upper_degC=max(float(v[1]) for s in scenes.values() for v in s['peaks_degC'].values()),
                peaks_degC={sid:s['peaks_degC'] for sid,s in scenes.items()},
                weighted_energy_components_J={k:[str(sum(Q(s['energy_components_J'][k][i]) for s in scenes.values())/2) for i in (0,1)] for k in next(iter(scenes.values()))['energy_components_J']})
        native=[]
        for response in sorted((slot/'worker/method/matlab').glob('request_*.response.json')):
            r=read(response);native.append({'path':response.relative_to(folder).as_posix(),'sha256':sha(response),
                'status':r.get('status'),'exitflag':r.get('exitflag'),'fval':r.get('fval'),
                'output':r.get('output'),'phase_seconds':r.get('phase_seconds'),
                'effective_MaxTime':(r.get('options') or {}).get('MaxTime'),
                'scope':'solver-reported diagnostic; may arrive after cutoff, never supplies a new accepted U'})
        row['native_diagnostics']=native
        if bound and bound.get('lower_bound_J') is not None and u is not None:
            lo=Q(bound['lower_bound_J']);row['U_minus_independent_L0_J']=str(Q(u)-lo)
            row['relative_gap_to_independent_L0_percent']=float(100*(Q(u)-lo)/lo) if lo>0 else None
        rows.append(row)
    usable=[r for r in rows if r['rankable']]
    best=min((Q(r['final_energy_J']) for r in usable),default=None)
    for r in usable:
        r['gap_to_best_observed_percent']=float(100*(Q(r['final_energy_J'])-best)/best)
    return {'schema':'one-natural-full-domain-comparison-v1','batch_state':batch['state'],
            'batch_error':batch.get('error'),'batch_total_wall_s':batch['total_wall_s'],
            'method_calls':batch['method_attempts'],'post_calls':batch['post_attempts'],
            'not_run':batch['not_run'],'batch_sha256':sha(folder/'batch.json'),'methods':rows,
            'best_observed_energy_J':str(best) if best is not None else None,
            'scope':'New full domain; no K194/K196 optimum imported. Saved evidence only; zero scientific calls.',
            'SA_scope':'One predeclared seed101, no replicate statistics or stability inference.'}


if __name__=='__main__':
    if len(sys.argv)!=3:raise SystemExit('Usage: summarize_natural_full.py BATCH_FOLDER NEW_OUTPUT_JSON')
    result=summarize(sys.argv[1]);p=Path(sys.argv[2]);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'state':result['batch_state'],'methods':result['method_calls'],'posts':result['post_calls'],
                      'results':[{k:r.get(k) for k in ('id','execution_status','final_energy_J','rankable')} for r in result['methods']]},ensure_ascii=False))
