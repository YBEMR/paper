"""Tiny fake-native final-serialization failure probe; no physical work."""
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
    out=HERE/'archive_retention_probe01';out.mkdir(exist_ok=False)
    fixtures.OUT=out
    source_before=sha(ROOT/'whole_augmented.py')
    counts={};contexts=[];archives=[]
    init=w.WholeAugmentedContext.__init__;archive=w._WholeRequest.archive
    def capture(context,*args,**kwargs):
        init(context,*args,**kwargs);contexts.append(context)
    def fail_final(request):
        archives.append({'call':len(archives)+1,'has_best':request.recorder.best is not None,
                         'safe_U':None if request.recorder.best is None else request.recorder.best['evaluation'].get('safe_upper_bound_J')})
        if len(archives)==2:raise OSError('EXPLICIT_FAKE_FINAL_ARCHIVE_FAILURE')
        return archive(request)
    def denied(name):
        def block(*args,**kwargs):
            counts[name]=counts.get(name,0)+1;raise RuntimeError('Scientific entry forbidden')
        return block
    case=fixtures.WholeAugmentedTests('runTest');case.setUp();returned=None;error=None
    with ExitStack() as stack:
        for module,name in [(milp,'build_model'),(milp.Model,'__init__'),(thermal,'evaluate_piecewise'),
            (scipy.optimize,'milp'),(scipy.optimize,'linprog'),(scipy.linalg,'expm'),(subprocess,'Popen')]:
            stack.enter_context(patch.object(module,name,denied(str(module)+'.'+name)))
        stack.enter_context(patch.object(w.WholeAugmentedContext,'__init__',capture))
        stack.enter_context(patch.object(w._WholeRequest,'archive',fail_final))
        try:
            returned=case.harness([{'callbacks':[fixtures.GOOD],'final':fixtures.GOOD}])
        except Exception as exception:
            error={'type':type(exception).__name__,'message':str(exception)}
    best=contexts[0].recorder.best if contexts else None
    record={'protocol':'K167-independent-final-archive-retention-probe-v1',
        'source_sha256_before':source_before,'source_sha256_after':sha(ROOT/'whole_augmented.py'),
        'archive_calls':archives,'escaped_exception':error,
        'public_result_returned':returned is not None,
        'formed_stub_SAFE_still_only_in_recorder_memory':None if best is None else best['evaluation']['safe_upper_bound_J'],
        'scientific_entry_attempts':counts,'new_model_solver_thermal_or_post_calls':0,
        'scope':'Handwritten five-variable/fake-native and stub SAFE only; final archive exception after original whole loop returned must not erase its formed result.'}
    with (out/'probe.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({k:record[k] for k in ('archive_calls','escaped_exception','public_result_returned','formed_stub_SAFE_still_only_in_recorder_memory','new_model_solver_thermal_or_post_calls')})


if __name__=='__main__':main()
