"""Full 13-allele main-stage GA and SA with identical generic FIFO repair."""
import math
from time import perf_counter
from fifo import EMPTY
from assets import assemble, idle_plan, record


def genes(plan):
    return tuple(row[:2] for row in plan[0][1::3])


def repair(model, requested, parent):
    # Keep the requested allele if step permits it. On a dead end, undo
    # proposed changes from the right until a complete feasible parent prefix
    # and suffix can be replayed. The parent is itself FIFO-feasible.
    state = EMPTY
    actual = []
    for i, op in enumerate(requested):
        nxt = model.step(state, i, op)
        if nxt is None:
            candidates = sorted(model.ops, key=lambda x: (x != parent[i], model.busy[i][x], x))
            for candidate in candidates:
                nxt = model.step(state, i, candidate)
                if nxt is not None:
                    op = candidate
                    break
        if nxt is None:
            break
        actual.append(op)
        state = nxt
    if len(actual) == model.n:
        return tuple(actual)
    trial = list(requested)
    for i in reversed(range(model.n)):
        if trial[i] != parent[i]:
            trial[i] = parent[i]
            if model.replay(trial) is not None:
                return tuple(trial)
    return tuple(parent)


def mutate(cfg, ops, rng, ga=False):
    trial = list(cfg)
    ids = [i for i in range(len(cfg)) if rng.random() < 1/len(cfg)] if ga else []
    if (ga and rng.random() < .25) or (not ga and rng.random() < .40):
        ids.extend(rng.sample(range(len(cfg)), rng.randint(2, min(8, len(cfg)))))
    elif not ga:
        ids.append(rng.randrange(len(cfg)))
    for i in sorted(set(ids)):
        trial[i] = rng.choice([o for o in ops if o != trial[i]])
    return trial


def evolved_plan(p, cfg):
    return idle_plan(p, assemble(p, cfg))


def evolve(ctx, model, rng, method, end, params, max_steps=None):
    initial = ctx.best
    start = perf_counter()
    original = genes(ctx.plan)
    cache = {original: initial}
    def judge(raw, parent):
        cfg = repair(model, raw, parent)
        if cfg not in cache:
            if len(cache) >= 2048:
                cache.clear()
            cache[cfg] = ctx.consider(evolved_plan(ctx.p, cfg), end)
        return cfg, cache[cfg]
    if method == "SA":
        cfg, score = original, initial
        step = uphill = 0
        while perf_counter() < end-.6 and (max_steps is None or step < max_steps):
            trial, value = judge(mutate(cfg, model.ops, rng), cfg)
            progress = min(1., (perf_counter()-start)/max(.001,end-start))
            temperature = params["T_initial"] * params["final_ratio"] ** progress
            if value and value["eligible"]:
                delta = (value["J"]-score["J"])/initial["J"]
                if delta <= 0 or rng.random() < math.exp(-delta/temperature):
                    uphill += int(delta > 0)
                    cfg, score = trial, value
            if step % 32 == 0:
                record(ctx.folder/"rounds.jsonl", dict(phase="SA", turn=step, temperature=temperature,
                       current=score["J"], best=ctx.best, uphill=uphill, elapsed_s=ctx.elapsed()))
            step += 1
        return dict(steps=step, uphill_accepted=uphill)
    size = params["population"]
    population = [(original, initial)]
    while len(population) < size and perf_counter() < end-.6:
        cfg, val = judge(mutate(original, model.ops, rng), original)
        population.append((cfg,val) if val and val["eligible"] else (original,initial))
    def tournament():
        return min(rng.sample(population,min(params["tournament"],len(population))), key=lambda pair:pair[1]["J"])
    turn = 0
    while perf_counter()<end-.6 and (max_steps is None or turn < max_steps):
        children = sorted(population,key=lambda pair:pair[1]["J"])[:params["elite"]]
        while len(children) < size and perf_counter() < end-.6:
            parent, old = tournament()
            other, _ = tournament()
            child = [a if rng.random()<.5 else b for a,b in zip(parent,other)] if rng.random()<params["crossover"] else parent
            child, value = judge(mutate(child, model.ops, rng, ga=True), parent)
            children.append((child,value) if value and value["eligible"] else (parent,old))
        population = children
        record(ctx.folder/"rounds.jsonl",dict(phase="GA",turn=turn,population=len(population),
               distinct=len({x for x,_ in population}),best=ctx.best,elapsed_s=ctx.elapsed()))
        turn += 1
    return dict(generations=turn, population=len(population))

