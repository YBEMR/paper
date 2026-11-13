"""Read only a completed, sealed D279 run. No solver, builder or thermal evaluation."""
from pathlib import Path
from fractions import Fraction
import collections,datetime,json,sys,time
ROOT=Path(__file__).resolve().parent.parent;PACKAGE=ROOT/'work/root_tail_observer_v1'
sys.path.insert(0,str(PACKAGE))
from guard import read,save,sha,verify_plan

def audit():
    started=time.monotonic()
    batchdir=ROOT/'work/root_tail_observation_execution_v1'
    batch=read(batchdir/'batch.json')
    folder=batchdir/'C_noheur_observe';r=read(folder/'receipt.json')
    checks={}
    plan=verify_plan(PACKAGE/'plan.json',ROOT,PACKAGE)
    checks['frozen_sources_unchanged']=True
    checks['one_completed_trial']=batch['scope']['completed']==['C_noheur_observe']
    checks['controller_intact']=batch.get('controller_integrity') is True
    checks['no_retry']=r['retries']==0 and batch['retries']==0
    checks['cleanup_complete']=r['cleanup'].get('complete') is True
    import psutil
    monitor=read(folder/'process_monitor.json');live=[];reused=[]
    for identity in monitor.get('observed_identities',[]):
        try:
            p=psutil.Process(identity['pid'])
            if p.create_time()==identity['create_time'] and p.is_running(): live.append(identity)
            elif p.create_time()!=identity['create_time']: reused.append(identity)
        except psutil.NoSuchProcess: pass
    checks['no_owned_identity_still_live']=not live
    checks['one_or_zero_native_entries']=r.get('actual_native_entry_events',0)<=1
    checks['maximum_two_evaluations']=r.get('physical_evaluations_attempted',0)<=2
    checks['no_model_build']=r.get('model_builds')==0
    checks['approval_identity']=read(batchdir/'approval_consumed.json')['plan_sha256']==sha(PACKAGE/'plan.json')
    snap=r.get('snapshot')
    checks['snapshot_hash']=bool(snap and sha(folder/snap['path'])==snap['sha256'])
    checks['snapshot_timely']=bool(snap and snap['completed_at_elapsed_s']<600 and r['scientific_archive_timely'])
    manifest=read(folder/'scientific_artifact_manifest.json') if (folder/'scientific_artifact_manifest.json').exists() else {}
    mismatches=[p for p,m in manifest.items() if sha(folder/p)!=m['sha256']]
    checks['archived_files_unchanged']=bool(manifest) and not mismatches
    checks['all_manifest_reads_timely']=bool(manifest) and all(m['hashed_at_elapsed_s']<600 for m in manifest.values())
    checks['manifest_hash']=bool(manifest and r.get('scientific_artifact_manifest_sha256')==sha(folder/'scientific_artifact_manifest.json'))
    checks['native_identity']=r.get('identity',{}).get('state')=='VERIFIED'
    raw=r.get('native') or {};obs=r.get('observation') or {}
    checks['native_response_before550']=obs.get('response_timely') is True
    checks['profile_fully_read_before550']=obs.get('profile_packet_timely') is True
    checks['public_profile_settings']=obs.get('profile_settings_verified') is True
    profilepath=folder/'matlab/request_000001.profile.mat'
    checks['profile_same_bytes_as_received']=profilepath.exists() and obs.get('profile_sha256')==sha(profilepath)
    old=read(ROOT/'work/mechanism_trials_execution_v1/C_noheur/native_receipt.json')
    expected=dict(old['options']);expected.update(Display='iter',MaxTime=(raw.get('options') or {}).get('MaxTime'))
    checks['search_options_match_C_noheur']=raw.get('options')==expected
    allocation=r.get('allocation') or {}
    from budget_policy import ABC_DYNAMIC
    checks['dynamic_quota_recomputed']=bool(allocation and ABC_DYNAMIC.allocate(allocation['measured_elapsed_s'])==allocation)
    native={};vector={}
    nativepath=folder/'matlab/request_000001.native.mat'
    if nativepath.exists() and checks['snapshot_timely'] and 'matlab/request_000001.native.mat' in manifest:
        import numpy as np
        from scipy.io import loadmat
        d=loadmat(nativepath,variable_names=['x','fval','exitflag','output','initialPoint'],simplify_cells=True)
        x=np.asarray(d.get('x',[]),dtype=float).reshape(-1);x0=np.asarray(d.get('initialPoint',[]),dtype=float).reshape(-1)
        saved=loadmat(ROOT/plan['saved_directory']/'matlab/request_000001.mat',variable_names=['x0'],simplify_cells=True)['x0'].reshape(-1)
        vector=dict(length=len(x),initial_length=len(x0),finite=bool(np.isfinite(x).all()),
            equals_native_initial=bool(np.array_equal(x,x0)),native_initial_equals_saved=bool(np.array_equal(x0,saved)),
            differing_coordinates=int(np.count_nonzero(x!=x0)) if x.shape==x0.shape else None,
            response_matches_raw_MAT=bool(np.array_equal(x,np.asarray(raw.get('x',[]),dtype=float).reshape(-1))))
        native=dict(exitflag=int(d['exitflag']),fval=float(d['fval']) if np.size(d['fval'])==1 else None,
            output=d['output'],warning_identifier=raw.get('solver_warning_identifier'),warning_message=raw.get('solver_warning_message'))
        checks['raw_vector_agrees_with_response']=vector['response_matches_raw_MAT']
        checks['native_initial_unchanged']=vector['native_initial_equals_saved']
    events=[]
    progresspath=folder/'progress.jsonl'
    if 'progress.jsonl' in manifest:
        events=[json.loads(line) for line in progresspath.read_text(encoding='utf-8').splitlines() if line.strip()]
    compact_events=[dict(event_number=e.get('event_number'),kind=e.get('kind'),state=e.get('state'),
        phase=e.get('values',{}).get('phase'),received_elapsed_s=e.get('received_elapsed_s'),
        request_wall_s=e.get('request_wall_seconds'),native_values=e.get('values'),vector_length=len(e.get('x',[]))) for e in events]
    profile=obs.get('profile_analysis',{});nativeobs=obs.get('native_observation',{})
    anchors=nativeobs.get('anchors',[])
    if isinstance(anchors,dict):anchors=[anchors]
    anchors={a['label']:a for a in anchors}
    ranked=[];tail=None
    if profile.get('history_complete') and profile.get('alignment')=='BOUNDED' and all(k in anchors for k in ('root','end')):
        start=anchors['root'];end=anchors['end']
        tail=dict(start_interval=[start['before_s'],start['after_s']],end_interval=[end['before_s'],end['after_s']],
            duration_interval_s=[end['before_s']-start['after_s'],end['after_s']-start['before_s']])
        totals=collections.defaultdict(lambda:[0.,0.,0])
        for s in profile['exclusive_intervals']:
            lo=max(0.,min(s['end_request_s'][0],end['before_s'])-max(s['start_request_s'][1],start['after_s']))
            hi=max(0.,min(s['end_request_s'][1],end['after_s'])-max(s['start_request_s'][0],start['before_s']))
            if hi:
                v=totals[s['function_index']];v[0]+=lo;v[1]+=hi;v[2]+=1
        functions={x['index']:x for x in profile['function_index']}
        ranked=[dict(function=functions[i],exclusive_root_tail_s=times[:2],visible_intervals=times[2]) for i,times in totals.items()]
        ranked.sort(key=lambda x:x['exclusive_root_tail_s'][0],reverse=True)
    s=obs.get('sampler',{});samples=s.get('samples',[])
    bypid=collections.defaultdict(list)
    for sample in samples:
        for p in sample['processes']:bypid[(p['pid'],p['create_time'])].append((sample['read_completed_elapsed_s'],p))
    resources=[]
    for (pid,created),rows in bypid.items():
        first,last=rows[0],rows[-1]
        resources.append(dict(pid=pid,create_time=created,samples=len(rows),first_elapsed_s=first[0],last_elapsed_s=last[0],
            user_cpu_delta_s=last[1]['cpu_user_s']-first[1]['cpu_user_s'],system_cpu_delta_s=last[1]['cpu_system_s']-first[1]['cpu_system_s'],
            maximum_observed_rss_bytes=max(p['rss_bytes'] for _,p in rows),
            io_read_delta_bytes=last[1]['io_read_bytes']-first[1]['io_read_bytes'],io_write_delta_bytes=last[1]['io_write_bytes']-first[1]['io_write_bytes']))
    initial=r.get('initial_evaluation') or {};final=r.get('returned_evaluation') or {}
    energy=dict(initial_interval_J=initial.get('weighted_energy_J'),returned_interval_J=final.get('weighted_energy_J'),
        schedule_same_as_initial=r.get('same_initial'),returned_complete_SAFE=r.get('returned_complete_SAFE'),
        new_complete_SAFE=r.get('new_complete_SAFE'),strict_energy_improvement=r.get('strict_energy_improvement'),
        scientific_success=r.get('scientific_success'),independent_optimality_proof=False)
    if initial.get('weighted_energy_J') and final.get('weighted_energy_J'):
        strict=Fraction(final['weighted_energy_J'][1])<Fraction(initial['weighted_energy_J'][0])
        checks['strict_energy_rule']=r.get('strict_energy_improvement')==bool(strict and r.get('same_initial') is False)
    out=dict(protocol='D279-post-run-readonly-audit-v1',date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        plan_sha256=sha(PACKAGE/'plan.json'),checks=checks,check_count=len(checks),all_checks_passed=all(checks.values()),
        mismatched_archive_files=mismatches,terminal_state=r['terminal_state'],native=native,vector=vector,energy=energy,
        progress=r.get('progress'),events=compact_events,observability=r.get('observability'),
        profile_summary={k:v for k,v in profile.items() if k not in ('exclusive_intervals','function_index')},
        native_observation=nativeobs,root_tail=tail,root_tail_visible_functions=ranked[:30],
        resource_summary=resources,resource_capture={k:v for k,v in s.items() if k not in ('samples','log_arrivals')},
        method_elapsed_s=r['method_elapsed_s'],total_elapsed_s=r['total_elapsed_s'],parent_total_wall_s=batch['actual_total_wall_s'],
        allocation=allocation,cleanup=r['cleanup'],scope=batch['scope'],
        independent_process_recheck=dict(observed=len(monitor.get('observed_identities',[])),still_live=live,reused_pids=reused,no_signals_sent=True),
        actual_scientific_calls=dict(MATLAB_sessions=int((folder/'matlab/session.json').exists()),
            native_entry_events=r['actual_native_entry_events'],full_builds=r['model_builds'],
            complete_evaluation_attempts=r['physical_evaluations_attempted'],standalone_LP_calls=0,retries=0),
        audit_scope='Post-run verification of already sealed records only; no new scientific evidence, LP/MILP or physical evaluation; no rescue of late evidence',
        post_run_audit_wall_s=time.monotonic()-started)
    dest=ROOT/'work/root_tail_observation_audit_v1';dest.mkdir(exist_ok=False)
    save(dest/'audit.json',out)
    print(json.dumps({k:out[k] for k in ['terminal_state','check_count','all_checks_passed','vector','energy','observability','profile_summary','root_tail','method_elapsed_s','parent_total_wall_s','actual_scientific_calls']},ensure_ascii=False,default=str))

if __name__=='__main__':audit()
