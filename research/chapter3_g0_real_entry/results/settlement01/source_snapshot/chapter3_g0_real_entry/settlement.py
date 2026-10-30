"""Control-only cancellation settlement. Never evaluates a solver vector."""
from copy import deepcopy
import hashlib
import json
import time

PROFILE='phase_public_startup_bounded_settlement_v1'
RULE={'profile':'bounded_cancel_drain_v1','max_seconds':10,'late_candidate_admission':False}

def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

class BoundedSettlement:
    def enable_bounded_settlement(self):
        if getattr(self,'counter',0) or getattr(self,'settlement_enabled',False):
            raise ValueError('SETTLEMENT_MUST_BE_CONFIGURED_ONCE_BEFORE_REQUESTS')
        self.settlement_enabled=True
        self.pending_settlement=None;self.settlement_fault=None;self.settlement_records=[]

    def note_request_return(self,returned,previous,scope,deadline):
        if not getattr(self,'settlement_enabled',False):return
        status=returned.get('status')
        if status=='BUDGET_EXHAUSTED_BEFORE_PUBLICATION':
            # The old bridge already reserved N; worker still waits for N.
            self.settlement_fault='UNPUBLISHED_RESERVED_SEQUENCE_STOP'
            self.request_blocked=True;self.request_settled=False
            return
        if status!='BUDGET_EXHAUSTED' or not returned.get('response_may_arrive_later'):return
        prefix=self.workdir/f'request_{self.counter:06d}'
        if (self.counter!=previous+1 or not prefix.with_suffix('.request.json').is_file()
                or not prefix.with_suffix('.cancel').is_file()):
            self.settlement_fault='CANCELLED_REQUEST_IDENTITY_UNVERIFIED';return
        self.pending_settlement=dict(number=self.counter,prefix=str(prefix),scope=deepcopy(scope),
            root_identity=deepcopy(self.budget.root_identity),request_sha256=file_sha(prefix.with_suffix('.request.json')),
            evidence_deadline_s=deadline,cancel_observed_s=self.budget.elapsed,
            # Conservative: expiry boundary precedes the observed cancel write.
            drain_deadline_s=min(float(self.budget.seconds),deadline+RULE['max_seconds']))
        self.request_blocked=True;self.request_settled=False

    def _settlement_owner(self):
        if self.closed or self.proc is None or self.proc.poll() is not None:
            raise RuntimeError('SETTLEMENT_WORKER_NOT_ALIVE')
        observed=self.dependencies['capture_tree'](self.proc,phase='settlement')
        expected=self.process_tree.get('root_identity')
        if (not expected or observed.get('root_identity')!=expected
                or observed.get('root_identity_verified') is not True):
            raise RuntimeError('SETTLEMENT_PROCESS_IDENTITY_CONFLICT')

    @staticmethod
    def _normal_cancel_response(value):
        if not isinstance(value,dict) or value.get('callback_error') or value.get('numerical_consistency'):
            return False
        if value.get('status')=='SOLVED':
            flag=value.get('exitflag')
            return (type(flag) in (int,float) and flag in (-1,0)
                    and not value.get('error_identifier') and not value.get('error_message'))
        return (value.get('status')=='BUDGET_EXHAUSTED_BEFORE_SOLVER'
                and value.get('intlinprog_entered') is False
                and value.get('error_identifier','') in ('','chapter3:requestReadCancelled'))

    def settle_pending(self,budget):
        if budget is not self.budget:raise ValueError('SETTLEMENT_ROOT_MISMATCH')
        if not getattr(self,'settlement_enabled',False):raise RuntimeError('SETTLEMENT_PROFILE_DISABLED')
        if self.settlement_fault:raise RuntimeError(self.settlement_fault)
        pending=self.pending_settlement
        if pending is None:
            if not self.is_idle():raise RuntimeError('UNEXPLAINED_UNSETTLED_WORKER')
            return {'outcome':'ALREADY_IDLE','late_candidate_admitted':False}
        if self.event_consumer is not None:raise RuntimeError('SETTLEMENT_CALLBACK_CONSUMER_STILL_ATTACHED')
        if pending['root_identity']!=budget.root_identity or self.counter!=pending['number']:
            raise RuntimeError('SETTLEMENT_PENDING_IDENTITY_CONFLICT')
        prefix=__import__('pathlib').Path(pending['prefix'])
        if prefix!=self.workdir/f'request_{self.counter:06d}':raise RuntimeError('SETTLEMENT_PREFIX_CONFLICT')
        record=dict(number=self.counter,started_s=budget.elapsed,deadline_s=pending['drain_deadline_s'],
            parent_scope=budget.capture_scope(),late_candidate_admitted=False,outcome='WAITING')
        self.settlement_records.append(record);verified=False
        try:
            self._settlement_owner()
            while True:
                budget.check()
                if budget.elapsed>=pending['drain_deadline_s']:raise RuntimeError('SETTLEMENT_TIME_LIMIT')
                if (not prefix.with_suffix('.cancel').is_file()
                        or file_sha(prefix.with_suffix('.request.json'))!=pending['request_sha256']
                        or (self.workdir/'stop').exists()
                        or (self.workdir/f'request_{self.counter+1:06d}.request.json').exists()):
                    raise RuntimeError('SETTLEMENT_PUBLICATION_IDENTITY_CONFLICT')
                if self.proc.poll() is not None:raise RuntimeError('SETTLEMENT_WORKER_EXITED')
                try:
                    raw=prefix.with_suffix('.response.json').read_bytes()
                    value=json.loads(raw.decode('utf-8-sig'))
                except (FileNotFoundError,PermissionError,UnicodeDecodeError,json.JSONDecodeError):
                    pause=min(.005,budget.remaining,max(0,pending['drain_deadline_s']-budget.elapsed))
                    self.dependencies.get('sleep',time.sleep)(pause);continue
                budget.check()
                if budget.elapsed>=pending['drain_deadline_s']:raise RuntimeError('SETTLEMENT_TIME_LIMIT')
                if not self._normal_cancel_response(value):raise RuntimeError('SETTLEMENT_NATIVE_STATE_NOT_WHITELISTED')
                self._settlement_owner()
                record.update(response_sha256=hashlib.sha256(raw).hexdigest(),outcome='CONTROL_SETTLED_LATE_NO_ADMISSION')
                # Archive inside the same root before making the queue reusable.
                self.dependencies['write_json'](prefix.with_suffix(f'.settlement_{len(self.settlement_records):03d}.json'),record)
                budget.check()
                if budget.elapsed>=pending['drain_deadline_s']:raise RuntimeError('SETTLEMENT_TIME_LIMIT')
                verified=True;break
        except BaseException as error:
            record.update(outcome='NOT_SETTLED',error_type=type(error).__name__,error=str(error))
            raise
        finally:
            record['finished_s']=budget.elapsed
            self.dependencies['write_json'](prefix.with_suffix(f'.settlement_{len(self.settlement_records):03d}.json'),record)
            # A slow final control receipt must not silently unlock after cutoff.
            if verified:
                budget.check()
                if budget.elapsed>=pending['drain_deadline_s']:raise RuntimeError('SETTLEMENT_TIME_LIMIT')
        self.pending_settlement=None;self.request_blocked=False;self.request_settled=True
        return deepcopy(record)
