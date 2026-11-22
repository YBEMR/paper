"""Frozen Kim operators with one external, non-inheritable SAFE check per complete generation."""
from collections import Counter
from dataclasses import asdict
import random

import search


def run(ev, domain, seed, anchors, generation_clock, clock, cfg, emit):
    rng = random.Random(seed)
    size, limit = cfg["population"], cfg["generations"]
    population = anchors + [rng.choice(domain.order) for _ in range(size-len(anchors))]
    emit("initial_population", population)
    visited, memo, checked, counts = {}, {}, {}, Counter()
    best = None
    first = best_time = None
    generations = 0

    def observe(dep, scene, opp):
        generation_clock.check()
        key = dep, scene, opp
        if key not in memo:
            value = ev.proxy(*key)
            generation_clock.check()
            memo[key] = value
            emit("scene_proxy", [*key, value])
        return memo[key]

    def certify(candidate, phase):
        nonlocal best, first, best_time
        clock.check()
        result = ev.replay(candidate.dep, candidate.opps)
        clock.check()
        when = clock.elapsed()
        checked[candidate.dep] = result
        key = (candidate.dep, *candidate.opps)
        emit("kim_check", [phase, key, asdict(result)], when)
        if result.status == "SAFE" and (best is None or result.energy_j < checked[best[0]].energy_j):
            best = key
            best_time = when
            if first is None:
                first = when
            emit("incumbent", [key,result.energy_j], when)

    gen_stop = "generation_limit"
    try:
        for gen in range(limit):
            for dep in population:
                generation_clock.check()
                counts["positions"] += 1
                if dep not in visited:
                    item = search.evaluate_mapping(dep, observe)
                    generation_clock.check()
                    visited[dep] = item
            evaluated = [visited[dep] for dep in population]
            generations += 1
            emit("kim_generation", [gen,population,[p.valid for p in evaluated]])
            candidate = next((c for c in search.ranked(visited.values(),domain) if c.dep not in checked), None)
            if candidate is not None:
                certify(candidate, gen)
            if gen+1 < limit:
                population = [domain.child(search.lexicase(evaluated,rng), search.lexicase(evaluated,rng),
                                           rng,counts) for _ in range(size)]
    except search.Cutoff:
        gen_stop = "generation_cutoff"
    ranked = search.ranked(visited.values(), domain)
    emit("kim_ranked",[item.row() for item in ranked])
    stop = "pool_exhausted"
    try:
        for item in ranked:
            if item.dep not in checked:
                certify(item,"tail")
    except search.Cutoff:
        stop = "admission_cutoff"
    return dict(winner=best, first_safe_s=first, best_s=best_time, reason=stop, generation_stop=gen_stop,
                completed_generations=generations, evaluated_mappings=len(visited), pool_size=len(ranked),
                counts=dict(counts), checked=len(checked),
                statuses=dict(Counter(r.status for r in checked.values())))
