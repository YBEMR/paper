"""Scoped numerical binding and post-accept cache commits; original ON-P executes."""
from contextlib import contextmanager
from copy import deepcopy
import json,time
from runtime import SceneReuse,IdentityError,RootClosed,digest,semantic
from prefix import PrefixReuse
from support import integration_identity

class Bridge:
    def __init__(self,thermal,budget,arm,stream=None):
        self.t,self.budget,self.arm,self.stream=thermal,budget,arm,stream
        self.original=thermal.evaluate_candidate;self.reuse=None
        self.records=[];self.assessments=[];self.candidate_sources={};self.owner=None
        self.observer_s=0.0;self.accept_cache_s=0.0;self.commit_count=0
    def configure(self,instance,config):
        if self.reuse is not None:raise IdentityError('SECOND_INPUT_LOAD')
        cls=PrefixReuse if self.arm=='C' else SceneReuse
        self.reuse=cls(self.t,instance,config,self.budget,digest(integration_identity()),enabled=self.arm!='A')
    def emit(self,x):
        if self.stream:self.stream.write(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n');self.stream.flush()
    def __call__(self,instance,candidate,accuracy,budget):
        if self.reuse is None or budget is not self.budget:raise IdentityError('UNCONFIGURED_OR_FOREIGN_ROOT')
        if digest(instance)!=self.reuse.identity[0] or accuracy!=self.reuse.config['accuracy_targets']:
            raise IdentityError('CALL_INPUT_OR_ACCURACY_DRIFT')
        row={'ordinal':len(self.records)+1,'candidate_sha256':digest(candidate),'start_s':budget.elapsed,
          'phase':self.owner.phase if self.owner else None,'state':'STARTED',
          'before_panels':budget.panels,'before_extrema':budget.extremum_calls,'before_refinements':budget.refinements}
        self.records.append(row);self.emit({'event':'EVALUATION_START',**row})
        original_exposed=self.t.evaluate_candidate
        try:
            # Identity guard sees Bridge, while the reused wrapper delegates to
            # the captured original and patches only the original scene boundary.
            self.t.evaluate_candidate=self.original
            result=self.reuse.evaluate(candidate)
            row.update(state=result['state'],complete_at_s=result.get('completed_at_elapsed_s'),
              semantic_sha256=digest(semantic(result)),provenance=deepcopy(result.get('reuse_provenance',[])),
              energy_J=deepcopy(result.get('weighted_energy_J')),receipt_identity=deepcopy(result.get('evidence_identity')))
            return result
        except BaseException as error:
            row.update(state='INTERRUPTED',error_type=type(error).__name__,reason=str(error))
            raise
        finally:
            self.t.evaluate_candidate=original_exposed
            row.update(returned_s=budget.elapsed,new_panels=budget.panels-row['before_panels'],
              new_extrema=budget.extremum_calls-row['before_extrema'],new_refinements=budget.refinements-row['before_refinements'])
            self.emit({'event':'EVALUATION_RETURN',**row})
    def accepted(self,row):
        began=time.perf_counter();key=row['candidate_sha256']
        if not row.get('cache_hit'):
            if not self.records or self.records[-1]['candidate_sha256']!=key or self.records[-1]['state']!='SAFE':
                raise IdentityError('NO_CURRENT_ACCEPTED_NUMERICAL_COMPONENT')
            self.reuse.commit(row['receipt']);self.commit_count+=1
            if self.arm=='C':self.candidate_sources[key]=dict(self.reuse.current_sources)
        if self.arm=='C' and row['incumbent_replaced']:
            if key not in self.candidate_sources:raise IdentityError('NO_CERTIFIED_INCUMBENT_CHECKPOINTS')
            self.reuse.current_sources=dict(self.candidate_sources[key]);self.reuse.promote()
        self.accept_cache_s+=time.perf_counter()-began

@contextmanager
def installed(thermal,blocking,onp,bridge):
    original_class=blocking.CompleteRecorder;original_source=onp.source_identity
    old_evaluator=thermal.evaluate_candidate;old_block_source=blocking.source_identity
    class Recorder(original_class):
        def __init__(self,*a,**k):
            super().__init__(*a,**k);bridge.owner=self
        def _commit(self,row):
            super()._commit(row)  # Unmodified initialization/refinement rules.
            bridge.accepted(row) # Only after the original full SAFE acceptance.
        def assess(self,candidate,source):
            if bridge.reuse.closed_reason is not None:raise RootClosed(bridge.reuse.closed_reason)
            start=self.budget.elapsed;count=len(self.rows);before=dict(bridge.reuse.metrics);problem=None
            try:return super().assess(candidate,source)
            except BaseException as error:
                problem={'type':type(error).__name__,'reason':str(error)}
                from research.chapter4_scheduler.i1.admission import AdmissionClosed
                if not isinstance(error,AdmissionClosed):
                    bridge.reuse.closed_reason='ROOT_STOP_AFTER_'+str(error)
                raise
            finally:
                began=time.perf_counter();fresh=self.rows[count:]
                record={'ordinal':len(bridge.assessments)+1,'candidate_sha256':digest(candidate),
                  'phase':self.phase,'source':source,'start_s':start,'end_s':self.budget.elapsed,
                  'cache_delta':{k:bridge.reuse.metrics[k]-before.get(k,0) for k in bridge.reuse.metrics},
                  'error':problem,'recorded':bool(fresh)}
                if fresh:
                    row=fresh[-1];record.update(accepted_safe=row['accepted_safe'],
                      incumbent_replaced=row['incumbent_replaced'],full_hash_hit=row.get('cache_hit',False),
                      state=row['receipt']['state'],energy=deepcopy(row.get('energy')))
                bridge.assessments.append(record);bridge.emit({'event':'ASSESSMENT_END',**record})
                bridge.observer_s+=time.perf_counter()-began
    def sources():return original_source()|integration_identity()
    blocking.CompleteRecorder=Recorder;onp.source_identity=sources;blocking.source_identity=sources;thermal.evaluate_candidate=bridge
    try:yield
    finally:
        blocking.CompleteRecorder=original_class;onp.source_identity=original_source;blocking.source_identity=old_block_source;thermal.evaluate_candidate=old_evaluator
