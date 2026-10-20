"""Offline K133 driver boundary checks; no MATLAB/optimizer/model/physics."""
from pathlib import Path
import argparse
from contextlib import nullcontext
import hashlib
import json
import traceback

import numpy as np
from scipy import sparse
import run_augmented_native_check as driver
from augmented_payload import build_augmented_payload, append_complements

HERE=Path(__file__).resolve().parent

class Clock:
    def __init__(self,t=0.):self.t=t
    def __call__(self):return self.t

def toy():
    p={'c':np.array([1.,0.]),'A':sparse.csr_matrix([[1.,64.]]),'b':np.array([64.]),
       'Aeq':sparse.csr_matrix((0,2)),'beq':np.empty(0),'lb':np.zeros(2),'ub':np.ones(2),
       'intcon':np.array([0])}
    augmented,meta=build_augmented_payload(p,{'names':['y:test','w:test'],'row_tags':['thermal_propagation/upper']})
    x=append_complements(np.array([0.,1.]),meta)
    return p,augmented,meta,x

def run(out):
    out.mkdir(parents=True,exist_ok=False);checks=[];error=None
    files=[Path(__file__),HERE/'run_augmented_native_check.py',HERE/'augmented_payload.py']
    sources={str(p.relative_to(driver.REPO).as_posix()):driver.sha(p) for p in files}
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    try:
        p,aug,meta,x=toy();clock=Clock();budget=driver.TechnicalBudget(0,clock)
        check('one_absolute_work_and_total_deadline',budget.deadline==135 and budget.total_deadline==180)
        check('native_cap_is_60_not_a_new_total_budget',driver.native_cap(budget)==60)
        clock.t=132
        check('native_cap_uses_original_remaining',driver.native_cap(budget)==3)
        clock.t=135
        try:driver.native_cap(budget)
        except TimeoutError:blocked=True
        else:blocked=False
        check('no_native_after_work_deadline',blocked)
        clock.t=0
        events=out/'events';events.mkdir()
        with nullcontext(events) as tmp:
            prefix=Path(tmp)/'request_000001'
            def publish(n,kind='callback',values=None,vector=None):
                event={'event_number':n,'kind':kind,'state':'iter','values':values or {},'x':[] if vector is None else vector}
                driver.save(Path(f'{prefix}.event_{n:06d}.json'),event)
            publish(1,'solver_entered');publish(2,vector=x.tolist(),values={'fval':0.})
            rec=driver.NumericalRecorder(p,aug,meta,budget)
            native={'status':'SOLVED','exitflag':2,'x':x.tolist(),'fval':0.,'budget_valid':True,
                    'intlinprog_entered':True,'callbacks':[{'event_number':2}]}
            final=rec.finalize(native,prefix)
            check('all_callback_and_final_vectors_checked',final['accepted'] and len(rec.vectors)==2)
            check('callback_completeness_verified',final['event_publications_complete'])
            check('original_tolerances_preserved',all(v['report']['constraint_tolerance']==1e-9 and v['report']['integer_tolerance']==1e-6 for v in rec.vectors))
            bad=x.copy();bad[0]=1
            failure=driver.NumericalRecorder(p,aug,meta,budget)
            failure.assess(bad,'bad_callback',prefix)
            check('bad_callback_cancels_and_latches',failure.failed and prefix.with_suffix('.cancel').exists())
            later=failure.assess(x,'later_good_final',prefix)
            check('later_valid_vector_does_not_clear_failure',not later['accepted'] and failure.failed)
            missing=driver.NumericalRecorder(p,aug,meta,budget)
            gap=missing.finalize(dict(native,callbacks=[{'event_number':2},{'event_number':3}]),prefix)
            check('missing_callback_blocks_valid_final',not gap['accepted'] and 'CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED' in missing.failure_reasons)
            minus2=driver.NumericalRecorder(p,aug,meta,budget)
            result=minus2.finalize(dict(native,exitflag=-2,x=[],fval=[]),prefix)
            check('minus2_never_certifies_infeasibility_or_success',not result['accepted'] and not result['independent_certificate'])
            missing_objective=driver.NumericalRecorder(p,aug,meta,budget)
            result=missing_objective.finalize(dict(native,fval=[]),prefix)
            check('missing_final_native_objective_is_unresolved',not result['accepted'] and 'NATIVE_FINAL_OBJECTIVE_MISSING' in missing_objective.failure_reasons)
            objective=driver.NumericalRecorder(p,aug,meta,budget)
            objective.assess(x,'native_mismatched_objective',prefix,reported_objective=1.)
            check('solver_objective_mismatch_latches',objective.failed and 'NATIVE_OBJECTIVE_MISMATCH' in objective.failure_reasons)
            expired=driver.NumericalRecorder(p,aug,meta,budget);clock.t=135
            result=expired.assess(x,'late_callback',prefix)
            check('no_late_numeric_acceptance',not result['accepted'] and 'report' not in result)
            clock.t=134.9
            def slow(*args):
                from augmented_payload import validate_projected_vector
                answer=validate_projected_vector(*args);clock.t=135.1;return answer
            slow_rec=driver.NumericalRecorder(p,aug,meta,budget,validator=slow)
            result=slow_rec.assess(x,'check_crossed_deadline',prefix)
            check('check_crossing_deadline_not_backdated',not result['accepted'] and slow_rec.failed)
            clock.t=0
            check('malformed_scalar_candidate_not_silently_empty',driver.vector_present(0.) and not driver.vector_present([]))
            publish(3,vector=0.)
            malformed=driver.NumericalRecorder(p,aug,meta,budget);malformed.poll(prefix)
            check('malformed_nonempty_callback_rejected',malformed.failed)
            bom_prefix=Path(tmp)/'bom_only'
            Path(f'{bom_prefix}.event_000001.json').write_text(json.dumps({'event_number':1,'kind':'callback','x':x.tolist(),'values':{'fval':0.}}),encoding='utf-8-sig')
            bom=driver.NumericalRecorder(p,aug,meta,budget);bom.poll(bom_prefix)
            check('BOM_callback_publication_supported',len(bom.events)==1 and bom.vectors[0]['accepted'])
        check('source_files_unchanged',all(driver.sha(driver.REPO/p)==h for p,h in sources.items()))
    except BaseException as exc:
        error={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
    report={'stage':'K133_driver_precheck','passed':error is None and all(x['passed'] for x in checks),
        'check_count':len(checks),'checks':checks,'error':error,'source_sha256':sources,
        'MATLAB_startups':0,'optimizer_calls':0,'models':0,'thermal_evaluations':0,
        'scope':'fake clock and immutable event fixtures; not a solver or thermal test'}
    driver.save(out/'checks.json',report)
    print(json.dumps({'passed':report['passed'],'count':len(checks),'error':error},ensure_ascii=False))
    return report['passed']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();raise SystemExit(0 if run(args.out.resolve()) else 1)
