"""Finite-path V1 evaluator. Reads inputs only; never imports expected answers."""
from copy import deepcopy
from decimal import Decimal as D
from fractions import Fraction as F
import json
import time

from interval import I, Budget, Exhausted, TaylorPanel, panel_count


class Invalid(Exception):
    pass


def require(test, reason):
    if not test:
        raise Invalid(reason)


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f, parse_float=D)


def stamp(t):
    t = F(t)
    return t.numerator if t.denominator == 1 else str(t)


def validate_platform(p):
    nodes, units = p['nodes'], p['units']
    n = len(nodes)
    require(n > 0 and len(set(nodes)) == n, 'node_identity')
    require(len(p['C_J_per_K']) == n and all(c > 0 for c in p['C_J_per_K']), 'capacitance')
    g = p['G_W_per_K']
    require(len(g) == n and all(len(row) == n for row in g), 'conductance_dimensions')
    require(all(g[i][j] == g[j][i] and (i == j or g[i][j] <= 0) for i in range(n) for j in range(n)), 'passive_symmetric_RC')
    require(all(sum(F(v) for v in row) > 0 for row in g), 'environment_conductance')
    require(len(p['temperature_limit_C']) == n, 'temperature_limits')
    require(p['valid_temperature_C'][0] < p['valid_temperature_C'][1], 'temperature_range')
    require(all(p['valid_temperature_C'][0] <= t <= p['valid_temperature_C'][1] for t in p['temperature_limit_C']), 'limit_outside_model_range')
    require(p['external_power_W'] >= 0, 'external_power')
    require(set(p['opps']) == set(units), 'OPP_units')
    # First implementation requires one explicitly metered unit per node;
    # shared-domain frequency control is supported, shared baseline allocation is not invented.
    require(sorted(u['node'] for u in units.values()) == sorted(nodes), 'one_metered_unit_per_node_required')
    for u in units:
        require(bool(p['opps'][u]), 'empty_OPPs')
        for v in p['opps'][u].values():
            require(v['f_Hz'] > 0 and v['V'] > 0 and v['leak_W_per_K'] >= 0, 'OPP_value')
            for t in p['valid_temperature_C']:
                require(F(v['base_W'])+F(v['leak_W_per_K'])*(F(t)-F(p['leak_reference_C'])) >= 0, 'negative_idle_power')


def validate_plans(x):
    s = x['semantics']
    require(s['extra_preparation_us'] == 0, 'V1_requires_explicit_Z0')
    require(s['relative_schedule'] == 'T1 whole-round translation', 'unsupported_schedule_semantics')
    require(s['nonpreemptive'] and not s['cross_round_overlap'], 'unsupported_execution_rules')
    p = x['platform']
    for name, plan in x['fixed_plans'].items():
        period, deadline, spacing = map(F, [plan['period_us'], plan['relative_deadline_us'], plan['minimum_switch_interval_us']])
        require(0 < deadline <= period <= spacing, 'period_deadline_spacing')
        stages = plan['stages']; by_id = {st['id']: st for st in stages}
        require(len(by_id) == len(stages) > 0, 'Stage_identity')
        for st in stages:
            require(st['unit'] in p['units'] and st['opp'] in p['opps'][st['unit']], 'illegal_mode')
            require(F(st['offset_us']) >= 0 and F(st['duration_us']) > 0 and st['activity_increment_W'] >= 0, 'Stage_value')
            require(all(pred in by_id for pred in st['predecessors']), 'unknown_predecessor')
            for pred in st['predecessors']:
                a = by_id[pred]
                require(F(a['offset_us'])+F(a['duration_us']) <= F(st['offset_us']), 'dependency_violation')
        # Positive durations plus offset inequalities also exclude directed cycles.
        for i, a in enumerate(stages):
            for b in stages[i+1:]:
                overlap = max(F(a['offset_us']), F(b['offset_us'])) < min(F(a['offset_us'])+F(a['duration_us']), F(b['offset_us'])+F(b['duration_us']))
                if overlap:
                    require(a['unit'] != b['unit'], 'unit_overlap')
                    ua, ub = p['units'][a['unit']], p['units'][b['unit']]
                    if ua['frequency_domain'] == ub['frequency_domain']:
                        va, vb = p['opps'][a['unit']][a['opp']], p['opps'][b['unit']][b['opp']]
                        require((va['f_Hz'], va['V']) == (vb['f_Hz'], vb['V']), 'shared_domain_conflict')


