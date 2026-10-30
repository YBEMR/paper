"""Scope-aware version of C's augmented numerical transport lifecycle.

Only lifecycle/cutoff classification changes. The selected exact-row
transformation, original-prefix projection, matrix and objective admission
use the original helpers. No thermal or optimization work runs on import.
"""
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys

from research.chapter3_g0.budget import ScopeExhausted
from .gating import require_permit,require_simulation_dependencies

PROTOCOL='g0-scope-aware-original-prefix-transport-v1'


def _legacy():
    folder=Path(__file__).resolve().parents[1]/'chapter3_experiments'
    if str(folder) not in sys.path:
        sys.path.insert(0,str(folder))
    module=importlib.import_module('augmented_method')
    if Path(module.__file__).resolve()!=folder/'augmented_method.py':
        raise ImportError('unexpected augmented helper source')
    return module


def production_dependencies(permit):
    if require_permit(permit)!='REAL':
        raise PermissionError('approved REAL permit required for production helpers')
    old=_legacy()
    return dict(transform=old.build_live_augmented_payload,
        validate=old.validate_projected_vector,append=old.append_complements,
        matrix_identity=old.matrix_identity,recorder_base=old.PartialRecorder,
        vector_present=old.vector_present,np=old.np,
        conflict_state=old.NUMERICAL_CONSISTENCY_CONFLICT)


def _save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)


class _ScopedRequest:
    def __init__(self,context,recorder,original,augmented,mapping,folder,labels):
        self.context,self.recorder,self.budget=context,recorder,context.budget
        self.original,self.augmented,self.mapping=original,augmented,mapping
        self.folder,self.prefix=folder,None
        self.events,self.checks,self.seen_callbacks=[],[],set()
        self.receipt=dict(request_index=len(context.requests)+1,protocol=PROTOCOL,
            prepared_at_s=self.budget.elapsed,failure_reasons=[],cutoffs=[],events=self.events,
            numerical_checks=self.checks,thermal_safe_claim=False,independent_certificate=False,
            label_sha256=hashlib.sha256(json.dumps(labels,sort_keys=True,separators=(',',':')).encode()).hexdigest())

    def cancel(self,reason):
        if self.prefix is not None and not self.receipt.get('cancel_requested'):
            try:
                self.prefix.with_suffix('.cancel').write_text(reason+'\n',encoding='ascii')
                self.receipt.update(cancel_requested=True,cancel_published_at_s=self.budget.elapsed)
            except OSError as error:
                self.receipt['cancel_error']=f'{type(error).__name__}: {error}'

    def fail(self,reason):
        if reason not in self.receipt['failure_reasons']:
            self.receipt['failure_reasons'].append(reason)
        self.context.fail(reason)
        self.cancel('g0 numerical admission unresolved')

    def cutoff(self,error=None,where='numerical_admission'):
        item=self.context.note_cutoff(error,where)
        self.receipt['cutoffs'].append(deepcopy(item))
        self.cancel('g0 scope cutoff')

    def assess_vector(self,vector,source,*,objective=None,require_objective=False):
        record=dict(source=source,started_at_s=self.budget.elapsed,accepted=False)
        self.checks.append(record)
        try:
            self.budget.check()
        except ScopeExhausted as error:
            self.cutoff(error,'before_numerical_admission');return None
        projected=None
        try:
            with self.budget.phase('augmented_numerical_admission'):
                projected,report=self.context.helpers['validate'](
                    vector,self.original,self.augmented,self.mapping)
                record['report']=deepcopy(report)
                if require_objective or objective is not None:
                    calculated=(report.get('original') or {}).get('objective')
                    np=self.context.helpers['np']
                    try:
                        raw=np.asarray(objective);value=np.asarray(objective,dtype=float).reshape(-1)
                        valid=(not np.iscomplexobj(raw) and value.size==1 and np.isfinite(value).all()
                               and calculated is not None)
                        tolerance=None if calculated is None else 1e-9*max(1.,abs(calculated))
                        consistent=bool(valid and abs(float(value[0])-calculated)<=tolerance)
                    except (TypeError,ValueError,OverflowError):
                        consistent,tolerance=False,None
                    record['objective_check']=dict(consistent=consistent,original_c_dot_x=calculated,
                        engineering_tolerance=tolerance,independent_energy_or_bound_claim=False)
                    if not consistent:
                        self.fail('NATIVE_OBJECTIVE_MISSING_OR_MISMATCH')
                if not report['accepted']:
                    self.fail('ORIGINAL_OR_AUGMENTED_NUMERICAL_CHECK_FAILED')
        except ScopeExhausted as error:
            self.cutoff(error,'during_numerical_admission')
        except Exception as error:
            record['error']=f'{type(error).__name__}: {error}'
            self.fail('NUMERICAL_ADMISSION_EXCEPTION')
        record.update(completed_at_s=self.budget.elapsed,within_budget=self.budget.remaining>0)
        if not record['within_budget']:
            self.cutoff(where='after_numerical_admission')
        record['accepted']=bool(projected is not None and record['within_budget'] and not self.context.failed)
        return projected if record['accepted'] else None

    def archive(self):
        self.receipt.update(latched_unresolved=self.context.failed,completed_at_s=self.budget.elapsed,
                            within_budget=self.budget.remaining>0)
        _save(self.folder/'admission.json',self.receipt)


