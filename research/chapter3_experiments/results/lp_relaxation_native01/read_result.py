"""Post-run static evidence analysis; never accepts late scientific output."""
from pathlib import Path
import hashlib
import json
import sys

REPO=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(REPO/'research/chapter3_experiments/lp_relaxation_native'))
import run_once as run


def main():
    d=run.admission()
    r=run.read(OUT/'method_return.json');t=run.read(OUT/'terminal.json')
    native=run.read(OUT/'matlab/response.json');request=run.read(OUT/'request.claim.json')
    guard=run.read(OUT/'matlab/options_guard.json');session=run.read(OUT/'matlab/session.json')
    run.verify_options(native['options'],request['declared_remaining_s'])
    lp=run.bind_lp()
    original,source=lp.numeric.load_original_mat(run.OLD/'method/matlab/request_000001.mat')
    sent=run.load_sent(OUT/'matlab/payload.mat');identity=lp.assert_identity(original,sent)
    elapsed=native['phase_seconds']['linprog_call']
    expected_timeout=(r['state']=='LATE_OR_TIMEOUT_UNRESOLVED'
        and native['exitflag']==0 and not native['x']
        and [e['type'] for e in r['errors']]==['PublicationTimeout']
        and r['lifecycle_complete'] and t['error'] is None)
    status='EXPECTED_TIME_LIMIT_UNRESOLVED' if expected_timeout else 'REQUIRES_REVIEW'
    hashes={}
    for folder in (OUT,OUT/'matlab'):
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name not in ('analysis.json','artifact_manifest.json'):
                hashes[p.relative_to(OUT).as_posix()]=dict(bytes=p.stat().st_size,sha256=run.sha(p))
    a=dict(scope='post-run static archival; no extra solve, heat or in-budget acceptance',
        classification=status,source=source,actual_transport_identity=identity,
        native_options_checked_post_run=True,in_budget_native_options_readback_completed=False,
        raw_method_options_match_false_means='default not completed before deadline; not an observed drift',
        native_guard_status=guard['status'],native_options=native['options'],
        native_exitflag=native['exitflag'],native_output=native['output'],native_vector_length=len(native['x']),
        native_linprog_entered=native['linprog_entered'],iterations=native['output']['iterations'],
        native_s=elapsed,native_MaxTime=native['options']['MaxTime'],
        native_stop_delay_vs_MaxTime_s=elapsed-native['options']['MaxTime'],
        method_s=r['method_elapsed_s'],method_overshoot_no_acceptance_s=r['method_elapsed_s']-300,
        startup_s=session['startup_s'],calendar_s=t['wall_s'],
        cleanup_s=r['cleanup']['cleanup_wall_seconds'],
        request_published_root_s=run.read(OUT/'request_publication.json')['root_s'],
        late_native_response=True,admitted_numeric_vector=False,
        response_status_SOLVED_means='native function returned; exitflag=0 is time limit, not optimality',
        solver_reported_infeasibility=False,new_SAFE_or_U=False,certified_lower_bound=False,
        LP_reproduces_internal_root=False,free_MILP_repaired=False,
        method_calls=t['method_calls'],native_requests=t['native_request_slots_consumed'],
        thermal_integrations=0,retries=0,resource_gate_block_before_any_launch=True,
        cleanup_complete=r['lifecycle_complete'],owned_processes_exited=t['observed_owned_processes_exited'],
        source_preserved=r['source_preserved'],artifact_hashes=hashes)
    run.write_new(OUT/'analysis.json',a)
    print({k:a[k] for k in ('classification','native_s','iterations','method_s','calendar_s',
        'native_vector_length','cleanup_complete')})


if __name__=='__main__':main()
