"""One fixed-instance delivery diagnostic: 600 s root, nominal 30 s reserve."""
from copy import deepcopy
from pathlib import Path
from research.chapter3_experiments import natural_full_600_entry as prior

base=prior.base
ENTRY='research/chapter3_experiments/natural_delivery_entry.py'
ADAPTER='research/chapter3_experiments/native_delivery_reserve.py'
PREPARATION=base.RESULTS/'natural_delivery_preparation01'
PREVIOUS=base.RESULTS/'natural_full_600_preparation01/plan.json'
POLICY={'profile':'native_delivery_reserve30_v1','method_root_s':600,'reserve_deduction_s':30,
        'meaning':'Native duration cap = effective deadline minus current clock minus 30 after equality conversion; actual delivery reserve is observed, not guaranteed.',
        'response_and_SAFE_deadline':'unchanged original 600 s absolute root',
        'insufficient_reserve':'fail closed without new native request; preserve failure; no retries',
        'reserve_tuning':False}

def validate_plan(plan):
    prior.repaired.validate_plan(plan)
    base.require(plan.get('delivery_policy')==POLICY and plan.get('budget_extension_only') is False,'DELIVERY_POLICY_DRIFT')
    base.require(ADAPTER in plan['source_sha256'],'DELIVERY_ADAPTER_MISSING')

def validate_response(request,response,reference):
    from research.chapter3_experiments.small_whole_execution import native_contract as n
    base.require(all(isinstance(v,dict) for v in (request,response,reference)),'NATIVE_RECORD_TYPES')
    remaining=n.positive_finite(request.get('remaining_s'),'remaining_s')
    declared=n.positive_finite(request.get('solver_max_time_s_declared'),'declared cap')
    cap=n.positive_finite(request.get('solver_max_time_s'),'allocated cap')
    base.require(cap<=declared<=600 and cap<=remaining<=600,'CAP_OR_ROOT_EXCEEDED')
    base.require(response.get('solver_max_time_s_declared')==declared and response.get('solver_max_time_s_allocated')==cap,'NATIVE_CAP_IDENTITY')
    options=response.get('options')
    base.require(isinstance(options,dict) and 'MaxTime' not in reference and set(options)==set(reference)|{'MaxTime'},'OPTION_INVENTORY')
    base.require(all(n._same_json_value(options[k],v) for k,v in reference.items()),'OPTION_DRIFT')
    used=n.positive_finite(options['MaxTime'],'MaxTime')
    base.require(used<=cap and used<=remaining and response.get('solver_max_time_s_used')==used,'ACTUAL_CAP_DRIFT')
    base.require(request.get('cut_max_iterations')==10 and response.get('cut_max_iterations_declared')==10
                 and response.get('cut_max_iterations_actual_effective')==10,'CUT_LIMIT_DRIFT')
    base.require(response.get('solver_max_time_s_scope')=='native_MaxTime_only_not_response_or_evidence_deadline','CAP_SCOPE_DRIFT')
    return dict(passed=True,state='DELIVERY_CAP_OPTIONS_PASS',root_s=600,nominal_reserve_s=30,
                request_remaining_s=remaining,declared_cap_s=declared,native_MaxTime_s=used,
                matching_options_except_MaxTime=len(reference),scope='allocation identity only; no SAFE or optimality claim')

def native_session_factory(plan):
    original=prior.repaired._native_factory_original(plan)
    def create(*args,**kwargs):
        session=original(*args,**kwargs)
        try:
            from research.chapter3_experiments.native_delivery_reserve import attach
            from research.chapter3_experiments.numeric_case_diagnostic.equality_session import attach as equalities
            # Outer equality conversion runs first; inner reserve charges it before cap allocation.
            attach(session)
            return equalities(session)
        except BaseException:
            session.close()
            raise
    return create

def freeze(folder):
    folder=Path(folder).resolve()
    base.require(folder==PREPARATION and not folder.exists(),'NEW_PREPARATION_REQUIRED')
    plan=deepcopy(base.read(PREVIOUS))
    # These two controllers had already received post-run audit-only fixes.
    allowed=(prior.repaired.BASE_ENTRY,prior.ENTRY)
    for rel,digest in plan['source_sha256'].items():
        if rel not in allowed:base.require(base.sha(base.ROOT/rel)==digest,'SOURCE_DRIFT:'+rel)
    for rel in (*allowed,ENTRY,ADAPTER):plan['source_sha256'][rel]=base.sha(base.ROOT/rel)
    plan.update(baseline_commit=base.git_bytes('rev-parse','HEAD').decode().strip(),jobs=base.JOBS,
                scope=prior.SCOPE,budget_extension_only=False,delivery_policy=POLICY,
                comparison='One fresh same-instance 600 s delivery diagnostic; old 300/600 s archives unchanged; no new HEFT/SA.')
    validate_plan(plan);base.verify_sources(plan)
    base.save(folder/'plan.json',plan)
    template=base.read(prior.PREPARATION/'approval_template.json')
    template.update(plan_sha256=base.sha(folder/'plan.json'),scope=prior.SCOPE)
    base.save(folder/'approval_template.json',template)
    return {'plan':str(folder/'plan.json'),'sha256':base.sha(folder/'plan.json'),'authorized':False}

def configure():
    prior.configure()
    base.ENTRY=ENTRY
    base.WORKER_MODULE='research.chapter3_experiments.natural_delivery_entry'
    base.PREPARATION=PREPARATION
    base.validate_plan=validate_plan
    base.freeze=freeze
    base.NATIVE_RESPONSE_VALIDATOR=validate_response
    base.native_session_factory=native_session_factory

if __name__=='__main__':
    configure()
    raise SystemExit(base.main())
