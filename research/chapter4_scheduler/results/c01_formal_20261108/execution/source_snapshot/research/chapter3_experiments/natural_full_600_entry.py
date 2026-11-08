"""One user-authorized fresh 600 s MILP; unchanged instance and algorithms."""
from copy import deepcopy
from pathlib import Path
import sys
from research.chapter3_experiments import natural_full_repaired_entry as repaired

base = repaired.base
ENTRY = 'research/chapter3_experiments/natural_full_600_entry.py'
PREPARATION = base.RESULTS/'natural_full_600_preparation01'
PREVIOUS = base.RESULTS/'natural_full_repaired_preparation01/plan.json'
_run_whole_original = base.run_whole
SCOPE = dict(method_calls=1, method_seconds_each=600, method_seconds_total=600,
             post_calls_at_most=1, post_seconds_each=60, post_seconds_total_at_most=60,
             job_calendar_seconds=780, batch_calendar_seconds=840, retries=0)

def validate_plan(plan):
    repaired.validate_plan(plan)
    base.require(plan.get('budget_extension_only') is True, 'EXPLICIT_600_SCOPE_REQUIRED')

def validate_response_600(request, response, reference):
    """Same option identity checks, bound to the explicitly approved 600 s root."""
    from research.chapter3_experiments.small_whole_execution import native_contract as n
    n.require(all(isinstance(v,dict) for v in (request,response,reference)), 'NATIVE_RECORD_TYPES')
    n.require(not any(k.startswith('solver_max_time_s') for r in (request,response) for k in r), 'NO_NATIVE_ONLY_CAP')
    remaining=n.positive_finite(request.get('remaining_s'),'remaining_s')
    n.require(remaining<=600,'REQUEST_EXCEEDS_600')
    n.require(n._same_json_value(request.get('cut_max_iterations'),10),'CUT_REQUEST_DRIFT')
    for key in ('cut_max_iterations_declared','cut_max_iterations_actual_effective'):
        n.require(n._same_json_value(response.get(key),10),'CUT_RESPONSE_DRIFT')
    options=response.get('options')
    n.require(isinstance(options,dict) and 'MaxTime' not in reference and set(options)==set(reference)|{'MaxTime'},'OPTION_INVENTORY_DRIFT')
    n.require(all(n._same_json_value(options[k],v) for k,v in reference.items()),'OPTION_VALUE_DRIFT')
    allocated=n.positive_finite(options['MaxTime'],'MaxTime')
    n.require(allocated<=remaining<=600,'NATIVE_ALLOCATION_EXCEEDS_ROOT')
    return dict(passed=True,state='NATIVE_OPTIONS_BUDGET_PASS',method_seconds=600,
                matching_options_except_MaxTime=len(reference),MaxTime=allocated,request_remaining_s=remaining)

def freeze(folder):
    folder = Path(folder).resolve()
    base.require(folder == PREPARATION and not folder.exists(), 'NEW_PREPARATION_REQUIRED')
    plan = deepcopy(base.read(PREVIOUS))
    for rel, digest in plan['source_sha256'].items():
        if rel != repaired.BASE_ENTRY:
            base.require(base.sha(base.ROOT/rel) == digest, 'PREVIOUS_SOURCE_DRIFT:'+rel)
    plan.update(baseline_commit=base.git_bytes('rev-parse','HEAD').decode().strip(),
                jobs=base.JOBS, scope=SCOPE, method_process_watchdog_seconds=705,
                budget_extension_only=True,
                comparison='Fresh MILP 600 s against archived 300 s results; unequal budgets explicitly reported.')
    for rel in (repaired.BASE_ENTRY, ENTRY):
        plan['source_sha256'][rel] = base.sha(base.ROOT/rel)
    validate_plan(plan)
    base.verify_sources(plan)
    base.save(folder/'plan.json',plan)
    template = base.read(repaired.PREPARATION/'approval_template.json')
    template.update(plan_sha256=base.sha(folder/'plan.json'),scope=SCOPE)
    base.save(folder/'approval_template.json',template)
    return {'plan_sha256':base.sha(folder/'plan.json'),'authorized':False}

def run_whole(*args, **kwargs):
    sys.path.insert(0,str(base.EXP/'p0_batch'))
    import audit_whole
    import audit_heuristic
    previous = audit_whole.SECONDS, audit_heuristic.SECONDS
    audit_whole.SECONDS = audit_heuristic.SECONDS = 600
    try:
        return _run_whole_original(*args, **kwargs)
    finally:
        audit_whole.SECONDS, audit_heuristic.SECONDS = previous

def configure():
    repaired.configure()
    base.ENTRY = ENTRY
    base.WORKER_MODULE = 'research.chapter3_experiments.natural_full_600_entry'
    base.PREPARATION = PREPARATION
    base.JOBS = [dict(id='whole_milp',method='whole_milp',seed=None)]
    base.SCOPE = SCOPE
    base.METHOD_SECONDS = 600
    base.METHOD_WATCHDOG_SECONDS = 705
    base.NATIVE_RESPONSE_VALIDATOR = validate_response_600
    base.validate_plan = validate_plan
    base.freeze = freeze
    base.run_whole = run_whole

if __name__ == '__main__':
    configure()
    raise SystemExit(base.main())
