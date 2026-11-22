"""Quota-coupled large-neighbourhood repair on the frozen deployment catalog."""
from collections import Counter
from functools import lru_cache
from itertools import combinations
import random

import numpy as np
import search
from catalog_ext import _stages


class Repair:
    def __init__(self, domain, ev, seed, variant, clock, log, config):
        self.domain, self.ev, self.clock, self.log = domain, ev, clock, log
        self.rng = random.Random(seed)
        self.tolerance = config["energy_tolerance_j"]
        self.batch = config["proposals_per_block"]
        self.blocks = list(combinations(range(4), 1 if variant == "single" else 2))
        self.safe_parent = variant == "safe_parent"
        self.alleles = [[(k,b) for k,shape in enumerate(shapes)
                         for b in range(2 if shape else 1)] for shapes in domain.cuts]
        self.slot_cost = [np.array([len(domain.cuts[a][i]) for i,_ in alleles])
                          for a,alleles in enumerate(self.alleles)]
        self.grid = {block: np.indices(tuple(len(self.alleles[a]) for a in block)).reshape(len(block),-1)
                     for block in self.blocks}
        self.lookups = [{x:i for i,x in enumerate(choices)} for choices in self.alleles]
        self.resources = ("GPU","DLA0","DLA1","XFER")
        self.costs = lru_cache(maxsize=512)(self.app_costs)
        self.genomes, self.mapped, self.polished = {}, {}, set()
        self.best = self.first_safe = self.best_time = None
        self.first_safe_time = None
        self.counter = Counter()

    def app_costs(self, app, scene, opp):
        # Per-frame service is used only to order repairs. Frozen replay owns all certificates.
        n = self.ev.counts[scene][app]
        table = np.zeros((len(self.alleles[app]), 6))
        if n:
            for k,(idx,bit) in enumerate(self.alleles[app]):
                stages = tuple(map(tuple,_stages(self.domain.sizes[app], self.domain.cuts[app][idx], bit)))
                service, energy = self.ev._chain_cost(app, stages, opp)
                table[k] = (n*sum(energy.values()), sum(service.values()),
                            *(service[r] for r in self.resources))
        return table

    def proposals(self, parent, block):
        dep, *freqs = parent
        layout = self.domain._decode(self.domain.raw(dep))
        grid = self.grid[block]
        old_index = [self.lookups[a][layout[a]] for a in range(4)]
        remaining = 4 - sum(self.slot_cost[a][old_index[a]] for a in range(4) if a not in block)
        legal = sum(self.slot_cost[a][g] for a,g in zip(block,grid)) <= remaining
        indices = np.nonzero(legal)[0]
        positions = {a:g[indices] for a,g in zip(block,grid)}
        n = len(indices)
        energy, excess, pressure = np.zeros(n), np.zeros(n), np.zeros(n)
        for j,opp in enumerate(freqs):
            self.clock.check()
            demands = np.zeros((n,4))
            serial = np.zeros(n)
            for app in range(4):
                rows = self.costs(app,j,opp)[positions.get(app,old_index[app])]
                energy += rows[...,0]
                serial = np.maximum(serial, rows[...,1])
                demands += rows[...,2:]
            load = demands.max(axis=1)
            excess = np.maximum(excess,np.maximum(serial,load)-40.)
            pressure += load
        # Among zero-overload policies minimize activity J, then resource peak demand.
        # Full replay may accept or reject either group after SetFreq.
        order = np.lexsort((np.array([self.rng.random() for _ in range(n)]),pressure,
                            np.round(energy,12),np.round(excess,9)))
        offered, seen_local = [], set()
        for pos in order:
            child = list(layout)
            for app, choices in positions.items():
                child[app] = self.alleles[app][choices[pos]]
            target = self.domain.ident(self.domain._encode(tuple(child)))
            if target == dep or target in seen_local or target in self.mapped:
                continue
            seen_local.add(target)
            offered.append((target, float(energy[pos]), float(excess[pos]),
                            sum(child[a] != layout[a] for a in block)))
            if len(offered) == self.batch:
                break
        self.counter["raw_legal_positions_scored"] += n
        return offered

    def replay(self, dep, freqs, source, parent=None):
        key = (dep,*freqs)
        if key in self.genomes:
            return key
        self.clock.check()
        out = self.ev.replay(dep, tuple(freqs))
        when = self.clock.elapsed()
        if when >= self.clock.end - self.clock.start:
            raise search.Cutoff
        self.genomes[key] = out
        self.log("replay", [key, out.status, out.energy_j, out.slack_ms, out.completed,
                            out.lower,out.upper,len(out.late_ids),source,parent], when)
        if out.status == "SAFE":
            if self.first_safe is None:
                self.first_safe, self.first_safe_time = key, when
            if self.best is None or out.energy_j < self.genomes[self.best].energy_j:
                self.best, self.best_time = key, when
                self.log("incumbent",[key,out.energy_j],when)
        return key

    def proxy(self, dep, j, i):
        self.clock.check()
        return self.ev.proxy(dep,j,i)

    def mapping(self, dep, origin, parent=None):
        if dep not in self.mapped:
            proposal = search.evaluate_mapping(dep,self.proxy)
            freqs = tuple(26 if i is None else i for i in proposal.opps)
            self.mapped[dep] = self.replay(dep,freqs,origin,parent)
        return self.mapped[dep]

    def polish(self, parent):
        if parent in self.polished:
            return []
        self.polished.add(parent)
        dep, *current = parent
        local = []
        for j, present in enumerate(current):
            options = [(value,i) for i in range(27) if (value := self.proxy(dep,j,i)) is not None]
            local.append(min(options)[1] if options else present)
        result = [self.replay(dep,local,"joint_frequency",parent)]
        for j,new in enumerate(local):
            f = current.copy()
            f[j] = new
            result.append(self.replay(dep,f,"scene_frequency",parent))
        return result

    def eligible(self, key):
        r = self.genomes[key]
        return r.status == "SAFE" or (not self.safe_parent and r.status == "VIOLATION")

    def cheapest(self, keys):
        admissible = [k for k in keys if self.eligible(k)]
        return min(admissible,key=lambda k:(self.genomes[k].energy_j,k),default=None)

    def run(self, initial):
        reason = "acceptance_cutoff"
        try:
            start = [self.mapping(dep,"initial") for dep in initial]
            parent = self.cheapest(start)
            while True:
                self.clock.check()
                if parent is None:
                    dep = self.rng.choice(self.domain.order)
                    self.counter["uniform_restarts"] += 1
                    parent = self.cheapest([self.mapping(dep,"restart")])
                    continue
                self.log("parent",[parent,self.genomes[parent].status])
                candidates = self.polish(parent)
                blocks = self.blocks.copy()
                self.rng.shuffle(blocks)
                for block in blocks:
                    proposals = self.proposals(parent,block)
                    self.log("repair",[parent,block,proposals])
                    for dep,_,_,_ in proposals:
                        # Frequencies inherited from the parent and recomputed by SetFreq.
                        candidates.append(self.replay(dep,parent[1:],"inherited",parent))
                        candidates.append(self.mapping(dep,"setfreq",parent))
                self.counter["sweeps"] += 1
                winner = self.cheapest(candidates)
                if winner is not None and self.genomes[winner].energy_j < self.genomes[parent].energy_j-self.tolerance:
                    parent = winner
                else:
                    parent = None
        except search.Cutoff:
            pass
        return dict(reason=reason,winner=self.best,first_safe_s=self.first_safe_time,best_safe_s=self.best_time,
                    unique_physical=len(self.genomes),unique_setfreq=len(self.mapped),
                    counts=dict(self.counter),statuses=dict(Counter(r.status for r in self.genomes.values())))
