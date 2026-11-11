"""Summarize saved R1 records only; no research imports or solver/evaluator calls."""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

HERE = Path(__file__).resolve().parent
RAW = HERE / 'raw'
LOCAL = RAW / 'local_records'
PAIR = LOCAL / 'r1_pair_run01'

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(name, data):
    with (HERE/name).open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')

def main():
    start = dt.datetime.now(dt.timezone.utc).isoformat()
    t = time.monotonic()
    checks = {}
    manifest = read(LOCAL/'execution_file_manifest.json')['files_sha256']
    checks['execution_manifest'] = dict(count=len(manifest), mismatches=[n for n,h in manifest.items() if sha(RAW/n)!=h])
    inner = RAW/'input_bundle/R1_support_local_matlab_20261110.zip'
    plan = read(LOCAL/'r1_local_plan.json')
    with zipfile.ZipFile(inner) as z:
        m = json.loads(z.read('research/chapter3_support_local_migration_20261110/migration_manifest.json'))
        for label,entries in [('migration_manifest',m['files_sha256']),('runtime_source',plan['runtime_source_sha256']),('input_byte_hashes',plan['input_sha256'])]:
            checks[label] = dict(count=len(entries),mismatches=[n for n,h in entries.items() if hashlib.sha256(z.read(n)).hexdigest()!=h])
    checks['input_bundle_sha256'] = sha(inner)
    checks['plan_sha256'] = sha(LOCAL/'r1_local_plan.json')
    checks['plan_identity_matches'] = checks['plan_sha256']==read(LOCAL/'r1_local_plan_identity.json')['plan_sha256']
    checks['input_files_identical'] = {name:(PAIR/'off/method'/name).read_bytes()==(PAIR/'on/method'/name).read_bytes() for name in ['input_instance.json','input_config.json']}
    protected = read(HERE/'protected_review_files.json')
    checks['protected_old_review_files'] = dict(count=len(protected), changed=[n for n,h in protected.items() if sha(HERE.parent/n)!=h])
    members = read(HERE/'zip_member_manifest.json')
    checks['raw_extraction'] = dict(count=len(members), changed=[e['path'] for e in members if sha(RAW/e['path'])!=e['sha256']])
    results = {}
    event_rows = []
    timings = []
    for variant in ['off','on']:
        m = PAIR/variant/'method'
        r = read(m/'result.json')
        c = r['construction']
        d = r['diagnostic']
        init = r['initialisation']['witness']
        guard = read(PAIR/variant/'initial_guard.json')
        inp = read(m/'matlab/request_000001.input.json')
        received = {e['event_number']:e for e in d['solver_progress']}
        events = []
        for p in sorted((m/'matlab').glob('request_000001.event_*.json')):
            e = read(p)
            number = e['event_number']
            row = dict(variant=variant,event_number=number,kind=e.get('kind'),state=e.get('state'),
                       request_wall_s=e.get('request_wall_seconds'),python_method_received_s=received.get(number,{}).get('method_elapsed_s'),
                       received_in_budget=number in received,x_length=len(e.get('x',[])),**e.get('values',{}))
            events.append(row)
            event_rows.append(row)
        evals=[]
        for e in d['evaluations']:
            ev=e['evaluation']
            evals.append(dict(source=e['source'],accepted_safe=e['accepted_safe'],
                completed_at_method_s=e['evaluation_returned_at_s'],state=ev['state'],
                weighted_energy_J=ev.get('weighted_energy_J'),evidence_identity=ev.get('evidence_identity'),
                candidate_equals_initial=e['candidate']==init['candidate']))
        summaries = dict(variant=variant,state=r['state'],reason=r['reason'],safe_solution_source=r['safe_solution_source'],
            safe_upper_bound_J=r['safe_upper_bound_J'],initial_safe_s=r['first_initial_safe_s'],
            x0_formed_s=r['initialisation']['completion']['completed_at_s'],guard=guard,
            python_initial_point=inp['initial_point'],native_entry_received_s=d['solver_entered_received_s'],
            events=events,solver_evaluations=evals,first_solver_SAFE_s=d['first_safe_receipt_s'],
            energy_improved=r['milp_improved_initial_upper_bound'],strict_improvement=r['strict_energy_improvement_certified'],
            initial_evidence_identity=init['evaluation']['evidence_identity'],
            model_counts={k:c.get(k) for k in ['options','variables','binary_variables','rows','nonzeros_in_rows','coefficient_sets_completed','events_per_scene','scene_control_intervals_begun','affine_templates','memory']},
            baseline_formulation=r['model_summary']['formulation'],
            support_summary={k:v for k,v in r['model_summary']['preprocessing'].get('option_support',{}).items() if k!='rounds'},
            timing=r['timing'],response_present=(m/'matlab/request_000001.response.json').exists(),
            native_mat_present=(m/'matlab/request_000001.native.mat').exists(),
            python_final_admission=read(m/'matlab/request_000001.python.json'))
        summaries['python_final_admission'].pop('x',None)
        if summaries['response_present']:
            resp=read(m/'matlab/request_000001.response.json')
            summaries['late_response']={k:v for k,v in resp.items() if k not in ['x','callbacks']}
            summaries['late_response_x_length']=len(resp.get('x',[]))
        results[variant]=summaries
        for phase in r['timing']['phase_records']:
            timings.append(dict(variant=variant,**phase))
    checks['initial_physical_candidates_equal'] = read(PAIR/'off/method/result.json')['initialisation']['witness']['candidate']==read(PAIR/'on/method/result.json')['initialisation']['witness']['candidate']
    checks['energy_upper_bounds_equal'] = results['off']['safe_upper_bound_J']==results['on']['safe_upper_bound_J']
    on4=next(e for e in results['on']['events'] if e['event_number']==4)
    gap=100*(on4['fval']-on4['lowerbound'])/(abs(on4['fval'])+1)
    checks['same_callback_gap_recomputed_percent']=gap
    checks['same_callback_gap_matches']=abs(gap-on4['relativegap'])<1e-12
    metrics=read(LOCAL/'verified_metrics.json')
    metric_differences=[]
    for slot in metrics['slots']:
        r=results[slot['variant']]
        for field, actual in [('safe_upper_bound_J',r['safe_upper_bound_J']),('first_solver_SAFE_s',r['first_solver_SAFE_s']),('final_response_missing',not r['response_present']),('initial_safe_s',r['initial_safe_s']),('method_elapsed_s',r['timing']['method_elapsed_s'])]:
            if slot[field]!=actual:
                metric_differences.append(dict(variant=slot['variant'],field=field,recorded=slot[field],actual=actual))
    checks['verified_metrics_selected_fields_differences']=metric_differences
    write('verification_checks.json',checks)
    write('raw_result_summary.json',results)
    for filename, rows in [('callback_timeline.csv',event_rows),('phase_timing.csv',timings)]:
        fields=list(dict.fromkeys(k for r in rows for k in r))
        with (HERE/filename).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields)
            w.writeheader()
            w.writerows([{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v) for k,v in r.items()} for r in rows])
    comparisons=[]
    for field in ['options','variables','binary_variables','rows','nonzeros_in_rows','coefficient_sets_completed']:
        a,b=(results[v]['model_counts'][field] for v in ['off','on'])
        comparisons.append(dict(metric=field,off=a,on=b,on_minus_off=b-a,reduction_percent=100*(a-b)/a))
    for field in ['model_construction','solver_startup','solver_wait_and_response_read']:
        a,b=(results[v]['timing']['phases_exclusive_s'][field] for v in ['off','on'])
        comparisons.append(dict(metric=field+'_exclusive_s',off=a,on=b,on_minus_off=b-a,reduction_percent=100*(a-b)/a))
    with (HERE/'comparison.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(comparisons[0]));w.writeheader();w.writerows(comparisons)
    write('analysis_execution.json',dict(started_utc=start,ended_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        wall_s=time.monotonic()-t,argv=sys.argv,python=sys.version,new_solver_build_thermal_calls=0,
        checks_scope='Hashes, saved JSON/event consistency and arithmetic only; no research imports, SAFE recalculation or new model'))
    print(json.dumps(dict(checks=checks,events=len(event_rows),comparison=comparisons),ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
