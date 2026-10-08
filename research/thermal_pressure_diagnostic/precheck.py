"""One-shot runner/summary tests with synthetic receipts. No research runs."""
from copy import deepcopy
from pathlib import Path
from contextlib import nullcontext
import run as r
a=r.a


def run(output):
    checks=[]
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)))
    ts=r.tasks();ck('28_calls',len(ts)==28)
    ck('locals_before_full_before_probes',[t['kind'] for t in ts[:16]].count('A_prefix')==8 and all(t['kind']=='full' for t in ts[16:20]) and all(t['kind']=='probe' for t in ts[20:]))
    ck('8_single_mode_probes_only',sum(t['kind']=='probe' for t in ts)==8 and all(t['mode'] in ['A','B'] for t in ts if t['kind']=='probe'))
    safe=dict(status='certified_candidate',sustained_safety={'status':'sustained_safe'},certified_candidate_energy={'status':'available','energy_J':['1','1']})
    bad=dict(status='violation',known_violations=[{'node':'NPU','lower_temperature_C':'81','witness_time_s':'0.1','limit_C':'80'}])
    ck('late_safe_not_U',r.late_guard(safe,'full',21)['certified_candidate_energy']['status']=='unavailable')
    ck('late_bad_retained',bool(r.late_guard(bad,'probe',21)['committed_evidence']))
    ck('certificate_probe_conflict',r.classify(safe,[bad])['status']=='evidence_conflict')
    ck('failed_certificate_not_exclusion',r.classify({'status':'unresolved'},[])['status']=='unresolved')
    ck('real_probe_exclusion',r.classify({'status':'unresolved'},[bad])['status']=='excluded_by_counterexample')
    records=[]
    for t in ts:
        if t['kind']=='full':v=deepcopy(safe) if t['a']== 'a_c' and t['b']=='b_c' else dict(status='unresolved')
        elif t['kind']=='probe':v=dict(status='finite_safe')
        else:v=dict(status='safe_reference',kind=t['kind'],binding={'fixture':'same'},score_J=['1','1'])
        records.append(dict(task=t,result=v))
    summary=r.summarize(records)
    ck('unknown_not_four_point_optimum',summary['four_point_optimality']=='unresolved' and len(summary['unresolved_candidates'])==3)
    ck('local_ties_preserved',len(summary['local_retained'])==4)
    ck('refill_first_safe',summary['simple_refill_first_certified']=='a_cb_c')
    missing=deepcopy(records);missing[0]['result']={'status':'unresolved'}
    ck('missing_local_no_order',r.summarize(missing)['local_choice_status']=='unresolved')
    excluded=deepcopy(records)
    for item in excluded:
        t=item['task']
        if t['kind']=='probe' and (t['a'],t['b'])!=('a_c','b_c'):item['result']=deepcopy(bad)
    ck('all_other_excluded_unique',r.summarize(excluded)['four_point_optimality']=='strict_unique')
    tied=deepcopy(records)
    for item in tied:
        if item['task']['kind']=='full':item['result']=deepcopy(safe)
    ck('safe_equal_energy_retained',len(r.summarize(tied)['safe_retained'])==4)
    # Full evidence flow: a late conflict must never become an exclusion.
    conflict=deepcopy(safe);conflict.update(status='evidence_conflict',known_violations=deepcopy(bad['known_violations']))
    guarded=r.late_guard(conflict,'full',21)
    ck('late_conflict_kept',guarded['status']=='evidence_conflict' and guarded['certified_candidate_energy']['status']=='unavailable')
    ck('late_conflict_classified',r.classify(guarded,[])['status']=='evidence_conflict')
    delayed=dict(status='unresolved',binding={'fixture':'committed'},safety_receipt=dict(kind='sustained_safety',binding={'fixture':'committed'},result={'status':'sustained_safe'}))
    late_receipt=r.late_guard(delayed,'full',21)
    ck('late_receipt_identity_kept',late_receipt['safety_receipt']==delayed['safety_receipt'] and late_receipt['source_binding']==delayed['binding'])
    ck('late_receipt_probe_conflict',r.classify(late_receipt,[bad])['status']=='evidence_conflict')
    for name,full,probe in [('conflict',guarded,dict(status='finite_safe')),('later_probe',late_receipt,bad)]:
        altered=deepcopy(excluded)
        for item in altered:
            t=item['task']
            if (t['a'],t['b'])!=('a_n','b_n'):continue
            if t['kind']=='full':item['result']=deepcopy(full)
            elif t['kind']=='probe':item['result']=deepcopy(probe)
        ss=r.summarize(altered)
        ck(name+'_summary_unresolved',ss['rows']['a_nb_n']['status']=='evidence_conflict' and 'a_nb_n' in ss['unresolved_candidates'] and ss['four_point_optimality']=='unresolved')
    # Isolated fake state and directory; never claims the real diagnostic.
    with nullcontext(output/'gate_fixture') as root:
        root.mkdir();folder=root/'run';state_path=root/'state.json';state={'phase':'ready','formal_run_count':0}
        a.old.write(state_path,state)
        r.claim(folder,state_path,state)
        ck('claim_before_execution',a.old.read(state_path)['formal_run_count']==1)
        state.update(phase='results_awaiting_review',completed_calls=28)
        r.save_state(state_path,state)
        ck('existing_state_final_update',a.old.read(state_path)==state and not state_path.with_name('state.json.tmp').exists())
        state.update(phase='failed_no_automatic_retry',completed_calls=4)
        r.save_state(state_path,state)
        ck('existing_state_failure_update',a.old.read(state_path)==state and state['formal_run_count']==1)
        try:r.claim(folder,state_path,state)
        except FileExistsError:ck('duplicate_claim_rejected',True)
        else:ck('duplicate_claim_rejected',False)
        gate=dict(passed=True,hashes=r.identities())
        review=root/'review.md';review.write_text('synthetic gate only')
        ready=dict(hashes=r.identities(),review_passed=True,review_path=str(review),review_sha256=a.cp.sha(review))
        r.check_gate(gate,ready,{'phase':'ready','formal_run_count':0});ck('matching_gate',True)
        for name,gg,rr,ss in [
            ('old_hash',dict(gate,hashes={}),ready,{'phase':'ready','formal_run_count':0}),
            ('unreviewed',gate,dict(ready,review_passed=False),{'phase':'ready','formal_run_count':0}),
            ('already_run',gate,ready,{'phase':'running','formal_run_count':1})]:
            try:r.check_gate(gg,rr,ss)
            except ValueError:ck(name+'_blocked',True)
            else:ck(name+'_blocked',False)
    return dict(passed=all(v['passed'] for v in checks),checks=checks,hashes=r.identities(),scope='synthetic runner checks; no thermal evaluations')


if __name__=='__main__':
    folder=r.HERE/'precheck04';folder.mkdir(exist_ok=False)
    out=run(folder);a.old.write(folder/'result.json',out)
    print(sum(c['passed'] for c in out['checks']),len(out['checks']))
    raise SystemExit(0 if out['passed'] else 1)