class ScopeAwareContext:
    def __init__(self,budget,*,permit,dependencies=None):
        require_permit(permit)
        require_simulation_dependencies(permit,dependencies)
        if dependencies is None:
            dependencies=production_dependencies(permit)
        keys=('transform','validate','append','matrix_identity','recorder_base','vector_present','np','conflict_state')
        if any(k not in dependencies for k in keys):
            raise ValueError('explicit augmented helper set incomplete')
        self.budget,self.permit,self.helpers=budget,permit,dict(dependencies)
        self.recorder=self.current=None
        self.requests,self.failure_reasons,self.cutoffs=[],[],[]
        self.failed=False

    def fail(self,reason):
        self.failed=True
        if reason not in self.failure_reasons:
            self.failure_reasons.append(reason)

    def note_cutoff(self,error=None,where='transport'):
        if error is None:
            try:
                self.budget.check()
            except ScopeExhausted as caught:
                error=caught
        item=dict(kind=getattr(error,'kind','scope'),where=where,root_elapsed_s=self.budget.elapsed,
                  new_numerical_or_thermal_admission=False)
        self.cutoffs.append(item)
        return item

    def recorder_factory(self,*args,**kwargs):
        base=self.helpers['recorder_base']
        recorder_type=type('G0ScopedAugmentedRecorder',(ScopedRecorderMixin,base),{})
        self.recorder=recorder_type(self,*args,**kwargs)
        return self.recorder

    def prepare(self,payload):
        if self.failed:
            raise ValueError('latched numerical admission failure')
        recorder=self.recorder
        if recorder is None or recorder.model is None or recorder.budget is not self.budget:
            raise ValueError('same-budget current model recorder required')
        self.budget.check()
        labels=dict(names=list(recorder.model.names),row_tags=[r['tag'] for r in recorder.model.rows])
        with self.budget.phase('augmented_payload_transform'):
            augmented,mapping=self.helpers['transform'](payload,labels)
        self.budget.check()
        folder=recorder.folder/'augmented_requests'/f'request_{len(self.requests)+1:06d}'
        with self.budget.phase('augmented_request_metadata'):
            folder.mkdir(parents=True,exist_ok=False)
            request=_ScopedRequest(self,recorder,payload,augmented,mapping,folder,labels)
            _save(folder/'mapping.json',mapping);_save(folder/'labels.json',labels)
            _save(folder/'matrix_identities.json',dict(original=self.helpers['matrix_identity'](payload),
                augmented=self.helpers['matrix_identity'](augmented)))
        self.current=request;self.requests.append(request.receipt);recorder.request=request
        self.budget.check()
        return request

    def summary(self):
        return dict(protocol=PROTOCOL,latched_unresolved=self.failed,failure_reasons=list(self.failure_reasons),
            cutoffs=deepcopy(self.cutoffs),requests=deepcopy(self.requests),
            original_rows_required_for_every_candidate=True,thermal_safe_claim=False,
            independent_certificate=False,numerical_helpers='unchanged existing C helpers')


