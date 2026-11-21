"""Budgeted cut/binding and frequency neighbourhood search on frozen physical replays."""
from collections import Counter
from dataclasses import asdict
from functools import lru_cache
from math import fsum
import random

import search


RESOURCES = ("CPU", "GPU", "DLA0", "DLA1", "XFER")
THERMAL_NODES = RESOURCES[:4]
VARIANTS = ("full", "no_heat", "no_contention", "no_coord")
SETTINGS = dict(initial_deployments=8, rounds=32, candidates_per_round=6,
                sampled_structures=16, elite_deployments=6, joint_parents=2,
                wait_ratio_cap=4.0, certificate_limit_c=80.0, initial_c=30.0,
                deadline_ms=40.0)
SCORE_FIELDS = ("active_energy", "contention", "deadline", "continuous_heat")
OPP_NEIGHBORS = tuple(
    tuple(j for j, other in enumerate(search.OPPS)
          if sum(abs("LMH".index(x) - "LMH".index(y)) for x, y in zip(opp, other)) == 1)
    for opp in search.OPPS)


def search_rank(item, use_heat):
    """The no_heat walk never uses the certificate flag to select an anchor."""
    key, result = item
    if result.status == "DEADLINE":
        return (2, len(result.late_ids), -result.completed, -result.slack_ms, key)
    if use_heat and result.status != "SAFE":
        return (1, max(result.upper) - SETTINGS["certificate_limit_c"], result.energy_j, key)
    return (0, result.energy_j, key)


def choose_anchor(results, expansions, iteration, rng, use_heat):
    ordered = sorted(results.items(), key=lambda item: search_rank(item, use_heat))
    if iteration % 3 == 0:
        return ordered[0][0]
    elite = {}
    for key, _ in ordered:
        elite.setdefault(key[0], key)
        if len(elite) == SETTINGS["elite_deployments"]:
            break
    least_visits = min(expansions[k] for k in elite.values())
    choices = [k for k in elite.values() if expansions[k] == least_visits]
    return choices[0] if iteration % 3 == 1 else rng.choice(choices)


def compact_profile(ev, dep, scene, opp):
    p = ev.profile(dep, scene, opp)
    apps = p["requests_by_app"]
    per_request = {}
    loads = dict.fromkeys(RESOURCES, 0.0)
    for app, count in apps.items():
        if count:
            busy = p["busy_ms"][app]
            per_request[app] = {r: busy.get(r, 0.) / count for r in RESOURCES}
            for r in RESOURCES:
                loads[r] += busy.get(r, 0.)
    return dict(active=p["active_j"], transfer=p["transfer_j"], energy=p["active_j_by_resource"],
                service=per_request, load=loads)


def observed_signals(diagnostics, use_heat, use_queues):
    signals = {}
    for row in diagnostics:
        prices = dict.fromkeys(RESOURCES, 0.)
        if use_queues:
            for r in RESOURCES:
                busy = sum(v.get(r, 0.) for v in row["busy_ms"].values())
                wait = sum(v.get(r, 0.) for v in row["wait_ms"].values())
                if busy > 0:
                    prices[r] = min(SETTINGS["wait_ratio_cap"], wait / busy)
        heat = dict.fromkeys(THERMAL_NODES, 0.)
        if use_heat:
            inlet = row["entry_c"]
            peak = row["peak_upper_c"] or inlet
            for r, entry, upper in zip(THERMAL_NODES, inlet, peak, strict=True):
                # The 30--80 C interval is the frozen initial-temperature-to-limit interval.
                span = SETTINGS["certificate_limit_c"] - SETTINGS["initial_c"]
                entry_load = max(0., (entry - SETTINGS["initial_c"]) / span)
                peak_load = max(0., (upper - SETTINGS["initial_c"]) / span)
                heat[r] = .5 * (entry_load ** 4 + peak_load ** 4)
        signals[row["index"]] = dict(queues=prices, heat=heat, slack=row["slack_ms"],
                                     app_slack=row.get("slack_by_app_ms", {}))
    return signals