def expand(x, tr, budget):
    plans = x['fixed_plans']; window = F(tr['window_us'])
    require(window > 0, 'window')
    require(tr['initial_unfinished_work'] == [], 'initial_pending_work_not_supported')
    require(tr['initial_release_us'] == 0, 'initial_release_must_be_zero_for_V1')
    mode = tr['initial_mode']; require(mode in plans, 'initial_mode')
    start = F(0); last_switch = F(x['semantics']['initial_switch_clock_origin_us'])
    require(last_switch == 0, 'initial_switch_clock_origin')
    releases = []
    for switch in tr['switch_requests'] + [None]:
        budget.check()
        end = F(switch['time_us']) if switch else window
        require(start < end <= window, 'unordered_or_outside_switch')
        if switch:
            require([mode, switch['to_mode']] in x['semantics']['allowed_transitions'], 'illegal_transition')
            require(switch['to_mode'] in plans, 'unknown_mode')
            require(end-last_switch >= F(plans[mode]['minimum_switch_interval_us']), 'minimum_switch_interval')
        r = start
        while r < end:
            budget.check()
            deadline = r+F(plans[mode]['relative_deadline_us'])
            require(deadline <= window, 'W1_incompatible')
            releases.append({'mode': mode, 'release_us': r, 'deadline_us': deadline})
            r += F(plans[mode]['period_us'])
        if switch:
            start = last_switch = end
            mode = switch['to_mode']
    rows, requests = [], []
    previous_finish = F(0)
    failure = None
    for k, r in enumerate(releases):
        budget.check()
        base = max(r['release_us'], previous_finish)
        rr = []
        for st in plans[r['mode']]['stages']:
            row = dict(r, request_id=k, stage=st['id'], unit=st['unit'], opp=st['opp'],
                       start_us=base+F(st['offset_us']), end_us=base+F(st['offset_us'])+F(st['duration_us']),
                       activity_increment_W=st['activity_increment_W'])
            rr.append(row)
        finish = max(a['end_us'] for a in rr)
        requests.append(dict(r, request_id=k, base_us=base, finish_us=finish))
        rows.extend(rr); previous_finish = finish
        if finish > r['deadline_us']:
            failure = dict(r, predicted_finish_us=finish, lateness_us=finish-r['deadline_us'])
            break  # No invented backlog/continuation rule beyond an already failed request.
    return rows, requests, releases, failure


def power_segments(x, tr, rows, horizon, budget):
    p = x['platform']; units = p['units']; opps = dict(tr['initial_opps'])
    require(set(opps) == set(units) and all(opps[u] in p['opps'][u] for u in units), 'initial_OPPs')
    domains = {}
    for u, data in units.items():
        domains.setdefault(data['frequency_domain'], []).append(u)
    def fv(u, o):
        v = p['opps'][u][o]; return (v['f_Hz'], v['V'])
    require(all(len({fv(u, opps[u]) for u in us}) == 1 for us in domains.values()), 'initial_domain_mismatch')
    events = {F(0), horizon}
    for row in rows:
        events.update(t for t in [row['start_us'], row['end_us']] if 0 <= t <= horizon)
    # Include requests/releases for traceability even if power is unchanged.
    events.update(F(s['time_us']) for s in tr['switch_requests'] if 0 <= F(s['time_us']) <= horizon)
    events.update(r['release_us'] for r in rows if r['release_us'] <= horizon)
    ev = sorted(events); out = []
    for a, b in zip(ev, ev[1:]):
        budget.check()
        starts = [r for r in rows if r['start_us'] == a]
        continuing = [r for r in rows if r['start_us'] < a < r['end_us']]
        for domain, members in domains.items():
            new = [r for r in starts if r['unit'] in members]
            if not new:
                continue
            choices = {fv(r['unit'], r['opp']) for r in new}
            require(len(choices) == 1, 'same_time_domain_conflict')
            target = next(iter(choices))
            require(all(fv(r['unit'], r['opp']) == target for r in continuing if r['unit'] in members), 'busy_domain_switch')
            for u in members:
                matches = [o for o in p['opps'][u] if fv(u, o) == target]
                require(len(matches) == 1, 'domain_OPP_mapping_not_unique_or_missing')
                opps[u] = matches[0]
        active = [r for r in rows if r['start_us'] <= a < r['end_us']]
        require(len({r['unit'] for r in active}) == len(active), 'resource_overlap')
        base, lam, q = [], [], []
        for node in p['nodes']:
            u = next(u for u in units if units[u]['node'] == node)
            v = p['opps'][u][opps[u]]
            base.append(v['base_W']); lam.append(v['leak_W_per_K'])
            q.append(sum((F(r['activity_increment_W']) for r in active if r['unit'] == u), F(0)))
        out.append({'start_us': a, 'end_us': b, 'base_W': base, 'leak_W_per_K': lam,
                    'activity_W': q, 'opps': dict(opps), 'active': [(r['request_id'], r['stage']) for r in active]})
    return out


