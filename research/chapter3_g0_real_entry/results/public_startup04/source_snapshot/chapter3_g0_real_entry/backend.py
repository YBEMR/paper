"""Same-call G0 backend binding; no native work at construction or import.

The production functions are lazily named, not executed by this release.
SIMULATION uses explicit fakes; REAL accepts only frozen production functions.
"""
from copy import deepcopy
from pathlib import Path
import importlib
import sys
import time

from .gating import require_permit, require_simulation_dependencies
from . import model_backend
from .receipts import RealArchive, RealReceiptBridge, receipt_source_identity
from .session import ScopedMatlabSession
from .numeric_transport import ScopeAwareContext, ScopedAugmentedSession
from ..chapter3_g0.budget import ScopeExhausted
from .execution_costs import LEGACY,PUBLIC,startup_cost


class StartupCutoff(Exception):
    g0_normal_startup_cutoff=True
    def __init__(self,error,cleanup_verified):
        self.kind=error.kind
        self.cleanup_verified=cleanup_verified
        super().__init__(self.kind.upper()+'_STARTUP_CUTOFF')


def cleanup_verified(receipt):
    return bool(isinstance(receipt,dict) and receipt.get('observed_tree_verified_terminated')
                and receipt.get('cleanup_status') in ('graceful_closed','forced_closed'))


def production_dependencies(permit):
    if require_permit(permit)!='REAL':
        raise PermissionError('REAL_BACKEND_REQUIRES_SEPARATE_RESEARCH_APPROVAL')
    folder=Path(__file__).resolve().parents[1]/'chapter3_experiments'
    if str(folder) not in sys.path:
        sys.path.insert(0,str(folder))
    from .receipts import production_dependencies as receipt_dependencies
    from partial_method import PartialRecorder
    from heft_method import run_heft
    from milp import evaluate_model_candidate
    from formal_milp import _checked_thermal_witnesses
    return dict(initializer=run_heft,receipt=None,model=None,evaluation=None,
                transport=None,numeric=None,recorder_factory=PartialRecorder,
                evaluate_model_candidate=evaluate_model_candidate,witness_validator=_checked_thermal_witnesses)


