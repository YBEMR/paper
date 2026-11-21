"""P2 pilot search. Callers supply scene proxy, continuous replay and an absolute clock."""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
import json
from math import fsum, inf, isfinite
import random
from time import perf_counter

OPPS = tuple(map("".join, product("LMH", repeat=3)))
TOL = 1e-9
KIM_POP, KIM_GENS = 8, 4
GA_POP, GA_GENS = 16, 8


class Cutoff(Exception):
    """A call returned too late or the next call cannot begin."""


class Clock:
    def __init__(self, start, end, now=perf_counter):
        self.start, self.end, self.now = start, end, now

    def check(self):
        if self.now() >= self.end:
            raise Cutoff

    def elapsed(self):
        return self.now() - self.start


def digest(value):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    return sha256(raw).hexdigest()


class Domain:
    def __init__(self, catalog, allowed):
        order = catalog["search_order"]
        allowed = tuple(allowed)
        if not allowed or len(set(allowed)) != len(allowed) or not set(allowed) <= set(order):
            raise ValueError("unknown, empty or duplicated deployment domain")
        self.order = [dep for dep in order if dep in allowed]
        self.rank = {dep: order.index(dep) for dep in self.order}
        groups = defaultdict(list)
        for dep in order:
            row = catalog["deployments"][dep]
            genes = tuple(row["per_app_candidate_ids"])
            if len(genes) != 4 or row["resident_dla_stages"] > 4:
                raise ValueError("invalid catalog")
            groups[genes].append(dep)
        self.encode, self.decode = {}, {}
        for genes, deps in groups.items():
            for binding, dep in enumerate(sorted(deps)):
                if dep in self.rank:
                    chrom = (*genes, binding)
                    self.encode[dep] = chrom
                    self.decode[chrom] = dep
        self.options = [sorted({c[i] for c in self.decode}) for i in range(5)]

    def child(self, first, second, rng, counts):
        a, b = self.encode[first], self.encode[second]
        genes = list(a)
        if rng.random() < .8:
            genes = [rng.choice((x, y)) for x, y in zip(a, b, strict=True)]
        if rng.random() < .2:
            i = rng.randrange(5)
            choices = [g for g in self.options[i] if g != genes[i]]
            if choices:
                genes[i] = rng.choice(choices)
        dep = self.decode.get(tuple(genes))
        if dep is None:
            counts["illegal_offspring"] += 1
            dep = rng.choice(self.order)
        return dep


def setfreq(observe):
    """Return best tested legal OPP and energy. Preserve the last schedulable path."""
    state = list("HHH")
    best, score = None, inf
    for _ in range(2):
        for axis in (1, 0, 2):
            previous = state[axis]
            for level in "HML":
                state[axis] = level
                idx = OPPS.index("".join(state))
                value = observe(idx)
                if value is None:
                    if level != "H":
                        state[axis] = previous
                    break
                if not isfinite(value) or value < 0:
                    raise ValueError("invalid scene proxy energy")
                if value < score:
                    best, score = idx, value
                previous = level
    return best, score


@dataclass(frozen=True)
class Candidate:
    dep: str
    opps: tuple
    scores: tuple

    @property
    def valid(self):
        return sum(i is not None for i in self.opps)

    def row(self):
        return [self.dep, self.opps, self.scores, fsum(self.scores)]


def lexicase(pop, rng):
    most = max(c.valid for c in pop)
    survivors = [c for c in pop if c.valid == most]
    for scene in rng.sample(range(4), 4):
        low = min(c.scores[scene] for c in survivors)
        survivors = [c for c in survivors if c.scores[scene] <= low + TOL]
        if len(survivors) == 1:
            break
    return rng.choice(survivors).dep


def ranked(candidates, domain):
    ordered = sorted((c for c in candidates if c.valid == 4), key=lambda c: fsum(c.scores))
    result = []
    while ordered:
        base = fsum(ordered[0].scores)
        stop = next((i for i, c in enumerate(ordered) if fsum(c.scores) > base + TOL), len(ordered))
        result.extend(sorted(ordered[:stop], key=lambda c: (domain.rank[c.dep], c.opps)))
        ordered = ordered[stop:]
    return result