def coeff_matrix(p, segment):
    n = len(p['nodes']); size = n+2
    matrix = [[I(0) for _ in range(size)] for _ in range(size)]
    for i in range(n):
        c = I(p['C_J_per_K'][i]); lam = I(segment['leak_W_per_K'][i])
        for j in range(n):
            matrix[i][j] = -I(p['G_W_per_K'][i][j])/c
        matrix[i][i] = matrix[i][i]+lam/c
        q = I.rational(segment['activity_W'][i])
        matrix[i][-1] = (I(segment['base_W'][i])+q+lam*(I(p['ambient_C'])-I(p['leak_reference_C'])))/c
        matrix[n][i] = lam
        matrix[n][-1] = matrix[n][-1]+lam*(I(p['ambient_C'])-I(p['leak_reference_C']))
    return matrix


def thermal(p, initial, segments, accuracy, budget):
    n = len(p['nodes']); ambient = I(p['ambient_C'])
    require(len(initial) == n, 'initial_temperature_dimensions')
    require(all(p['valid_temperature_C'][0] <= t <= p['valid_temperature_C'][1] for t in initial), 'initial_temperature_outside_model')
    z = [I(t)-ambient for t in initial]+[I(0), I(1)]
    peaks = [I(t) for t in initial]; peak_at = [F(0)]*n
    base_parts = [I(0)]*n; activity_parts = [I(0)]*n; external = I(0)
    states = [{'time_us': 0, 'temperature_C': [I(t).data() for t in initial]}]
    logs = []; completed = F(0)
    try:
        for seg in segments:
            budget.check()
            duration = (seg['end_us']-seg['start_us'])/1000000
            matrix = coeff_matrix(p, seg)
            count = panel_count(matrix, duration); step = duration/count
            for j in range(count):
                budget.panel()
                panel = TaylorPanel(matrix, z, step)
                image = panel.value(F(0), step)
                # No clipping at model boundaries. Wide range -> unresolved.
                if any((v+ambient).lo < p['valid_temperature_C'][0] or (v+ambient).hi > p['valid_temperature_C'][1] for v in image[:n]):
                    raise Exhausted('model_range_enclosure_unresolved')
                start_s = seg['start_us']/1000000+j*step
                for i in range(n):
                    peak, at = panel.peak(i, D(accuracy['temperature_enclosure_width_C']), budget)
                    peak = peak+ambient
                    if peak.lo > peaks[i].lo:
                        peak_at[i] = start_s+at
                    peaks[i] = I(max(peaks[i].lo, peak.lo), max(peaks[i].hi, peak.hi))
                budget.check()
                z = panel.value(step); z[-1] = I(1)  # exact constant coordinate
                for i in range(n):
                    base_parts[i] = base_parts[i]+I(seg['base_W'][i])*I.rational(step)
                    activity_parts[i] = activity_parts[i]+I.rational(seg['activity_W'][i])*I.rational(step)
                external = external+I(p['external_power_W'])*I.rational(step)
                completed = (start_s+step)*1000000
            states.append({'time_us': stamp(seg['end_us']), 'temperature_C': [(v+ambient).data() for v in z[:n]]})
            logs.append(dict(seg, panel_count=count))
        energy = sum(base_parts, I(0))+sum(activity_parts, I(0))+external+z[n]
        precision = (energy.width <= D(accuracy['energy_enclosure_width_J'])
                     and all(v.width <= D(accuracy['temperature_enclosure_width_C']) for v in peaks))
        if any(v.lo > limit for v, limit in zip(peaks, p['temperature_limit_C'])):
            status = 'violation'
        elif precision and all(v.hi <= limit for v, limit in zip(peaks, p['temperature_limit_C'])):
            status = 'safe'
        else:
            status = 'unresolved'
        return {'status': status, 'complete': True, 'precision_met': precision,
                'peak_C': [v.data() for v in peaks], 'peak_lower_witness_s': [str(t) for t in peak_at],
                'end_temperature_C': [(v+ambient).data() for v in z[:n]], 'energy_J': energy.data(),
                'base_by_node_J': [v.data() for v in base_parts], 'activity_by_node_J': [v.data() for v in activity_parts],
                'leakage_J': z[n].data(), 'external_J': external.data(), 'states': states, 'segments': logs,
                'covered_until_us': stamp(completed)}
    except Exhausted as exc:
        return {'status': 'unresolved', 'complete': False, 'precision_met': False,
                'reason': str(exc), 'covered_until_us': stamp(completed), 'states': states,
                'segments': logs, 'rankable_energy': False}