class G0Backend:
    def __init__(self,workdir,*,permit,dependencies=None,execution_organization=LEGACY):
        if execution_organization not in (LEGACY,PUBLIC):raise ValueError('UNKNOWN_EXECUTION_ORGANIZATION')
        self.execution_organization=execution_organization
        self.evidence_kind=require_permit(permit)
        if self.evidence_kind=='REAL' and execution_organization!=permit.context.get('plan',{}).get('execution_organization'):
            raise PermissionError('BACKEND_EXECUTION_ORGANIZATION_DRIFT')
        require_simulation_dependencies(permit,dependencies)
        if dependencies is None:
            dependencies=production_dependencies(permit)
        required=('initializer','receipt','model','evaluation','transport','numeric',
                  'recorder_factory','evaluate_model_candidate','witness_validator')
        if not isinstance(dependencies,dict) or any(k not in dependencies for k in required):
            raise ValueError('complete explicit wiring dependencies required')
        self.workdir=Path(workdir);self.permit=permit;self.dependencies=dict(dependencies)
        self.receipt_dependencies=self.dependencies['receipt']
        self.session=None;self.numeric_context=None
        self.bridge=self.archive=self.budget=self.config=self.instance=None
        self.timings={};self.search_records=[];self.startup_failure=None
        self.session_state='NOT_ATTEMPTED';self.session_attempts=0
        self.public_start_records=[];self.startup_accounting=None

    @property
    def source_hashes(self):
        # Read when the coordinator creates its archive, inside the root clock.
        return receipt_source_identity()

    def attach_context(self,config,instance,budget,archive,bridge):
        budget.check()
        self.config,self.instance,self.budget=config,instance,budget
        self.archive,self.bridge=archive,bridge
        if self.evidence_kind == 'REAL':
            from .persistence import CheckpointStore
            archive._checkpoint_writer=CheckpointStore(self.workdir/'checkpoints',self.permit,budget,config,instance)

    def initializer(self,instance,config,budget,assess):
        if budget is not self.budget:
            raise ValueError('initializer changed root budget')
        return self.dependencies['initializer'](instance,config,budget,assess,allow_auto_low=True)

    def build(self,config,instance,condition,budget):
        model=model_backend.build(config,instance,condition,budget,
            permit=self.permit,dependencies=self.dependencies['model'])
        # Runtime selection is metadata; never an extra physical/model row.
        model.g0_condition=deepcopy(condition)
        return model

    def _ensure_session(self,budget):
        if self.startup_failure is not None:
            raise RuntimeError('prior startup failed; no restart')
        if self.session is None:
            if self.session_state!='NOT_ATTEMPTED':raise RuntimeError('SESSION_RESTART_FORBIDDEN')
            budget.check()
            started=budget.elapsed
            self.session_state='STARTING';self.session_attempts+=1
            try:
                self.session=ScopedMatlabSession(self.workdir/'matlab',budget=budget,
                    permit=self.permit,dependencies=self.dependencies['transport'],cut_max_iterations=10)
                budget.check()
                if self.session.budget is not budget or not self.session.is_idle():
                    raise RuntimeError('NEW_SESSION_NOT_VERIFIABLY_IDLE')
                self.session_state='READY'
            except BaseException as error:
                self.session_state='FAILED_OR_CUTOFF'
                if self.session is not None:
                    intervals=self.session.metadata.setdefault('startup_intervals',{})
                    intervals['failure_cleanup_start_s']=budget.elapsed
                    try:self.session.close()
                    except Exception as cleanup_error:
                        error.cleanup_error=str(cleanup_error)
                    finally:intervals['failure_cleanup_end_s']=budget.elapsed
                    error.matlab_cleanup=deepcopy(getattr(self.session,'cleanup',None))
                    error.matlab_startup_metadata=deepcopy(getattr(self.session,'metadata',{}))
                self.startup_failure={
                    'error_type':type(error).__name__,'message':str(error),
                    'cleanup':deepcopy(getattr(error,'matlab_cleanup',None)),
                    'metadata':deepcopy(getattr(error,'matlab_startup_metadata',None))}
                cutoff=error if isinstance(error,ScopeExhausted) else None
                if cutoff is None and isinstance(error,TimeoutError):
                    try:budget.check()
                    except ScopeExhausted as timed:cutoff=timed
                if cutoff is not None:
                    raise StartupCutoff(cutoff,cleanup_verified(self.startup_failure['cleanup'])) from error
                raise
            finally:
                self.timings['matlab_startup_seconds']=budget.elapsed-started
                metadata=(getattr(self.session,'metadata',{}) if self.session is not None else
                          (self.startup_failure or {}).get('metadata',{}))
                self.startup_accounting=startup_cost(started,budget.elapsed,metadata)
        budget.check()

    def _require_ready(self,budget):
        if (budget is not self.budget or self.session_state!='READY' or self.session is None
                or self.session.budget is not budget or not self.session.is_idle()
                or self.numeric_context is not None and self.numeric_context.failed):
            raise RuntimeError('SAME_ROOT_READY_IDLE_SESSION_REQUIRED_NO_IMPLICIT_START')
        budget.check()

    def start_public_session(self,budget,*,phase):
        if self.execution_organization!=PUBLIC or budget is not self.budget:
            raise ValueError('PUBLIC_START_PROFILE_OR_ROOT_MISMATCH')
        scope=budget.capture_scope()
        if (scope.get('kind')!='phase' or scope.get('name')!='phase'+str(phase)
                or phase not in (1,2)):
            raise ValueError('PUBLIC_START_REQUIRES_PHASE_NOT_SLOT')
        budget.check()
        item={'phase':phase,'scope':scope,'started_s':budget.elapsed,
              'state_before':self.session_state,'new_attempt':self.session_state=='NOT_ATTEMPTED'}
        self.public_start_records.append(item)
        try:
            if self.session_state=='NOT_ATTEMPTED':self._ensure_session(budget)
            self._require_ready(budget)
            item['outcome']='READY'
        finally:
            item.update(finished_s=budget.elapsed,state_after=self.session_state,
                        session_attempts=self.session_attempts)

    def prepare(self,model,anchor,budget):
        if self.execution_organization==PUBLIC:self._require_ready(budget)
        else:self._ensure_session(budget)
        return model_backend.prepare(model,anchor,budget,self.bridge,permit=self.permit,
            dependencies=self.dependencies['evaluation'])

    def search(self,model,x0,budget,emit):
        if self.session is None or model.budget is not budget or budget is not self.budget:
            raise ValueError('search lacks same-root prepared session')
        phase=model.g0_condition['phase']
        if phase==2:
            if self.numeric_context is None:
                self.numeric_context=ScopeAwareContext(budget,permit=self.permit,
                                                       dependencies=self.dependencies['numeric'])
            transport=ScopedAugmentedSession(self.session,self.numeric_context)
            recorder_factory=self.numeric_context.recorder_factory
        else:
            transport=self.session;recorder_factory=self.dependencies['recorder_factory']
        folder=self.workdir/f'phase{phase}'/model.g0_condition['scene_id']
        folder.mkdir(parents=True,exist_ok=False)
        record=dict(phase=phase,scene=model.g0_condition['scene_id'],rounds=[],feedback=[],
                    evaluations=[],reason=None,started_s=budget.elapsed)
        self.search_records.append(record)

        def remembered(candidate,raw,source):
            record['evaluations'].append({'candidate':deepcopy(candidate),'raw':deepcopy(raw),'source':source})
            # Transfer already formed violation evidence before another check.
            if raw.get('state')=='THERMAL_VIOLATION':
                emit(candidate,self.bridge.bind_model_view(model.instance,candidate,raw))

        def safe(candidate,raw,source):
            emit(candidate,self.bridge.bind_model_view(model.instance,candidate,raw))

        recorder=recorder_factory(model,self.bridge.accuracy,budget,folder,
            model_evaluator=self.dependencies['evaluate_model_candidate'],
            on_evaluation=remembered,on_safe=safe,
            witness_validator=self.dependencies['witness_validator'])
        transport.event_consumer=recorder.poll
        try:
            for iteration in range(50):
                budget.check();recorder.begin_request()
                with budget.phase('matrix_export'):
                    payload=model.as_solver_dict()
                budget.check()
                options=dict(remaining_s=budget.remaining,budget=budget,
                             solver_max_time_s=budget.remaining)
                if iteration==0 and x0 is not None:
                    options['x0']=x0
                returned=transport.solve(payload,**options)
                record['rounds'].append(deepcopy(returned))
                if (returned.get('numerical_consistency') or {}).get('state') in (
                        'NUMERICAL_CONSISTENCY_CONFLICT','SOLVER_NUMERICAL_CONSISTENCY_CONFLICT'):
                    raise ArithmeticError('NATIVE_NUMERICAL_CONSISTENCY_CONFLICT')
                if self.numeric_context is not None and self.numeric_context.failed:
                    raise ArithmeticError('ORIGINAL_AUGMENTED_ADMISSION_CONFLICT')
                budget.check()
                if returned.get('status')!='SOLVED' or returned.get('budget_valid') is not True:
                    raise RuntimeError('NATIVE_INTERFACE_OR_UNSETTLED_RESPONSE')
                candidate=raw=None
                vector=returned.get('x')
                if vector is not None and len(vector):
                    if returned.get('accepted_for_evaluation') is not True:
                        raise ValueError('UNADMITTED_NATIVE_CANDIDATE')
                    candidate,raw=recorder.assess(vector,f'round{iteration+1}:final')
                pending=getattr(recorder,'pending',None)
                if pending is not None:
                    candidate,raw=pending['candidate'],pending['evaluation']
                if raw is None:
                    record['reason']='NO_INTEGER_CANDIDATE';break
                if raw.get('state')=='SAFE':
                    record['reason']='SAFE_RETURNED_CANDIDATE';break
                if raw.get('state')!='THERMAL_VIOLATION':
                    record['reason']='EVALUATION_UNRESOLVED';break
                wrapped=self.bridge.bind_model_view(model.instance,candidate,raw)
                added=model_backend.feedback(model,candidate,wrapped,budget,self.bridge,
                    permit=self.permit,dependencies=self.dependencies['evaluation'])
                record['feedback'].append(deepcopy(added))
                if not (added.get('added') or added.get('rows_added',0)>0):
                    record['reason']='NO_NEW_STRICT_FEEDBACK';break
            if record['reason'] is None:
                record['reason']='DECLARED_ROUND_LIMIT'
        except ScopeExhausted as error:
            record.update(reason=error.kind.upper()+'_CUTOFF',cutoff_kind=error.kind)
            raise
        finally:
            # No numerical admission/evaluation/aggregation is done here.
            transport.event_consumer=None
            if self.session is not None:
                self.session.event_consumer=None
            record['finished_s']=budget.elapsed
            record['recorder']=deepcopy(recorder.summary())
            if hasattr(recorder,'release'):
                recorder.release()
        return deepcopy(record)

    def is_idle(self):
        if self.startup_failure is not None:
            return False
        return ((self.session is None or self.session.is_idle())
                and (self.numeric_context is None or not self.numeric_context.failed))

    def close(self):
        self.session_state='CLOSED'
        if self.session is None:
            return {'required':self.startup_failure is not None,'startup_failure':deepcopy(self.startup_failure),
                    'verified':self.startup_failure is None or cleanup_verified(self.startup_failure.get('cleanup'))}
        started=self.budget.clock()
        try:
            if not self.session.closed:self.session.close()
            cleanup=deepcopy(getattr(self.session,'cleanup',None))
            return {'required':True,'receipt':cleanup,'verified':cleanup_verified(cleanup)}
        finally:
            self.timings['cleanup_seconds']=self.budget.clock()-started


