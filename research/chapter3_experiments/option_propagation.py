"""Remove unsupported local options before generating events and physics."""
from collections import defaultdict

from inputs import _fraction


def propagate_local_options(instance, options, *, budget):
    """Return the surviving options, in their original order, and audit counts.

    A feasible assignment supplies a predecessor that finishes on time, a
    successor that starts on time, and the same concrete unit in every copy
    of a shared Stage. No option in such an assignment can be the first one
    removed. Times are exact and touching endpoints are compatible.
    """
    domains, shared, edges = {}, defaultdict(list), []
    for scene in instance['scenarios']:
        sid = scene['id']
        for stage in scene['stage_instances']:
            key = sid, stage['id']
            domains[key] = []
            shared[stage['shared_stage_id']].append(key)
        edges.extend(((sid, before), (sid, after)) for before, after in scene['dependencies'])

    starts, ends, units = [], [], []
    for index, option in enumerate(options):
        if index % 128 == 0:
            budget.check()
        domains[option['scenario_id'], option['stage_instance_id']].append(index)
        starts.append(_fraction(option['start_ms']))
        ends.append(_fraction(option['end_ms']))
        units.append(option['unit_id'])

    counts = dict(precedence_forward=0, precedence_backward=0, shared_unit=0)
    trace = []

    def retain(key, kept, rule, support):
        removed = len(domains[key]) - len(kept)
        if removed:
            domains[key] = kept
            counts[rule] += removed
            trace.append(dict(pass_index=passes, stage=key, rule=rule,
                              support=support, removed=removed))

    passes = 0
    while True:
        budget.check()
        passes += 1
        prior_changes = len(trace)
        for before, after in edges:
            budget.check()
            earliest_end = min((ends[i] for i in domains[before]), default=None)
            latest_start = max((starts[i] for i in domains[after]), default=None)
            retain(after, [i for i in domains[after]
                           if earliest_end is not None and starts[i] >= earliest_end],
                   'precedence_forward', dict(stage=before,
                       earliest_end_ms=None if earliest_end is None else str(earliest_end)))
            retain(before, [i for i in domains[before]
                            if latest_start is not None and ends[i] <= latest_start],
                   'precedence_backward', dict(stage=after,
                       latest_start_ms=None if latest_start is None else str(latest_start)))
        for stage, copies in shared.items():
            budget.check()
            if len(copies) < 2:
                continue
            support = set.intersection(*({units[i] for i in domains[key]} for key in copies))
            for key in copies:
                retain(key, [i for i in domains[key] if units[i] in support],
                       'shared_unit', dict(shared_stage_id=stage, common_units=sorted(support)))
        if len(trace) == prior_changes:
            break

    surviving = {i for indices in domains.values() for i in indices}
    retained = [option for i, option in enumerate(options) if i in surviving]
    budget.check()
    return retained, dict(options_before=len(options), options_after=len(retained),
                          passes=passes, removed_by_rule=counts, trace=trace,
                          empty_stage_domains=[key for key, domain in domains.items() if not domain])