def evaluate_trace(x, tr, budget=None):
    budget = budget or Budget()
    result = {'id': tr.get('id'), 'scope': 'given_finite_path', 'sustained_safety': 'not_evaluated',
              'input_status': 'unchecked', 'execution_status': 'unchecked', 'rankable_energy': False}
    try:
        budget.check(); validate_platform(x['platform']); validate_plans(x)
        rows, requests, releases, failure = expand(x, tr, budget)
        horizon = failure['deadline_us'] if failure else F(tr['window_us'])
        segments = power_segments(x, tr, rows, horizon, budget)
        result.update(input_status='valid', execution_status='deadline_violation' if failure else 'valid',
                      schedule=rows, requests=requests, releases=releases, failure=failure,
                      energy_scope='prefix_to_failed_deadline' if failure else 'complete_window')
        result['thermal'] = thermal(x['platform'], tr['initial_temperature_C'], segments, x['accuracy'], budget)
        result['rankable_energy'] = not failure and result['thermal']['status'] == 'safe' and result['thermal']['complete']
    except Invalid as exc:
        result.update(input_status='invalid', reason=str(exc))
    except Exhausted as exc:
        result.update(coverage='incomplete', reason=str(exc), thermal={'status': 'unresolved', 'complete': False})
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        result.update(input_status='invalid', reason=f'{type(exc).__name__}: {exc}')
    result['diagnostic'] = {'elapsed_s': time.monotonic()-budget.start, 'panels': budget.panels, 'peak_refinements': budget.refinements}
    return result


def evaluate_primitive(v, accuracy, budget=None):
    budget = budget or Budget()
    if v['kind'] == 'single_node_constant_segment':
        n, nodes = 1, ['node']
        p = {'C_J_per_K': [v['C_J_per_K']], 'G_W_per_K': [[v['ambient_conductance_W_per_K']]],
             'temperature_limit_C': [v['temperature_limit_C']]}
        initial = [v['initial_temperature_C']]
        b, q, lam = [v['base_W']], [v['activity_increment_W']], [v['leak_W_per_K']]
    else:
        n, nodes = len(v['nodes']), v['nodes']
        p = {k: v[k] for k in ['C_J_per_K', 'G_W_per_K', 'temperature_limit_C']}
        initial = v['initial_temperature_C']; b, q, lam = v['base_W'], v['activity_increment_W'], v['leak_W_per_K']
    p.update({k: v[k] for k in ['ambient_C', 'leak_reference_C', 'valid_temperature_C', 'external_power_W']})
    p['nodes'] = nodes
    seg = {'start_us': F(0), 'end_us': F(v['duration_us']), 'base_W': b, 'activity_W': list(map(F, q)), 'leak_W_per_K': lam}
    r = thermal(p, initial, [seg], accuracy, budget)
    r['id'] = v['id']; r['diagnostic'] = {'elapsed_s': time.monotonic()-budget.start, 'panels': budget.panels, 'peak_refinements': budget.refinements}
    return r


def encode(value):
    if isinstance(value, F):
        return stamp(value)
    if isinstance(value, D):
        return str(value)
    raise TypeError(type(value).__name__)
