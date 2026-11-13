"""Read-only analysis of the sealed D283 run; no solver, rebuild or thermal call."""
from pathlib import Path
from fractions import Fraction
from decimal import Decimal,localcontext
import csv,hashlib,json,time
ROOT=Path(__file__).resolve().parent.parent
RUN=ROOT/'work/cplex_C_scientific_execution_v1'
OUT=ROOT/'work/cplex_C_D283_analysis_v1'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def decimal(q):
    with localcontext() as c:
        c.prec=65;return str(Decimal(q.numerator)/Decimal(q.denominator))
def schedule_key(x):return {k:sorted((v['stage_id'],v['unit'],v['opp'],str(Fraction(v['start_ms']))) for v in rows) for k,rows in x['scenes'].items()}

start=time.monotonic();OUT.mkdir(exist_ok=False)
plan=read(ROOT/'work/cplex_C_solve_v2/plan.json');controller=read(RUN/'controller_receipt.json');snapshot=read(RUN/'scientific_snapshot.json')
response=read(RUN/'native_response.json');ack=read(RUN/'response_ack.json');completion=read(RUN/'controller_completion.json')
audit=read(ROOT/'work/cplex_C_D283_launch_v1/post_run_audit.json');host=read(ROOT/'work/cplex_C_D283_launch_v1/host_receipt.json')
checks={}
checks['original_sealed_evidence_hashes']=all(sha(RUN/k)==h for k,h in controller['evidence_hashes'].items())
checks['scientific_snapshot_identity']=sha(RUN/'scientific_snapshot.json')==read(RUN/'worker_receipt.json')['snapshot_sha256']
checks['final_archive_identity']=sha(RUN/'controller_receipt.json')==completion['receipt_sha256']
checks['no_budget_revocation']=(not (RUN/'budget_invalidated.json').exists()) and completion['within_method_window'] and host['exit_code']==0
checks['source_inputs_still_frozen']=all(sha(ROOT/k)==h for k,h in plan['input_hashes'].items())
checks['science_source_still_frozen']=all(sha(ROOT/k)==h for k,h in plan['evaluation_source_hashes'].items())
checks['executor_source_still_frozen']=all(sha(ROOT/'work/cplex_C_solve_v2'/k)==h for k,h in plan['code_hashes'].items())
checks['runtime_still_frozen']=all(sha(k)==h for k,h in plan['runtime_hashes'].items())
checks['post_run_audit_retains_success']=audit['audit_passed'] and audit['retained_strict_success']
checks['exactly_one_solve_two_evaluations']=snapshot['solve_attempts']==1 and snapshot['complete_evaluation_attempts']==2
initial=read(ROOT/'work/mechanism_trials_execution_v1/C_noheur/initialization.json')['attempts'][0]['candidate']
final=snapshot['final_admission']['candidate'];ki=schedule_key(initial);kf=schedule_key(final)
checks['different_final_schedule']=ki!=kf
checks['final_schedule_identity_matches']=digest(kf)==snapshot['final_admission']['schedule_identity']
ei=snapshot['initial']['weighted_energy_J'];ef=snapshot['final']['weighted_energy_J']
il,iu=map(Fraction,ei);fl,fu=map(Fraction,ef)
checks['strict_energy_interval_order']=fu<il
checks['complete_two_scene_safe']=all(e['state']=='SAFE' and e['rankable_energy'] and set(e['scenes'])==set(plan['scene_ids']) and all(s['state']=='SAFE' and s['complete'] and s['energy_accuracy_met'] and Fraction(s['covered_until_s'])==Fraction(2,5) for s in e['scenes'].values()) for e in (snapshot['initial'],snapshot['final']))
checks['no_final_vector_substitution']=ack['vector_sha256']==response['vector']['sha256']==sha(RUN/'final_vector.npy') and ack['timely']
assert all(checks.values()),checks
save(OUT/'initial_schedule.json',initial);save(OUT/'final_schedule.json',final)
rows=[]
for scene,previous in initial['scenes'].items():
    now={r['stage_id']:r for r in final['scenes'][scene]}
    for old in previous:
        new=now[old['stage_id']]
        rows.append(dict(scene=scene,stage=old['stage_id'],old_unit=old['unit'],new_unit=new['unit'],old_opp=old['opp'],new_opp=new['opp'],old_start_ms=old['start_ms'],new_start_ms=new['start_ms']))
