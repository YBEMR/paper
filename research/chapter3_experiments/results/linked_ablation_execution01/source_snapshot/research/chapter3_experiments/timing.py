"""One method deadline, disjoint phase accounting, no budget replenishment."""
from contextlib import contextmanager
import math
import time

from thermal import Budget, Exhausted


class MethodBudget(Budget):
    """Evidence cutoff is strict; execution stops at cooperative checkpoints.

    Interpreter startup/imports precede the method. Start this clock before
    reading any case input. Cleanup/reporting are outside the method and may
    only serialize evidence already formed before the deadline.
    """
    def __init__(self, seconds=60, *, clock=time.monotonic, hook=None):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('method seconds must be finite and positive')
        super().__init__(seconds=seconds, hook=hook)
        self.clock = clock
        self.start = clock()
        self.deadline = self.start + float(seconds)
        self.records = []
        self._stack = []

    @property
    def elapsed(self):
        return self.clock() - self.start

    @property
    def remaining(self):
        return max(0.0, self.deadline-self.clock())

    def check(self):
        if self.clock() >= self.deadline:
            raise Exhausted('wall_time_limit')

    @contextmanager
    def phase(self, name):
        self.check()
        frame = {'phase': name, 'start_s': self.elapsed, 'children_s': 0.0,
                 'depth': len(self._stack)}
        self._stack.append(frame)
        try:
            yield
        except BaseException as error:
            frame['exception'] = type(error).__name__
            raise
        finally:
            frame['end_s'] = self.elapsed
            frame['wall_s'] = frame['end_s']-frame['start_s']
            frame['exclusive_s'] = max(0.0, frame['wall_s']-frame.pop('children_s'))
            self._stack.pop()
            if self._stack:
                self._stack[-1]['children_s'] += frame['wall_s']
            self.records.append(frame)
        # Intentionally no exit check: the caller first commits any evaluator
        # receipt formed before the deadline, then checks remaining time.

    def summary(self, stopped_s=None):
        stopped_s = self.elapsed if stopped_s is None else stopped_s
        totals = {}
        for frame in self.records:
            totals[frame['phase']] = totals.get(frame['phase'], 0.0)+frame['exclusive_s']
        return {'limit_s': self.seconds, 'method_elapsed_s': stopped_s,
                'deadline_overshoot_s': max(0.0, stopped_s-self.seconds),
                'phases_exclusive_s': totals, 'phase_records': list(self.records),
                'unattributed_s': max(0.0, stopped_s-sum(totals.values())),
                'clock_origin': 'before input read; imports excluded for all methods',
                'execution_stop': 'cooperative checkpoints, not a hard real-time process stop',
                'evidence_cutoff': 'one absolute monotonic deadline; no round reset'}
