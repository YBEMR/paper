"""Real backend wiring, dormant until the separate user execution gate opens.
No physical function executes at import. B0 tests inject mock bindings only.
"""
from dataclasses import dataclass
from functools import partial
from copy import deepcopy
from h02_pair_preflight.common import require,sha,encoded,byte_sha,raw_candidate,candidate_identity,timely,BASE_SHA,POLICY
from h02_pair_preflight.paired_heuristic_entry import validate_packet
from h02_pair_preflight.receipts import safe_receipt,thermal_witness,technical_issues
from .io_contract import require_research_authorization,atomic_json,policy_files
from .budget import anchored_budget_class,RootBudgetExpired
from .exports import verify_final_export
from .classification import classify_invalid_schedule

@dataclass
class CoreBindings:
    runner_module: object
    search: object
    evaluator: object
    validator: object
    budget_base: type
    exhausted: type
    kind: str="MOCK_ONLY"

def resolve_real_bindings(gate,policy):
    require_research_authorization(gate,policy)  # BEFORE importing core definitions.
    import heuristic_runner
    import heft_method
    import schedules
    import thermal
    import timing
    return CoreBindings(heuristic_runner,partial(heft_method.run_heft,allow_auto_low=True),thermal.evaluate_candidate,schedules.validate_schedule,timing.MethodBudget,thermal.Exhausted,kind="REAL_CORE")

def observing_recorder_class(base,on_snapshot):
    class ObservingRecorder(base):
        def assess(self,candidate,source):
            try: return super().assess(candidate,source)
            finally:
                # Observe only. Never repair, evaluate, modify best/cache or add SAFE.
                on_snapshot(deepcopy({'best':self.best,'evaluations':self.evaluations,'events':self.events,'violations':self.violations,'first_safe_at_s':self.first_safe_s}))
    return ObservingRecorder

def planner_chain(bindings,packet,root,workdir):
    """Only worker calls with real bindings; mock tests exercise this same wiring."""
    if bindings.kind=='REAL_CORE':
        policy,gate=policy_files(); require_research_authorization(gate,policy)
    require(bindings.kind in ('REAL_CORE','MOCK_ONLY'),'UNRECOGNIZED_BACKEND_KIND')
    require(root.limit_s==120,'PLAN_ROOT_NOT_120'); root.check(); validate_packet(packet)
    before=sha(packet); module=bindings.runner_module
    original_budget,original_recorder=module.MethodBudget,module.CandidateRecorder
    def snapshot(value):
        atomic_json(workdir.parent/'accepted_checkpoint.json',{'kind':'RECORDER_OBSERVATION_ONLY','packet_sha256':before,'root_origin':root.origin,'root_limit_s':120,'archived_at_elapsed_s':root.elapsed,**value})
    module.MethodBudget=anchored_budget_class(bindings.budget_base,root,root.clock)
    module.CandidateRecorder=observing_recorder_class(original_recorder,snapshot)
    # Closure captures only public H or masked R bytes. No truth/controller/audit state.
    public_bytes=encoded(packet['planner'])
    def loader(budget):
        import json
        budget.check(); value=json.loads(public_bytes); budget.check()
        return value['config'],value['instance']
    try:
        result=module.execute_heuristic(loader,workdir,method='heft',seconds=120,seed=None,clock=root.clock,evaluator=bindings.evaluator,search=bindings.search,allow_auto_low=True)
    finally:
        module.MethodBudget, module.CandidateRecorder=original_budget,original_recorder
    require(sha(packet)==before,'PUBLIC_PACKET_MUTATION')
    checked=verify_final_export(packet,result)
    return {'raw_method_result':result,'checked':checked,'root':root.summary(),'checkpoint_is_not_final_export':True}

def verify_audit_identity(truth,token):
    c,i=truth['config'],truth['instance']
    require(token['source_commit_sha']==BASE_SHA and token['truth_H_sha256']==sha(i) and token['truth_H_config_sha256']==sha(c),'TRUTH_H_SOURCE_IDENTITY')
    require(token['problem_id']==i['id'] and token['policy_id']==POLICY and token['accuracy_sha256']==sha(c['accuracy_targets']),'AUDIT_CONTEXT_IDENTITY')
    require(token.get('p1_p2_static_passed') is True and token.get('planning_top_state')=='SAFE','PLAN_NOT_FROZEN_SAFE')
    raw=token['candidate_json'].encode('utf-8'); require(byte_sha(raw)==token['candidate_raw_sha256'],'CANDIDATE_RAW_HASH')
    candidate=raw_candidate(raw); identity=candidate_identity(i,candidate)
    require(identity['candidate_semantic_sha256']==token['candidate_semantic_sha256'],'CANDIDATE_SEMANTIC_HASH')
    require(timely(token['plan_formed_at_elapsed_s'],120),'PLAN_NOT_TIMELY')
    return c,i,candidate

