"""Population drivers for the frozen Kim and Thermal-GA operators on an indexable catalog."""
from collections import Counter
from dataclasses import asdict
import random

import search


def kim_safe(ev, domain, seed, initial, generation_clock, clock, emit):
    rng = random.Random(seed)
    pop = initial + [rng.choice(domain.order) for _ in range(24 - len(initial))]
    emit("initial_population", pop)
    visited, memo, counts = {}, {}, Counter()
    generations = 0
    generation_stop = "generation_limit"
    def observe(dep, scene, opp):
        generation_clock.check()
        key = dep, scene, opp
        if key not in memo:
            value = ev.proxy(*key)
            generation_clock.check()
            memo[key] = value
            emit("scene_proxy", [*key, value])
        return memo[key]
    try:
        for gen in range(64):
            for dep in pop:
                generation_clock.check()
                counts["positions"] += 1
                if dep not in visited:
                    mapping = search.evaluate_mapping(dep, observe)
                    generation_clock.check()
                    visited[dep] = mapping
            evaluated = [visited[dep] for dep in pop]
            emit("kim_generation", [gen, pop, [p.valid for p in evaluated]])
            generations += 1
            if gen < 63:
                pop = [domain.child(search.lexicase(evaluated, rng), search.lexicase(evaluated, rng),
                                    rng, counts) for _ in range(24)]
    except search.Cutoff:
        generation_stop = "generation_cutoff"
    ranked = search.ranked(visited.values(), domain)
    emit("kim_ranked", [c.row() for c in ranked])
    winner = None
    statuses = Counter()
    stop = "pool_exhausted" if ranked else "empty_pool"
    for candidate in ranked:
        try:
            clock.check()
            result = ev.replay(candidate.dep, candidate.opps)
            clock.check()
        except search.Cutoff:
            stop = "timeout"
            break
        statuses[result.status] += 1
        emit("kim_check", [candidate.dep, candidate.opps, asdict(result)])
        if result.status == "SAFE":
            winner = (candidate.dep, *candidate.opps)
            stop = "first_safe"
            break
    return dict(winner=winner, reason=stop, generation_stop=generation_stop, completed_generations=generations,
                counts=dict(counts), evaluated_mappings=len(visited), proxy_evaluations=len(memo),
                pool_size=len(ranked), completed_checks=sum(statuses.values()), unique_status_counts=dict(statuses),
                first_safe_s=clock.elapsed() if winner else None)


def thermal_ga(ev, domain, seed, initial, clock, emit):
    rng = random.Random(seed)
    pop = []
    for i in range(32):
        dep = initial[i] if i < len(initial) else rng.choice(domain.order)
        pop.append((dep, *(rng.randrange(27) for _ in range(4))))
    emit("initial_population", pop)
    memo, statuses = {}, Counter()
    best = first_safe = None
    generations = positions = 0
    reason = "generation_limit"
    def rank(key):
        return search.thermal_rank((key, memo[key]))
    def tournament():
        return min(rng.sample(pop, 2), key=rank)
    try:
        for gen in range(96):
            for key in pop:
                clock.check()
                positions += 1
                if key not in memo:
                    result = ev.replay(key[0], key[1:])
                    clock.check()
                    memo[key] = result
                    statuses[result.status] += 1
                    emit("ga_evaluation", [key, asdict(result)])
                    if result.status == "SAFE" and (best is None or rank(key) < rank(best)):
                        best = key
                        if first_safe is None:
                            first_safe = clock.elapsed()
            generations += 1
            emit("ga_generation", [gen, pop, best])
            if gen < 95:
                pop = [min(pop, key=rank)] + [search.thermal_child(tournament(), tournament(), domain, rng)
                                              for _ in range(31)]
    except search.Cutoff:
        reason = "timeout"
    return dict(winner=best, reason=reason, first_safe_s=first_safe, completed_generations=generations,
                positions=positions, unique_completed=len(memo), unique_status_counts=dict(statuses))
