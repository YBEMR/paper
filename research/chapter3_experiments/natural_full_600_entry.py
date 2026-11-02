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
    previous = audit_whole.SECONDS
    audit_whole.SECONDS = 600
    try:
        return _run_whole_original(*args, **kwargs)
    finally:
        audit_whole.SECONDS = previous

def configure():
    repaired.configure()
    base.ENTRY = ENTRY
    base.WORKER_MODULE = 'research.chapter3_experiments.natural_full_600_entry'
    base.PREPARATION = PREPARATION
    base.JOBS = [dict(id='whole_milp',method='whole_milp',seed=None)]
    base.SCOPE = SCOPE
    base.METHOD_SECONDS = 600
    base.METHOD_WATCHDOG_SECONDS = 705
    base.validate_plan = validate_plan
    base.freeze = freeze
    base.run_whole = run_whole

if __name__ == '__main__':
    configure()
    raise SystemExit(base.main())