with (OUT/'schedule_changes.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
events=[json.loads(x) for x in (RUN/'parent_events.jsonl').read_text().splitlines()]
candidates=[]
for row in events:
    e=row['event']
    if e.get('kind')=='mip_info_callback' and e.get('vector'):
        candidates.append(dict(parent_received_elapsed_s=row['parent_received_elapsed_s'],worker_observed_elapsed_s=e['worker_elapsed_s'],
            native_objective=e['incumbent_objective']['value'],native_lower_bound=e['best_bound']['value'],nodes=e['nodes']['value'],
            vector_file=e['vector']['file'],vector_sha256=e['vector']['sha256'],scope='Native callback evidence only; no full thermal evaluation at this time'))
save(OUT/'native_candidate_timeline.json',candidates)
resources=[json.loads(x) for x in (RUN/'resources.jsonl').read_text().splitlines()]
phases=snapshot['phase_records'];wr=read(RUN/'worker_receipt.json');owned=controller['owned']
costs=[dict(stage='control entry, identity checks, process startup and imports',seconds=phases[0]['start_s'])]
cursor=phases[0]['start_s']
for row in phases:
    if row['start_s']>cursor:costs.append(dict(stage='between-stage vector reading / orchestration',seconds=row['start_s']-cursor))
    costs.append(dict(stage=row['stage'],seconds=row['end_s']-row['start_s']));cursor=row['end_s']
costs+= [dict(stage='worker source recheck and scientific sealing',seconds=wr['sealed_elapsed_s']-cursor),
         dict(stage='worker exit and owned process cleanup confirmation',seconds=owned['cleanup_elapsed_s']-wr['sealed_elapsed_s']),
         dict(stage='parent evidence/source checks, observation and final archive',seconds=completion['after_receipt_and_hash_elapsed_s']-owned['cleanup_elapsed_s'])]
assert abs(sum(x['seconds'] for x in costs)-completion['after_receipt_and_hash_elapsed_s'])<1e-8
save(OUT/'cost_ledger.json',dict(method_phase_partition=costs,method_after_receipt_and_hash_s=completion['after_receipt_and_hash_elapsed_s'],
    host_wall_s=host['outer_command_wall_s'],host_startup_exit_overhead_s=host['outer_command_wall_s']-completion['after_receipt_and_hash_elapsed_s'],
    native_CPLEX_reported_total_s=527.08,native_root_LP_s=61.56,native_root_node_s=271.73,native_branch_and_cut_s=255.34,
    note='Native reported times are overlapping drill-downs, not additional wall cost. Administrative read-only audit cannot add scientific credit.',
    post_run_readonly_audit=read(ROOT/'work/cplex_C_D283_launch_v1/post_run_audit_host.json'),CPU=owned['job_accounting'],
    peak_job_commit_MiB=owned['job']['peak_job_memory']/2**20,peak_worker_private_MiB=owned['peak_sampled_private_bytes']/2**20,
    peak_worker_RSS_MiB=max(r['rss_bytes'] for r in resources)/2**20,peak_parent_private_MiB=owned['peak_parent_private_bytes']/2**20,
    resource_samples=len(resources),system_available_at_entry_GiB=owned['available_at_entry']/2**30))
summary=dict(status='STRICT_ENERGY_IMPROVEMENT_RETAINED_BY_READONLY_AUDIT',checks=checks,plan_sha256=sha(ROOT/'work/cplex_C_solve_v2/plan.json'),
    frozen_commit='c3435233b78daf2a77b348c3f223818e2c38a73a',native_exit_status=response['status']['value'],native_exit_reason=response['status_string']['value'],
    complete_initial_energy_J=ei,complete_final_energy_J=ef,
    strict_energy_reduction_J_interval_exact=[str(il-fu),str(iu-fl)],strict_energy_reduction_J_interval_decimal=[decimal(il-fu),decimal(iu-fl)],
    strict_reduction_percent_interval_exact=[str(100*(1-fu/il)),str(100*(1-fl/iu))],strict_reduction_percent_interval_decimal=[decimal(100*(1-fu/il)),decimal(100*(1-fl/iu))],
    interval_decimal_display_note='Decimal strings are display approximations; acceptance uses exact Fraction endpoints, not these rounded percentages.',
    schedule_identities=dict(initial=digest(ki),final=digest(kf)),stage_executions=len(rows),unit_changes=sum(r['old_unit']!=r['new_unit'] for r in rows),
    opp_changes=sum(r['old_opp']!=r['new_opp'] for r in rows),start_changes=sum(Fraction(r['old_start_ms'])!=Fraction(r['new_start_ms']) for r in rows),
    native_objective=response['finite_native_upper_bound'],native_bound=response['finite_native_lower_bound'],native_gap=response['finite_native_gap'],
    native_nodes=response['nodes']['value'],native_iterations=response['iterations']['value'],
    full_energy_minus_native_objective_exact=str(fl-Fraction.from_float(response['finite_native_upper_bound'])),
    callback_vector_count=len(candidates),final_vector_sha256=response['vector']['sha256'],
    per_scene={k:dict(energy_J=v['energy_J'],peaks_degC=v['peaks_degC'],state=v['state'],complete=v['complete']) for k,v in snapshot['final']['scenes'].items()},
    independent_optimality_proof='UNKNOWN',two_level_speedup_proved=False,formal_ABC=False,extra_native_calls=0,extra_thermal_evaluations=0,
    elapsed_postseal_analysis_s=time.monotonic()-start)
save(OUT/'summary.json',summary)
print(json.dumps(dict(passed=True,checks=len(checks),reduction_percent=summary['strict_reduction_percent_interval_decimal'],phase_sum=sum(x['seconds'] for x in costs),peak_commit_MiB=owned['job']['peak_job_memory']/2**20,unit_changes=summary['unit_changes'],callback_vectors=len(candidates),postseal_analysis_s=summary['elapsed_postseal_analysis_s']),ensure_ascii=False))
