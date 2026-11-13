"""One finite observation, all scientific formation/read/archive inside 600 seconds."""
from fractions import Fraction
from budget_policy import ABC_DYNAMIC,ResponseDeadline
from evidence import full_safe,progress,StopWindow,InsufficientNativeBudget
from observation import grade

class PreparationStop(Exception): pass

def execute(runtime):
    r=dict(arm=runtime.arm,terminal_state=None,native_request_attempts=0,retries=0,
        initial_evaluation=None,returned_evaluation=None,returned_vector_validation=None,
        candidate=None,same_initial=None,strict_energy_improvement=None,energy_identity_conflict=False,
        native=None,identity=None,error=None,fault_scope=None,affected_arms=[],independent_optimality_proof=False,
        observation={},snapshot=None,scientific_archive_timely=False)
    try:
        runtime.prepare();runtime.check()
        r['initial_evaluation']=runtime.evaluate_initial();runtime.check()
        if not full_safe(r['initial_evaluation'],runtime.scene_count): raise PreparationStop('INITIAL_SAFE_NOT_ESTABLISHED')
        if not ABC_DYNAMIC.allocate(runtime.elapsed)['can_submit']: raise InsufficientNativeBudget()
        runtime.start_native();runtime.check()
        if not ABC_DYNAMIC.allocate(runtime.elapsed)['can_submit']: raise InsufficientNativeBudget()
        r['native_request_attempts']=1
        r['native']=n=runtime.solve(None);runtime.check()
        r['identity']=runtime.inspect_identity(n)
        if r['identity']['state']=='INVALID': r.update(terminal_state='INPUT_OR_OPTIONS_DRIFT',fault_scope='ALL')
        elif n.get('status')=='SOLVED' and n.get('budget_valid') and n.get('accepted_for_evaluation') and n.get('x'):
            r['returned_vector_validation']=v=runtime.validate_returned(n['x']);runtime.check()
            if v['state']!='ADMITTED': r['terminal_state']='RETURNED_VECTOR_REJECTED'
            else:
                r.update(candidate=v['candidate'],same_initial=v['same_initial'])
                r['returned_evaluation']=runtime.evaluate_returned(v['candidate']);runtime.check()
                if full_safe(r['returned_evaluation'],runtime.scene_count):
                    initial=r['initial_evaluation']['weighted_energy_J'];final=r['returned_evaluation']['weighted_energy_J']
                    improved=Fraction(final[1])<Fraction(initial[0])
                    disjoint=improved or Fraction(initial[1])<Fraction(final[0])
                    r.update(strict_energy_improvement=bool(improved and not r['same_initial']),
                        energy_identity_conflict=bool(disjoint and r['same_initial']),terminal_state='RETURNED_COMPLETE_SAFE')
                    if r['energy_identity_conflict']: r.update(fault_scope='ALL',terminal_state='ENERGY_IDENTITY_CONFLICT')
                else: r['terminal_state']='RETURNED_SAFE_UNKNOWN_OR_REJECTED'
        else: r['terminal_state']='NO_TIMELY_ACCEPTED_NATIVE_VECTOR'
    except PreparationStop as e: r['terminal_state']=str(e)
    except InsufficientNativeBudget: r['terminal_state']='INSUFFICIENT_BUDGET_NO_REQUEST'
    except ResponseDeadline: r['terminal_state']='RESPONSE_WINDOW_EXHAUSTED'
    except StopWindow: r['terminal_state']='METHOD_WINDOW_EXHAUSTED'
    except Exception as e: r.update(terminal_state='UNCLASSIFIED_EXECUTION_ERROR',error=repr(e),fault_scope='ALL')
    try:
        runtime.check()
        r['progress']=p=progress(runtime.events,runtime.objective_reference,550,runtime.objective_lower_bound)
        conflict=any(b['consistency']=='CONFLICT' for b in p['finite_bounds'])
        r['native_bound_conflict']=conflict
        if conflict:
            r['fault_scope']=r['fault_scope'] or ('TRIAL' if (r['identity'] or {}).get('state')=='VERIFIED' else 'ALL')
            r['affected_arms']=[runtime.arm]
        r['observation']=runtime.finish_observation(r['native'])
        r['returned_complete_SAFE']=full_safe(r['returned_evaluation'],runtime.scene_count)
        r['new_complete_SAFE']=bool(r['returned_complete_SAFE'] and r['same_initial'] is False)
        r['candidate_scientific_success']=bool(r['new_complete_SAFE'] and r['strict_energy_improvement'] and
            (r['identity'] or {}).get('state')=='VERIFIED' and not conflict and not r['fault_scope'])
        r['observability_provisional']=grade(r['observation'],(r['identity'] or {}).get('state')=='VERIFIED',True,True)
        r['observability_provisional']['cleanup_pending']=True
        r['snapshot']=runtime.freeze(r)
        r['scientific_archive_timely']=True
    except StopWindow:
        r.update(terminal_state='METHOD_WINDOW_EXHAUSTED',scientific_archive_timely=False)
    except Exception as e:
        r.update(archive_error=repr(e),scientific_archive_timely=False,fault_scope='ALL')
    r['method_elapsed_s']=runtime.elapsed
    try: r['cleanup']=runtime.close()
    except Exception as e: r['cleanup']=dict(complete=False,error=repr(e))
    try: r['identity_after']=runtime.verify_after()
    except Exception as e: r['identity_after']=dict(state='INVALID',error=repr(e))
    # These post-window decisions can only revoke the frozen snapshot's claims.
    intact=bool(r['cleanup'].get('complete') and r['identity_after'].get('state')=='VERIFIED')
    r['total_elapsed_s']=runtime.elapsed
    r['cleanup_and_administrative_wall_s']=r['total_elapsed_s']-r['method_elapsed_s']
    if not intact: r['fault_scope']='ALL'
    r['evidence_integrity']=bool(intact and r['scientific_archive_timely'] and not r.get('native_bound_conflict')
        and not r['energy_identity_conflict'] and not r['error'] and (r['identity'] or {}).get('state')=='VERIFIED')
    r['scientific_success']=bool(r['evidence_integrity'] and r.get('candidate_scientific_success'))
    g=dict(r.get('observability_provisional',dict(O0=False,O1=False,O2='NOT_ESTABLISHED',O2_review_eligible=False)))
    if not r['evidence_integrity']:
        for k in ('O0','O1','O2_review_eligible'): g[k]=False
    g['cleanup_pending']=False;g['targeted_intervention_eligible']=False
    r['observability']=g
    r['next_action']='NO AUTOMATIC NEXT CALL; if no independently established O2, stop parameter scanning'
    return r
