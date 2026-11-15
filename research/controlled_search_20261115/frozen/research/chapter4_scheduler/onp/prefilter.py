"""Exact rejections for a fixed incumbent, selected modes and start template.

No thermal approximation, candidate acceptance, resource rescheduling or mode
dominance. A group rejection applies to every permitted extra edge of that
group; an edge rejection applies only to that edge. Caches live for one round.
"""
from bisect import bisect_left, bisect_right
from collections import Counter
from fractions import Fraction as F

from .. import graph_core


class RoundFilter:
    def __init__(self, instance, incumbent, budget, counts):
        self.instance, self.budget, self.counts = instance, budget, counts
        self.grid = F(instance['start_grid_ms'])
        self.declared = graph_core.explicit_start_sets(instance, budget)
        validated = graph_core._validated(instance, incumbent, budget)
        self.scenes, self.cache = {}, {}
        for scene in instance['scenarios']:
            budget.check()
            sid = scene['id']
            nodes = {n['id']: n for n in scene['stage_instances']}
            old = {r['stage_id']: r for r in validated['scenes'][sid]['rows']}
            pred, succ = ({n: set() for n in nodes} for _ in range(2))
            for u, v in scene['dependencies']:
                pred[v].add(u); succ[u].add(v)
            order, pending = [], set(nodes)
            while pending:
                budget.check()
                ready = sorted(n for n in pending if not (pred[n] & pending))
                if not ready:
                    raise graph_core.GraphInputError('TASK_DAG_CYCLE')
                order.extend(ready); pending.difference_update(ready)
            reach = {n: set() for n in nodes}
            for n in reversed(order):
                for v in succ[n]:
                    reach[n].add(v); reach[n].update(reach[v])
            requests = {r['id']: r for r in scene['requests']}
            modes, release, due = {}, {}, {}
            for n, node in nodes.items():
                budget.check()
                modes[n] = {}
                for m in instance['stage_modes'][node['shared_stage_id']]:
                    key = (m['unit_id'], m['opp_id'])
                    if key in modes[n]:
                        raise graph_core.GraphInputError('AMBIGUOUS_MODE')
                    modes[n][key] = F(m['duration_ms'])
                req = requests[node['request_id']]
                release[n] = max(F(0), F(req['release_ms']))
                due[n] = min(F(req['deadline_ms']), F(instance['window_ms']))
            self.scenes[sid] = dict(old=old, pred=pred, succ=succ,
                order=order, reach=reach, modes=modes, release=release, due=due)

    def next_start(self, sid, node, lower):
        if self.declared is None:
            return -((-lower) // self.grid) * self.grid
        choices = self.declared[sid][node]
        j = bisect_left(choices, lower)
        return choices[j] if j < len(choices) else None

    def previous_start(self, sid, node, upper):
        if self.declared is None:
            return (upper // self.grid) * self.grid
        choices = self.declared[sid][node]
        j = bisect_right(choices, upper) - 1
        return choices[j] if j >= 0 else None

    def bounds(self, sid, selected, overrides, template):
        key = (sid, tuple(sorted(selected)), tuple(sorted(overrides.items())), template)
        if key in self.cache:
            self.counts['bounds_cache_hits'] += 1
            return self.cache[key]
        self.counts['bounds_computations'] += 1
        s = self.scenes[sid]
        affected = set(selected)
        for n in selected:
            affected.update(s['reach'][n])
        durations, earliest, latest = {}, {}, {}
        data = dict(sid=sid, duration=durations, earliest=earliest, latest=latest,
                    rejection=None)
        for n in s['order']:
            self.budget.check()
            row = s['old'][n]
            durations[n] = s['modes'][n][(row['unit'], overrides.get(n, row['opp']))]
            lower = s['release'][n]
            if template == 'preserve' and n not in affected:
                lower = max(lower, F(row['start_ms']))
            lower = max([lower] + [earliest[p] + durations[p] for p in s['pred'][n]])
            earliest[n] = self.next_start(sid, n, lower)
            if earliest[n] is None:
                data['rejection'] = dict(kind='DAG_NO_ALLOWED_START', node=n, lower_ms=str(lower))
                break
        if data['rejection'] is None:
            for n in reversed(s['order']):
                self.budget.check()
                upper = min([s['due'][n] - durations[n]] +
                            [latest[v] - durations[n] for v in s['succ'][n]])
                latest[n] = self.previous_start(sid, n, upper)
                if latest[n] is None or earliest[n] > latest[n]:
                    data['rejection'] = dict(kind='DAG_TIME_BOUNDS', node=n,
                        earliest_ms=str(earliest[n]), latest_ms=None if latest[n] is None else str(latest[n]))
                    break
        self.cache[key] = data
        return data

    def group(self, sid, selected, overrides, orientation, template):
        """Only these certificates may eliminate a base AND all its repairs."""
        self.budget.check(); self.counts['base_considered'] += 1
        s = self.scenes[sid]
        if orientation == 'reverse' and len(selected) == 2:
            u, v = sorted(selected, key=lambda n: graph_core._time_key(s['old'][n]))
            a, b = s['old'][u], s['old'][v]
            resource = a['unit'] == b['unit'] or (a['domain_id'] == b['domain_id'] and
                overrides.get(u, a['opp']) != overrides.get(v, b['opp']))
            if resource and v in s['reach'][u]:
                cert = dict(kind='PRIMARY_TASK_RESOURCE_CYCLE', original_edge=[u, v])
                return None, cert
        bounds = self.bounds(sid, selected, overrides, template)
        return bounds, bounds['rejection']

    def edge(self, bounds, base, edge):
        """Reject only this extra edge; the caller MUST continue other edges."""
        self.budget.check(); self.counts['extra_considered'] += 1
        edge = tuple(edge)
        u, v = edge
        for trace in base['blocking_traces']:
            self.budget.check()
            if edge not in [(e['from'], e['to']) for e in trace['edges']]:
                return dict(kind='UNCHANGED_LATE_PATH', late_node=trace['stage_id'],
                            original_edge=list(edge))
        assert bounds is not None and bounds['rejection'] is None
        lower = max(bounds['earliest'][u], bounds['earliest'][v] + bounds['duration'][v])
        start = self.next_start(bounds['sid'], u, lower)
        if start is None or start > bounds['latest'][u]:
            return dict(kind='REVERSE_EDGE_TIME_BOUND', original_edge=list(edge),
                earliest_ms=None if start is None else str(start), latest_ms=str(bounds['latest'][u]))
        return None


def new_counts():
    return Counter()
