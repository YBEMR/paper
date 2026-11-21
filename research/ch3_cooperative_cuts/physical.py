"""Common physical interface for one case and one isolated algorithm process.

Only the per-network stage assignment changes. Profiles, dispatch, power,
continuous thermal propagation and the deadline-failure prefix are frozen.
Each cache is private to this instance. Reuse of an event schedule requires
the same scene, active applications' physical chains and clock triplet.
"""
from collections import Counter
import csv
from functools import lru_cache
from hashlib import sha256
from math import fsum
from pathlib import Path
import sys
from unittest.mock import patch


RESOURCES = ("CPU", "GPU", "DLA0", "DLA1", "XFER")


def grouped_resource(name):
    return "CPU" if name.startswith("CPU") else name


def zero_resources():
    return dict.fromkeys(RESOURCES, 0.0)


class Physical:
    def __init__(self, root, case_id, stages_for, emit=None):
        root = Path(root).resolve()
        comparison = root / "research/ch3_final_experiments"
        sys.path.insert(0, str(comparison / "p2"))
        import evaluator
        import search

        for mod, expected in ((evaluator, "b013404c8855d91a254844c80929b741f3ebc13e85516666ac8f8c0b0e614134"),
                              (search, "9d8145253a56a0d2f3991518eaf50c864414d83574b826f0872c132d89c7165e")):
            if sha256(Path(mod.__file__).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Frozen module differs: {mod.__name__}")
        self.unit = evaluator.load_frozen(root)
        self.events = self.unit.events
        self.result_type = search.Result
        self.opps = search.OPPS
        self.opp_index = {opp: i for i, opp in enumerate(self.opps)}
        self.stages_for = stages_for
        self.emit = emit
        self.case_id = case_id
        self.counters = Counter()
        case = next(c for c in self.unit.design.cases() if c["id"] == case_id)
        self.ambient = case["ambient"]
        self.scenes = self.unit.design.make_scenes(case)
        with (comparison / "derived/instances.csv").open(encoding="utf-8-sig", newline="") as stream:
            row = next(r for r in csv.DictReader(stream) if r["instance_id"] == case_id)
        self.identity = self.unit.verify_stream(self.scenes, dict(
            request_stream_sha256=row["request_sha"], scene_order=row["scene_order"].split("/"),
            frames_in_execution_order=[int(t) for t in row["frames_execution_order"].split("/")]))
        self.platform = self.events.PLATFORM
        thermal = self.platform["thermal"]
        if not (self.ambient == float(row["ambient_c"]) and case["fps"] == 25 and
                self.platform["image"]["bytes_per_scalar"] == 2 and thermal["reference_C"] == 25 and
                thermal["initial_C"] == [30.] * 4 and thermal["limits_C"] == [80.] * 4 and
                self.events.OPPS == self.opps):
            raise ValueError("Frozen workload, precision or thermal contract differs")
        self.apps = {a["id"]: a for a in self.events.FROZEN["applications"]}
        self.counts = [Counter(q.app for q in s.requests) for s in self.scenes]
        self._stages = lru_cache(maxsize=8192)(self._get_stages)
        self._chain = lru_cache(maxsize=4096)(self._make_chain)
        self._chain_cost = lru_cache(maxsize=4096)(self._get_chain_cost)
        self._schedule = lru_cache(maxsize=48)(self._make_schedule)
        self._resource_diag = lru_cache(maxsize=2048)(self._get_resource_diag)
        self._proxy = lru_cache(maxsize=32768)(self._get_proxy)
        self._outcomes = {}
        self._physical = {}

    def _get_stages(self, dep):
        mapping = self.stages_for(dep)
        return {i: tuple(tuple(s) for s in mapping[str(i)]) for i in self.apps}

    def _make_chain(self, app, stages, opp):
        # build_chains computes each app independently from its frozen graph.
        binding = dict(applications=[self.apps[app]], deployments={
            "candidate": {"stages": {str(app): stages}}})
        return self.events.build_chains(self.platform, binding, "candidate", self.opps[opp])[app]

    def _signature(self, dep, scene):
        stages = self._stages(dep)
        return tuple((a, stages[a]) for a in sorted(self.counts[scene]))

    def _make_schedule(self, j, signature, opp):
        chains = {app: self._chain(app, stages, opp) for app, stages in signature}
        scene = self.scenes[j]
        self.counters["event_dispatches"] += 1
        return self.events.simulate(scene.requests, chains, scene.duration_ns)

    def _bound_schedule(self, platform, scene, deployment, opp):
        if platform is not self.platform or scene is not self.scenes[scene.index]:
            raise ValueError("Unexpected event replay scope")
        return self._schedule(scene.index, self._signature(deployment, scene.index), self.opp_index[opp])

    def _get_chain_cost(self, app, stages, opp):
        times, energies = zero_resources(), zero_resources()
        for stage in self._chain(app, stages, opp):
            resource = grouped_resource(stage.resource)
            times[resource] += stage.duration_ns / 1e6
            energies[resource] += stage.duration_ns * 1e-9 * stage.activity_w
        return times, energies

    def profile(self, dep, j, opp):
        """Serialized service demand for all released requests, without queue or thermal prediction."""
        by_app = {str(a): zero_resources() for a in self.apps}
        energy = zero_resources()
        for app, stages in self._signature(dep, j):
            n = self.counts[j][app]
            times, joules = self._chain_cost(app, stages, opp)
            for r in RESOURCES:
                by_app[str(app)][r] = n * times[r]
                energy[r] += n * joules[r]
        return dict(busy_ms=by_app, active_j_by_resource=energy, active_j=sum(energy.values()),
                    transfer_j=energy["XFER"], requests_by_app=self._app_requests(j))

    def _app_requests(self, j):
        return {str(a): self.counts[j][a] for a in self.apps}

    def _get_proxy(self, j, signature, opp):
        schedule = self._schedule(j, signature, opp)
        if not schedule.deadline_feasible:
            return None
        args = self.events.thermal_kwargs(self.platform, self.opps[opp], self.ambient, True, "base")
        data = self.events.evaluate_thermal(schedule.duration_ns * 1e-9, schedule.active_w,
                                            transfer_W=schedule.transfer_w, **args)
        return float(data["energy_J"])

    def proxy(self, dep, j, opp):
        self.counters["proxy_calls"] += 1
        return self._proxy(j, self._signature(dep, j), opp)

    def replay(self, dep, indices):
        indices = tuple(indices)
        if len(indices) != 4 or any(type(i) is not int or not 0 <= i < 27 for i in indices):
            raise ValueError("Expected four valid OPP indices")
        self.counters["replay_calls"] += 1
        key = dep, indices
        if key in self._outcomes:
            return self._outcomes[key]
        opps = [self.opps[i] for i in indices]
        # The source function checks every request, carries four-node inlet
        # temperatures, and includes the terminal 40 ms. Bind its time_scene
        # lookup only for this call; worker processes never share this module.
        with patch.object(self.events, "time_scene", self._bound_schedule):
            p = self.events.replay_sequence(self.platform, self.scenes, dep, opps, self.ambient,
                                            leakage=True, variation="base", reset=False)
        if p["required"] != 500:
            raise ValueError("Invalid workload size during replay")
        if p["fully_replayed"]:
            result = self.result_type(p["thermal_status"], p["completed"], p["min_slack_ms"],
                                      p["energy_j"], tuple(p["peak_lower_c"]), tuple(p["peak_upper_c"]))
        else:
            last = p["scene_rows"][-1]
            if (p["deadline_ok"] or p["energy_j"] is not None or p["thermal_status"] != "NOT_EVALUATED"
                    or last["deadline_ok"] or not last["late_ids"]):
                raise ValueError("Invalid incomplete physical prefix")
            result = self.result_type("DEADLINE", p["completed"], p["min_slack_ms"], None, None, None,
                                      tuple(last["late_ids"]))
        self._outcomes[key] = result
        self._physical[key] = p
        self.counters["unique_replays"] += 1
        self.counters[result.status] += 1
        if self.emit is not None:
            self.emit("physical", dict(dep=dep, indices=indices, status=result.status,
                                       energy_j=result.energy_j, completed=result.completed,
                                       slack_ms=result.slack_ms, peak_upper_c=result.upper))
        return result

    def _get_resource_diag(self, j, signature, opp):
        sched = self._schedule(j, signature, opp)
        scene = self.scenes[j]
        app_ids = {q.id: str(q.app) for q in scene.requests}
        ready = {q.id: q.release_ns for q in scene.requests}
        min_slack = {}
        for q in scene.requests:
            app = str(q.app)
            slack = (q.deadline_ns - sched.completions_ns[q.id]) / 1e6
            min_slack[app] = min(min_slack.get(app, slack), slack)
        wait = {str(a): zero_resources() for a in self.apps}
        busy = {str(a): zero_resources() for a in self.apps}
        xfer_j = 0.
        for row in sched.rows:
            app, r = app_ids[row.request], grouped_resource(row.resource)
            start = min(scene.duration_ns, row.start_ns)
            end = min(scene.duration_ns, row.end_ns)
            wait[app][r] += (start - min(ready[row.request], scene.duration_ns)) / 1e6
            busy[app][r] += (end-start) / 1e6
            if r == "XFER":
                xfer_j += (end-start) * 1e-9 * row.activity_w
            ready[row.request] = row.end_ns
        return dict(wait_ms=wait, busy_ms=busy, transfer_j=xfer_j, requests_by_app=self._app_requests(j),
                    slack_ms=sched.min_slack_ns / 1e6, slack_by_app_ms=min_slack)

    def diagnostics(self, dep, indices):
        """Return signals only for visited scenes; failing scene retains the previous valid outlet."""
        key = dep, tuple(indices)
        p = self._physical[key]
        rows = []
        inlet = [30.] * 4
        for j, segment in enumerate(p["scene_rows"]):
            resource = self._resource_diag(j, self._signature(dep, j), key[1][j])
            rows.append(dict(index=j, scene=segment["scene"], entry_c=inlet,
                             peak_upper_c=segment.get("peak_upper_c"), **resource))
            inlet = segment.get("final_c")
        return rows

    def evidence(self, dep, indices):
        """Selected candidate's original replay and request completion ledger (prefix for a miss)."""
        indices = tuple(indices)
        p = self._physical[dep, indices]
        opps = [self.opps[i] for i in indices]
        schedules = [{indices[j]: self._bound_schedule(self.platform, self.scenes[j], dep, opps[j])}
                     for j in range(len(p["scene_rows"]))]
        if p["fully_replayed"]:
            rows = self.unit.completions(self.scenes, schedules, opps)
            self.unit.verify_replay(p, rows, self.scenes, opps,
                                    {"SAFE": 1, "VIOLATION": 2, "UNRESOLVED": 3}[p["thermal_status"]],
                                    fsum(s["energy_j"] for s in p["scene_rows"]))
        else:
            rows = []
            for j, slot in enumerate(schedules):
                scene, sched = self.scenes[j], slot[indices[j]]
                for q in scene.requests:
                    finish = sched.completions_ns[q.id]
                    rows.append(dict(scene=scene.name, request_id=q.id, app_id=q.app,
                                     release_ns=scene.start_ns+q.release_ns, deadline_ns=scene.start_ns+q.deadline_ns,
                                     completion_ns=scene.start_ns+finish, slack_ns=q.deadline_ns-finish))
        return dict(request_sha256=self.identity, case=self.case_id, ambient_c=self.ambient,
                    dep=dep, stages=self.stages_for(dep), indices=indices, opps=opps, physical=p,
                    completions=rows)
