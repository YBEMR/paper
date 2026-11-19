"""Joint finite-domain search with original physical replays and run-local scene compilation."""
from collections import Counter
from contextlib import contextmanager
from copy import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "kim_multidnn_expansion"
sys.path.insert(0, str(EXP))
import experiment as model
import joint_thermal as thermal
from design import make_scenes

events = model.events
joint = model.joint
FROZEN = json.loads((EXP / "expanded_input.json").read_bytes())
CATALOG = json.loads((EXP / "catalog.json").read_bytes())["search_order"]
events.FROZEN = FROZEN
OPPS = events.OPPS
SIZE = len(OPPS) ** 4
EPS = 1e-9
REPLAY_TOL = 1e-7


def read(path):
    return json.loads(path.read_bytes())


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


@contextmanager
def measured(stats, key):
    start = perf_counter()
    try:
        yield
    finally:
        stats[key] += perf_counter() - start


class SceneTable:
    """One instance per run/case. Keys are exact tuples. Values contain no inlet temperatures from search."""
    def __init__(self, scenes, method, stats, freeze_sha):
        self.scenes = scenes
        self.method = method
        self.stats = stats
        self.cache = {}
        self.scope = freeze_sha
        self.requests = [tuple((q.id, q.app, q.release_ns, q.deadline_ns) for q in s.requests) for s in scenes]
        self.active = [sorted({q.app for q in s.requests}) for s in scenes]
        # The immutable protocol pins platform, dispatcher, block settings and ambient.
        self.contexts = [(self.scope,i,s.name,s.duration_ns,s.service_end_ns-s.start_ns,
                          self.requests[i],25,True,"base",thermal.BLOCK_SECONDS,thermal.SCREEN_GUARD_C)
                         for i,s in enumerate(scenes)]

    def key(self, deployment, index, opp):
        stages = FROZEN["deployments"][deployment]["stages"]
        active_stages = tuple((a, tuple(map(tuple,stages[str(a)]))) for a in self.active[index])
        # Index interns the exact, immutable context above in this private case cache.
        return self.scope, index, opp, active_stages

    def get(self, deployment, index, opp):
        stats = self.stats
        stats["scene_requests"] += 1
        key = None
        if self.method == "M2":
            with measured(stats,"key_s"):
                key = self.key(deployment,index,opp)
                hit = key in self.cache
            if hit:
                template = self.cache[key]
                stats["hits"] += 1
                stats["legal_hits" if template is not None else "deadline_hits"] += 1
                return self.private(template)
        stats["misses"] += 1
        scene = self.scenes[index]
        with measured(stats,"schedule_s"):
            scheduled = events.time_scene(events.PLATFORM,scene,deployment,opp)
        template = None
        if scheduled.deadline_feasible:
            with measured(stats,"compile_s"):
                kw = events.thermal_kwargs(events.PLATFORM,opp,25,True,"base")
                template = thermal.compile_scene(scheduled.duration_ns*1e-9, scheduled.active_w,
                                                 scheduled.transfer_w,kw)
            stats["compiles"] += 1
            stats["compile_integrations"] += 1 + len(template.upper)
        if template is not None:
            for value in vars(template).values():
                if isinstance(value,np.ndarray):
                    value.flags.writeable = False
        if key is not None:
            self.cache[key] = template
        return self.private(template)

    @staticmethod
    def private(template):
        if template is None:
            return None
        # Only screen_calls and fallback_calls mutate in frozen batch(). Isolate each logical use.
        result = copy(template)
        result.screen_calls = result.fallback_calls = 0
        return result


def energy_search(tables):
    codes = np.zeros(1,dtype=np.int32)
    temps = joint.INITIAL[None,:]
    energies = np.zeros(1)
    depth = []
    for table in tables:
        codes_next, temps_next, costs_next = [], [], []
        for i,kernel in enumerate(table):
            if kernel is None or not len(codes):
                continue
            delta = temps - kernel.initial
            costs_next.append(energies + (kernel.energy0 + delta @ kernel.w))
            temps_next.append(kernel.final0 + delta @ kernel.F.T)
            codes_next.append(codes*len(OPPS)+i)
        if not codes_next:
            return None,np.full(SIZE,np.nan),depth+[0]*(4-len(depth))
        codes = np.concatenate(codes_next)
        temps = np.concatenate(temps_next)
        energies = np.concatenate(costs_next)
        depth.append(len(codes))
    result = np.full(SIZE,np.nan)
    result[codes] = energies
    return joint.pick(codes,energies),result,depth


