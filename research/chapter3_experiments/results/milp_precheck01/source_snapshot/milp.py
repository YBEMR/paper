"""Finite-option, full thermal-energy MILP and validated continuous feedback.

All exported rows are <= inequalities. Coefficient and double conversion
errors enlarge rows outwards. intlinprog bounds/status remain solver-reported;
only the common evaluator supplies a safe schedule and system-energy upper
bound. Small explicit start sets are permitted solely for named fixtures.
"""
from bisect import bisect_right
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import math

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from inputs import expand_options
from schedules import validate_schedule
from thermal import I, Budget, Exhausted, _q, evaluate_candidate
from milp_coefficients import Coefficients


def _box(value):
    return value if isinstance(value, I) else I.rational(F(value))


def _up(value):
    value = F(value)
    f = float(value)
    if not math.isfinite(f):
        raise ValueError('unrepresentable MILP coefficient/bound')
    return math.nextafter(f, math.inf) if F.from_float(f) < value else f


def _down(value):
    return -_up(-F(value))


def _plus(row, index, value):
    row[index] = _box(row.get(index, 0))+_box(value)


class Model:
    def __init__(self, instance, budget):
        self.instance = deepcopy(instance)
        self.budget = budget
        self.names, self.lb, self.ub, self.integer, self.c = [], [], [], [], []
        self.bounds, self.rows, self.scenes, self.shared = [], [], {}, {}
        self.options, self.option_vars, self.feedback_log = [], [], []
        self.coefficients = Coefficients(self.instance['platform'], budget)
        self.excluded_schedules = set()
        self.feedback_identities = set()

    def var(self, name, lower=0, upper=1, integer=False, cost=0):
        lower, upper = F(lower), F(upper)
        if lower > upper:
            raise ValueError('incompatible variable bounds: '+name)
        index = len(self.names)
        self.names.append(name)
        self.lb.append(_down(lower))
        self.ub.append(_up(upper))
        self.bounds.append((F.from_float(self.lb[-1]), F.from_float(self.ub[-1])))
        self.c.append(float(F(cost)))
        if integer:
            self.integer.append(index)
        return index

    def le(self, row, rhs, tag):
        """Necessary outer row for interval coefficients on a finite box.

        If exact a*z<=b and a,b lie in supplied intervals, then nominal(a)*z
        <= upper(b)+sum(delta_a*maxabs(z)). Final rhs rounds upwards.
        """
        self.budget.check()
        exported, allowance = {}, F(0)
        for index, value in row.items():
            value = _box(value)
            if value.lo == value.hi == 0:
                continue
            nominal = float((F(value.lo)+F(value.hi))/2)
            exact_nominal = F.from_float(nominal)
            deviation = max(abs(F(value.lo)-exact_nominal), abs(F(value.hi)-exact_nominal))
            allowance += deviation*max(abs(v) for v in self.bounds[index])
            if nominal:
                exported[index] = nominal
        rhs = _box(rhs)
        self.rows.append({'coef': exported, 'rhs': _up(F(rhs.hi)+allowance), 'tag': tag,
                          'rounding_allowance': str(allowance), 'rhs_interval': rhs.data()})

    def eq(self, row, rhs, tag):
        self.le(row, rhs, tag+'/upper')
        self.le({i: -_box(v) for i, v in row.items()}, -_box(rhs), tag+'/lower')

    def conditional_le(self, row, rhs, gate, tag):
        # This M covers the full residual on the exported variable box, not a
        # guessed scheduling horizon. Interval products include every sign.
        rhs = _box(rhs)
        residual = sum((_box(a)*I.rational(self.bounds[j][0]) if self.bounds[j][0] == self.bounds[j][1]
                        else _box(a)*I(I.rational(self.bounds[j][0]).lo, I.rational(self.bounds[j][1]).hi)
                        for j, a in row.items()), I(0))-rhs
        big_m = max(F(0), F(residual.hi))
        lifted = dict(row)
        _plus(lifted, gate, big_m)
        self.le(lifted, rhs+I.rational(big_m), tag)
        self.rows[-1]['big_M'] = str(big_m)

    def conditional_eq(self, row, rhs, gate, tag):
        self.conditional_le(row, rhs, gate, tag+'/upper')
        self.conditional_le({i: -_box(v) for i, v in row.items()}, -_box(rhs), gate, tag+'/lower')

    def as_solver_dict(self):
        ri, ci, data = [], [], []
        for i, row in enumerate(self.rows):
            for j, value in row['coef'].items():
                ri.append(i); ci.append(j); data.append(value)
        n = len(self.names)
        return {'c': np.array(self.c), 'A': coo_matrix((data, (ri, ci)), shape=(len(self.rows), n)).tocsr(),
                'b': np.array([r['rhs'] for r in self.rows]), 'Aeq': csr_matrix((0, n)), 'beq': np.empty(0),
                'lb': np.array(self.lb), 'ub': np.array(self.ub), 'intcon': np.array(self.integer, dtype=int)}

    def summary(self):
        return {'problem_id': self.instance['id'], 'variables': len(self.names),
                'binary_variables': len(self.integer), 'rows': len(self.rows),
                'options': len(self.options), 'coefficient_sets': self.coefficients.calls,
                'events_per_scene': {sid: len(s['events']) for sid, s in self.scenes.items()},
                'objective': 'weighted complete system energy including leakage and idle tail',
                'coefficient_errors': 'outward interval rows; not solver arithmetic certification',
                'optimality_level': 'solver-reported only; external SAFE supplies a feasible upper bound'}


