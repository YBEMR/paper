"""Probe the actual archive _save contract with a handwritten fake native only."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
import precheck_whole_augmented as fixtures
import whole_augmented as w
import milp
import thermal
import scipy.linalg
import scipy.optimize
import subprocess

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    out=HERE/'archive_save_probe02';out.mkdir(exist_ok=False)
    fixtures.OUT=out
    source_before=sha(ROOT/'whole_augmented.py')
    counts={};saves=[]
    save=w._save
    def fail_second_admission(path,value):
        if Path(path).name=='admission.json':
            saves.append({'ordinal':len(saves)+1,'path':str(path)})
            if len(saves)==2:raise OSError('EXPLICIT_FAKE_FINAL_ADMISSION_SAVE_FAILURE')
        return save(path,value)
    def denied(name):
        def block(*args,**kwargs):
            counts[name]=counts.get(name,0)+1;raise RuntimeError('Scientific entry forbidden')
        return block
    case=fixtures.WholeAugmentedTests('runTest');case.setUp()
    with ExitStack() as stack:
        for module,name in [(milp,'build_model'),(milp.Model,'__init__'),(thermal,'evaluate_piecewise'),
            (scipy.optimize,'milp'),(scipy.optimize,'linprog'),(scipy.linalg,'expm'),(subprocess,'Popen')]:
            stack.enter_context(patch.object(module,name,denied(str(module)+'.'+name)))
        stack.enter_context(patch.object(w,'_save',fail_second_admission))
        got=case.harness([{'callbacks':[fixtures.GOOD],'final':fixtures.GOOD}])
    result=got.result
    receipt=got.context.requests[0].receipt
    checks={'second_save_fault_injected':len(saves)==2,
        'existing_stub_SAFE_retained':result.get('state')=='SAFE',
        'old_stub_U_retained':str(result.get('safe_upper_bound_J'))=='1.0',
        'archive_reason_explicit':result.get('reason')=='WHOLE_AUGMENTED_ADMISSION_ARCHIVE_UNRESOLVED',
        'interface_failure_latched':got.context.failed and 'interface' in got.context.failure_categories,
        'archive_error_retained':'EXPLICIT_FAKE_FINAL_ADMISSION_SAVE_FAILURE' in receipt.get('archive_error',''),
        'source_unchanged':source_before==sha(ROOT/'whole_augmented.py'),
        'no_scientific_entry_attempts':not counts}
    record={'protocol':'K167-independent-real-save-contract-probe-v1','checks':checks,
        'passed':all(checks.values()),'source_sha256_before':source_before,
        'source_sha256_after':sha(ROOT/'whole_augmented.py'),'save_calls':saves,
        'state':result.get('state'),'reason':result.get('reason'),
        'safe_upper_bound_J':result.get('safe_upper_bound_J'),'archive_error':receipt.get('archive_error'),
        'scientific_entry_attempts':counts,'new_model_solver_thermal_or_post_calls':0,
        'scope':'Actual archive implementation retained; _save raises on second admission serialization only. All SAFE/U are explicit fake evaluator outputs.'}
    with (out/'probe.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    assert record['passed'],checks
    print(record)

if __name__=='__main__':main()