def scene_delta(base, new, signal, duration_ms, base_energy):
    """All contributions are dimensionless; lower indicates a better proposal."""
    energy = (new["active"] - base["active"]) / base_energy
    transfer = new["transfer"] - base["transfer"]  # Already included once in active energy.
    if signal is None:
        return (energy, 0., 0., 0., transfer)
    queues = signal["queues"]
    contention = sum(queues[r] * (new["load"][r] - base["load"][r]) for r in RESOURCES) / duration_ms
    heat = sum(signal["heat"][r] * (new["energy"].get(r, 0.) - base["energy"].get(r, 0.))
               for r in THERMAL_NODES) / base_energy
    # Approximate change in one request's response time from changed stage demand
    # and observed relative waiting for each resource, including serial transfers.
    excess_before = excess_after = 0.
    for app, old_service in base["service"].items():
        new_service = new["service"][app]
        delta_ms = sum((1. + queues[r]) * (new_service[r] - old_service[r]) for r in RESOURCES)
        slack = signal["app_slack"].get(app, signal["slack"])
        excess_before = max(excess_before, -slack)
        excess_after = max(excess_after, delta_ms - slack)
    deadline = (excess_after - excess_before) / SETTINGS["deadline_ms"]
    return (energy, contention, deadline, heat, transfer)


def proposals(anchor, ev, domain, rng, clock, profile, variant):
    dep, *opps = anchor
    observed = observed_signals(ev.diagnostics(dep, tuple(opps)), variant != "no_heat",
                                variant != "no_contention")
    base = [profile(dep, j, i) for j, i in enumerate(opps)]
    energy_scale = max(1e-12, sum(p["active"] for p in base))
    duration_ms = [scene.duration_ns / 1e6 for scene in ev.scenes]
    scene_weights = [len(s.requests) / 500 for s in ev.scenes]

    @lru_cache(None)
    def change(d, j, i):
        clock.check()
        v = scene_delta(base[j], profile(d, j, i), observed.get(j), duration_ms[j], energy_scale)
        return (v[0], v[1]*scene_weights[j], v[2]*scene_weights[j], v[3], v[4])

    pool = {}

    def add(d, choices, action):
        key = (d, *choices)
        if key == anchor or key in pool:
            return
        terms = tuple(map(fsum, zip(*(change(d, j, i) for j, i in enumerate(choices)))))
        pool[key] = (fsum(terms[:4]), action, terms)

    neighbors = domain.neighbors(dep, SETTINGS["sampled_structures"], rng,
                                 allow_exchange=variant != "no_coord")
    for d, action in neighbors:
        add(d, opps, action)
    structural = sorted(pool, key=lambda key: (pool[key][0], key))
    # Reserve one coupled frequency proposal for each of a local mapping and a
    # two-network transfer, so a large single-network neighbourhood cannot crowd it out.
    parents = []
    for exchange in (False, True):
        first = next((k for k in structural if (pool[k][1] == "exchange") == exchange), None)
        if first is not None:
            parents.append(first)
    for k in structural:
        if len(parents) == SETTINGS["joint_parents"]:
            break
        if k not in parents:
            parents.append(k)

    for d, action in [(dep, "dvfs"), *((k[0], pool[k][1]+"+dvfs") for k in parents)]:
        joint = list(opps)
        for j, current in enumerate(opps):
            options = (current, *OPP_NEIGHBORS[current])
            joint[j] = min(options, key=lambda i: fsum(change(d, j, i)[:4]))
            if d == dep:
                for opp in options[1:]:
                    single = list(opps)
                    single[j] = opp
                    add(d, single, action)
        add(d, joint, action)
    return pool