def build_model(instance, config, starts=None, budget=None, include_physics=True):
    budget = budget if budget is not None else Budget()
    model = Model(instance, budget)
    p = model.instance['platform']
    nodes = p['node_order']; n = len(nodes)
    units = {u['id']: u for u in p['units']}
    domains = p['domains']
    if starts is not None and not instance['id'].startswith('fixture_'):
        raise ValueError('explicit reduced start sets are fixture-only; production domain must not be trimmed')
    options = expand_options(instance, config)
    if starts is not None:
        options = [o for o in options if F(o['start_ms']) in set(map(F, starts[o['scenario_id']][o['stage_instance_id']]))]
    model.options = options
    model.option_vars = [model.var('y:'+o['option_id'], integer=True) for o in options]
    for shared, modes in instance['stage_modes'].items():
        for unit in sorted({m['unit_id'] for m in modes}):
            model.shared[shared, unit] = model.var('x:'+shared+':'+unit, integer=True)
        model.eq({v: 1 for (stage, _), v in model.shared.items() if stage == shared}, 1, 'shared_unique')
    for scene in instance['scenarios']:
        budget.check()
        sid = scene['id']; scene_options = [(o, y) for o, y in zip(options, model.option_vars) if o['scenario_id'] == sid]
        stage_options = {s['id']: [(o, y) for o, y in scene_options if o['stage_instance_id'] == s['id']]
                         for s in scene['stage_instances']}
        for stage in scene['stage_instances']:
            choices = stage_options[stage['id']]
            model.eq({y: 1 for o, y in choices}, 1, 'stage_unique')
            for (shared, unit), x in model.shared.items():
                if shared == stage['shared_stage_id']:
                    model.eq({x: -1, **{y: 1 for o, y in choices if o['unit_id'] == unit}}, 0, 'shared_link')
            # Every Stage belongs to its request; all must finish by deadline.
            deadline = F(next(r['deadline_ms'] for r in scene['requests'] if r['id'] == stage['request_id']))/1000
            model.le({y: F(o['end_ms'])/1000 for o, y in choices}, deadline, 'request_deadline')
        for before, after in scene['dependencies']:
            row = {y: F(o['end_ms'])/1000 for o, y in stage_options[before]}
            for o, y in stage_options[after]:
                _plus(row, y, -F(o['start_ms'])/1000)
            model.le(row, 0, 'dependency')
        events = sorted({F(0), F(instance['window_ms'])/1000} |
                        {F(o[k])/1000 for o, _ in scene_options for k in ('start_ms', 'end_ms')})
        K = len(events)-1
        meta = {'events': events, 'rho': {}, 'joint': {}, 'theta': [], 'q': [], 'energy': [],
                'active': [], 'options': scene_options, 'stage_options': stage_options,
                'start_indicators': {}, 'states': []}
        model.scenes[sid] = meta
        for l, (left, right) in enumerate(zip(events, events[1:])):
            active = [(o, y) for o, y in scene_options if F(o['start_ms'])/1000 <= left < F(o['end_ms'])/1000]
            meta['active'].append(active)
            for unit in units:
                model.le({y: 1 for o, y in active if o['unit_id'] == unit}, 1, 'unit_mutex')
            possible = []
            for domain_id, domain in domains.items():
                for opp in domain['opps']:
                    meta['rho'][l, domain_id, opp] = model.var(f'rho:{sid}:{l}:{domain_id}:{opp}', integer=True)
                rhos = {meta['rho'][l, domain_id, opp]: 1 for opp in domain['opps']}
                model.eq(rhos, 1, 'domain_unique')
                starting = [y for o, y in scene_options if units[o['unit_id']]['domain_id'] == domain_id and F(o['start_ms'])/1000 == left]
                trigger = model.var(f'J:{sid}:{l}:{domain_id}', upper=int(bool(starting)), integer=True)
                meta['start_indicators'][l, domain_id] = trigger
                for y in starting:
                    model.le({y: 1, trigger: -1}, 0, 'start_or_lower')
                model.le({trigger: 1, **{y: -1 for y in starting}}, 0, 'start_or_upper')
                for opp in domain['opps']:
                    now = meta['rho'][l, domain_id, opp]
                    difference = {now: 1}
                    previous = int(scene['entry']['domain_opp'][domain_id] == opp) if l == 0 else 0
                    if l:
                        difference[meta['rho'][l-1, domain_id, opp]] = -1
                    model.le({**difference, trigger: -1}, previous, 'idle_hold_upper')
                    model.le({**{j: -a for j, a in difference.items()}, trigger: -1}, -previous, 'idle_hold_lower')
                for o, y in active:
                    if units[o['unit_id']]['domain_id'] == domain_id:
                        model.le({y: 1, meta['rho'][l, domain_id, o['opp_id']]: -1}, 0, 'active_locks_opp')
                # Necessary prefix reachability only: an OPP cannot be held
                # before any possible Stage using it has started.
                prefix_opps = {scene['entry']['domain_opp'][domain_id]} | {
                    o['opp_id'] for o, y in scene_options if units[o['unit_id']]['domain_id'] == domain_id and F(o['start_ms'])/1000 <= left}
                possible.append(sorted(prefix_opps))
            states = list(product(*possible))
            meta['states'].append(states)
            for state in states:
                meta['joint'][l, state] = model.var(f'w:{sid}:{l}:{state}', integer=True)
            model.eq({meta['joint'][l, state]: 1 for state in states}, 1, 'joint_unique')
            for di, (domain_id, domain) in enumerate(domains.items()):
                for opp in domain['opps']:
                    model.eq({meta['rho'][l, domain_id, opp]: -1,
                              **{meta['joint'][l, state]: 1 for state in states if state[di] == opp}}, 0, 'joint_marginal')
        if not include_physics:
            continue
        ambient = F(p['ambient_temperature_degC']); reference = F(p['reference_temperature_degC'])
        valid_low, valid_high = map(F, p['power_model_temperature_range_degC'])
        temp_upper = [min(valid_high, F(v)) for v in scene['maximum_temperature_degC']]
        for l in range(K+1):
            meta['theta'].append([model.var(f'theta:{sid}:{l}:{node}', valid_low-ambient, temp_upper[i]-ambient)
                                  for i, node in enumerate(nodes)])
        for i in range(n):
            model.eq({meta['theta'][0][i]: 1}, F(scene['entry']['temperature_degC'][i])-ambient, 'entry_temperature')
        for l, (left, right) in enumerate(zip(events, events[1:])):
            qmax = []
            meta['q'].append([])
            for node in nodes:
                active_node = [(o, y) for o, y in meta['active'][l] if units[o['unit_id']]['thermal_node_id'] == node]
                maximum = max([F(o['activity_power_W']) for o, _ in active_node]+[F(0)])
                qmax.append(maximum)
                qv = model.var(f'q:{sid}:{l}:{node}', 0, maximum)
                meta['q'][l].append(qv)
                model.eq({qv: 1, **{y: -F(o['activity_power_W']) for o, y in active_node}}, 0, 'activity_power')
            states = meta['states'][l]
            power_upper = max(sum(base)+sum(qmax)+sum(lam*(upper-reference) for lam, upper in zip(slopes, temp_upper))
                              +F(p['external_common_power_W']) for base, slopes in (model.coefficients.power(s) for s in states))
            ev = model.var(f'energy:{sid}:{l}', 0, power_upper*(right-left), cost=F(scene['weight']))
            meta['energy'].append(ev)
            sources = meta['theta'][l]+meta['q'][l]
            for state in states:
                gate = meta['joint'][l, state]
                coeff = model.coefficients.get(state, right-left)
                for i, row in enumerate(coeff['temperature']):
                    model.conditional_eq({meta['theta'][l+1][i]: 1, **{j: -a for j, a in zip(sources, row[:-1])}}, row[-1], gate, 'thermal_propagation')
                row = coeff['energy']
                model.conditional_eq({ev: 1, **{j: -a for j, a in zip(sources, row[:-1])}}, row[-1], gate, 'complete_energy')
    return model


