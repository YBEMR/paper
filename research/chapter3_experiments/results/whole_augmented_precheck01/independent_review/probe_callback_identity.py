"""Independent five-variable fake-native probe; no production model or heat."""
from copy import deepcopy
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
import whole_augmented
import milp
import thermal
import scipy.optimize
import scipy.linalg
import subprocess


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    out=HERE/'callback_identity_probe01';out.mkdir(exist_ok=False)
    fixtures.OUT=out
    source_before={p.name:sha(p) for p in [ROOT/'whole_augmented.py',ROOT/'precheck_whole_augmented.py',ROOT/'formal_milp.py']}
    calls={}
    def forbidden(name):
        def denied(*args,**kwargs):
            calls[name]=calls.get(name,0)+1
            raise RuntimeError('Independent identity probe forbids '+name)
        return denied
    real_factory=fixtures.FakeNative.factory
    def altered_factory(owner,*args,**kwargs):
        session=real_factory(owner,*args,**kwargs)
        solve=session.solve
        def altered_solve(*a,**k):
            returned=solve(*a,**k)
            # The immutable live file remains GOOD / fval0.  Only the saved
            # response entry with the same callback event number is changed.
            returned=deepcopy(returned)
            returned['callbacks'][0]['x']=list(fixtures.SLOW)
            returned['callbacks'][0]['values']['fval']=1.
            prefix=Path(session.workdir)/f'request_{session.counter:06d}'
            fixtures.write(prefix.with_suffix('.python.json'),returned)
            return returned
        session.solve=altered_solve
        return session
    case=fixtures.WholeAugmentedTests('runTest');case.setUp()
    with ExitStack() as stack:
        for module,name in [(milp,'build_model'),(milp.Model,'__init__'),
            (thermal,'evaluate_piecewise'),(scipy.optimize,'milp'),(scipy.optimize,'linprog'),
            (scipy.linalg,'expm'),(subprocess,'Popen')]:
            stack.enter_context(patch.object(module,name,forbidden(str(module)+'.'+name)))
        stack.enter_context(patch.object(fixtures.FakeNative,'factory',altered_factory))
        h=case.harness([{'callbacks':[fixtures.GOOD],'final':fixtures.GOOD}],seed=False)
    request=h.context.summary()['requests'][0]
    raw=h.result['native_rounds'][0]
    prefix=Path(h.native.calls[0]['prefix'])
    live=json.loads(Path(str(prefix)+'.event_000002.json').read_text('utf-8'))
    record={'protocol':'K167-independent-same-number-different-callback-content-probe-v1',
        'source_sha256_before':source_before,
        'source_sha256_after':{p.name:sha(p) for p in [ROOT/'whole_augmented.py',ROOT/'precheck_whole_augmented.py',ROOT/'formal_milp.py']},
        'live_callback':live,'native_response_callback':raw['callbacks'][0],
        'same_event_number':live['event_number']==raw['callbacks'][0]['event_number'],
        'different_callback_content':live!=raw['callbacks'][0],
        'context_latched':h.context.failed,
        'failure_reasons':h.context.failure_reasons,
        'callback_publications_complete':request.get('callback_publications_complete'),
        'derived_accepted_for_evaluation':h.result['rounds'][0].get('accepted_for_evaluation'),
        'stub_SAFE_preexisting_from_live_callback_retained':h.result.get('safe_upper_bound_J'),
        'scientific_entry_attempts':calls,'new_solver_model_thermal_or_post_calls':0,
        'scope':'Identity refusal should be independent of prior valid callback stub SAFE retention; no physical safety or method-quality claim.'}
    with (out/'probe.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print({k:record[k] for k in ('same_event_number','different_callback_content','context_latched','failure_reasons','callback_publications_complete','derived_accepted_for_evaluation','new_solver_model_thermal_or_post_calls')})


if __name__=='__main__':main()
