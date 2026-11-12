"""Pure budget allocation and independent-arm policy. No scientific dependencies."""
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
import math


class ResponseDeadline(Exception):
    pass


@dataclass(frozen=True)
class BudgetPolicy:
    total: float
    mode: str
    native_cap: float
    dispatch_reserve: float = 10.0
    validation_reserve: float = 50.0
    minimum_native: float = 30.0

    def __post_init__(self):
        if self.mode not in ('fixed', 'dynamic'): raise ValueError('Unknown policy')
        for value in (self.total,self.native_cap,self.dispatch_reserve,self.validation_reserve,self.minimum_native):
            if isinstance(value,bool) or not math.isfinite(value) or value<=0: raise ValueError('Invalid budget')
        if self.native_cap+self.dispatch_reserve+self.validation_reserve>self.total:
            raise ValueError('Native ceiling cannot fit even with zero preparation')
        if self.minimum_native>self.native_cap:raise ValueError('Minimum native window exceeds cap')

    @property
    def response_cutoff(self): return self.total-self.validation_reserve

    def allocate(self, elapsed):
        if isinstance(elapsed,bool) or not math.isfinite(elapsed) or elapsed<0: raise ValueError('Invalid elapsed time')
        available=self.total-elapsed-self.dispatch_reserve-self.validation_reserve
        if self.mode=='fixed': quota=self.native_cap if available>=self.native_cap else None
        else:
            quota=math.floor(min(self.native_cap,max(0.,available)))
            if quota<self.minimum_native: quota=None
        return dict(can_submit=quota is not None,native_seconds=quota,
                    reason='ALLOCATED' if quota is not None else 'INSUFFICIENT_BUDGET_NO_CALL',
                    measured_elapsed_s=elapsed,response_cutoff_elapsed_s=self.response_cutoff,
                    evidence_cutoff_elapsed_s=self.total,validation_reserve_s=self.validation_reserve,
                    dispatch_reserve_s=self.dispatch_reserve)

    def actual_cap_matches(self, allocated, actual):
        return isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isfinite(actual) and actual==allocated


NEXT_ON = BudgetPolicy(total=420., mode='fixed', native_cap=240.)
ABC_DYNAMIC = BudgetPolicy(total=600., mode='dynamic', native_cap=540.)


def box_objective_bound(c,lb,ub):
    """Exact binary64 objective lower bound from variable bounds only, no LP solve."""
    if not len(c)==len(lb)==len(ub):raise ValueError('Objective/bounds length mismatch')
    bound=Fraction(0)
    for coefficient,lower,upper in zip(c,lb,ub):
        coefficient=float(coefficient)
        if not math.isfinite(coefficient):raise ValueError('Nonfinite objective')
        if coefficient==0:continue
        endpoint=float(lower if coefficient>0 else upper)
        if not math.isfinite(endpoint):return None
        bound+=Fraction.from_float(coefficient)*Fraction.from_float(endpoint)
    return str(bound)


class ResponseBudget:
    """Absolute solver/response cutoff; physical validation keeps the parent deadline."""
    def __init__(self, parent, policy, clock):
        self.parent=parent;self.clock=clock;self.start=parent.start
        self.deadline=min(parent.deadline,parent.start+policy.response_cutoff)
    @property
    def remaining(self):return max(0.,self.deadline-self.clock())
    @property
    def elapsed(self):return self.clock()-self.start
    def check(self):
        self.parent.check()
        if self.clock()>=self.deadline:raise ResponseDeadline('Reserved validation window has begun')
    @contextmanager
    def phase(self,name):
        self.check()
        with self.parent.phase(name):yield


def candidate_admission(receipt, total):
    """Pure classification of already produced receipts, not a numerical verifier."""
    if receipt is None:return 'NO_VECTOR'
    elapsed=receipt.get('received_elapsed_s')
    if not isinstance(elapsed,(int,float)) or isinstance(elapsed,bool) or not math.isfinite(elapsed) or elapsed<0:return 'INVALID_TIME'
    if elapsed>=total:return 'LATE_UNCREDITED'
    if not receipt.get('vector_present'):return 'NO_VECTOR'
    if receipt.get('new_rows') is not True or receipt.get('original_rows') is not True:return 'REJECTED_ROWS'
    if receipt.get('schedule_legal') is not True:return 'REJECTED_SCHEDULE'
    completed=receipt.get('physical_completed_s')
    if (receipt.get('physical_complete') is not True or receipt.get('physical_state')!='SAFE'
            or not isinstance(completed,(int,float)) or isinstance(completed,bool)
            or not math.isfinite(completed) or not elapsed<=completed<total):return 'SAFE_NOT_ESTABLISHED'
    return 'SAME_INITIAL_SAFE' if receipt.get('same_initial') is True else (
        'NEW_SAFE' if receipt.get('same_initial') is False else 'SAFE_IDENTITY_UNKNOWN')


def remaining_arms(order, completed, fault=None):
    """No optimization-success dependency between arms; explicit error impact scope."""
    pending=[arm for arm in order if arm not in completed]
    if fault is None or fault['kind'] in ('TIMEOUT','NO_VECTOR','NO_IMPROVEMENT','CANDIDATE_REJECTED'):
        return pending
    if fault['kind'] in ('CLEANUP_UNKNOWN','SHARED_IDENTITY_DRIFT','SHARED_CORRECTNESS_ERROR'):
        return []
    if fault['kind'] in ('ARM_CORRECTNESS_ERROR','ARM_IDENTITY_DRIFT','ISOLATED_NATIVE_ERROR'):
        affected=fault.get('affected_arms')
        if not affected:raise ValueError('Explicit verified impact scope required')
        return [arm for arm in pending if arm not in affected]
    raise ValueError('Unclassified fault must be resolved before continuation')