def select_keys(pool, results):
    ordered = sorted((k for k in pool if k not in results), key=lambda k: (pool[k][0], k))
    chosen = []
    # Fixed operator quotas prioritize different mechanisms, then unused slots go
    # to the best remaining proposal. The no_coord variant uses the identical cap.
    for actions in ({"dvfs"}, {"cut", "binding"}, {"exchange"}, {"cut+dvfs", "binding+dvfs"},
                    {"exchange+dvfs"}):
        key = next((k for k in ordered if pool[k][1] in actions), None)
        if key is not None:
            chosen.append(key)
    for k in ordered:
        if len(chosen) == SETTINGS["candidates_per_round"]:
            break
        if k not in chosen:
            chosen.append(k)
    return chosen


def run(ev, domain, seed, clock, emit, *, variant="full", initial_deps=None):
    """Return a flat (deployment, four OPPs) SAFE witness plus search accounting."""
    if variant not in VARIANTS:
        raise ValueError(f"Unsupported ablation: {variant}")
    rng = random.Random(seed)
    if initial_deps is None:
        initial_deps = rng.sample(domain.order, min(len(domain.order), SETTINGS["initial_deployments"]))
    starts = list(dict.fromkeys(initial_deps))[:SETTINGS["initial_deployments"]]
    if not starts:
        raise ValueError("Empty common initialization")
    results, expansions, actions = {}, Counter(), Counter()
    profile = lru_cache(maxsize=8192)(lambda d, j, i: compact_profile(ev, d, j, i))
    best = first_safe = None
    completed_rounds = 0
    reason = "round_limit"
    proxy_calls = 0
    settings = {**SETTINGS, "variant": variant, "seed": seed, "initial_deps": starts}
    emit("cooperative_settings", settings)

    def check_state(key, action, parent=None, terms=None):
        nonlocal best, first_safe
        clock.check()
        emit("cooperative_start", dict(genome=key, operator=action))
        result = ev.replay(key[0], key[1:])
        clock.check()
        results[key] = result
        actions[action] += 1
        if result.status == "SAFE":
            if first_safe is None:
                first_safe = clock.elapsed()
            if best is None or (result.energy_j, key) < (results[best].energy_j, best):
                best = key
        parts = {} if terms is None else dict(zip((*SCORE_FIELDS, "transfer_delta_j"), terms))
        emit("cooperative_position", dict(genome=key, parent=parent, operator=action, score_terms=parts,
                                          result=asdict(result), at_s=clock.elapsed()))

    def observe(d, j, i):
        nonlocal proxy_calls
        clock.check()
        p = ev.proxy(d, j, i)
        proxy_calls += 1
        clock.check()
        return p

    try:
        for d in starts:
            candidate = search.evaluate_mapping(d, observe)
            # An infeasible scene has no proxy OPP; replay its fastest OPP to
            # diagnose the deadline and expose possible cut or resource repair.
            key = (d, *(26 if i is None else i for i in candidate.opps))
            check_state(key, "initialize")
        for iteration in range(SETTINGS["rounds"]):
            clock.check()
            anchor = choose_anchor(results, expansions, iteration, rng, variant != "no_heat")
            expansions[anchor] += 1
            pool = proposals(anchor, ev, domain, rng, clock, profile, variant)
            chosen = select_keys(pool, results)
            emit("cooperative_round", dict(index=iteration, anchor=anchor,
                                           proposals=len(pool), selected=len(chosen)))
            for key in chosen:
                _, action, terms = pool[key]
                check_state(key, action, anchor, terms)
            completed_rounds += 1
    except search.Cutoff:
        reason = "timeout"
    failed = [(k, r) for k, r in results.items() if r.status != "SAFE"]
    diagnostic = min(failed, key=search.thermal_rank)[0] if failed else None
    return dict(winner=best, first_safe_s=first_safe, reason=reason, unique_completed=len(results),
                unique_status_counts=dict(Counter(r.status for r in results.values())),
                initialized=actions["initialize"], completed_rounds=completed_rounds,
                action_counts=dict(actions), proxy_calls=proxy_calls, best_failed=diagnostic,
                scope="checked_individuals_only")
