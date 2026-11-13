"""Recover the fixed original slot1 export, audit once, then run slots2--4."""
import argparse
from pathlib import Path
import sys

from h02_pair_b0.io_contract import (load_json, atomic_json, policy_files,
                                   require_research_authorization)
from h02_pair_b0.bundle import build_bundle, verify_runtime_freeze
from h02_pair_b0.budget import RootClock, RootBudgetExpired
from h02_pair_b0.exports import verify_final_export
from h02_pair_b0.controller import (CallLedger, claim_authorization_once,
                                   frozen_candidate, supervise, prepare_public_slot)
from h02_pair_preflight.common import require, sha

CORE = Path(__file__).resolve().parent.parent
PRE = CORE/'results/response_information_resume_precheck01'
OLD = CORE/'results/response_information_execution01'
OUT = CORE/'results/response_information_resume01'


def check_prior(declaration):
    """Only archived bytes and hashes; no scientific evaluator."""
    import hashlib
    for relative, wanted in declaration['prior_sha256'].items():
        path=CORE.parent.parent/relative
        require(hashlib.sha256(path.read_bytes()).hexdigest()==wanted,
                'OLD_EVIDENCE_DRIFT:'+relative)
    original=load_json(OLD/'terminal.json')
    require(original.get('stopped') is True and len(original['slots'])==1,
            'PRIOR_PREFIX_NOT_ONE_STOPPED_SLOT')
    require(len(list((OLD/'ledger').glob('slot_*.claim.json')))==1
            and not list((OLD/'ledger').glob('audit_*.claim.json')),
            'PRIOR_CALLS_DRIFT')


def audit_one(slot, callroot, private, token, truth, root, ledger, policy):
    """The unique 60s root also charges recovery reads and export checks."""
    root.check()
    claim=ledger.claim('audit_'+str(slot['ordinal']),
        {'token_sha256':sha(token),'budget_s':60,'root_origin':root.origin})
    atomic_json(private/'frozen_candidate.json',token)
    root.check()
    auditdir=callroot/'H_audit_private'; auditdir.mkdir()
    bundle=auditdir/'code'; info=build_bundle(bundle); root.check()
    job={'kind':'audit','ordinal':slot['ordinal'],'launch_claim_sha256':sha(claim),
         'root_origin':root.origin,'limit_s':60,'truth':truth,'token':token,
         'audit_claim_sha256':sha(claim)}
    process=supervise(job,info,bundle,auditdir,policy)
    require(not process['watchdog_killed'] and process['returncode']==0,
            'AUDIT_PROCESS_FAILURE_OR_HARD_CUTOFF')
    returned=load_json(auditdir/'worker_return.json')
    require(returned['job_sha256']==sha(job),'AUDIT_RETURN_IDENTITY')
    return returned['payload']


def recover_one(declaration, ledger, policy):
    # Start before reading sealed H, original job/result or any recovery hash.
    root=RootClock(60)
    check_prior(declaration); root.check()
    slot=policy['slots'][0]
    require(slot=={'ordinal':1,'problem_id':'base__R1','view':'H'},'RECOVERY_SLOT')
    original=OLD/'slot_1'
    job=load_json(original/'planner_public/job.json')
    raw=load_json(original/'planner_public/method/result.json')
    truth=load_json(original/'controller_private/truth_H.json')
    contract=load_json(original/'controller_private/static_contract.json')
    checked=verify_final_export(job['packet'],raw); root.check()
    require(not checked['technical_details'] and checked['best'] is not None,
            'RECOVERED_EXPORT_INVALID')
    require(raw['reason']=='DECLARED_SEARCH_COMPLETED','RECOVERED_CORE_NOT_COMPLETE')
    token=frozen_candidate(job['packet'],raw,truth,contract,
                           sha(verify_runtime_freeze()))
    require(token['candidate_semantic_sha256']==declaration['recovered_candidate_semantic_sha256'],
            'RECOVERED_BEST_REPLACED')
    callroot=OUT/'slot_1'; callroot.mkdir()
    private=callroot/'controller_private'; private.mkdir()
    atomic_json(private/'recovery.json',{
        'original_method_result':str(original/'planner_public/method/result.json'),
        'original_result_sha256':declaration['prior_sha256'][(original/'planner_public/method/result.json').relative_to(CORE.parent.parent).as_posix()],
        'original_planning_120s_still_consumed':True,'new_planner_calls':0,
        'new_search_or_thermal_evaluation':False,'candidate_replaced':False,
        'replayed_export_at_post_elapsed_s':root.elapsed})
    audited=audit_one(slot,callroot,private,token,truth,root,ledger,policy)
    return {'slot':slot,'plan_status':'RECOVERED_ORIGINAL_PLAN_SAFE',
            'planning_source':'K177 frozen raw; no replan','post':audited}


