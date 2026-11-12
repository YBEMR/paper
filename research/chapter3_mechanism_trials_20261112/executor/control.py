"""Formal arm state machine. No solver import; all science is injected by Runtime."""
from fractions import Fraction
from budget_policy import ABC_DYNAMIC,ResponseDeadline
from evidence import full_safe,progress,StopWindow,InsufficientNativeBudget

class PreparationStop(Exception): pass
class ScopedCorrectnessError(Exception):
    def __init__(self,message,affected_arms):
        super().__init__(message);self.affected_arms=list(affected_arms)

def next_arms(order,completed,result,trials=None):
    pending=[a for a in order if a not in completed]
    if not result.get('cleanup',{}).get('complete') or result.get('identity_after',{}).get('state')!='VERIFIED':return []
    if result.get('fault_scope')=='ALL':return []
    affected=result.get('affected_arms',[])
    return [a for a in pending if a not in affected and (trials or {}).get(a,{}).get('model_arm') not in affected]

def execute(runtime):
    r=dict(arm=runtime.arm,terminal_state=None,native_request_attempts=0,retries=0,
        initial_evaluation=None,returned_evaluation=None,returned_vector_validation=None,
        candidate=None,same_initial=None,strict_energy_improvement=None,energy_identity_conflict=False,
        native=None,identity=None,error=None,fault_scope=None,affected_arms=[],independent_optimality_proof=False)
    try:
        runtime.prepare();runtime.check()
        r['initial_evaluation']=runtime.evaluate_initial()
        if not full_safe(r['initial_evaluation'],runtime.scene_count):
            raise PreparationStop('INITIAL_SAFE_NOT_ESTABLISHED')
        if not ABC_DYNAMIC.allocate(runtime.elapsed)['can_submit']:raise InsufficientNativeBudget()
        runtime.start_native();runtime.check()
        if not ABC_DYNAMIC.allocate(runtime.elapsed)['can_submit']:raise InsufficientNativeBudget()
        r['native_request_attempts']=1
        r['native']=n=runtime.solve(None)
        r['identity']=runtime.inspect_identity(n)
        if r['identity']['state']=='INVALID':
            r.update(terminal_state='INPUT_OR_OPTIONS_DRIFT',fault_scope='ALL')
        elif n.get('status')=='SOLVED' and n.get('budget_valid') and n.get('accepted_for_evaluation') and n.get('x'):
            runtime.check();v=runtime.validate_returned(n['x']);r['returned_vector_validation']=v
            runtime.check()
            if v['state']!='ADMITTED':r['terminal_state']='RETURNED_VECTOR_REJECTED'
            else:
                r.update(candidate=v['candidate'],same_initial=v['same_initial'])
                r['returned_evaluation']=runtime.evaluate_returned(v['candidate']);runtime.check()
                if full_safe(r['returned_evaluation'],runtime.scene_count):
                    initial,final=r['initial_evaluation']['weighted_energy_J'],r['returned_evaluation']['weighted_energy_J']
                    improved=Fraction(final[1])<Fraction(initial[0])
                    disjoint=improved or Fraction(initial[1])<Fraction(final[0])
                    r.update(strict_energy_improvement=bool(improved and not r['same_initial']),
                        energy_identity_conflict=bool(disjoint and r['same_initial']),terminal_state='RETURNED_COMPLETE_SAFE')
                    if r['energy_identity_conflict']:r.update(fault_scope='ALL',terminal_state='ENERGY_IDENTITY_CONFLICT')
                else:r['terminal_state']='RETURNED_SAFE_UNKNOWN_OR_REJECTED'
        else:r['terminal_state']='NO_TIMELY_ACCEPTED_NATIVE_VECTOR'
    except PreparationStop as e:r.update(terminal_state=str(e))
    except InsufficientNativeBudget:r['terminal_state']='INSUFFICIENT_BUDGET_NO_REQUEST'
    except ResponseDeadline:r['terminal_state']='RESPONSE_WINDOW_EXHAUSTED'
    except StopWindow:r['terminal_state']='METHOD_WINDOW_EXHAUSTED'
    except ScopedCorrectnessError as e:
        r.update(terminal_state='REDUCTION_CERTIFICATE_ERROR',error=repr(e),fault_scope='FEATURE',affected_arms=e.affected_arms)
    except Exception as e:r.update(terminal_state='UNCLASSIFIED_EXECUTION_ERROR',error=repr(e),fault_scope='ALL')
    finally:
        r['method_elapsed_s']=runtime.elapsed
        try:r['cleanup']=runtime.close()
        except Exception as e:r['cleanup']=dict(complete=False,error=repr(e))
        try:r['identity_after']=runtime.verify_after()
        except Exception as e:r['identity_after']=dict(state='INVALID',error=repr(e))
        r['total_elapsed_s']=runtime.elapsed
    if r['identity_after'].get('native_identity_after') is not None:
        after=r['identity_after']['native_identity_after']
        if (r['identity'] or {}).get('state')!='INVALID':r['identity']=after
    if (r['identity'] or {}).get('state')=='INVALID':
        r['fault_scope']='ALL'
        r['identity_invalidated']=True
    r['progress']=progress(runtime.events,runtime.objective_reference,ABC_DYNAMIC.response_cutoff,runtime.objective_lower_bound)
    p=r['progress'];conflict=any(b['consistency']=='CONFLICT' for b in p['finite_bounds'])
    r['native_bound_conflict']=conflict
    # Native bound conflicts are arm-local only when matrix/settings identity is established.
    if conflict:
        if r['fault_scope'] is None:
            r['fault_scope']='ARM' if (r['identity'] or {}).get('state')=='VERIFIED' else 'ALL'
        r['affected_arms']=sorted(set(r['affected_arms']+[runtime.arm]))
    r['returned_complete_SAFE']=full_safe(r['returned_evaluation'],runtime.scene_count)
    r['new_complete_SAFE']=r['returned_complete_SAFE'] and r['same_initial'] is False
    r['lifecycle_integrity']=bool(r['cleanup'].get('complete') and r['identity_after'].get('state')=='VERIFIED' and not r['error'])
    r['evidence_integrity']=bool(r['lifecycle_integrity'] and (r['identity'] or {}).get('state')=='VERIFIED'
        and not r['energy_identity_conflict'] and not conflict)
    r['progress_usable']=bool(r['evidence_integrity'] and (p['root_lp_completion_observed'] or p['native_bound_exceeds_box_bound'] or r['new_complete_SAFE']))
    r['next_action']='NEXT_INDEPENDENT_ARM_IF_SCOPE_PERMITS; NEVER_RETRY'
    return r
