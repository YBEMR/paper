"""Static receipt/hash analysis only: no solver, recovery replay or integration."""
import hashlib
import json
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
RUN=ROOT/'research/chapter3_g0_real_entry/results/public_start_real01'

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    b=read(RUN/'batch.json');m=b['method']['worker']['result'];r=m['raw']
    s=r['stages']['1'][0];session=read(RUN/'method/work/matlab/session.json')
    native=read(RUN/'method/work/matlab/request_000001.response.json')
    py=read(RUN/'method/work/matlab/request_000001.python.json')
    meta=read(RUN/'method/work/matlab/request_000001.input.json')
    records=r['native_search_records'];rec=b['recovery']
    recovery_same=(rec['record']['candidate']==r['final']['candidate']
        and Fraction(rec['record']['U_J'])==Fraction(r['final']['U_J']))
    body=r['stopped_s'];timing=r['execution_timing']
    summary={
      'kind':'STATIC_ANALYSIS_OF_ONE_REAL_RUN_NO_NEW_EVALUATION',
      'execution_organization':m['execution_organization'],
      'engineering_source_commit':'e4184dcb6fae272b11b6ebd1278dd975c6405554',
      'plan_sha256':b['plan_sha256'],'method_calls':b['method_calls'],'post_calls':b['post_calls'],
      'granted_method_seconds':300,'batch_elapsed_s':b['batch_elapsed_s'],
      'method_body_elapsed_s':body,'method_through_close_s':timing['observed_elapsed_through_close_s'],
      'method_process_s':b['method']['process_elapsed_s'],
      'initializer_end_s':next(e['root_elapsed_s'] for e in r['events'] if e['kind']=='INITIALIZATION_END'),
      'first_legal_s':r['first_legal_s'],'first_internal_complete_safe_s':r['first_safe_s'],
      'S0_completed_s':r['S0']['completed_at_elapsed_s'],
      'S0_energy_J':float(Fraction(r['S0']['U_J'])),
      'final_energy_J':float(Fraction(r['final']['U_J'])),
      'final_same_as_S0':r['S0']==r['final'],'local_strict_improvement_J':0,
      'public_start_records':r['public_start_records'],
      'startup_scope_kind':session['startup_scope_snapshot']['kind'],
      'startup_scope_deadline_root_s':session['startup_scope_snapshot']['deadline_elapsed_s'],
      'ready_accepted_root_s':session['startup_intervals']['ready_accepted_s'],
      'startup_overview_s':session['startup_wall_seconds'],
      'session_attempts':r['session_lifecycle']['attempts'],
      'first_slot_start_s':s['started_s'],'first_slot_deadline_s':s['deadline_elapsed_s'],
      'first_slot_width_s':s['deadline_elapsed_s']-s['started_s'],
      'local_build_s':s['model_build_seconds'],'local_warm_preparation_s':s['warm_preparation_seconds'],
      'request_remaining_s':meta['case_budget_at_entry_s'],'native_MaxTime_used_s':native['solver_max_time_s_used'],
      'native_phase_seconds':native['phase_seconds'],'native_response_request_wall_s':native['matlab_request_wall_seconds'],
      'native_intlinprog_entered':native['intlinprog_entered'],
      'native_exitflag':native['exitflag'],'native_output':native['output'],
      'native_nonempty_x':bool(native.get('x')),'native_callback_count':len(native.get('callbacks',[])),
      'variables':native['initial_point']['length'],
      'python_response_status':py['status'],'python_response_accepted':py['accepted_for_evaluation'],
      'phase_native_entries':m['phase_native_entries'],
      'local_feedback_count':sum(len(x['feedback']) for x in records),
      'local_candidate_evaluation_count':sum(len(x['evaluations']) for x in records),
      'failure':r['failure'],'method_execution_state':m['execution_state'],
      'batch_stop_reason':b['stop_reason'],'phase2_entered':bool(r.get('S1')),
      'recovery_status':rec['status'],'recovery_files_seen':rec['files_seen'],
      'recovery_rejected_count':len(rec['rejected']),'recovery_retained_same_safe':recovery_same,
      'independent_post_performed':False,'post_ineligible_reason':b['stop_reason'],
      'final_close_s':timing['final_close']['seconds'],
      'matlab_observed_tree_cleanup_verified':r['cleanup']['verified'],
      'supervisor_cleanup_verified':b['method']['cleanup_verified'],
      'sampled_peak_observed_tree_rss_GiB':read(RUN/'method/memory.json')['summary']['sampled_peak_same_time_rss_sum_bytes']/2**30,
      'optimality_proved':False,'new_numerical_conflict_observed':False,
      'interpretation':'READY and intlinprog entry verified; slot response cutoff leaves blocked/unsettled state; final cleanup succeeds but method stops; late empty response is diagnostic only'}
    assert b['method_calls']==1 and b['post_calls']==0 and not (RUN/'post').exists()
    assert py['accepted_for_evaluation'] is False and native['intlinprog_entered'] is True
    assert recovery_same and r['S0']==r['final']
    save(HERE/'summary.json',summary)
    planfile=ROOT/'research/chapter3_g0_real_entry/results/public_start_plan01/frozen/plan.json'
    plan=read(planfile);drift=[p for p,h in plan['source_sha256'].items() if sha(ROOT/p)!=h]
    old=read(ROOT/'research/chapter3_g0_real_entry/results/real_entry01_analysis/integrity_audit.json')
    claim=ROOT/('research/chapter3_g0_real_entry/claims/'+b['plan_sha256']+'.json')
    audit={'source_drift':drift,'frozen_source_count':len(plan['source_sha256']),
      'input_hash_matches':sha(ROOT/plan['input'])==plan['input_sha256'],
      'plan_hash_matches':sha(planfile)==b['plan_sha256'],
      'claim_exists':claim.exists(),'claim_sha256':sha(claim),
      'approval_sha256':sha(ROOT/'research/chapter3_g0_real_entry/results/public_start_execution_precheck01/user_approval.json'),
      'old_batch_unchanged':sha(ROOT/'research/chapter3_g0_real_entry/results/real_entry01/batch.json')==old['original_batch_sha256'],
      'old_claim_unchanged':sha(Path(old['claim_path']))==old['claim_sha256'],
      'raw_batch_sha256':sha(RUN/'batch.json'),'new_calls_in_this_analysis':0,
      'new_integrations_in_this_analysis':0,'recovery_replayed':False}
    audit['passed']=(not drift and all(audit[k] for k in ('input_hash_matches','plan_hash_matches','claim_exists','old_batch_unchanged','old_claim_unchanged')))
    save(HERE/'integrity_audit.json',audit)
    save(HERE/'raw_files_sha256.json',{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(RUN.rglob('*')) if p.is_file()})
    assert audit['passed']
    print(json.dumps({k:summary[k] for k in ['method_calls','post_calls','batch_elapsed_s','native_intlinprog_entered','final_energy_J','recovery_status','batch_stop_reason']},ensure_ascii=False))

if __name__=='__main__':main()
