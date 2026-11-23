"""Adapters only: frozen 81 concrete bindings and approved variable-size streams."""
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from math import isfinite, fsum
from pathlib import Path
import json
import sys
from time import perf_counter
from types import ModuleType
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT/"research"/p) for p in
    ("multidnn_diagnostics", "ch3_final_experiments/p2", "ch3_cooperative_cuts",
     "ch3_algorithm_selection")]
from instance import Instance, events
from physical import Physical as FrozenPhysical
from catalog_ext import make_domain
import search
import kim_anytime

def encoded(x):
    return json.dumps(x, separators=(",",":"), ensure_ascii=False, allow_nan=False).encode()

def sha(p):
    return sha256(p.read_bytes()).hexdigest()

@dataclass(frozen=True)
class Result:
    status: str
    completed: int
    slack_ms: float
    energy_j: float | None
    lower: tuple | None
    upper: tuple | None
    late_ids: tuple = ()
    required: int = 500

    def __post_init__(self):
        if not (type(self.completed) is int and 0 <= self.completed <= self.required
                and isfinite(self.slack_ms)):
            raise ValueError("invalid request metrics")
        if self.status == "DEADLINE":
            if (self.energy_j,self.lower,self.upper) != (None,None,None) or not self.late_ids:
                raise ValueError("invalid deadline prefix")
            return
        if (self.completed != self.required or self.slack_ms < 0 or self.energy_j is None
                or not isfinite(self.energy_j) or self.energy_j < 0 or self.late_ids):
            raise ValueError("invalid full replay")
        if (self.lower is None or self.upper is None or len(self.lower) != 4 or len(self.upper) != 4
                or any(not isfinite(a) or not isfinite(b) or a>b for a,b in zip(self.lower,self.upper))):
            raise ValueError("invalid continuous peak bounds")
        expected = "VIOLATION" if max(self.lower)>80 else "SAFE" if max(self.upper)<=80 else "UNRESOLVED"
        if self.status != expected:
            raise ValueError("thermal status mismatch")

def energy_explorer():
    """One checked interface substitution; search decisions remain frozen."""
    path = ROOT/"research/ch3_energy_repair/optimizer.py"
    source = path.read_text(encoding="utf-8")
    old = "result.completed != 500"
    assert source.count(old) == 1
    module = ModuleType("approved_energy_only")
    module.__file__ = str(path)
    exec(compile(source.replace(old,"result.completed != self.ev.required"),str(path),"exec"), module.__dict__)
    return module.Explorer

def domain_for(instance):
    domain = make_domain(ROOT,"legacy81")
    assert domain.size == 81 and domain.order == instance.order
    for dep in domain.order:
        assert encoded(domain.stages(dep)) == encoded(instance.frozen["deployments"][dep]["stages"])
    # Enumeration is of 81 fixed physical assignments, NOT a warm-state symmetry argument.
    return domain