def evaluate_mapping(dep, observe):
    evaluated = [setfreq(lambda idx: observe(dep, scene, idx)) for scene in range(4)]
    return Candidate(dep, tuple(idx for idx, _ in evaluated), tuple(value for _, value in evaluated))


def setfreq_enum(domain, observe):
    """SetFreq-Enum81 diagnostic; P2 invokes it only on substitute inputs."""
    return ranked((evaluate_mapping(dep, observe) for dep in domain.order), domain)


def kim_pool(domain, proxy, seed, clock, emit):
    rng = random.Random(seed)
    pop = [rng.choice(domain.order) for _ in range(KIM_POP)]
    visited, memo, counts = {}, {}, Counter()
    reason = "generation_limit"
    try:
        for gen in range(KIM_GENS):
            for slot, dep in enumerate(pop):
                clock.check()
                counts["positions"] += 1
                if dep in visited:
                    counts["deployment_hits"] += 1
                    continue
                def observe(dep, scene, idx):
                    clock.check()
                    key = dep, scene, idx
                    hit = key in memo
                    if not hit:
                        counts["proxy_started"] += 1
                        begin = clock.now()
                        value = proxy(*key)
                        clock.check()
                        memo[key] = value
                        counts["proxy_completed"] += 1
                    emit("setfreq", dict(dep=dep, scene=scene, opp=idx, energy=memo[key], hit=hit,
                                         compute_s=0. if hit else clock.now()-begin))
                    return memo[key]
                mapping = evaluate_mapping(dep, observe)
                clock.check()
                visited[dep] = mapping
            evaluated = [visited[dep] for dep in pop]
            emit("kim_generation", dict(gen=gen, population=pop,
                                        deadline_scenes=[c.valid for c in evaluated]))
            if gen + 1 < KIM_GENS:
                pop = [domain.child(lexicase(evaluated, rng), lexicase(evaluated, rng), rng, counts)
                       for _ in range(KIM_POP)]
    except Cutoff:
        reason = "generation_cutoff"
    pool = ranked(visited.values(), domain)
    rows = [c.row() for c in pool]
    info = dict(seed=seed, reason=reason, domain=domain.order, allowed=len(domain.order), unique_deployments=len(visited),
                pool=rows, pool_sha256=digest(rows), counts=dict(counts), at_s=clock.elapsed())
    emit("kim_pool", info)
    return pool, info


def paired(first, second):
    return all(first[k] == second[k] for k in ("seed", "domain", "pool_sha256", "pool"))


@dataclass(frozen=True)
class Result:
    status: str
    completed: int
    slack_ms: float
    energy_j: float | None
    lower: tuple | None
    upper: tuple | None
    late_ids: tuple = ()

    def __post_init__(self):
        if not (type(self.completed) is int and 0 <= self.completed <= 500 and isfinite(self.slack_ms)):
            raise ValueError("invalid request metrics")
        if self.status == "DEADLINE":
            if (self.energy_j, self.lower, self.upper) != (None, None, None) or not self.late_ids:
                raise ValueError("invalid deadline prefix")
            return
        if (self.completed != 500 or self.slack_ms < 0 or self.energy_j is None or
                not isfinite(self.energy_j) or self.energy_j < 0 or self.late_ids):
            raise ValueError("invalid complete replay")
        if (self.lower is None or self.upper is None or len(self.lower) != 4 or len(self.upper) != 4 or
                any(not isfinite(x) or not isfinite(y) or x > y for x, y in zip(self.lower, self.upper))):
            raise ValueError("invalid four-node bounds")
        status = "VIOLATION" if max(self.lower) > 80 else "SAFE" if max(self.upper) <= 80 else "UNRESOLVED"
        if self.status != status:
            raise ValueError("status inconsistent with peak certificate")