def decode(model, values, integer_tolerance=1e-6):
    values = np.asarray(values, dtype=float).reshape(-1)
    if len(values) != len(model.names) or not np.all(np.isfinite(values)):
        raise ValueError('invalid solver vector')
    if any(abs(values[i]-round(values[i])) > integer_tolerance for i in model.integer):
        raise ValueError('nonintegral solver candidate')
    candidate = {'scenes': {s['id']: [] for s in model.instance['scenarios']}}
    for o, v in zip(model.options, model.option_vars):
        if round(values[v]) == 1:
            candidate['scenes'][o['scenario_id']].append({'stage_id': o['stage_instance_id'],
                'unit': o['unit_id'], 'opp': o['opp_id'], 'start_ms': o['start_ms']})
    result = validate_schedule(model.instance, candidate)
    if result['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('decoded candidate failed independent legality: '+result['reason'])
    return candidate


def selected_options(model, candidate, sid):
    wanted = {(r['stage_id'], r['unit'], r['opp'], F(r['start_ms'])) for r in candidate['scenes'][sid]}
    found = [(o, y) for o, y in model.scenes[sid]['options'] if
             (o['stage_instance_id'], o['unit_id'], o['opp_id'], F(o['start_ms'])) in wanted]
    if len(found) != len(wanted):
        raise ValueError('candidate outside declared option domain')
    return found


def lift_candidate(model, candidate, allow_invalid=False):
    """Independent floating lift for PRECHECKS, never a search warm start.

    scipy expm uses physical coordinates and a separately assembled energy
    state. It does not certify coefficients. For schedule-only projection
    tests allow_invalid creates a deterministic assignment whose violated
    rows can be compared with an independent Cartesian legality oracle.
    """
    from scipy.linalg import expm
    if not allow_invalid:
        checked = validate_schedule(model.instance, candidate)
        if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            raise ValueError('cannot physically lift illegal schedule')
    elif not model.instance['id'].startswith('fixture_'):
        raise ValueError('illegal lifting is a fixture-only check')
    x = np.zeros(len(model.names))
    p = model.instance['platform']; nodes = p['node_order']; n = len(nodes)
    units = {u['id']: u for u in p['units']}
    selected_by_scene = {sid: selected_options(model, candidate, sid) for sid in model.scenes}
    selected_shared = {}
    for choices in selected_by_scene.values():
        for o, y in choices:
            x[y] = 1
            selected_shared.setdefault(o['shared_stage_id'], o['unit_id'])
    for (shared, unit), index in model.shared.items():
        x[index] = int(selected_shared.get(shared) == unit)
    for scene in model.instance['scenarios']:
        sid = scene['id']; meta = model.scenes[sid]; choices = selected_by_scene[sid]
        held = dict(scene['entry']['domain_opp'])
        ambient, reference = float(F(p['ambient_temperature_degC'])), float(F(p['reference_temperature_degC']))
        theta = np.array([float(F(v)) for v in scene['entry']['temperature_degC']])-ambient
        if meta['theta']:
            x[meta['theta'][0]] = theta
        for l, (left, right) in enumerate(zip(meta['events'], meta['events'][1:])):
            active = [o for o, y in choices if F(o['start_ms'])/1000 <= left < F(o['end_ms'])/1000]
            for domain_id, domain in p['domains'].items():
                starting = [o for o, y in choices if units[o['unit_id']]['domain_id'] == domain_id and F(o['start_ms'])/1000 == left]
                if starting:
                    held[domain_id] = starting[0]['opp_id']
                x[meta['start_indicators'][l, domain_id]] = int(bool(starting))
                for opp in domain['opps']:
                    x[meta['rho'][l, domain_id, opp]] = int(held[domain_id] == opp)
            state = tuple(held[d] for d in p['domains'])
            for possible in meta['states'][l]:
                x[meta['joint'][l, possible]] = int(state == possible)
            if not meta['theta']:
                continue
            q = [sum(F(o['activity_power_W']) for o in active if units[o['unit_id']]['thermal_node_id'] == node) for node in nodes]
            x[meta['q'][l]] = list(map(float, q))
            # Independently reconstruct baseline and local slopes from input.
            base = np.zeros(n); slopes = np.zeros(n)
            for domain_id, domain in p['domains'].items():
                opp = held[domain_id]
                base += float(F(domain['baseline_W'][opp]))*np.array([float(F(v)) for v in domain['baseline_heat_distribution']])
                for uid in domain['unit_ids']:
                    slopes[nodes.index(units[uid]['thermal_node_id'])] += float(F(domain['local_temperature_slope_W_per_K'][opp]))
            c = np.array([float(F(v)) for v in p['heat_capacity_J_per_K']])
            g = np.array([[float(F(v)) for v in row] for row in p['conductance_W_per_K']])
            a = np.zeros((n+2, n+2))
            a[:n, :n] = (np.diag(slopes)-g)/c[:, None]
            a[:n, -1] = (base+np.array(list(map(float, q)))+slopes*(ambient-reference))/c
            a[n, :n] = slopes
            a[n, -1] = sum(base)+sum(map(float, q))+sum(slopes)*(ambient-reference)+float(F(p['external_common_power_W']))
            evolved = expm(a*float(right-left)) @ np.r_[theta, 0.0, 1.0]
            theta = evolved[:n]
            x[meta['theta'][l+1]] = theta
            x[meta['energy'][l]] = evolved[n]
    return x


def add_thermal_feedback(model, candidate, evaluation):
    """Use only certified point violations; no cuts for numerical unknowns.

    A new point yields a necessary state-conditional temperature row. If the
    same failed scene recurs, add its full-assignment no-good: an outer band
    can leave the old assignment feasible via relaxed internal temperatures.
    """
    if evaluation['state'] != 'THERMAL_VIOLATION' or not evaluation.get('violations'):
        return {'state': 'NO_VALID_EXCLUSION', 'rows_added': 0}
    checked = validate_schedule(model.instance, candidate)
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('feedback requires legal candidate')
    initial_rows = len(model.rows)
    actions = []
    for witness in evaluation['violations']:
        sid, node, when = witness['scene_id'], witness['node'], F(witness['time_s'])
        scene = next(s for s in model.instance['scenarios'] if s['id'] == sid)
        if F(witness['temperature_degC'][0]) <= F(witness['limit_degC']):
            raise ValueError('feedback has no strict point witness')
        selected = selected_options(model, candidate, sid)
        signature = (sid, tuple(sorted(y for _, y in selected)))
        meta = model.scenes[sid]
        l = min(len(meta['events'])-2, bisect_right(meta['events'], when)-1)
        if l < 0:
            raise ValueError('feedback time outside evaluation window')
        left, right = meta['events'][l:l+2]
        if not left <= when <= right:
            raise ValueError('feedback time outside evaluation window')
        # Find actual control at the MASTER interval entrance, not the
        # candidate's merged power-interval entrance.
        segment = next(seg for seg in checked['scenes'][sid]['segments']
                       if F(seg['start_ms'])/1000 <= left < F(seg['end_ms'])/1000)
        state = tuple(segment['domain_opps'][d] for d in model.coefficients.domains)
        identity = (sid, l, state, node, when)
        if identity not in model.feedback_identities:
            row = model.coefficients.get(state, when-left)['temperature'][model.coefficients.nodes.index(node)]
            rhs = I.rational(F(witness['limit_degC'])-F(model.instance['platform']['ambient_temperature_degC']))-row[-1]
            sources = meta['theta'][l]+meta['q'][l]
            model.conditional_le(dict(zip(sources, row[:-1])), rhs, meta['joint'][l, state], 'continuous_thermal_feedback')
            model.feedback_identities.add(identity)
            actions.append({'type': 'conditional_temperature', 'scene': sid, 'node': node,
                            'time_s': str(when), 'master_interval': l, 'state': list(state)})
        elif signature not in model.excluded_schedules:
            model.le({y: 1 for _, y in selected}, len(selected)-1, 'certified_scene_assignment_exclusion')
            model.excluded_schedules.add(signature)
            actions.append({'type': 'scene_assignment_exclusion', 'scene': sid,
                            'selected_option_ids': [o['option_id'] for o, _ in selected]})
    result = {'state': 'FEEDBACK_ADDED' if actions else 'NO_NEW_FEEDBACK',
              'rows_added': len(model.rows)-initial_rows, 'actions': actions}
    model.feedback_log.append(result)
    return result


def solve_with_feedback(model, session, accuracy, budget=None, max_rounds=50):
    budget = budget if budget is not None else model.budget
    result = {'state': 'UNRESOLVED', 'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'rounds': [], 'feedback': [], 'independently_proven_optimal': False,
              'independently_proven_infeasible': False, 'remaining_domain': 'retained', 'reason': None}
    try:
        for iteration in range(max_rounds):
            budget.check()
            returned = session.solve(model.as_solver_dict(), remaining_s=max(0, budget.seconds-budget.elapsed))
            result['rounds'].append(returned)
            budget.check()
            if not returned.get('budget_valid', False):
                result['reason'] = 'SOLVER_RETURN_AFTER_BUDGET'; break
            if not returned.get('x'):
                result['reason'] = 'SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag') == -2 else 'NO_INTEGER_CANDIDATE'
                break
            try:
                candidate = decode(model, returned['x'])
            except ValueError as error:
                result['reason'] = 'NUMERICAL_CANDIDATE_ANOMALY: '+str(error); break
            evaluation = evaluate_candidate(model.instance, candidate, accuracy, budget)
            # Preserve evaluator evidence even if the deadline just elapsed.
            result['evaluation'] = evaluation
            if evaluation['state'] == 'SAFE' and evaluation.get('rankable_energy'):
                budget.check()
                result.update(state='SAFE', safe_candidate=candidate,
                              safe_upper_bound_J=evaluation['safe_upper_bound_J'],
                              reason='SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag') == 1 else 'SAFE_INCUMBENT')
                break
            if evaluation['state'] != 'THERMAL_VIOLATION':
                result['reason'] = 'EVALUATION_UNRESOLVED'; break
            budget.check()
            feedback = add_thermal_feedback(model, candidate, evaluation)
            result['feedback'].append(feedback)
            if not feedback['rows_added']:
                result['reason'] = 'FEEDBACK_UNRESOLVED'; break
        else:
            result['reason'] = 'OUTER_ROUND_LIMIT'
    except Exhausted as error:
        result['reason'] = str(error)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    result['elapsed_s'] = budget.elapsed
    return result
