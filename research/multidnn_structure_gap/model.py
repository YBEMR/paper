"""Instance adapter. The original event dispatcher and thermal integrator are unchanged."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from functools import lru_cache
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch
from topology import ROOT,HERE
import service

sys.path.insert(0,str(ROOT/"research/kim_scene_dvfs_admission"))
import scene_events as events
import joint_thermal
sys.path.insert(0,str(ROOT/"research/ch3_cooperative_cuts"))
from physical import Physical as OldPhysical

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
    return m

# Reuse the previously verified declared-count result type and request-ledger verifier.
prior=load_module("prior_comparison_common",ROOT/"research/multidnn_algorithm_comparison/common.py")
Result=prior.Result
OPPS=events.OPPS

def read(p):return json.loads(p.read_bytes())
def encoded(x):return json.dumps(x,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
def sha(p):return sha256(p.read_bytes()).hexdigest()

class Instance:
    def __init__(self,case_id,holdout=False):
        self.case=read(HERE/"inputs"/("holdout" if holdout else "cases")/(case_id+".json"))
        self.required=self.case["required"];self.initial=self.case["initial_c"];self.ambient=self.case["ambient_c"]
        self.window_ns=self.case["window_ns"];self.stream={"requests":self.case["requests"]}
        self.domain=read(HERE/self.case["domain_file"]);self.order=self.domain["search_order"]
        self.graphs={name:read(HERE/"inputs/graphs"/(name+".json")) for name in self.case["models"]}
        self.platform=deepcopy(events.PLATFORM);self.platform["thermal"]["initial_C"]=list(self.initial)
        self.frozen=dict(applications=[dict(id=i,model=name,cpu_core=f"CPU{i}",layers=len(self.graphs[name]["ops"]))
                         for i,name in enumerate(self.case["models"])],deployments=self.domain["deployments"],graphs=self.graphs)
        self.scenes=events.partition_requests([events.Request(*r) for r in self.case["requests"]],
                         self.case["switches"],self.window_ns,self.case["service_ns"])
        recovered=[[q.id,q.app,s.start_ns+q.release_ns,s.start_ns+q.deadline_ns] for s in self.scenes for q in s.requests]
        assert recovered==self.case["requests"] and len(recovered)==self.required==sum(self.case["counts"])
        self.identity=sha256(encoded(dict(case=self.case,domain=self.domain,graphs=self.graphs,
                                         platform=self.platform))).hexdigest()
    def bind(self):
        events.PLATFORM=self.platform
        events.FROZEN=self.frozen
        events.build_chains=service.build_chains
    def replay(self,dep,opps):
        self.bind()
        return events.replay_sequence(self.platform,self.scenes,dep,opps,self.ambient)

class Physical(OldPhysical):
    def __init__(self,inst,emit=None):
        inst.bind();self.instance=inst;self.events=events;self.emit=emit
        self.case_id=inst.case["case_id"];self.required=inst.required;self.identity=inst.identity
        self.ambient=inst.ambient;self.platform=inst.platform;self.scenes=inst.scenes
        self.opps=OPPS;self.opp_index={o:i for i,o in enumerate(OPPS)}
        self.stages_for=lambda dep:inst.domain["deployments"][dep]["stages"]
        self.apps={a["id"]:a for a in inst.frozen["applications"]}
        self.counts=[Counter(q.app for q in s.requests) for s in self.scenes]
        self.counters,self.seconds=Counter(),Counter()
        for name,size,func in [
           ("_stages",8192,self._get_stages),("_chain",4096,self._make_chain),
           ("_chain_cost",4096,self._get_chain_cost),("_schedule",48,self._make_schedule),
           ("_resource_diag",2048,self._get_resource_diag),("_proxy",32768,self._get_proxy)]:
            setattr(self,name,lru_cache(maxsize=size)(func))
        self._physical,self._outcomes={},{}
    def _make_chain(self,app,stages,opp):
        binding=dict(applications=[self.apps[app]],graphs=self.instance.graphs,
                     deployments={"candidate":{"stages":{str(app):stages}}})
        return service.build_chains(self.platform,binding,"candidate",OPPS[opp])[app]
    def _make_schedule(self,j,signature,opp):
        t=perf_counter()
        schedule=super()._make_schedule(j,signature,opp)
        self.seconds["schedule_s"]+=perf_counter()-t
        self.counters["deadline_pass" if schedule.deadline_feasible else "deadline_fail"]+=1
        if self.emit:self.emit("schedule",dict(scene=j,signature=signature,opp=OPPS[opp],
             required=len(self.scenes[j].requests),deadline_ok=schedule.deadline_feasible,
             min_slack_ns=schedule.min_slack_ns,late_ids=schedule.late_ids,
             completion_sha256=sha256(encoded(sorted(schedule.completions_ns.items()))).hexdigest()))
        return schedule
    def _get_proxy(self,j,signature,opp):
        t=perf_counter();self.counters["unique_proxy"]+=1
        result=super()._get_proxy(j,signature,opp)
        self.seconds["proxy_inclusive_s"]+=perf_counter()-t
        return result
    def replay(self,dep,indices):
        indices=tuple(indices);assert len(indices)==len(self.scenes)
        assert dep in self.instance.domain["deployments"] and all(type(i) is int and 0<=i<27 for i in indices)
        key=dep,indices
        self.counters["replay_calls"]+=1
        if key in self._outcomes:return self._outcomes[key]
        t=perf_counter()
        with patch.object(events,"time_scene",self._bound_schedule):
            p=events.replay_sequence(self.platform,self.scenes,dep,[OPPS[i] for i in indices],self.ambient)
        self.seconds["continuous_replay_s"]+=perf_counter()-t
        assert p["required"]==self.required
        if p["fully_replayed"]:
            assert p["scene_rows"][-1]["end_ns"]==self.instance.window_ns
            r=Result(p["thermal_status"],p["completed"],p["min_slack_ms"],p["energy_j"],
                     tuple(p["peak_lower_c"]),tuple(p["peak_upper_c"]),required=self.required)
        else:
            assert p["energy_j"] is None and not p["deadline_ok"]
            r=Result("DEADLINE",p["completed"],p["min_slack_ms"],None,None,None,
                     tuple(p["scene_rows"][-1]["late_ids"]),self.required)
        self._physical[key],self._outcomes[key]=p,r
        self.counters["unique_replays"]+=1;self.counters[r.status]+=1
        if self.emit:self.emit("physical",dict(dep=dep,indices=indices,physical=p))
        return r
    evidence=prior.Physical.evidence

def bind_kim(inst):
    """Only declared app/scene counts change. SetFreq and genetic decisions do not."""
    from types import ModuleType
    path=ROOT/"research/ch3_final_experiments/p2/search.py"
    source=path.read_text(encoding="utf-8")
    n=len(inst.case["models"]);k=len(inst.scenes)
    edits=[
      ("len(genes) != 4","len(genes) != N_APPS",1),
      ("for i in range(5)]","for i in range(N_APPS+1)]",1),
      ("rng.randrange(5)","rng.randrange(N_APPS+1)",1),
      ("rng.sample(range(4), 4)","rng.sample(range(N_SCENES), N_SCENES)",1),
      ("c.valid == 4","c.valid == N_SCENES",1),
      ("for scene in range(4)","for scene in range(N_SCENES)",1)]
    for old,new,count in edits:
        assert source.count(old)==count,(old,source.count(old))
        source=source.replace(old,new)
    m=ModuleType("generalized_kim_search");m.__file__=str(path)
    m.N_APPS=n;m.N_SCENES=k;sys.modules[m.__name__]=m
    exec(compile(source,str(path),"exec"),m.__dict__)
    runner=load_module("generalized_kim_anytime",ROOT/"research/ch3_algorithm_selection/kim_anytime.py")
    runner.search=m
    return m,runner,dict(source_sha=sha(path),bound_source_sha=sha256(source.encode()).hexdigest(),
                          changes=[(a,b) for a,b,_ in edits],apps=n,scenes=k)
