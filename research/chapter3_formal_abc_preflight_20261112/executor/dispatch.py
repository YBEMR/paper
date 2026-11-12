"""Compute the shared dynamic quota after MAT serialization, before JSON publication."""
from contextlib import contextmanager
from budget_policy import ABC_DYNAMIC
from evidence import InsufficientNativeBudget

@contextmanager
def allocate_at_publication(bridge,elapsed,record):
    original=bridge._json;published=[]
    def publish(path,value):
        if path.name.endswith('.request.json'):
            if published: raise RuntimeError('No second native request')
            allocation=ABC_DYNAMIC.allocate(elapsed())
            record(allocation)
            if not allocation['can_submit']: raise InsufficientNativeBudget('Final publication has less than 30 native seconds')
            # Recheck after durable allocation bookkeeping, without increasing the frozen cap.
            now=elapsed();allowed=ABC_DYNAMIC.allocate(now)
            if not allowed['can_submit'] or allowed['native_seconds']<allocation['native_seconds']:
                raise InsufficientNativeBudget('Quota crossed a boundary during publication bookkeeping; no retry')
            value=dict(value,remaining_s=min(value['remaining_s'],ABC_DYNAMIC.response_cutoff-now),
                       solver_max_time_s=allocation['native_seconds'],solver_max_time_s_declared=allocation['native_seconds'])
            published.append(allocation)
        return original(path,value)
    bridge._json=publish
    try: yield published
    finally: bridge._json=original
