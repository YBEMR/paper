"""Explicit typed integration; original lifecycle and conditional feedback.

No session masquerades as the legacy full-coordinate solve API. Native return
objects and publications stay unchanged. Full original rows/logic/SAFE precede
every callback/final receipt, without the old schedule cache. Any rejected
vector fails closed; previously committed SAFE evidence survives separately.
"""
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time
import psutil

from thermal import Exhausted
from native_projection import ProjectedSession
from initial_point import _InitialSession
from matlab_bridge import NUMERICAL_CONSISTENCY_CONFLICT, NUMERICAL_CONSISTENCY_UNRESOLVED
from formal_milp import (OUTER_ROUND_LIMIT, _require_kind, _checked_thermal_witnesses,
                         add_thermal_feedback, add_assignment_feedback)


def summarize(adapter):
    """Archive already committed receipts only; no files/candidates are read."""
    evaluations = []
    progress = []
    for record in adapter.records:
        for event in record.events:
            row = dict(event['metadata'], method_elapsed_s=event['received_at_elapsed_s'],
                       request=record.prefix.name, evidence='solver-reported')
            progress.append(row)
        for receipt in record.receipts:
            committed=receipt.get('admission_committed_at_s')
            if (type(committed) not in (int,float) or not math.isfinite(committed)
                    or not 0<=committed<record.budget.seconds
                    or not record.budget.start+committed<record.request_deadline):
                raise ValueError('Uncommitted projection receipt cannot enter summary')
            evaluations.append(dict(receipt,
                candidate_sha256=hashlib.sha256(json.dumps(receipt['candidate'],sort_keys=True).encode()).hexdigest(),
                evaluation_returned_at_s=receipt['admission_committed_at_s']))
    def earliest(values):
        return min(values) if values else None
    safe = [r for r in evaluations if r['accepted_safe']]
    return dict(evaluations=evaluations, solver_progress=progress,
        first_candidate_received_s=earliest([r['numeric']['completed_at_elapsed_s'] for r in evaluations]),
        first_legal_candidate_s=earliest([r['numeric']['completed_at_elapsed_s'] for r in evaluations]),
        first_safe_receipt_s=earliest([r['evaluation']['completed_at_elapsed_s'] for r in safe]),
        solver_entered_received_s=earliest([r['method_elapsed_s'] for r in progress if r.get('kind')=='solver_entered']),
        worker_events=len(progress),candidate_receipts=len(evaluations),duplicate_receipts=0,
        decode_records=[],decode_rejections=0,solver_bounds_independently_certified=False,
        no_schedule_cache=True,per_vector_full_original_rows_logic_and_safe=True,
        time_semantics='Original numeric admission time and committed complete SAFE receipts; no retrospective acceptance')


