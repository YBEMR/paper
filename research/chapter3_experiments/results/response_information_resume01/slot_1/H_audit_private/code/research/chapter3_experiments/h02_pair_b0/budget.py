"""B0 root-deadline wiring: no scheduler, thermal kernel or solver imports.

The controller constructs RootClock before input preparation or worker spawn.
Workers inherit that immutable origin and full declared limit, never a fresh
remaining-time budget. The clock is the same host monotonic clock in seconds.
Archive grace changes process termination only, never the evidence cutoff.
"""
import math
import time


class BudgetContractError(ValueError):
    pass


class RootBudgetExpired(RuntimeError):
    pass


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BudgetContractError(name + ' must be a finite real clock value')
    try:
        valid = math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        valid = False
    if not valid:
        raise BudgetContractError(name + ' must be finite')
    return value


def _limit(value):
    value = _finite(value, 'limit_s')
    if value <= 0:
        raise BudgetContractError('limit_s must be positive')
    return value


class RootClock:
    """One controller deadline, usable before any worker/backend exists.

    This is not a physical evaluator Budget. check() only gates new work;
    completed receipt archival is separately governed by timely_receipt().
    """
    __slots__ = ('_clock', '_origin', '_limit')

    def __init__(self, limit_s, *, clock=time.monotonic, origin=None):
        if not callable(clock):
            raise BudgetContractError('clock must be callable')
        self._clock = clock
        self._limit = _limit(limit_s)
        self._origin = _finite(clock() if origin is None else origin, 'origin')
        _finite(self._origin + self._limit, 'deadline')

    @property
    def clock(self):
        return self._clock

    @property
    def origin(self):
        return self._origin

    @property
    def start(self):
        return self._origin

    @property
    def seconds(self):
        return self._limit

    @property
    def limit_s(self):
        return self._limit

    @property
    def deadline(self):
        return self._origin + self._limit

    @property
    def elapsed(self):
        now = _finite(self._clock(), 'now')
        if now < self._origin:
            raise BudgetContractError('clock precedes root origin')
        return now - self._origin

    @property
    def remaining(self):
        return max(0.0, self._limit - self.elapsed)

    def check(self):
        if self.elapsed >= self._limit:
            raise RootBudgetExpired('root_wall_time_limit')

    def summary(self):
        elapsed = self.elapsed
        return dict(limit_s=self._limit, root_origin=self._origin,
                    root_deadline=self.deadline, method_elapsed_s=elapsed,
                    deadline_overshoot_s=max(0.0, elapsed-self._limit),
                    clock_origin='controller: before input read/expansion/projection, '
                                 'hashing, handoff, worker startup and imports',
                    evidence_cutoff='strict elapsed < declared root limit',
                    no_budget_replenishment=True)


def anchored_budget_class(base_cls, origin, clock):
    """Inject root time into an existing Budget class without importing it.

    Prefer passing a RootClock as origin: that additionally binds the declared
    120/60 s limit and rejects attempts to pass remaining seconds instead.
    Numeric origin is supported for serialized worker roots; its declared
    limit must be checked by the worker envelope before construction.
    The caller provides MethodBudget or a mock base explicitly.
    """
    root = origin if isinstance(origin, RootClock) else None
    fixed_origin = root.origin if root is not None else _finite(origin, 'origin')
    if not isinstance(base_cls, type) or not callable(clock):
        raise BudgetContractError('explicit base class and callable clock required')
    if root is not None and clock is not root.clock:
        raise BudgetContractError('root and worker must share declared clock')

    class AnchoredBudget(base_cls):
        def __init__(self, seconds=60, *, clock=clock, **kwargs):
            if getattr(self, '_h02_root_initialized', False):
                raise BudgetContractError('root budget cannot be reinitialized')
            seconds = _limit(seconds)
            if root is not None and seconds != root.limit_s:
                raise BudgetContractError('declared root limit cannot become remaining seconds')
            if clock is not factory_clock:
                raise BudgetContractError('worker clock differs from root clock')
            # The base may take a local timestamp; immediately replace it with
            # the original controller origin, before exposing this budget.
            super().__init__(seconds=seconds, clock=clock, **kwargs)
            self.start = fixed_origin
            self.seconds = seconds
            self.deadline = fixed_origin + seconds
            _finite(self.deadline, 'deadline')
            self._h02_root_origin = fixed_origin
            self._h02_root_limit = seconds
            self._h02_root_initialized = True

        def _root_integrity(self):
            if (self.start != self._h02_root_origin or
                    self.seconds != self._h02_root_limit or
                    self.deadline != self._h02_root_origin+self._h02_root_limit or
                    self.clock is not factory_clock):
                raise BudgetContractError('root budget metadata drift/reset')
            now = _finite(self.clock(), 'now')
            if now < self._h02_root_origin:
                raise BudgetContractError('clock precedes root origin')
            return now

        @property
        def elapsed(self):
            return self._root_integrity()-self._h02_root_origin

        @property
        def remaining(self):
            return max(0.0, self._h02_root_limit-self.elapsed)

        def check(self):
            now = self._root_integrity()
            # Let the supplied physical base preserve its own exhaustion type
            # and additional checks. If it fails to enforce the root deadline,
            # fail closed here instead of granting extra runtime.
            super().check()
            if now >= self.deadline:
                raise RootBudgetExpired('root_wall_time_limit')

        def summary(self, stopped_s=None):
            self._root_integrity()
            result = dict(super().summary(stopped_s))
            result.update(root_origin=self._h02_root_origin,
                          root_deadline=self.deadline,
                          clock_origin='controller: before input read/expansion/projection, '
                                       'hashing, handoff, worker startup and imports',
                          evidence_cutoff='strict elapsed < declared root limit',
                          no_budget_replenishment=True)
            return result

    factory_clock = clock
    AnchoredBudget.__name__ = 'H02Anchored' + base_cls.__name__
    return AnchoredBudget


def watchdog_decision(now, origin, limit, grace=5):
    """Pure parent decision; ARCHIVE_ONLY never permits new computation."""
    now, origin = _finite(now, 'now'), _finite(origin, 'origin')
    limit, grace = _limit(limit), _finite(grace, 'grace')
    if grace < 0 or now < origin:
        raise BudgetContractError('invalid watchdog interval')
    deadline = _finite(origin+limit, 'deadline')
    hard_stop = _finite(deadline+grace, 'hard_stop')
    if now < deadline:
        return 'RUN'
    if now < hard_stop:
        return 'ARCHIVE_ONLY'
    return 'TERMINATE'


def timely_receipt(formed_at_elapsed_s, limit_s, *, returned_at_elapsed_s=None):
    """Late archival can preserve an already formed complete receipt.

    The receipt still needs independent identity/completeness validation.
    A timestamp alone never establishes SAFE or authorizes new evaluation.
    """
    try:
        formed = _finite(formed_at_elapsed_s, 'formed_at_elapsed_s')
        limit = _limit(limit_s)
        if not 0 <= formed < limit:
            return False
        if returned_at_elapsed_s is not None:
            returned = _finite(returned_at_elapsed_s, 'returned_at_elapsed_s')
            if returned < formed or returned < 0:
                return False
        return True
    except BudgetContractError:
        return False
