"""Request/chain execution at fixed clocks; integer nanoseconds and exclusive resources.

Models the frozen per-app CPU affinities. At most one application priority exists
on each CPU core: fixed-priority preemption cannot arise across unequal
priorities on that core. Within equal priority use the frozen FIFO tie breaks.
Energy is evaluated on the common finite window; the dispatcher always drains
all released requests and records their true finishing times, including misses.
"""
from dataclasses import dataclass
from heapq import heappop, heappush
from math import isfinite
from numbers import Integral

import numpy as np


CPU_CORES = tuple(f"CPU{i}" for i in range(8))
RESOURCES = (*CPU_CORES, "GPU", "DLA0", "DLA1", "XFER")
THERMAL_NODES = ("CPU", "GPU", "DLA0", "DLA1")
PRIORITY = {app: rank for rank, app in enumerate((0, 3, 1, 2))}


@dataclass(frozen=True)
class Request:
    id: str
    app: int
    release_ns: int
    deadline_ns: int


@dataclass(frozen=True)
class Stage:
    name: str
    resource: str
    duration_ns: int
    activity_w: float


@dataclass(frozen=True)
class Row:
    request: str
    stage: str
    stage_index: int
    resource: str
    start_ns: int
    end_ns: int
    activity_w: float


@dataclass
class Schedule:
    rows: list
    requests: tuple
    completions_ns: dict
    late_ids: tuple
    unfinished_ids: tuple
    busy_ns: dict
    start_ns: np.ndarray
    duration_ns: np.ndarray
    active_w: np.ndarray
    transfer_w: np.ndarray
    window_ns: int
    last_completion_ns: int
    max_response_ns: int
    min_slack_ns: int | None
    max_tardiness_ns: int
    stages_touching_after_window: int

    @property
    def deadline_feasible(self):
        return not self.late_ids and not self.unfinished_ids

    @property
    def idle_ns(self):
        return {unit: self.window_ns - busy for unit, busy in self.busy_ns.items()}


def _validate(requests, chains, window, boundaries):
    if not isinstance(window, Integral) or window <= 0:
        raise ValueError("window must be a positive integer in nanoseconds")
    if any(not isinstance(b, Integral) or not 0 <= b <= window for b in boundaries):
        raise ValueError("scene boundary lies outside the evaluation window")
    ids = set()
    for req in requests:
        if not isinstance(req.id, str) or not req.id or req.id in ids:
            raise ValueError("empty or duplicate request id")
        ids.add(req.id)
        if req.app not in chains or req.app not in PRIORITY:
            raise ValueError("unrecognized application or missing chain")
        if not (isinstance(req.release_ns, Integral) and isinstance(req.deadline_ns, Integral)
                and 0 <= req.release_ns < window and req.release_ns <= req.deadline_ns <= window):
            raise ValueError("invalid release or deadline for a closed workload")
    for app, chain in chains.items():
        if app not in PRIORITY or not chain:
            raise ValueError("unrecognized app or empty chain")
        for stage in chain:
            if (stage.resource not in RESOURCES or not stage.name or not isinstance(stage.duration_ns, Integral)
                    or stage.duration_ns <= 0 or not isfinite(stage.activity_w) or stage.activity_w < 0):
                raise ValueError("invalid stage resource, duration or power")
            if stage.resource in CPU_CORES and stage.resource != f"CPU{app}":
                raise ValueError("CPU affinity violates the frozen per-app binding")