def solve_projected_diagnostic(model, session, accuracy, budget, *,
                                feedback_kind='conditional',max_rounds=OUTER_ROUND_LIMIT,
                                adapter_factory=ProjectedSession):
    _require_kind(feedback_kind)
    if not isinstance(session,_InitialSession) or not session.first or session.x0 is None:
        raise ValueError('Fresh original admitted initial-session wrapper required')
    native = session.session
    adapter = adapter_factory(native,model,accuracy,budget)
    result = dict(state='UNRESOLVED',safe_candidate=None,safe_upper_bound_J=None,
        evaluation=None,rounds=[],feedback=[],feedback_kind=feedback_kind,
        outer_round_limit=max_rounds,independently_proven_optimal=False,
        independently_proven_infeasible=False,remaining_domain='retained',reason=None)
    try:
        for iteration in range(max_rounds):
            budget.check()
            with budget.phase('matrix_export'):
                solver_input=model.as_solver_dict()
            budget.check()
            with budget.phase('solver_transport_and_solve'):
                packet=adapter.solve(solver_input,remaining_s=budget.remaining,budget=budget,
                                     x0=session.x0 if iteration==0 else None)
            returned=packet['native_result']
            result['rounds'].append(returned)
            budget.check()
            if not returned.get('budget_valid'):
                result['reason']='SOLVER_RETURN_AFTER_BUDGET';break
            if (returned.get('numerical_consistency') or {}).get('state')==NUMERICAL_CONSISTENCY_CONFLICT:
                result.update(reason=NUMERICAL_CONSISTENCY_UNRESOLVED,
                              numerical_consistency=returned['numerical_consistency']);break
            if not returned.get('x'):
                result['reason']='SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag')==-2 else 'NO_INTEGER_CANDIDATE';break
            if not returned.get('accepted_for_evaluation'):
                result['reason']='SOLVER_INTERFACE_ERROR';break
            final=packet['final_admission']
            if final is None:
                result['reason']='NUMERICAL_CANDIDATE_ANOMALY';break
            candidate,evaluation=final['candidate'],final['evaluation']
            result['evaluation']=evaluation
            if final['accepted_safe']:
                result['reason']='SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag')==1 else 'SAFE_INCUMBENT';break
            if evaluation['state']!='THERMAL_VIOLATION':
                result['reason']='EVALUATION_UNRESOLVED';break
            budget.check()
            with budget.phase('thermal_feedback'):
                if not _checked_thermal_witnesses(model,candidate,evaluation):
                    feedback=dict(state='NO_VALID_EXCLUSION',rows_added=0)
                elif feedback_kind=='conditional':
                    feedback=add_thermal_feedback(model,candidate,evaluation)
                else:
                    feedback=add_assignment_feedback(model,candidate,evaluation)
            feedback['completed_at_elapsed_s']=budget.elapsed
            feedback['within_budget']=budget.elapsed<budget.seconds
            result.setdefault('feedback' if feedback['within_budget'] else 'late_feedback_diagnostics',[]).append(feedback)
            budget.check()
            if not feedback['rows_added']:
                result['reason']='FEEDBACK_UNRESOLVED';break
        else:
            result['reason']='OUTER_ROUND_LIMIT'
    except Exhausted as error:
        result['reason']=str(error)
    except MemoryError:
        result['reason']='RESOURCE_LIMIT'
    except Exception as error:
        result.update(reason='INTERFACE_ERROR',error=f'{type(error).__name__}: {error}')
    finally:
        native.event_consumer=None
        # A final evaluation may exhaust the budget after a genuine native
        # result was returned. Retain that exact existing round, once only.
        known={id(r) for r in result['rounds']}
        for record in adapter.records:
            returned=record.native_result
            if returned is not None and id(returned) not in known:
                result['rounds'].append(returned)
                known.add(id(returned))
        result['diagnostic']=summarize(adapter)
        committed=[r.best for r in adapter.records if r.best is not None]
        best=min(committed,key=lambda r:Fraction(r['evaluation']['safe_upper_bound_J'])) if committed else None
        if best is not None:
            result.update(state='SAFE',safe_candidate=best['candidate'],
                safe_upper_bound_J=best['evaluation']['safe_upper_bound_J'],evaluation=best['evaluation'])
        result['elapsed_s']=budget.elapsed
    return result


@contextmanager
def install_projection(entry, folder):
    """Dedicated process hooks, restored on exit; repository bytes unchanged."""
    import formal_milp
    import method_runner
    import matlab_bridge
    original_solver=formal_milp.solve_formal_diagnostic
    original_factory=entry.base.native_session_factory
    original_budget=method_runner.MethodBudget
    original_prefs=matlab_bridge.REPO
    samples=[]
    class ResourceBudget(original_budget):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.resource_last=-1.
        def check(self):
            super().check()
            if self.elapsed-self.resource_last>=1:
                available=psutil.virtual_memory().available
                samples.append(dict(elapsed_s=self.elapsed,available_memory_bytes=available))
                self.resource_last=self.elapsed
                if available<2*1024**3:
                    raise MemoryError('Original 2GiB resource gate')
    def factory(plan):
        create=entry.repaired._native_factory_original(plan)
        def launch(*args,**kwargs):
            from research.chapter3_method_entry_executor.monitor import default_host_probe,host_gate
            budget=kwargs['budget']
            probe=default_host_probe(entry.base.ROOT)
            gate=host_gate(probe)
            if not gate['passed']:
                raise MemoryError('Pre-native resource/identity gate')
            entry.base.save(Path(folder)/'native_launch_notice.json',dict(
                utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                root_start=budget.start,root_deadline=budget.deadline,elapsed_s=budget.elapsed,
                host=probe,gate=gate))
            session=create(*args,**kwargs)
            try:
                available=psutil.virtual_memory().available
                entry.base.save(Path(folder)/'host_ready.json',dict(available_memory_bytes=available,
                    elapsed_s=budget.elapsed,native_session=str(session.workdir)))
                if available<2*1024**3:
                    raise MemoryError('After-ready 2GiB resource gate')
                budget.check()
                return session
            except BaseException as error:
                session.close()
                error.matlab_cleanup=session.cleanup
                raise
        return launch
    formal_milp.solve_formal_diagnostic=solve_projected_diagnostic
    entry.base.native_session_factory=factory
    method_runner.MethodBudget=ResourceBudget
    matlab_bridge.REPO=Path(__file__).resolve().parent
    try:
        yield
    finally:
        formal_milp.solve_formal_diagnostic=original_solver
        entry.base.native_session_factory=original_factory
        method_runner.MethodBudget=original_budget
        matlab_bridge.REPO=original_prefs
        entry.base.save(Path(folder)/'projection_resource_samples.json',samples)