class ScopedRecorderMixin:
    def __init__(self,context,*args,**kwargs):
        self.context,self.request=context,None
        super().__init__(*args,**kwargs)
        if self.budget is not context.budget:
            raise ValueError('recorder requires same root budget')

    def assess(self,vector,source,*,reported_objective=None,require_objective=False):
        if self.request is None:
            self.context.fail('CANDIDATE_WITHOUT_CURRENT_REQUEST');return None,None
        projected=self.request.assess_vector(vector,source,objective=reported_objective,
                                             require_objective=require_objective)
        if projected is None:
            return None,None
        values=projected.tolist() if hasattr(projected,'tolist') else list(projected)
        return super().assess(values,source)

    def poll(self,prefix):
        prefix=Path(prefix)
        if self.request is None:
            self.context.fail('CALLBACK_WITHOUT_CURRENT_REQUEST');return
        request=self.request;request.prefix=prefix
        if self.context.failed:
            request.fail(self.context.failure_reasons[-1]);return
        previous,self.current_prefix=self.current_prefix,prefix
        try:
            self.budget.check()
            number=self.next_event.get(str(prefix),1)
            while self.budget.remaining>0:
                path=Path(f'{prefix}.event_{number:06d}.json')
                try:
                    event=json.loads(path.read_text(encoding='utf-8-sig'))
                except (FileNotFoundError,PermissionError,UnicodeDecodeError,json.JSONDecodeError):
                    break
                self.budget.check()
                self.next_event[str(prefix)]=number+1;self.event_count+=1
                if (not isinstance(event,dict) or isinstance(event.get('event_number'),bool)
                        or not isinstance(event.get('event_number'),int) or event['event_number']!=number):
                    request.fail('CALLBACK_EVENT_IDENTITY_MISMATCH');break
                stamp=self.budget.elapsed
                row={k:v for k,v in event.items() if k!='x'}
                row.update(event='worker_event_received',method_elapsed_s=stamp,request=prefix.name,evidence='solver-reported')
                self.progress.append(row)
                if event.get('kind')=='solver_entered' and self.solver_entered_s is None:
                    self.solver_entered_s=stamp
                request.events.append(dict(number=number,kind=event.get('kind'),received_at_s=stamp,
                    file=path.name,file_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                if event.get('kind')=='callback':
                    request.seen_callbacks.add(number)
                self.log(row)
                if self.context.helpers['vector_present'](event.get('x')):
                    values=event.get('values',{})
                    if not isinstance(values,dict):
                        request.fail('CALLBACK_VALUES_NOT_AN_OBJECT')
                    else:
                        self.assess(event['x'],f'{prefix.name}:event{number}',
                            reported_objective=values.get('fval'),require_objective='fval' in values)
                number+=1
                if self.context.failed:
                    break
            if self.budget.remaining<=0:
                request.cutoff(where='callback_poll')
        except ScopeExhausted as error:
            request.cutoff(error,'callback_poll')
        except Exception:
            request.fail('CALLBACK_PROCESSING_EXCEPTION');raise
        finally:
            self.current_prefix=previous

    def summary(self):
        out=super().summary();out['augmented_transport']=self.context.summary();return out

    def release(self):
        request=self.request
        if self.context.current is request:self.context.current=None
        if self.context.recorder is self:self.context.recorder=None
        self.request=None
        if request is not None:request.recorder=None
        return super().release()


class ScopedAugmentedSession:
    def __init__(self,native,context):
        self.session,self.context=native,context
        self._consumer=getattr(native,'event_consumer',None)

    def __getattr__(self,name):
        return getattr(self.session,name)

    @property
    def event_consumer(self):return self._consumer

    @event_consumer.setter
    def event_consumer(self,value):
        self._consumer=value;self.session.event_consumer=value

    @property
    def request_blocked(self):
        return self.context.failed or getattr(self.session,'request_blocked',False)

    def _result(self,returned,request=None):
        result=dict(returned)
        if request is not None:result['augmented_admission']=deepcopy(request.receipt)
        if self.context.failed:
            result.update(accepted_for_evaluation=False,numerical_consistency=dict(
                state=self.context.helpers['conflict_state'],protocol=PROTOCOL,
                reasons=list(self.context.failure_reasons),native_consistency=result.get('numerical_consistency')))
        elif self.context.cutoffs and (request is None or request.receipt['cutoffs']):
            result['native_candidate_diagnostic']=deepcopy(result.get('x',[]))
            result.update(x=[],accepted_for_evaluation=False,g0_scope_cutoff=deepcopy(self.context.cutoffs[-1]))
        return result

    def solve(self,payload,**kwargs):
        if self.context.failed:
            return self._result(dict(status='NUMERICAL_ADMISSION_BLOCKED',budget_valid=False,x=[]))
        request=None;native_started=False;native_returned=False
        returned=dict(status='G0_AUGMENTED_UNRESOLVED',budget_valid=False,x=[],accepted_for_evaluation=False)
        try:
            request=self.context.prepare(payload)
            if kwargs.get('budget',request.budget) is not request.budget:
                raise ValueError('augmented transport requires identical root budget')
            if kwargs.get('x0') is not None:
                kwargs['x0']=self.context.helpers['append'](kwargs['x0'],request.mapping)
                if request.assess_vector(kwargs['x0'],'request_initial_point') is None:
                    if self.context.failed:return self._result(returned,request)
                    request.archive();return self._result(returned,request)
            request.budget.check();native_started=True
            returned=self.session.solve(request.augmented,**kwargs);native_returned=True
            if (returned.get('numerical_consistency') or {}).get('state')==self.context.helpers['conflict_state']:
                request.fail('NATIVE_NUMERICAL_CONSISTENCY_CONFLICT')
            request.receipt.update(native_status=returned.get('status'),native_exitflag=returned.get('exitflag'),
                                   solver_reported_only=True)
            if request.budget.remaining<=0:
                request.cutoff(where='before_final_admission')
            else:
                prefix=request.prefix or Path(self.session.workdir)/f'request_{getattr(self.session,"counter",0):06d}'
                request.prefix=prefix;request.recorder.poll(prefix)
                callbacks=returned.get('callbacks',[]);expected=[]
                if not isinstance(callbacks,list):
                    request.fail('CALLBACK_RESPONSE_NOT_A_LIST')
                else:
                    for callback in callbacks:
                        value=callback.get('event_number') if isinstance(callback,dict) else None
                        if isinstance(value,bool) or not isinstance(value,int) or value<1 or value in expected:
                            request.fail('CALLBACK_RESPONSE_IDENTITY_INVALID')
                        else:expected.append(value)
                complete=set(expected)==request.seen_callbacks
                if returned.get('intlinprog_entered') and not any(e['kind']=='solver_entered' for e in request.events):
                    complete=False
                request.receipt.update(expected_callback_numbers=sorted(expected),
                    checked_callback_numbers=sorted(request.seen_callbacks),callback_publications_complete=complete)
                if not complete:
                    if request.budget.remaining<=0:request.cutoff(where='callback_publications_incomplete')
                    else:request.fail('CALLBACK_PUBLICATIONS_NOT_FULLY_CHECKED')
                if self.context.helpers['vector_present'](returned.get('x')):
                    projected=request.assess_vector(returned['x'],'final_return',
                        objective=returned.get('fval'),require_objective=True)
                    if projected is not None:
                        # Keep the immutable native augmented vector at this
                        # interface. The recorder projects it once on its way
                        # to the original decoder/evaluator, as in old C.
                        returned=dict(returned);returned['original_prefix_admitted']=True
            request.archive()
            if request.budget.remaining<=0 and not request.receipt['cutoffs']:
                request.cutoff(where='during_admission_archive');request.archive()
            return self._result(returned,request)
        except ScopeExhausted as error:
            if request is None:self.context.note_cutoff(error,'transport_prepare')
            else:
                request.cutoff(error,'transport');request.archive()
            if native_started and not native_returned:
                self.session.request_blocked=True
            return self._result(returned,request)
        except Exception as error:
            self.context.fail('AUGMENTED_TRANSPORT_EXCEPTION')
            if request is not None:
                request.fail('AUGMENTED_TRANSPORT_EXCEPTION')
                request.receipt['exception']=f'{type(error).__name__}: {error}'
                try:request.archive()
                except Exception:pass
            if native_started and not native_returned:self.session.request_blocked=True
            returned=dict(returned);returned['error']=f'{type(error).__name__}: {error}'
            return self._result(returned,request)

    def is_idle(self):
        return not self.context.failed and self.session.is_idle()

    def close(self):
        self.event_consumer=None
        return self.session.close()
