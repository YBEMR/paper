"""D283 scientific worker. Entry requires independent approval and parent GO nonce."""
import argparse,os,sys,time
from pathlib import Path
from core import read,save,sha,verify,authorize,Clock,IntegrityError,WindowExpired,error_record,safe_interval,strict_improvement,finite_native

def run_pipeline(science,native,events,clock,out,plan,plan_hash):
    """Dependency-injected chain; control tests use no CPLEX or physical evaluator."""
    out=Path(out);stages=[];result=dict(outcome='NOT_REACHED',strict_success=False,initial=None,final=None,
        native_response=None,final_admission=None,native_model_prepared=False,independent_optimality='UNKNOWN',error=None)
    def call(name,fn,*args):
        t=clock.elapsed
        try:return fn(*args)
        finally:stages.append(dict(stage=name,start_s=t,end_s=clock.elapsed))
    try:
        call('saved_input_and_initial_admission',science.prepare)
        call('native_environment_load_readback_and_parameters',native.prepare,science.new)
        result['native_model_prepared']=True
        initial=call('fresh_initial_complete_AB_AC',science.evaluate,science.initial,'initial_complete_evaluation.json')
        result['initial']=initial
        if safe_interval(initial,science.scenes) is None:
            result['outcome']='INITIAL_NOT_COMPLETE_SAFE';return result
        # Historical interval is only an identity/consistency check, never a free evaluation.
        from fractions import Fraction
        historical=plan['historical_common_energy_J'];lo,hi=safe_interval(initial,science.scenes)
        if hi<Fraction(historical['lower']) or lo>Fraction(historical['upper']): raise IntegrityError('Fresh common energy contradicts frozen reference')
        response=call('single_native_solve_and_response_extraction',native.solve_once,plan_hash)
        result['native_response']=response
        if response is None: result['outcome']='INSUFFICIENT_NATIVE_BUDGET';return result
        t=clock.elapsed
        while not (out/'response_ack.json').exists():
            clock.check(550);time.sleep(.01)
        ack=read(out/'response_ack.json')
        if ack.get('plan_sha256')!=plan_hash or ack.get('response_sha256')!=sha(out/'native_response.json'):
            raise IntegrityError('Response acknowledgment drift')
        result['response_ack']=ack;stages.append(dict(stage='parent_response_acknowledgment',start_s=t,end_s=clock.elapsed))
        if ack.get('timely') is not True or not 0<=ack.get('received_elapsed_s',550)<550:
            result['outcome']='LATE_NATIVE_RESPONSE';return result
        if response.get('error'):
            result['outcome']=response['native_exit_category'];return result
        if response.get('native_exit_category') in ('NATIVE_MEMORY_LIMIT','NUMERICAL_FAILURE'):
            result['outcome']=response['native_exit_category'];return result
        if not response.get('vector'):
            result['outcome']='NO_FINAL_NATIVE_VECTOR';return result
        import numpy as np
        v=response['vector'];path=out/v['file']
        if v['file']!='final_vector.npy' or sha(path)!=v['sha256'] or ack.get('vector_sha256')!=v['sha256']:
            raise IntegrityError('Final vector source/hash drift')
        x=np.load(path,allow_pickle=False);clock.check()
        validation=call('both_matrices_and_independent_legality',science.validate_vector,x,'final_admission.json')
        result['final_admission']=validation
        if not validation['passed']: result['outcome']='FINAL_VECTOR_REJECTED';return result
        bound=response.get('finite_native_lower_bound');upper=response.get('finite_native_upper_bound')
        objective=float(Fraction(validation['objective_exact_binary64']))
        tolerance=plan['bound_objective_consistency_tolerance']*max(1.,abs(objective),abs(bound or 0),abs(upper or 0))
        if (bound is not None and bound>objective+tolerance) or (bound is not None and upper is not None and bound>upper+tolerance) or (upper is not None and abs(upper-objective)>tolerance):
            result['outcome']='BOUND_CONFLICT';result['bound_conflict']=dict(lower=bound,upper=upper,exact_binary64_objective=validation['objective_exact_binary64'],tolerance=tolerance,meaning='Numerical consistency failure; not a mathematical infeasibility proof');return result
        final=call('fresh_final_complete_AB_AC',science.evaluate,validation['candidate'],'final_complete_evaluation.json')
        result['final']=final
        result['strict_success']=strict_improvement(initial,final,science.scenes,validation['same_initial'] is False,True,True)
        if result['strict_success']: result['outcome']='STRICT_ENERGY_IMPROVEMENT'
        elif safe_interval(final,science.scenes) is None: result['outcome']='FINAL_NOT_COMPLETE_SAFE'
        elif validation['same_initial']: result['outcome']='COMMON_INITIAL_RETURNED_SAFE'
        else: result['outcome']='DIFFERENT_SAFE_WITHOUT_STRICT_IMPROVEMENT'
    except WindowExpired as e:
        result.update(outcome='WINDOW_EXPIRED',strict_success=False,error=error_record(e))
    except IntegrityError as e:
        result.update(outcome='IDENTITY_OR_CORRECTNESS_ERROR',strict_success=False,error=error_record(e))
    except BaseException as e:
        result.update(outcome='WORKER_ERROR',strict_success=False,error=error_record(e))
    finally:
        result['phase_records']=stages
        result['solve_attempts']=native.calls
        result['complete_evaluation_attempts']=science.evaluations
        t=clock.elapsed
        try: native.close();result['native_handle_closed']=True
        except BaseException as e: result.update(outcome='CLEANUP_FAILURE',strict_success=False,cleanup_error=error_record(e),native_handle_closed=False)
        stages.append(dict(stage='native_handle_and_stream_release',start_s=t,end_s=clock.elapsed))
        result['pipeline_completed_elapsed_s']=clock.elapsed
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--t0',type=float,required=True)
    args=p.parse_args();root=args.workspace.resolve();here=Path(__file__).resolve().parent;out=args.output.resolve()
    plan=read(args.plan);plan_hash=sha(args.plan);approval=read(out/'approval_consumed.json');authorize(approval,plan_hash)
    claim=read(out/'claim.json')
    if claim['plan_sha256']!=plan_hash or claim['parent_pid']!=os.getppid() or claim['start_monotonic']!=args.t0:
        raise PermissionError('Parent claim mismatch')
    if sys.stdin.readline().strip()!='D283_GO '+claim['nonce']: raise PermissionError('No parent GO')
    clock=Clock(args.t0);clock.check()
    from environment import verify_environment
    verify_environment(plan['environment'])
    # All scientific imports are below the new approval, one-use claim and protected GO.
    verify(here,plan['code_hashes']);verify(root,plan['input_hashes']);verify(root,plan['evaluation_source_hashes'])
    verify(Path('/'),plan['runtime_hashes'])
    import cplex
    from native import Native,Events
    from science import Science
    events=Events(out,clock);native=Native(cplex,plan,out,clock,events);science=Science(root,plan,out,clock)
    reserve=bytearray(4*1024*1024)
    try:
        result=run_pipeline(science,native,events,clock,out,plan,plan_hash)
    except BaseException as e:
        reserve=None
        result=dict(outcome='WORKER_OUTER_FAILURE',error=error_record(e),strict_success=False,solve_attempts=native.calls,complete_evaluation_attempts=science.evaluations)
        try:native.close()
        except BaseException as cleanup:result['cleanup_error']=error_record(cleanup)
    finally:
        reserve=None;events.close()
    try:
        clock.check();verify(here,plan['code_hashes']);verify(root,plan['input_hashes']);verify(root,plan['evaluation_source_hashes']);verify(Path('/'),plan['runtime_hashes']);clock.check()
        hashes={f.name:sha(f) for f in out.iterdir() if f.is_file() and f.name not in ('resources.jsonl','parent_events.jsonl') and not f.name.endswith('.partial')}
        clock.check();result.update(plan_sha256=plan_hash,in_window_sources_verified=True,evidence_hashes=hashes,sealed_elapsed_s=clock.elapsed)
        save(out/'scientific_snapshot.json',result);clock.check()
        save(out/'worker_receipt.json',dict(snapshot_sha256=sha(out/'scientific_snapshot.json'),sealed_elapsed_s=clock.elapsed,plan_sha256=plan_hash))
    except BaseException as e:
        save(out/'unsealed_failure.json',dict(error=error_record(e),result=result,elapsed_s=clock.elapsed,scientific_credit=False))
        return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