class Physical(FrozenPhysical):
    def __init__(self, instance, domain, emit=None):
        instance.bind()
        self.instance, self.domain = instance, domain
        self.events, self.result_type = events, Result
        self.opps, self.opp_index = search.OPPS, {o:i for i,o in enumerate(search.OPPS)}
        self.stages_for, self.emit = domain.stages, emit
        self.case_id, self.required = instance.case["case_id"], instance.required
        self.identity, self.ambient = instance.identity, instance.ambient
        self.scenes, self.platform = instance.scenes, instance.platform
        self.counters, self.seconds = Counter(), Counter()
        self.apps = {a["id"]:a for a in instance.frozen["applications"]}
        self.counts = [Counter(q.app for q in s.requests) for s in self.scenes]
        assert self.platform["image"]["bytes_per_scalar"] == 2
        assert self.platform["thermal"]["limits_C"] == [80.]*4
        assert self.events.OPPS == self.opps
        for scene in self.scenes:
            # Energy-Only's cohort-demand rank is retained: every active app releases
            # at scene entry and all requests have D=40ms, including period-80ms apps.
            assert {q.app for q in scene.requests if q.release_ns==0} == {q.app for q in scene.requests}
            assert all(q.deadline_ns-q.release_ns==40_000_000 for q in scene.requests)
        for name, size, func in [
            ("_stages",8192,self._get_stages),("_chain",4096,self._make_chain),
            ("_chain_cost",4096,self._get_chain_cost),("_schedule",48,self._make_schedule),
            ("_resource_diag",2048,self._get_resource_diag),("_proxy",32768,self._get_proxy)]:
            setattr(self,name,lru_cache(maxsize=size)(func))
        self._outcomes,self._physical = {},{}

    def _get_stages(self, dep):
        if dep not in self.domain.rank:
            raise ValueError("outside the frozen concrete domain")
        return super()._get_stages(dep)

    def _make_schedule(self,j,signature,opp):
        t=perf_counter()
        result=super()._make_schedule(j,signature,opp)
        self.seconds["event_schedule_s"] += perf_counter()-t
        self.counters["deadline_schedule_pass" if result.deadline_feasible else "deadline_schedule_fail"] += 1
        return result

    def _get_proxy(self,j,signature,opp):
        self.counters["unique_scene_proxies"] += 1
        t=perf_counter()
        result=super()._get_proxy(j,signature,opp)
        self.seconds["proxy_inclusive_s"] += perf_counter()-t
        return result

    def replay(self,dep,indices):
        indices=tuple(indices)
        assert dep in self.domain.rank
        assert len(indices)==4 and all(type(i) is int and 0<=i<27 for i in indices)
        self.counters["replay_calls"] += 1
        key=dep,indices
        if key in self._outcomes:
            return self._outcomes[key]
        t=perf_counter()
        with patch.object(events,"time_scene",self._bound_schedule):
            p=events.replay_sequence(self.platform,self.scenes,dep,[self.opps[i] for i in indices],
                                    self.ambient,leakage=True,variation="base",reset=False)
        self.seconds["continuous_replay_inclusive_s"] += perf_counter()-t
        assert p["required"]==self.required
        if p["fully_replayed"]:
            assert p["scene_rows"][-1]["end_ns"]==self.instance.window_ns
            result=Result(p["thermal_status"],p["completed"],p["min_slack_ms"],p["energy_j"],
                          tuple(p["peak_lower_c"]),tuple(p["peak_upper_c"]),required=self.required)
        else:
            last=p["scene_rows"][-1]
            assert not p["deadline_ok"] and p["energy_j"] is None and p["thermal_status"]=="NOT_EVALUATED"
            assert not last["deadline_ok"] and last["late_ids"]
            result=Result("DEADLINE",p["completed"],p["min_slack_ms"],None,None,None,
                          tuple(last["late_ids"]),self.required)
        self._physical[key],self._outcomes[key]=p,result
        self.counters["unique_replays"]+=1
        self.counters[result.status]+=1
        if self.emit:
            self.emit("physical",dict(dep=dep,indices=indices,physical=p))
        return result

    def evidence(self,dep,indices):
        t=perf_counter()
        indices=tuple(indices)
        p=self._physical[dep,indices]
        rows=[]
        for j in range(len(p["scene_rows"])):
            s=self.scenes[j]
            schedule=self._bound_schedule(self.platform,s,dep,self.opps[indices[j]])
            for q in s.requests:
                end=schedule.completions_ns[q.id]
                rows.append(dict(scene=s.name,request_id=q.id,app_id=q.app,
                    release_ns=s.start_ns+q.release_ns,deadline_ns=s.start_ns+q.deadline_ns,
                    completion_ns=s.start_ns+end,slack_ns=q.deadline_ns-end))
        if p["fully_replayed"]:
            assert len(rows)==self.required and len({r["request_id"] for r in rows})==self.required
            assert [[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]] for r in rows]==self.instance.stream["requests"]
            assert min(r["slack_ns"] for r in rows)>=0
            assert abs(min(r["slack_ns"] for r in rows)/1e6-p["min_slack_ms"])<1e-12
            assert abs(fsum(s["energy_j"] for s in p["scene_rows"])-p["energy_j"])<1e-10
            previous=self.instance.initial
            for scene in p["scene_rows"]:
                assert max(abs(a-b) for a,b in zip(previous,scene["entry_c"]))<1e-12
                previous=scene["final_c"]
        self.seconds["evidence_s"]+=perf_counter()-t
        return dict(identity=self.identity,case=self.case_id,required=self.required,
                    ambient_c=self.ambient,initial_c=self.instance.initial,dep=dep,
                    stages=self.stages_for(dep),indices=indices,opps=[self.opps[i] for i in indices],
                    physical=p,completions=rows)
