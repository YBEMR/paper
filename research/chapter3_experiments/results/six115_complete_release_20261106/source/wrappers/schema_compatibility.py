"""Fixed-input schema view for the unchanged original legality validator.

No model/evaluator input is replaced. Only the validator's local top-level view
has a legacy schema label; its scientific values remain the identical objects.
"""
from contextlib import contextmanager
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys
import bootstrap
import controlled_inputs as ci

LEGACY_SCHEMA='chapter3-input-v0.1'
MODULES=('schedules','heft_method','heuristic_runner','heuristic_common',
         'initial_schedule','milp','formal_milp','thermal','initial_point')

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
                                    allow_nan=False).encode()).hexdigest()

def eligible(module):
    path=getattr(module,'__file__',None)
    if not path: return False
    path=Path(path).resolve()
    if path.name.startswith(('test_','run_test','run_offline')) or path.name=='schema_compatibility.py':
        return False
    return path.is_relative_to(bootstrap.SOURCE) or path.parent==bootstrap.ROOT

def aliases(function):
    found=[]
    for module in list(sys.modules.values()):
        if module is not None and eligible(module):
            for name,value in list(vars(module).items()):
                if value is function:
                    found.append((module,name))
    return found

@contextmanager
def install_schema_compatibility(audit=None):
    # Bind fresh file bytes and the complete parsed controlled instance first.
    config,frozen=ci.load_controlled_inputs()
    expected=digest(frozen)
    modules=[importlib.import_module(name) for name in MODULES]
    schedules=modules[0]
    original=schedules.validate_schedule
    ci.require(not getattr(original,'_six115_schema_adapter',False),'NESTED_SCHEMA_ADAPTER_FORBIDDEN')
    summary={} if audit is None else audit
    ci.require(isinstance(summary,dict) and not summary,'EMPTY_SCHEMA_AUDIT_REQUIRED')
    summary.update(policy='fixed-byte-input-local-schema-view-v1',input_file_sha256=ci.HASHES['input_instance.json'],
        input_canonical_sha256=expected,legacy_view_schema=LEGACY_SCHEMA,controlled_schema=ci.SCHEMA,
        source_validator_sha256=ci.sha(Path(schedules.__file__)),calls=0,reasons={},
        scientific_input_replaced=False,physical_evaluator_replaced=False,restored=False)
    reasons=Counter()

    def validate(instance,candidate):
        summary['calls']+=1
        if not isinstance(instance,dict) or instance.get('schema_version')!=ci.SCHEMA:
            result=dict(state='INVALID_SCHEDULE',reason='UNSUPPORTED_INPUT_SCHEMA',details={},
                        thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')
        elif digest(instance)!=expected:
            result=dict(state='INVALID_SCHEDULE',reason='CONTROLLED_INPUT_IDENTITY_MISMATCH',details={},
                        thermal_status='NOT_EVALUATED',energy_status='NOT_EVALUATED')
        else:
            ci.validate(config,instance)
            candidate_before=digest(candidate)
            view=dict(instance,schema_version=LEGACY_SCHEMA)
            ci.require(all(view[k] is value for k,value in instance.items() if k!='schema_version'),
                       'SCIENTIFIC_VIEW_OBJECT_DRIFT')
            result=original(view,candidate)
            ci.require(digest(instance)==expected and digest(candidate)==candidate_before,
                       'ORIGINAL_VALIDATOR_MUTATED_INPUT_OR_CANDIDATE')
        reasons[result.get('reason') or result['state']]+=1
        summary['reasons']=dict(reasons)
        return result

    validate._six115_schema_adapter=True
    initial=aliases(original)
    ci.require(any(m is schedules and n=='validate_schedule' for m,n in initial),'SCHEDULES_ALIAS_MISSING')
    summary['patched_initial_aliases']=[m.__name__+'.'+n for m,n in initial]
    for module,name in initial: setattr(module,name,validate)
    try:
        ci.require(all(getattr(sys.modules[n],'validate_schedule',validate) is validate for n in MODULES),
                   'REQUIRED_VALIDATOR_ALIAS_NOT_PATCHED')
        yield summary
    finally:
        # Include aliases captured by imports after entering this context.
        restored=aliases(validate)
        for module,name in restored: setattr(module,name,original)
        summary['restored_aliases']=[m.__name__+'.'+n for m,n in restored]
        summary['restored']=not aliases(validate)
        ci.require(summary['restored'],'SCHEMA_ALIAS_RESTORE_FAILED')