class Trial:
    def __init__(self,case,method,order,freeze,output,emit):
        self.case, self.method, self.order = case, method, order
        self.scenes = make_scenes(case)
        self.stats = Counter()
        self.builder = SceneTable(self.scenes,method,self.stats,freeze)
        self.output, self.emit = output,emit
        self.verified, self.results = {}, []
        self.replays = {}
        self.best = None
        self.reference_dir = EXP/"raw"/"expanded"/case["id"]
        self.archive = {p.stem[6:]:p for p in self.reference_dir.glob("space_*.npz")}
        self.chosen = []
        self.uncertain = 0
        self.strict = []
        self.original_replay = thermal.SceneKernel.replay
        self.original_screen = thermal._screen

    def report(self, kind, **details):
        self.emit(kind,stats=dict(self.stats), **details)

    def tables(self, deployment):
        tables = []
        for i,_ in enumerate(self.scenes):
            self.report("phase",deployment=deployment,phase="build",index=i)
            tables.append([self.builder.get(deployment,i,o) for o in OPPS])
        return tables

    def constrained(self, tables):
        stats = self.stats
        previous_batch = thermal.SceneKernel.batch
        def checkpoint_batch(kernel, entries):
            energy, end, status = previous_batch(kernel, entries)
            stats['screen_entries_live'] += len(entries)
            stats['fallback_integrals_live'] += kernel.fallback_calls - getattr(kernel,'prior_fallbacks',0)
            kernel.prior_fallbacks = kernel.fallback_calls
            if perf_counter() - self.last_checkpoint >= 2.0:
                self.report('search_progress', phase='constrained', deployment=self.current_deployment)
                self.last_checkpoint = perf_counter()
            return energy,end,status
        def timed_replay(kernel,*args,**kw):
            with measured(stats,"fallback_integral_s"):
                return self.original_replay(kernel,*args,**kw)
        def timed_screen(*args):
            with measured(stats,"envelope_s"):
                return self.original_screen(*args)
        thermal.SceneKernel.replay,thermal._screen = timed_replay,timed_screen
        thermal.SceneKernel.batch = checkpoint_batch
        self.last_checkpoint = perf_counter()
        try:
            with measured(stats,"constrained_search_s"):
                winner,status,energy,depth = joint.joint_search(tables)
        finally:
            thermal.SceneKernel.replay,thermal._screen = self.original_replay,self.original_screen
            thermal.SceneKernel.batch = previous_batch
        kernels = [k for table in tables for k in table if k is not None]
        stats["screen_entries"] += sum(k.screen_calls for k in kernels)
        stats["fallback_integrals"] += sum(k.fallback_calls for k in kernels)
        assert sum(depth)==sum(k.screen_calls for k in kernels)
        return winner,status,energy,depth

    def inspect_array(self, deployment, status, energy, depth, phase):
        legal = np.isfinite(energy)
        count = int(np.count_nonzero(legal))
        assert count == depth[-1]
        if status is not None:
            assert np.array_equal(status!=0,legal)
        tolerance_error = None
        if deployment in self.archive:
            with measured(self.stats,"archive_check_s"),np.load(self.archive[deployment],allow_pickle=False) as old:
                archived = old["energy_j"]
                assert np.array_equal(np.isfinite(archived),legal)
                tolerance_error = float(np.max(np.abs(energy[legal]-archived[legal]))) if count else 0.
                assert tolerance_error<=REPLAY_TOL,(deployment,tolerance_error)
                if status is not None:
                    assert np.array_equal(status,old["status"]),deployment
        fields = dict(legal=count,energy_sha256=digest(energy),depth=depth,max_archive_error_j=tolerance_error)
        if status is not None:
            fields.update(status_sha256=digest(status),unresolved=int(np.sum(status==3)),
                          safe=int(np.sum(status==1)),overtemp=int(np.sum(status==2)))
            # Preserve the frozen original arrays by reference if exactly equal, otherwise archive the pair.
            archive_ref = None
            if deployment in self.archive:
                with np.load(self.archive[deployment],allow_pickle=False) as saved:
                    if digest(saved["energy_j"])==fields["energy_sha256"]:
                        archive_ref = str(self.archive[deployment].relative_to(EXP).as_posix())
            with measured(self.stats,"array_io_s"):
                # All M0/fallback runs pay the original compressed-array write, including archived matches.
                name = phase+"_"+deployment+".npz"
                path = self.output/name
                np.savez_compressed(path,status=status,energy_j=energy)
                if archive_ref:
                    path.unlink()
                fields["arrays"] = archive_ref or name
        return fields

    def verify(self, choice):
        if choice is None:
            return None
        d,code = choice["deployment"],choice["code"]
        if (d,code) not in self.replays:
            with measured(self.stats,"safe_replay_s"):
                physical = events.replay_sequence(events.PLATFORM,self.scenes,d,choice["opps"],25)
            assert physical["required"]==physical["completed"]==500 and physical["deadline_ok"] and physical["fully_replayed"]
            assert len(physical["scene_rows"])==4 and physical["scene_rows"][-1]["end_ns"]==10040000000
            assert abs(physical["energy_j"]-choice["predicted_j"])<=REPLAY_TOL
            assert physical["thermal_status"] in {"SAFE","VIOLATION","UNRESOLVED"}
            assert physical["feasible"]==(physical["thermal_status"]=="SAFE")
            if physical["feasible"]:
                assert max(physical["peak_upper_c"])<=80
            if d in self.archive:
                with np.load(self.archive[d],allow_pickle=False) as old:
                    assert int(old["status"][code])=={"SAFE":1,"VIOLATION":2,"UNRESOLVED":3}[physical["thermal_status"]]
            self.stats["full_replays"] += 1
            self.replays[d,code] = dict(**choice,physical=physical)
            if physical["feasible"]:
                self.verified[d,code] = choice
                self.best = model.choose(list(self.verified.values()))
            self.report("full_replay",choice=self.replays[d,code],best=self.best)
        return self.replays[d,code]

    def scan(self,constrained,phase):
        options, floors, unresolved = [],[],0
        for n,d in enumerate(self.order,1):
            self.current_deployment=d
            tables=self.tables(d)
            self.report("phase",phase=phase,deployment=d,index="search")
            if constrained:
                winner,status,energy,depth=self.constrained(tables)
            else:
                with measured(self.stats,"affine_search_s"):
                    winner,energy,depth=energy_search(tables)
                status=None
            fields=self.inspect_array(d,status,energy,depth,phase)
            self.stats["evaluated_prefixes"]+=sum(depth)
            local=np.isfinite(energy) if status is None else status==1
            floor=float(np.min(energy[local])) if np.any(local) else None
            if floor is not None:
                floors.append(floor)
            unresolved+=fields.get("unresolved",0)
            option=dict(deployment=d,**winner) if winner else None
            if option:
                options.append(option)
                leading=model.choose(options)
                selected=self.verify(leading)
                if constrained:
                    assert selected["physical"]["feasible"]
            self.report("deployment",phase=phase,deployment=d,completed=n,choice=option,
                        strict_min_j=floor,best=self.best,**fields)
        return model.choose(options),min(floors,default=None),unresolved

    def run(self):
        self.report("start_search",method=self.method,domain=self.order,case=self.case)
        with measured(self.stats,"bounds_s"):
            bounds=model.static_lower_bounds(FROZEN,self.scenes)
        self.report("lower_bounds",values={r["deployment"]:r["lower_bound_j"] for r in bounds})
        constrained=self.method=="M0"
        selected,floor,unresolved=self.scan(constrained,"constrained" if constrained else "energy")
        if not constrained and selected and not self.verify(selected)["physical"]["feasible"]:
            self.report("policy_fallback",candidate=selected,reason=self.verify(selected)["physical"]["thermal_status"])
            selected,floor,unresolved=self.scan(True,"fallback")
        replay=self.verify(selected)
        if replay:
            assert replay["physical"]["feasible"] and abs(replay["physical"]["energy_j"]-floor)<=REPLAY_TOL
        self.report("certificate" if not unresolved else "undetermined",scope="catalog" if len(self.order)==81 else "subset",
                    n=len(self.order),winner=replay,lower_bound_j=floor,unresolved=unresolved)
        return replay
