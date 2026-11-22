"""Energy-first search with an exact deadline screen and an optional hotspot repair queue."""
from collections import Counter
from functools import lru_cache
from math import exp
import random

import search

NODES = ("CPU", "GPU", "DLA0", "DLA1")


class Explorer:
    def __init__(self, ev, domain, seed, method, config, clock, emit):
        self.ev, self.domain, self.rng = ev, domain, random.Random(seed)
        self.directed = method == "directed"
        self.cfg, self.clock, self.emit = config, clock, emit
        self.seen, self.returned = set(), {}
        self.archives = {"SAFE": {}, "VIOLATION": {}}
        self.visits = Counter()
        self.counts = Counter()
        self.best = self.first = self.best_time = None
        self.mapped = set()
        self.span = [s.duration_ns * 1e-9 for s in ev.scenes]
        self.power = ev.platform["power"]
        self.profile = lru_cache(maxsize=32768)(self.scene_profile)

    def scene_profile(self, dep, j, opp):
        p = self.ev.profile(dep,j,opp)
        activity = p["active_j_by_resource"]
        levels = ["LMH".index(c) for c in self.ev.opps[opp]]
        shares = self.power["DLA_node_weights"]
        def nodes(field):
            x = [self.power[field][name][level] for name,level in zip(("CPU","GPU","DLA"),levels)]
            return (x[0],x[1],x[2]*shares[0],x[2]*shares[1])
        span = self.span[j]
        idle, slope = nodes("idle_by_domain_W"), nodes("temp_slope_domain_W_K")
        # All active applications release synchronously once per 40 ms frame.
        apps = [a for a,n in p["requests_by_app"].items() if n]
        service = [{r:v/p["requests_by_app"][a] for r,v in p["busy_ms"][a].items()} for a in apps]
        demand = max(max(sum(row.values()) for row in service),
                     max(sum(row[r] for row in service) for r in ("GPU","DLA0","DLA1","XFER")))
        energy = p["active_j"] + span*(sum(idle)+self.power["board_W"])
        heat_j = [activity[r]+span*idle[i]+p["transfer_j"]*self.power["transfer_heat_fraction"][i]
                  +span*self.power["board_W"]*self.power["board_heat_fraction"][i] for i,r in enumerate(NODES)]
        return energy, heat_j, slope, demand

    def evaluate(self, key, action, parent=None, target=None, proposal=None):
        if key in self.seen:
            return
        self.clock.check()
        dep, *opps = key
        for j,opp in enumerate(opps):
            schedule = self.ev._bound_schedule(self.ev.platform,self.ev.scenes[j],dep,self.ev.opps[opp])
            self.clock.check()
            if not schedule.deadline_feasible:
                self.seen.add(key)
                self.counts["screen_deadline"] += 1
                self.emit("candidate",[key,action,parent,"DEADLINE",None,schedule.min_slack_ns/1e6,
                                       None,j,target,proposal])
                return
        result = self.ev.replay(dep,tuple(opps))
        self.clock.check()
        if result.status == "DEADLINE" or result.completed != 500:
            raise ValueError("Exact screen and frozen replay disagree")
        self.seen.add(key)
        self.returned[key] = result
        self.counts[result.status] += 1
        if target and proposal is not None:
            j,node,_ = target
            row = self.ev._physical[dep,tuple(opps)]["scene_rows"][j]
            proposal["actual_target_peak_c"] = row["peak_upper_c"][node]
            proposal["actual_target_entry_c"] = row["entry_c"][node]
        self.emit("candidate",[key,action,parent,result.status,result.energy_j,result.slack_ms,
                               result.upper,None,target,proposal])
        if result.status in self.archives:
            archive = self.archives[result.status]
            incumbent = archive.get(dep)
            if incumbent is None or self.returned[incumbent].energy_j > result.energy_j:
                archive[dep] = key
        if result.status == "SAFE" and (self.best is None or result.energy_j < self.returned[self.best].energy_j):
            self.best = key
            self.best_time = self.clock.elapsed()
            if self.first is None:
                self.first = self.best_time
            self.emit("incumbent",[key,result.energy_j],self.best_time)

    def setfreq(self, dep, action, parent=None):
        if dep in self.mapped:
            return
        def proxy(d,j,i):
            self.clock.check()
            return self.ev.proxy(d,j,i)
        sol = search.evaluate_mapping(dep,proxy)
        self.mapped.add(dep)
        self.evaluate((dep,*(26 if i is None else i for i in sol.opps)),action,parent)

    def parent(self, round_index):
        safe, hot = self.archives["SAFE"], self.archives["VIOLATION"]
        archive = hot if hot and (not safe or round_index % self.cfg["hot_period"] == 0) else safe
        if not archive:
            return None
        pool = sorted(archive.values(), key=lambda k:(self.returned[k].energy_j,k))[:self.cfg["archive_elites"]]
        # Greedy exploitation alternates with least-expanded low-energy deployments.
        key = pool[0] if round_index % 2 == 0 else min(pool,key=lambda k:(self.visits[k],self.returned[k].energy_j,k))
        self.visits[key] += 1
        return key

    def neighborhood(self, parent, iteration):
        dep, *freqs = parent
        pool = {}
        def offer(key, action):
            if key not in self.seen and key != parent:
                pool.setdefault(key,action)
        for d,action in self.domain.neighbors(dep,self.cfg["random_neighbors"],self.rng):
            offer((d,*freqs),action)
        # Complete one network's coordinate, retaining all other slot assignments.
        app = iteration % 4
        layout = self.domain._decode(self.domain.raw(dep))
        used = sum(len(self.domain.cuts[a][i]) for a,(i,_) in enumerate(layout) if a!=app)
        for i,shape in enumerate(self.domain.cuts[app]):
            if len(shape)+used > 4:
                continue
            for bit in range(2 if shape else 1):
                child = list(layout)
                child[app] = (i,bit)
                offer((self.domain.ident(self.domain._encode(tuple(child))),*freqs),"cut_or_bind")
        for j in range(4):
            for opp in range(27):
                new = freqs.copy()
                new[j] = opp
                offer((dep,*new),"dvfs")
        return pool

    def rank(self, parent, pool):
        dep, *freqs = parent
        rows = self.ev._physical[dep,tuple(freqs)]["scene_rows"]
        base = [self.profile(dep,j,i) for j,i in enumerate(freqs)]
        reference = self.ev.platform["thermal"]["reference_C"]
        temp = [[(a+b)*.5-reference for a,b in zip(row["entry_c"],row["final_c"])] for row in rows]
        observed_slack = [row["min_slack_ns"]/1e6 for row in rows]
        peak,jstar,node = max((t,j,i) for j,row in enumerate(rows) for i,t in enumerate(row["peak_upper_c"]))
        therm = self.ev.platform["thermal"]
        g = therm["ambient_conductance_W_K"][node]+sum(therm["pair_conductance_W_K"][node])
        tau = therm["capacity_J_K"][node]/g
        target = [jstar,node,peak] if self.returned[parent].status=="VIOLATION" else None
        energy_rank, cooling_rank, predicted = {}, {}, {}
        for key in pool:
            self.clock.check()
            total = excursion = response = 0.
            for j,opp in enumerate(key[1:]):
                joules,heat,slope,demand = self.profile(key[0],j,opp)
                total += joules + self.span[j]*sum(x*y for x,y in zip(slope,temp[j]))
                excursion = max(excursion,demand-40.,demand-base[j][3]-observed_slack[j])
                if target and self.directed and j<=jstar:
                    delta_w = ((heat[node]-base[j][1][node])/self.span[j]
                               +(slope[node]-base[j][2][node])*temp[j][node])
                    decay = exp(-self.span[j]/tau)
                    response = decay*response+(1.-decay)*delta_w/g
            energy_rank[key] = (excursion>0,total,excursion,key)
            # Residual >0 is ordered by predicted violation. Once repaired, rank by joules.
            cooling_rank[key] = (excursion>0,max(0.,peak+response-80.),total,key)
            predicted[key] = peak+response if target and self.directed else None
        return energy_rank, cooling_rank, target, predicted

    def run(self, starts):
        it = 0
        try:
            for dep in starts:
                self.setfreq(dep,"initial")
            while True:
                self.clock.check()
                parent = self.parent(it)
                if parent is None or (it+1)%self.cfg["restart_period"] == 0:
                    self.setfreq(self.rng.choice(self.domain.order),"restart")
                if parent is not None:
                    pool = self.neighborhood(parent,it)
                    energy,heat,target,predicted = self.rank(parent,pool)
                    ranked = sorted(pool,key=energy.get)
                    chosen = list(dict.fromkeys([items[0] for items in (
                        [k for k in ranked if pool[k]=="dvfs"],
                        [k for k in ranked if pool[k]=="exchange"],
                        [k for k in ranked if pool[k] not in ("dvfs","exchange")]) if items]))
                    supplement = sorted(pool,key=heat.get) if target and self.directed else ranked
                    reserved = set(chosen)
                    chosen = list(dict.fromkeys(chosen+supplement))[:self.cfg["proposals"]]
                    self.emit("parent",[parent,target,len(pool),len(chosen)])
                    for k in chosen:
                        rule = "operator_reservation" if k in reserved else (
                            "hotspot" if target and self.directed else "energy")
                        self.evaluate(k,pool[k],parent,target,dict(rule=rule,estimated_j=energy[k][1],
                                      predicted_target_peak_c=predicted[k]))
                    unmapped = next((k[0] for k in ranked if k[0] not in self.mapped),None)
                    if unmapped is not None:
                        self.setfreq(unmapped,"setfreq",parent)
                it += 1
        except search.Cutoff:
            pass
        return dict(winner=self.best, first_safe_s=self.first, best_s=self.best_time, rounds=it,
                    unique=len(self.seen),counts=dict(self.counts),stop="admission_cutoff")