def audit_chain(bindings,truth,token,root,on_receipt=lambda r:None):
    """Independent post root starts before worker reads truth/candidate files.
    Controller has already consumed the unique audit token before process spawn.
    """
    if bindings.kind=='REAL_CORE':
        policy,gate=policy_files(); require_research_authorization(gate,policy)
    require(bindings.kind in ('REAL_CORE','MOCK_ONLY'),'UNRECOGNIZED_BACKEND_KIND')
    require(root.limit_s==60,'AUDIT_ROOT_NOT_60')
    out={'evidence_kind':bindings.kind,'usable_as_research_evidence':bindings.kind=='REAL_CORE','audit_status':'TRUE_H_UNRESOLVED','real_safe':False,'stop_required':False,'audit_consumed':True}
    budget=anchored_budget_class(bindings.budget_base,root,root.clock)(seconds=60,clock=root.clock)
    try:
        budget.check(); c,i,candidate=verify_audit_identity(truth,token)
        before=(sha(i),sha(candidate),sha(c['accuracy_targets']))
        vi,vc=deepcopy(i),deepcopy(candidate); legal=bindings.validator(vi,vc)
        require((sha(vi),sha(vc))==before[:2],'VALIDATOR_MUTATED_INPUT')
        out['legality']=deepcopy(legal)  # archive existing raw receipt even if the next check expires
        budget.check()
        if legal.get('state')!='SCHEDULE_VALID_THERMAL_UNCHECKED':
            classified=classify_invalid_schedule(i,candidate,legal); budget.check()
            out.update(classified,legality=legal,violation_formed_at_elapsed_s=root.elapsed)
        else:
            ei,ec,ea=deepcopy(i),deepcopy(candidate),deepcopy(c['accuracy_targets'])
            receipt=bindings.evaluator(ei,ec,ea,budget)
            require((sha(ei),sha(ec),sha(ea))==before,'EVALUATOR_MUTATED_INPUT')
            out['raw_receipt']=deepcopy(receipt); state=receipt.get('state'); issues=technical_issues(receipt)
            if state=='SAFE':
                if timely(receipt.get('completed_at_elapsed_s'),60):
                    energy=safe_receipt(i,candidate,receipt,c['accuracy_targets'],60)
                    out.update(audit_status='TRUE_H_SAFE',real_safe=bindings.kind=='REAL_CORE',certified_energy=energy)
                else: out['reason']='LATE_OR_INVALID_SAFE_TIMESTAMP'
            elif state=='THERMAL_VIOLATION':
                require(receipt.get('problem_id')==i['id'] and receipt.get('evidence_identity')=={'input_sha256':sha(i),'candidate_sha256':sha(candidate)},'VIOLATION_IDENTITY')
                witnesses=thermal_witness(i,receipt,60)
                out.update(audit_status='TRUE_H_THERMAL_VIOLATION' if witnesses else 'TRUE_H_UNRESOLVED',violations=deepcopy(witnesses))
            elif state=='INVALID_SCHEDULE':
                # The evaluator recomputes legality too; apply the SAME strict classifier.
                classified=classify_invalid_schedule(i,candidate,receipt.get('legality',{})); budget.check()
                out.update(classified)
            elif state=='UNRESOLVED' and not issues: out['reason']=receipt.get('reason')
            else: out.update(audit_status='INPUT_OR_INTERFACE_ERROR',reason=receipt.get('reason'))
            if issues: out.update(technical_failure=True,technical_details=issues,stop_required=True)
        if out['audit_status'] in ('TRUE_H_INVALID','TRUE_H_THERMAL_VIOLATION') and token['view']=='R':
            out.update(anomaly='MONOTONICITY_CONTRACT_ANOMALY',stop_required=True)
        if out['audit_status']=='INPUT_OR_INTERFACE_ERROR': out['stop_required']=True
        on_receipt(deepcopy(out))  # archive only; no planner callback exists.
    except (bindings.exhausted,RootBudgetExpired): out.setdefault('reason','AUDIT_ROOT_EXHAUSTED')
    except Exception as error: out.update(audit_status='INPUT_OR_INTERFACE_ERROR',reason=type(error).__name__+':'+str(error),stop_required=True)
    out['root']=root.summary()
    return out