def execute_wiring(input_loader,workdir,*,permit,dependencies=None,seconds=300,clock=time.monotonic,budget=None,
                   execution_organization=LEGACY):
    """Shared coordinator with a single root formed before backend preparation."""
    from types import SimpleNamespace
    from ..chapter3_g0.method import run_g0
    from ..chapter3_g0.budget import G0Budget
    budget=G0Budget(seconds,clock=clock) if budget is None else budget
    require_permit(permit)
    budget.check()
    backend=G0Backend(workdir,permit=permit,dependencies=dependencies,execution_organization=execution_organization)
    wiring=SimpleNamespace(permit=permit,archive_factory=RealArchive,bridge_factory=RealReceiptBridge,
                           execution_organization=execution_organization)
    result=None
    try:
        result=run_g0(input_loader,backend,seconds=seconds,clock=clock,_wiring=wiring,_budget=budget)
    finally:
        close_start=budget.elapsed
        try:
            cleanup=backend.close()
        except Exception as error:
            cleanup={'required':True,'verified':False,'error_type':type(error).__name__,'message':str(error)}
        close_end=budget.elapsed
        if result is not None:
            result['cleanup']=cleanup
            result['backend_timings']=deepcopy(backend.timings)
            result['native_search_records']=deepcopy(backend.search_records)
            result['public_start_records']=deepcopy(getattr(backend,'public_start_records',[]))
            result['session_lifecycle']={'state':getattr(backend,'session_state','UNKNOWN'),
                                        'attempts':getattr(backend,'session_attempts',0)}
            result['execution_timing']={'body_stopped_s':result.get('stopped_s'),
                'final_close':{'start_s':close_start,'end_s':close_end,'seconds':close_end-close_start},
                'observed_elapsed_through_close_s':close_end,
                'root_deadline_elapsed_s':float(seconds),
                'elapsed_after_root_for_cleanup_s':max(0.,close_end-max(close_start,float(seconds))),
                'startup':deepcopy(getattr(backend,'startup_accounting',None)),
                'rule':'startup overview contains its components; final close is a separate actual interval'}
            result['numeric_transport']=None if backend.numeric_context is None else backend.numeric_context.summary()
            if 'budget' in result:
                result['budget']['real_execution_enabled']=require_permit(permit)=='REAL'
            if cleanup.get('verified') is not True:
                result.setdefault('cleanup_errors',[]).append(deepcopy(cleanup))
                if result.get('failure') is None:
                    result['failure']={'kind':'CLEANUP_FAILURE','message':'FINAL_CLEANUP_NOT_CONFIRMED'}
                    result['reason']='CLEANUP_FAILURE'
    return result
