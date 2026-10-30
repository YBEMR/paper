"""G0 method/post handlers. No scientific execution is enabled by import."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time
from fractions import Fraction

from .gating import require_permit, require_simulation_dependencies, require_role
from .backend import execute_wiring
from ..chapter3_g0.budget import G0Budget, ScopeExhausted
from ..chapter3_g0.contract import canonical_hash, validate_inputs
from .execution_costs import PUBLIC


def load_common(path,expected_sha256):
    data=Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_sha256:
        raise ValueError('FROZEN_COMMON_INPUT_CHANGED')
    document=json.loads(data)
    if set(document)-{'schema','config','instance','provenance'} or 'candidate' in document:
        raise ValueError('COMMON_INPUT_MUST_NOT_CONTAIN_A_FREE_INITIAL_SOLUTION')
    config,instance=document['config'],document['instance']
    validate_inputs(config,instance)
    return config,instance


def normalize(raw,*,input_sha256,method_seconds,process_seconds):
    """Preserve complete archived SAFE independently of the method stop state."""
    final=raw.get('final')
    retained=False
    if isinstance(final,dict):
        aggregate=final.get('aggregate') or {}
        formed=final.get('completed_at_elapsed_s')
        try:
            same_upper=(Fraction(aggregate.get('safe_upper_bound_J'))==Fraction(final.get('U_J')))
        except (ValueError,TypeError,ZeroDivisionError):
            same_upper=False
        retained=(aggregate.get('state')=='SAFE' and aggregate.get('rankable_energy') is True
            and isinstance(final.get('candidate'),dict)
            and aggregate.get('safe_candidate')==final.get('candidate')
            and same_upper
            and aggregate.get('identity',{}).get('candidate_sha256')==canonical_hash(final.get('candidate'))
            and aggregate.get('identity',{}).get('full_input_sha256')==raw.get('input_sha256')
            and type(formed) in (int,float) and math.isfinite(formed) and 0<=formed<method_seconds)
    failure=raw.get('failure')
    if final is not None and not retained:
        state='TECHNICAL_FAILURE'
    elif failure:
        state='NUMERICAL_ANOMALY' if (failure.get('error_type')=='ArithmeticError' or
            'NUMERICAL' in failure.get('message','')) else 'CLEANUP_FAILURE' if failure.get('kind')=='CLEANUP_FAILURE' else 'TECHNICAL_FAILURE'
    elif 'CUTOFF' in str(raw.get('reason','')) or any(
            r.get('status','').endswith('CUTOFF') for records in raw.get('stages',{}).values() for r in records):
        state='NORMAL_TIME_LIMIT'
    elif raw.get('reason')=='CONSTRUCTOR_UNSUPPORTED':
        state='CONSTRUCTOR_UNSUPPORTED'
    elif final is None:
        state='NO_SAFE_UNRESOLVED'
    else:
        state='NORMAL_COMPLETION'
    local=[r for records in raw.get('stages',{}).values() for r in records]
    return dict(schema='g0-wired-worker-receipt-v1',evidence_kind=raw.get('evidence_kind','UNKNOWN'),
        execution_organization=raw.get('execution_organization','legacy_slot_startup_v1'),
        execution_state=state,input_sha256=input_sha256,full_input_sha256=raw.get('input_sha256'),
        safe_retained=retained,safe_candidate=deepcopy(final['candidate']) if retained else None,
        safe_upper_bound_J=final['U_J'] if retained else None,full_safe_aggregate=deepcopy(final['aggregate']) if retained else None,
        weighted_energy_J=deepcopy(final.get('weighted_energy_J')) if retained else None,
        first_legal_s=raw.get('first_legal_s'),first_safe_s=raw.get('first_safe_s'),
        method_elapsed_s=raw.get('stopped_s'),process_elapsed_s=process_seconds,
        execution_timing=deepcopy(raw.get('execution_timing')),
        method_elapsed_scope='coordinator body before final close; process_elapsed includes close/serialization',
        matlab_startup_s=raw.get('backend_timings',{}).get('matlab_startup_seconds'),
        phase_native_entries={str(p):sum(r.get('solver_entered',False) for r in raw.get('stages',{}).get(str(p),[])) for p in (1,2)},
        local_path_entered=any(r.get('solver_entered') for r in local),
        post_eligible=retained and state in ('NORMAL_COMPLETION','NORMAL_TIME_LIMIT'),
        raw=deepcopy(raw),performance_ranking_claim=False)


def execute_method(common_file,expected_sha256,workdir,*,permit,dependencies=None,seconds=300,clock=time.monotonic,started_at=None,
                   execution_organization=PUBLIC):
    budget=G0Budget(seconds,clock=clock,started_at=started_at)
    require_permit(permit)
    require_role(permit,'method')
    if require_permit(permit)=='REAL' and execution_organization!=permit.context['plan'].get('execution_organization'):
        raise PermissionError('METHOD_EXECUTION_ORGANIZATION_DRIFT')
    started=budget.start
    try:
        result=execute_wiring(lambda:load_common(common_file,expected_sha256),workdir,
            permit=permit,dependencies=dependencies,seconds=seconds,clock=clock,budget=budget,
            execution_organization=execution_organization)
    except ScopeExhausted as e:
        result={'evidence_kind':require_permit(permit),'reason':e.kind.upper()+'_CUTOFF',
                'stopped_s':budget.elapsed,'stages':{},'final':None,'failure':None}
    return normalize(result,input_sha256=expected_sha256,method_seconds=seconds,
                     process_seconds=clock()-started)


def execute_post(common_file,expected_sha256,candidate,*,permit,dependencies=None,seconds=60,clock=time.monotonic,started_at=None):
    budget=G0Budget(seconds,clock=clock,started_at=started_at)
    kind=require_simulation_dependencies(permit,dependencies)
    require_role(permit,'post')
    budget.check()
    if kind == 'REAL':
        from .model_backend import _legacy_module
        dependencies={'evaluate_candidate':_legacy_module('thermal').evaluate_candidate}
    out={'schema':'g0-independent-post-receipt-v1','evidence_kind':kind,
         'state':'UNRESOLVED','reason':None,'evaluation':None,'candidate':deepcopy(candidate)}
    if not isinstance(dependencies,dict) or not callable(dependencies.get('evaluate_candidate')):
        raise PermissionError('EXPLICIT_SIMULATED_POST_PROVIDER_REQUIRED')
    try:
        config,instance=load_common(common_file,expected_sha256)
        budget.check()
        supplied=deepcopy(candidate)
        expected={'input_sha256':canonical_hash(instance),'candidate_sha256':canonical_hash(supplied)}
        # evaluate_candidate's original receipt does not itself contain the
        # MILP-view identity field. This post handler owns a separate binding;
        # it never fabricates/edits fields in the untouched physical receipt.
        out['identity']=deepcopy(expected)
        evaluation=dependencies['evaluate_candidate'](instance,supplied,config['accuracy_targets'],budget)
        out['evaluation']=deepcopy(evaluation)
        if (canonical_hash(instance)!=expected['input_sha256'] or canonical_hash(supplied)!=expected['candidate_sha256']
                or evaluation.get('evidence_identity',expected)!=expected):
            raise ValueError('POST_INPUT_OR_CANDIDATE_IDENTITY_MISMATCH')
        out['state']=evaluation.get('state','UNRESOLVED')
        if out['state']=='SAFE':
            formed=evaluation.get('completed_at_elapsed_s')
            physical=evaluation.get('scenes',{})
            ids={s['id'] for s in instance['scenarios']}
            from fractions import Fraction as F
            if (evaluation.get('rankable_energy') is not True or not budget.accept_formed(formed)
                    or set(physical)!=ids or any(r.get('state')!='SAFE' or r.get('complete') is not True
                    or F(r.get('covered_until_s','-1'))!=F(instance['window_ms'])/1000 for r in physical.values())):
                out.update(state='UNRESOLVED',reason='POST_SAFE_INCOMPLETE_OR_LATE')
    except ScopeExhausted as error:
        out.update(state='UNRESOLVED',reason=error.kind.upper()+'_CUTOFF')
    except Exception as error:
        out.update(state='TECHNICAL_FAILURE',reason=str(error),error_type=type(error).__name__)
    if out['state']=='SAFE' and budget.elapsed>=seconds:
        out.update(state='UNRESOLVED',reason='POST_PROCESS_DEADLINE')
    out['process_elapsed_s']=budget.elapsed
    return out