def inspect_kim(pool, enhanced, replay, clock, emit):
    seen, attempts, duplicates = set(), [], 0
    limit = 3 if enhanced else 1
    stop = "empty_pool" if not pool else "exhausted"
    winner = None
    for c in pool:
        key = (c.dep, c.opps)
        if key in seen:
            duplicates += 1
            continue
        try:
            clock.check()
            start = clock.now()
            seen.add(key)
            emit("check_start", dict(dep=c.dep, opps=c.opps))
            r = replay(*key)
            clock.check()
        except Cutoff:
            stop = "timeout"
            break
        step = dict(dep=c.dep, opps=c.opps, result=asdict(r), seconds=clock.now()-start, at_s=clock.elapsed())
        attempts.append(step)
        emit("kim_check", step)
        if r.status == "SAFE":
            winner, stop = key, "first_safe"
            break
        if len(attempts) == limit:
            stop = "k_limit" if enhanced else "first_only"
            break
    return dict(winner=winner, reason=stop, attempts=attempts, duplicates=duplicates,
                checks_started=len(seen), status_counts=dict(Counter(r["result"]["status"] for r in attempts)),
                first_safe_s=attempts[-1]["at_s"] if winner else None, scope="checked_individuals_only")


def thermal_rank(item):
    key, r = item
    if r.status == "SAFE":
        return (0, r.energy_j, key)
    if r.status == "VIOLATION":
        return (1, max(r.lower) - 80, key)
    if r.status == "DEADLINE":
        return (2, len(r.late_ids), max(0., -r.slack_ms), key)
    return (3, key)


def thermal_child(first, second, domain, rng):
    genes = list(first)
    if rng.random() < .8:
        genes = [rng.choice(pair) for pair in zip(first, second, strict=True)]
    for i in range(5):
        if rng.random() < .2:
            genes[i] = rng.choice(domain.order) if i == 0 else rng.randrange(27)
    return tuple(genes)


def thermal_ga(domain, replay, seed, clock, emit):
    rng = random.Random(seed)
    pop = [(rng.choice(domain.order), *(rng.randrange(27) for _ in range(4))) for _ in range(GA_POP)]
    cache, logs = {}, []
    positions = started = hits = 0
    best = first_safe = None
    stop = "generation_limit"
    for gen in range(GA_GENS):
        completed = 0
        try:
            for slot, key in enumerate(pop):
                clock.check()
                positions += 1
                hit = key in cache
                begin = clock.now()
                if hit:
                    hits += 1
                else:
                    started += 1
                    emit("ga_start", dict(gen=gen, slot=slot, genome=key))
                    result = replay(key[0], key[1:])
                    clock.check()
                    cache[key] = result
                res = cache[key]
                if res.status == "SAFE":
                    if first_safe is None:
                        first_safe = clock.elapsed()
                    if best is None or thermal_rank((key, res)) < thermal_rank((best, cache[best])):
                        best = key
                completed += 1
                emit("ga_position", dict(gen=gen, slot=slot, genome=key, hit=hit, result=asdict(res),
                                         seconds=clock.now()-begin, at_s=clock.elapsed()))
        except Cutoff:
            stop = "timeout"
        log = dict(gen=gen, completed=completed, positions=positions, started=started, unique=len(cache),
                   hits=hits, best=best, first_safe_s=first_safe, at_s=clock.elapsed())
        logs.append(log)
        emit("ga_generation", log)
        if stop == "timeout" or gen+1 == GA_GENS:
            break
        def rank(key):
            return thermal_rank((key, cache[key]))
        def tournament():
            return min(rng.sample(pop, 2), key=rank)
        pop = [min(pop, key=rank)] + [thermal_child(tournament(), tournament(), domain, rng)
                                      for _ in range(GA_POP-1)]
    return dict(winner=best, first_safe_s=first_safe, reason=stop, generations=logs,
                completed_generations=sum(g["completed"] == GA_POP for g in logs),
                positions=positions, unique_completed=len(cache), unique_started=started, hits=hits,
                unique_status_counts=dict(Counter(r.status for r in cache.values())),
                scope="checked_individuals_only")
