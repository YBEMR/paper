"""One inherited MethodBudget, with earlier G0 phase/slot guards.

Import loads legacy class definitions only. No planner, model construction,
MATLAB process, coefficient calculation or thermal evaluation is invoked.
"""
from contextlib import contextmanager
from copy import deepcopy
import importlib
import math
from pathlib import Path
import sys
import time
import uuid


def _legacy_classes():
    folder = str(Path(__file__).resolve().parents[1] / "chapter3_experiments")
    inserted = folder not in sys.path
    if inserted:
        sys.path.insert(0, folder)
    try:
        timing = importlib.import_module("timing")
        thermal = importlib.import_module("thermal")
        if Path(timing.__file__).resolve().parent != Path(folder).resolve():
            raise ImportError("wrong legacy timing module")
        if Path(thermal.__file__).resolve().parent != Path(folder).resolve():
            raise ImportError("wrong legacy thermal module")
        return timing.MethodBudget, thermal.Exhausted
    finally:
        if inserted:
            sys.path.remove(folder)


MethodBudget, Exhausted = _legacy_classes()


class ScopeExhausted(Exhausted):
    """A legacy-catchable deadline, with its actual limiting scope."""
    def __init__(self, kind, scope=None):
        self.kind, self.scope = kind, scope
        super().__init__("wall_time_limit" if kind == "root" else kind + "_time_limit")


class G0Budget(MethodBudget):
    """The same root object and receipt token are used across both stages.

    The root start, seconds and deadline are never rewritten. Scope deadlines
    are root-elapsed seconds, not fresh durations. End-of-scope does not create
    new evidence or perform an exit check; callers first retain already formed
    evidence, confirm worker idle, and only then leave/seal the scope.
    """
    def __init__(self, seconds, *, clock=time.monotonic, hook=None):
        super().__init__(seconds, clock=clock, hook=hook)
        self._root_fingerprint = (self.start, self.seconds, self.deadline)
        self._scene_adapter_budget_identity = {
            "token": uuid.uuid4().hex, "start": repr(self.start),
            "seconds": repr(self.seconds), "panel_limit": self.panel_limit,
            "refinement_limit": self.refinement_limit}
        self._identity_fingerprint = deepcopy(self._scene_adapter_budget_identity)
        self._guards = []
        self._scopes = {}
        self.scope_records = []

    @property
    def root_identity(self):
        self._verify_root()
        return deepcopy(self._identity_fingerprint)

    def _verify_root(self):
        if (self.start, self.seconds, self.deadline) != self._root_fingerprint:
            raise ValueError("G0 root clock was changed")
        if self._scene_adapter_budget_identity != self._identity_fingerprint:
            raise ValueError("G0 root receipt identity was changed")

    @property
    def root_remaining(self):
        self._verify_root()
        return max(0.0, self.deadline - self.clock())

    @property
    def effective_deadline_elapsed_s(self):
        self._verify_root()
        return min([float(self.seconds)] + [self._scopes[t]["deadline_elapsed_s"]
                                          for t in self._guards])

    @property
    def remaining(self):
        return max(0.0, self.effective_deadline_elapsed_s - self.elapsed)

    def check(self):
        self._verify_root()
        now = self.elapsed
        if now >= self.seconds:
            raise ScopeExhausted("root")
        # Earliest guard is the actual stopping cause. Stable ties retain the
        # enclosing phase instead of relabeling it as a child slot.
        guards = sorted((self._scopes[token] for token in self._guards),
                        key=lambda item: item["deadline_elapsed_s"])
        for item in guards:
            if now >= item["deadline_elapsed_s"]:
                raise ScopeExhausted(item["kind"], item["token"])

    @contextmanager
    def scope(self, name, deadline_elapsed_s, *, kind="phase"):
        self.check()
        if (isinstance(deadline_elapsed_s, bool) or
                not isinstance(deadline_elapsed_s, (int, float)) or
                not math.isfinite(deadline_elapsed_s) or deadline_elapsed_s < 0):
            raise ValueError("scope deadline must be finite root-elapsed seconds")
        if kind not in ("phase", "slot", "initialization", "selection"):
            raise ValueError("unknown scope kind")
        token = uuid.uuid4().hex
        inherited = self.effective_deadline_elapsed_s
        item = {"token": token, "name": str(name), "kind": kind,
                "deadline_elapsed_s": min(float(deadline_elapsed_s), inherited),
                "opened_at_elapsed_s": self.elapsed, "closed": False,
                "parent_token": self._guards[-1] if self._guards else None,
                "root_identity": self.root_identity}
        self._scopes[token] = item
        self._guards.append(token)
        try:
            self.check()
            yield token
        finally:
            if not self._guards or self._guards[-1] != token:
                raise ValueError("G0 scopes must close in stack order")
            self._guards.pop()
            self.seal_scope(token)

    def capture_scope(self):
        self._verify_root()
        if not self._guards:
            return {"token": None, "kind": "root", "root_identity": self.root_identity,
                    "deadline_elapsed_s": float(self.seconds), "opened_at_elapsed_s": 0.0}
        return deepcopy(self._scopes[self._guards[-1]])

    def scope_snapshot(self, token=None):
        if token is None:
            return self.capture_scope()
        if token not in self._scopes:
            raise ValueError("unknown G0 scope token")
        return deepcopy(self._scopes[token])

    def seal_scope(self, token):
        if token not in self._scopes:
            raise ValueError("unknown G0 scope token")
        item = self._scopes[token]
        if not item["closed"]:
            item.update(closed=True, closed_at_elapsed_s=self.elapsed)
            self.scope_records.append(deepcopy(item))

    def accept_formed(self, formed_elapsed_s, *, scope=None):
        """Check formation time, not return time; sealed callback scopes lose.

        No new calculation is allowed here. A timely complete result returned
        after a deadline is retainable only while its dispatch scope remains
        unsealed. A single timely scene cannot authorize a late aggregate.
        """
        self._verify_root()
        if (isinstance(formed_elapsed_s, bool) or
                not isinstance(formed_elapsed_s, (int, float)) or
                not math.isfinite(formed_elapsed_s) or
                not 0 <= formed_elapsed_s <= self.elapsed):
            return False
        if scope is None:
            scope = self.capture_scope()
        elif isinstance(scope, str):
            scope = self.scope_snapshot(scope)
        if not isinstance(scope, dict) or scope.get("root_identity") != self.root_identity:
            return False
        token = scope.get("token")
        if token is not None:
            actual = self._scopes.get(token)
            if actual is None or actual["closed"]:
                return False
            # Never trust a caller-supplied wider deadline or earlier start.
            if any(scope.get(key) != actual[key] for key in
                   ("deadline_elapsed_s", "opened_at_elapsed_s", "kind")):
                return False
            parent = actual["parent_token"]
            while parent is not None:
                if self._scopes[parent]["closed"]:
                    return False
                parent = self._scopes[parent]["parent_token"]
        elif scope.get("deadline_elapsed_s") != float(self.seconds):
            return False
        deadline = min(float(self.seconds), scope["deadline_elapsed_s"])
        return scope.get("opened_at_elapsed_s", 0.0) <= formed_elapsed_s < deadline

    def summary(self, stopped_s=None):
        out = super().summary(stopped_s)
        out.update(scope_records=deepcopy(self.scope_records),
                   root_identity=self.root_identity,
                   stage_deadlines="earlier guards; unchanged root MethodBudget",
                   real_execution_enabled=False)
        return out