def run(destination):
    policy,gate=policy_files(); require_research_authorization(gate,policy)
    verify_runtime_freeze()
    declaration=load_json(PRE/'execution_declaration.json')
    check_prior(declaration)
    require(Path(destination).resolve()==OUT.resolve() and not OUT.exists(),
            'FRESH_FIXED_RESUME_DIRECTORY_REQUIRED')
    claim=claim_authorization_once(gate,OUT)
    OUT.mkdir(); atomic_json(OUT/'authorization_claim.json',claim)
    ledger=CallLedger(OUT/'ledger'); outputs=[]
    try:
        recovered=recover_one(declaration,ledger,policy); outputs.append(recovered)
        if recovered['post'].get('stop_required'):
            ledger.stop('RECOVERED_AUDIT_STOP')
        # Never creates slot_1 planner claim; original consumed root is not reset.
        for slot in policy['slots'][1:]:
            if ledger.stopped: break
            root=RootClock(120)
            callroot=OUT/('slot_'+str(slot['ordinal'])); callroot.mkdir()
            plan=ledger.claim('slot_'+str(slot['ordinal']),
                {'slot':slot,'budget_s':120,'root_origin':root.origin})
            packet,truth,contract,private=prepare_public_slot(root,slot,callroot)
            planner=callroot/'planner_public'; planner.mkdir()
            bundle=planner/'code'; info=build_bundle(bundle); root.check()
            job={'kind':'planner','root_origin':root.origin,'limit_s':120,
                 'packet':packet,'ordinal':slot['ordinal'],
                 'launch_claim_sha256':sha(plan)}
            process=supervise(job,info,bundle,planner,policy)
            require(not process['watchdog_killed'] and process['returncode']==0,
                    'PLANNER_PROCESS_FAILURE_OR_HARD_CUTOFF')
            returned=load_json(planner/'worker_return.json')
            require(returned['job_sha256']==sha(job),'PLANNER_RETURN_IDENTITY')
            raw=returned['payload']['raw_method_result']
            checked=verify_final_export(packet,raw)
            atomic_json(private/'raw_planner_return.json',returned)
            require(not checked['technical_details'],'PLANNER_TECHNICAL_FAILURE')
            if checked['best'] is None:
                outputs.append({'slot':slot,'plan_status':
                    'PLAN_NO_SAFE' if raw.get('reason')=='DECLARED_SEARCH_COMPLETED' else 'PLAN_UNRESOLVED'})
                continue
            token=frozen_candidate(packet,raw,truth,contract,info['bundle_sha256'])
            # Same original post rules; formation and all post work share 60s.
            post=RootClock(60)
            audited=audit_one(slot,callroot,private,token,truth,post,ledger,policy)
            outputs.append({'slot':slot,'plan_status':'PLAN_SAFE','post':audited})
            if audited.get('stop_required'): ledger.stop('AUDIT_TECHNICAL_FAILURE_OR_ANOMALY')
    except Exception as error:
        ledger.stop(type(error).__name__+':'+str(error))
        outputs.append({'technical_failure':True,'reason':type(error).__name__+':'+str(error),
                        'existing_claims_and_raw_outputs_preserved':True})
    terminal={'slots':outputs,'stopped':ledger.stopped,'no_automatic_retry':True,
              'prior_plans_consumed':1,'prior_audits_consumed':0,
              'first_planner_not_rerun':True}
    atomic_json(OUT/'terminal.json',terminal)
    return terminal


if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--execute',type=Path,required=True)
    result=run(a.parse_args().execute)
    raise SystemExit(3 if result['stopped'] else 0)
