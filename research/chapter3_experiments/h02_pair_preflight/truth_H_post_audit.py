"""One-use, mock-only H audit. No repairs and no feedback transport to planner."""
from dataclasses import dataclass
from unittest.mock import Mock
class MockBudgetExpired(RuntimeError):
    """Mock deadline; never repurposed as a technical error or new SAFE."""

from .common import BASE_SHA,POLICY,require,copy,sha,byte_sha,raw_candidate,candidate_identity,timely,ContractError
from .receipts import safe_receipt,thermal_witness,TECHNICAL,technical_issues

@dataclass
class MockAuditBackend:
    validator: Mock
    evaluator: Mock
    budget_factory: Mock
    kind: str='MOCK_ONLY'
    def check(self): require(self.kind=='MOCK_ONLY' and all(isinstance(f,Mock) for f in (self.validator,self.evaluator,self.budget_factory)),'FORMAL_AUDIT_NOT_AUTHORIZED')

def truth_H_post_audit(token,truth,binding,backend,registry):
    backend.check(); out=dict(evidence_kind='MOCK_ONLY',usable_as_research_evidence=False,audit_status='TRUE_H_UNRESOLVED',real_safe=False,stop_required=False)
    if token is None: return dict(out,reason='NO_PLAN_CANDIDATE',audit_consumed=False)
    try:
        budget=backend.budget_factory(seconds=60)  # Starts before hashing/decoding/validation.
        key=registry.verify(token); registry.audit_consumed.add(key)
        budget.check(); c,i=truth['config'],truth['instance']
        require(binding=={k:token[k] for k in ('source_commit_sha','problem_id','truth_H_sha256','policy_id','accuracy_sha256')},'AUDIT_ENVELOPE_IDENTITY')
        require(token['source_commit_sha']==BASE_SHA and token['problem_id']==i['id'] and token['truth_H_sha256']==sha(i) and token['policy_id']==POLICY and token['accuracy_sha256']==sha(c['accuracy_targets']),'TRUTH_H_IDENTITY')
        require(sha(c)==token['truth_H_config_sha256'],'TRUTH_CONFIG_IDENTITY')
        raw=token['candidate_json'].encode('utf-8'); require(byte_sha(raw)==token['candidate_raw_sha256'],'CANDIDATE_RAW_HASH')
        candidate=raw_candidate(raw); identity=candidate_identity(i,candidate); require(identity['candidate_semantic_sha256']==token['candidate_semantic_sha256'],'CANDIDATE_SEMANTIC_HASH')
        require(timely(token['plan_formed_at_elapsed_s'],120),'PLAN_SAFE_NOT_TIMELY')
        budget.check()  # One root budget; no reset at validator/evaluator boundary.
        vi,vc=copy(i),copy(candidate)
        legal=backend.validator(vi,vc)
        require(sha(vi)==sha(i) and sha(vc)==sha(candidate),'VALIDATOR_MUTATED_INPUT')
        budget.check()
        if legal.get('state')!='SCHEDULE_VALID_THERMAL_UNCHECKED':
            status='TRUE_H_INVALID' if legal.get('state')=='INVALID_SCHEDULE' else 'INPUT_OR_INTERFACE_ERROR'
            out.update(audit_status=status,reason=legal.get('reason'),legality=legal)
        else:
            ei,ec,ea=copy(i),copy(candidate),copy(c['accuracy_targets'])
            receipt=backend.evaluator(ei,ec,ea,budget)
            require(sha(ei)==sha(i) and sha(ec)==sha(candidate) and sha(ea)==sha(c['accuracy_targets']),'EVALUATOR_MUTATED_INPUT')
            require(sha(i)==token['truth_H_sha256'] and sha(candidate)==identity['candidate_raw_sha256'],'AUDIT_MUTATED_INPUT')
            out['raw_receipt']=copy(receipt); state=receipt.get('state'); issues=technical_issues(receipt)
            if state=='SAFE':
                if not timely(receipt.get('completed_at_elapsed_s'),60): out.update(reason='LATE_OR_INVALID_SAFE_TIMESTAMP')
                else:
                    energy=safe_receipt(i,candidate,receipt,c['accuracy_targets'],60); out.update(audit_status='TRUE_H_SAFE',certified_mock_energy=energy)
            elif state=='THERMAL_VIOLATION':
                require(receipt.get('problem_id')==i['id'] and receipt.get('evidence_identity')=={'input_sha256':sha(i),'candidate_sha256':sha(candidate)},'VIOLATION_INPUT_IDENTITY')
                witnesses=thermal_witness(i,receipt,60)
                out.update(audit_status='TRUE_H_THERMAL_VIOLATION' if witnesses else 'TRUE_H_UNRESOLVED',violations=witnesses,reason=receipt.get('reason'))
            elif state=='UNRESOLVED' and not issues: out['reason']=receipt.get('reason')
            else: out.update(audit_status='INPUT_OR_INTERFACE_ERROR',reason=receipt.get('reason'))
            if issues:
                out.update(technical_failure=True,technical_details=issues,stop_required=True)
                registry.stop('AUDIT_TECHNICAL_FAILURE')
        if out['audit_status'] in ('TRUE_H_INVALID','TRUE_H_THERMAL_VIOLATION') and token['view']=='R' and token['p1_p2_static_passed']:
            out.update(anomaly='MONOTONICITY_CONTRACT_ANOMALY',stop_required=True); registry.stop(out['anomaly'])
        if out['audit_status']=='INPUT_OR_INTERFACE_ERROR': out['stop_required']=True; registry.stop(out.get('reason','AUDIT_INTERFACE_ERROR'))
        out.update(audit_consumed=True,returned_at_elapsed_s=budget.elapsed)
        return out
    except MockBudgetExpired as error:
        return dict(out,reason='AUDIT_BUDGET_EXHAUSTED',audit_consumed=token.get('token_id') in registry.audit_consumed)
    except Exception as error:

        registry.stop(str(error)); return dict(out,audit_status='INPUT_OR_INTERFACE_ERROR',reason=type(error).__name__+':'+str(error),stop_required=True,audit_consumed=token.get('token_id') in registry.audit_consumed)