def _dispatch(requests, chains):
    releases = sorted(requests, key=lambda r: (r.release_ns, r.id))
    jobs = {r.id: r for r in requests}
    ready = {unit: [] for unit in RESOURCES}
    running = set()
    finishes = []
    completions = {}
    rows = []

    def enqueue(req, index, now):
        stage = chains[req.app][index]
        # CPU's app priority is constant on this core. Other resources use
        # ready time, request release, application priority, stage index, ID.
        app_order = req.app if stage.resource in CPU_CORES else PRIORITY[req.app]
        heappush(ready[stage.resource], (now, req.release_ns, app_order, index, req.id))

    cursor = 0
    while cursor < len(releases) or finishes:
        next_release = releases[cursor].release_ns if cursor < len(releases) else None
        next_finish = finishes[0][0] if finishes else None
        now = next_release if next_finish is None else next_finish
        if next_release is not None:
            now = min(now, next_release)
        # Enqueue all same-time successors and external arrivals before dispatch.
        while finishes and finishes[0][0] == now:
            _, unit, rid, index = heappop(finishes)
            running.remove(unit)
            req = jobs[rid]
            if index + 1 == len(chains[req.app]):
                completions[rid] = now
            else:
                enqueue(req, index + 1, now)
        while cursor < len(releases) and releases[cursor].release_ns == now:
            enqueue(releases[cursor], 0, now)
            cursor += 1
        for unit, queue in ready.items():
            if unit in running or not queue:
                continue
            _, _, _, index, rid = heappop(queue)
            stage = chains[jobs[rid].app][index]
            end = now + stage.duration_ns
            rows.append(Row(rid, stage.name, index, unit, now, end, stage.activity_w))
            heappush(finishes, (end, unit, rid, index))
            running.add(unit)
    if len(completions) != len(requests):
        raise RuntimeError("released work did not drain")
    return rows, completions


def _window_activity(rows, window, boundaries):
    """Piecewise-constant activity over the common window only (no idle base)."""
    points = {0, window, *boundaries}
    by_unit = {unit: [] for unit in RESOURCES}
    busy = dict.fromkeys(RESOURCES, 0)
    for row in rows:
        if row.start_ns >= window:
            continue
        end = min(row.end_ns, window)
        by_unit[row.resource].append(row)
        points.update((row.start_ns, end))
        busy[row.resource] += end - row.start_ns
    edges = np.array(sorted(points), dtype=np.int64)
    starts = edges[:-1]
    active = np.zeros((len(starts), 4))
    transfer = np.zeros(len(starts))
    for unit, spans in by_unit.items():
        if not spans:
            continue
        first = np.array([row.start_ns for row in spans], dtype=np.int64)
        last = np.array([row.end_ns for row in spans], dtype=np.int64)
        if (first[1:] < last[:-1]).any():
            raise RuntimeError(f"conflicting intervals on {unit}")
        watts = np.array([row.activity_w for row in spans])
        index = np.searchsorted(first, starts, side="right") - 1
        on = (index >= 0) & (starts < last[index])
        if unit == "XFER":
            transfer[on] = watts[index[on]]
        else:
            node = 0 if unit in CPU_CORES else THERMAL_NODES.index(unit)
            active[on, node] += watts[index[on]]
    return busy, starts, np.diff(edges), active, transfer


def simulate(requests, chains, window_ns, boundaries_ns=()):
    """Simulate all jobs once; independent/reset and continuous heat use identical rows.

    boundaries_ns may include 0 and the window end. Additional boundaries
    split the power waveform without clearing queues or restarting stages.
    Intervals are half-open. As in the V1 deadline check, equality at the
    deadline passes and completion strictly later is a miss.
    """
    requests = tuple(requests)
    boundaries = tuple(boundaries_ns)
    _validate(requests, chains, window_ns, boundaries)
    rows, completions = _dispatch(requests, chains)
    busy, starts, durations, active, transfer = _window_activity(rows, window_ns, boundaries)
    late = tuple(r.id for r in requests if completions[r.id] > r.deadline_ns)
    unfinished = tuple(r.id for r in requests if completions[r.id] > window_ns)
    slack = min((r.deadline_ns - completions[r.id] for r in requests), default=None)
    return Schedule(
        rows=rows, requests=requests, completions_ns=completions, late_ids=late,
        unfinished_ids=unfinished, busy_ns=busy, start_ns=starts, duration_ns=durations,
        active_w=active, transfer_w=transfer, window_ns=window_ns,
        last_completion_ns=max(completions.values(), default=0),
        max_response_ns=max((completions[r.id] - r.release_ns for r in requests), default=0),
        min_slack_ns=slack, max_tardiness_ns=max(0, -slack) if slack is not None else 0,
        stages_touching_after_window=sum(row.end_ns > window_ns for row in rows),
    )
