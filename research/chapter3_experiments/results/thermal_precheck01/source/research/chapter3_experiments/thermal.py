"""Continuous, outward-bounded thermal/energy evaluation of one full candidate.

No optimizer, candidate repair or historical answer is used. Decimal interval
arithmetic and the Taylor remainder come from the existing V1 numerical kernel;
the four-node accounting, aggregation and evidence lifecycle here are new.
Time is converted exactly from ms to s. Numerical panels do NOT restrict starts
or check temperature only at discrete samples.
"""
from decimal import Decimal
from fractions import Fraction as F
import importlib.util
import math
from pathlib import Path
import time

from schedules import validate_schedule

KERNEL_PATH = Path(__file__).resolve().parents[1] / 'v1_evaluator' / 'interval.py'
_spec = importlib.util.spec_from_file_location('_chapter3_interval_kernel', KERNEL_PATH)
_kernel = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kernel)
I, UP, DOWN = _kernel.I, _kernel.UP, _kernel.DOWN
Exhausted = _kernel.Exhausted
SCALE = 100  # Coordinate scaling only, not a physical parameter.
DEFAULT_ACCURACY = {'temperature_enclosure_width_K': '0.001',
                    'energy_absolute_error_J': '0.000001',
                    'energy_relative_error': '0.000001'}


class Budget(_kernel.Budget):
    """One wall clock across legality, all scenes, extrema and aggregation.

    Hooks are solely for deterministic interruption tests. A completed witness
    is committed before after_violation_commit; later expiry cannot erase it.
    """
    def __init__(self, seconds=60, panels=100000, refinements=20000, hook=None):
        super().__init__(seconds, panels, refinements)
        self.hook = hook

    def mark(self, event):
        if self.hook:
            self.hook(event, self)
        self.check()

    @property
    def elapsed(self):
        return time.monotonic() - self.start


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, F)):
        raise ValueError('physical scalars must be exact strings/integers/rationals')
    return F(value)


def _iv(value):
    return I.rational(_q(value))


def _accuracy(value):
    out = dict(DEFAULT_ACCURACY)
    if value is not None:
        out.update(value)
    for key in DEFAULT_ACCURACY:
        if _q(out[key]) <= 0:
            raise ValueError('accuracy targets must be positive')
    return out


class Panel(_kernel.TaylorPanel):
    def value(self, left, right=None):
        # At time zero the supplied interval state is exact as a box; avoid
        # adding the whole-panel Taylor remainder to this known boundary.
        if left == 0 and (right is None or right == 0):
            return self.coeffs[0]
        out = super().value(left, right)
        out[-1] = I(1)  # Constant coordinate is invariant analytically.
        return out

    def extremum(self, node, tolerance, budget, sign=1, on_point=None):
        """Enclose max(sign*x_node), with a genuine point as lower witness.

        For sign=-1 this is a minimum-temperature computation; the dynamics
        are not changed. Every derivative/image is multiplied by the sign.
        """
        def cell(left, right):
            a, b = self.value(left), self.value(right)
            image = self.value(left, right)
            derivative = _kernel.dot(self.matrix[node], image) * sign
            av, bv, whole = a[node] * sign, b[node] * sign, image[node] * sign
            upper = bv.hi if derivative.lo >= 0 else av.hi if derivative.hi <= 0 else whole.hi
            if on_point:
                on_point(left, a[node])
                on_point(right, b[node])
            return ((left, right, upper), av.lo, left) if av.lo >= bv.lo else ((left, right, upper), bv.lo, right)

        first, lower, at = cell(F(0), self.h)
        cells = [first]
        while True:
            budget.check()
            index = max(range(len(cells)), key=lambda j: cells[j][2])
            upper = max(lower, cells[index][2])
            if UP.subtract(upper, lower) <= tolerance:
                return I(lower, upper), at
            budget.refine()
            left, right, _ = cells[index]
            middle = (left + right) / 2
            a, av, atime = cell(left, middle)
            b, bv, btime = cell(middle, right)
            for v, t in ((av, atime), (bv, btime)):
                if v > lower:
                    lower, at = v, t
            cells[index:index+1] = [a, b]
            cells = [c for c in cells if c[2] >= lower] or [(left, right, lower)]


def _physical_input(platform, entry, limits, segments, window_ms):
    nodes = platform['node_order']
    n = len(nodes)
    if not n or len(set(nodes)) != n or len(entry) != n or len(limits) != n:
        raise ValueError('node/temperature dimensions')
    c = list(map(_q, platform['heat_capacity_J_per_K']))
    g = [list(map(_q, row)) for row in platform['conductance_W_per_K']]
    if len(c) != n or len(g) != n or any(len(row) != n for row in g):
        raise ValueError('thermal matrix dimensions')
    if any(v <= 0 for v in c):
        raise ValueError('nonpositive heat capacity')
    for i in range(n):
        if g[i][i] <= 0 or sum(g[i]) <= 0:
            raise ValueError('non-passive grounded conductance')
        for j in range(n):
            if g[i][j] != g[j][i] or (i != j and g[i][j] > 0):
                raise ValueError('non-passive conductance coupling')
    ambient, reference = _q(platform['ambient_temperature_degC']), _q(platform['reference_temperature_degC'])
    valid = list(map(_q, platform['power_model_temperature_range_degC']))
    if len(valid) != 2 or valid[0] >= valid[1]:
        raise ValueError('invalid power model range')
    initial, maximum = list(map(_q, entry)), list(map(_q, limits))
    if any(v < valid[0] or v > valid[1] for v in initial):
        raise ValueError('entry outside power model range')
    window = _q(window_ms)
    if window <= 0 or not segments:
        raise ValueError('empty evaluation window')
    cursor = F(0)
    prepared = []
    for segment in segments:
        start, end, duration = map(_q, (segment['start_ms'], segment['end_ms'], segment['duration_ms']))
        if start != cursor or end <= start or duration != end-start:
            raise ValueError('incomplete/overlapping power segments')
        cursor = end
        vectors = []
        for field in ('baseline_by_node_W', 'activity_by_node_W',
                      'local_leakage_slope_W_per_K', 'node_power_constant_at_reference_W'):
            if set(segment[field]) != set(nodes):
                raise ValueError('power-node identities')
            vectors.append([_q(segment[field][node]) for node in nodes])
        base, activity, slopes, constant = vectors
        if any(v < 0 for row in (base, activity, slopes) for v in row):
            raise ValueError('negative baseline/activity/leakage slope')
        if any(constant[i] != base[i]+activity[i] for i in range(n)):
            raise ValueError('power constant accounting')
        if sum(map(_q, segment['baseline_by_power_group_W'].values())) != sum(base):
            raise ValueError('baseline must be counted once')
        if any(constant[i]+slopes[i]*(valid[0]-reference) < 0 for i in range(n)):
            raise ValueError('negative node power within declared range')
        external = _q(segment['external_common_power_W'])
        if external < 0 or external != _q(platform['external_common_power_W']):
            raise ValueError('external power mismatch')
        if _q(segment['external_common_injected_heat_W']) != 0:
            raise ValueError('external power may not heat local nodes')
        if _q(segment['reference_temperature_degC']) != reference:
            raise ValueError('reference temperature mismatch')
        # x=theta/100, z'=x, plus an exact constant coordinate.
        matrix = [[I(0) for _ in range(2*n+1)] for _ in range(2*n+1)]
        for i in range(n):
            for j in range(n):
                matrix[i][j] = I.rational(((slopes[i] if i == j else 0)-g[i][j])/c[i])
            matrix[i][-1] = I.rational((constant[i]+slopes[i]*(ambient-reference))/(c[i]*SCALE))
            matrix[n+i][i] = I(1)
        prepared.append((segment, matrix, base, activity, slopes, external))
    if cursor != window:
        raise ValueError('power segments do not cover full window including idle tail')
    return nodes, c, g, ambient, reference, valid, initial, maximum, prepared


def _empty_scene(scene_id):
    return {'scene_id': scene_id, 'state': 'UNRESOLVED', 'reason': None,
            'complete': False, 'rankable_energy': False, 'energy_J': None,
            'energy_components_J': {}, 'peaks_degC': {}, 'minimum_degC': {},
            'peak_witnesses': {}, 'final_temperature_degC': {}, 'violations': [],
            'covered_until_s': '0', 'trace': []}


def _energy_accuracy(energy, accuracy):
    # A conservative abs/relative stopping target, NOT a physical tolerance.
    # Using the nonnegative lower endpoint avoids understating relative error.
    allowed = max(_iv(accuracy['energy_absolute_error_J']).lo,
                  (_iv(accuracy['energy_relative_error'])*I(max(Decimal(0), energy.lo))).lo)
    return energy.width <= allowed


def evaluate_piecewise(platform, entry_temperatures, limits, segments, window_ms,
                       accuracy=None, budget=None, scene_id='fixture'):
    """Evaluate a fully declared power history; no scheduling/search here.

    This lower-level interface is useful for analytic tests. Production callers
    must use evaluate_candidate so schedule legality is independently checked.
    A violation is a point witness within the model's certified validity range.
    Energy of an unsafe complete scene is diagnostic only, never rankable.
    """
    budget = budget if budget is not None else Budget()
    out = _empty_scene(scene_id)
    try:
        budget.check()
        accuracy = _accuracy(accuracy)
        data = _physical_input(platform, entry_temperatures, limits, segments, window_ms)
        nodes, capacity, conductance, ambient, reference, valid, initial, maximum, prepared = data
        n = len(nodes)
        theta = [I.rational((t-ambient)/SCALE) for t in initial]
        peaks = [I.rational(t) for t in initial]
        minima = [I.rational(t) for t in initial]
        witnesses = [{'time_s': '0', 'temperature_degC': p.data()} for p in peaks]
        energy_parts = {k: I(0) for k in ('baseline', 'activity', 'external_common', 'temperature_correction')}
        node_energy = [I(0) for _ in nodes]
        theta_integrals = [I(0) for _ in nodes]
        tolerance = (_iv(accuracy['temperature_enclosure_width_K'])/SCALE).lo
        seen_violation = set()

        def record_point(index, when, scaled_value):
            value = scaled_value*SCALE + I.rational(ambient)
            if value.lo > I.rational(maximum[index]).hi and index not in seen_violation:
                budget.check()  # Evidence must already be complete within budget.
                out['violations'].append({'scene_id': scene_id, 'node': nodes[index],
                    'time_s': str(when), 'temperature_degC': value.data(),
                    'limit_degC': str(maximum[index]), 'formed_at_elapsed_s': budget.elapsed})
                seen_violation.add(index)
                budget.mark('after_violation_commit')

        # Entry lies in the declared model range, so its violation is usable
        # even if no propagation panel can complete.
        for i in range(n):
            record_point(i, F(0), theta[i])
        for segment_index, (segment, matrix, base, activity, slopes, external) in enumerate(prepared):
            duration = _q(segment['duration_ms'])/1000
            count = max(1, math.ceil(4*F(_kernel.norm(matrix))*duration))
            h = duration/count
            start = _q(segment['start_ms'])/1000
            for panel_index in range(count):
                budget.mark('before_panel')
                budget.panel()
                when = start + panel_index*h
                state = theta + [I(0) for _ in nodes] + [I(1)]
                panel = Panel(matrix, state, h, order=18)
                image = panel.value(F(0), h)
                broad = [v*SCALE+I.rational(ambient) for v in image[:n]]
                range_known = all(v.lo >= I.rational(valid[0]).hi and v.hi <= I.rational(valid[1]).lo for v in broad)
                local_peaks, local_minima, local_witnesses = [], [], []
                # If the cheap whole-panel enclosure is too wide, refined
                # extrema can certify the power model range. No physical
                # violation witness is accepted before this range is known.
                for i in range(n):
                    callback = (lambda t, v, i=i: record_point(i, when+t, v)) if range_known else None
                    peak, at = panel.extremum(i, tolerance, budget, on_point=callback)
                    minus_min, _ = panel.extremum(i, tolerance, budget, sign=-1)
                    local_peaks.append(peak*SCALE+I.rational(ambient))
                    local_minima.append(-minus_min*SCALE+I.rational(ambient))
                    value = panel.value(at)[i]*SCALE+I.rational(ambient)
                    local_witnesses.append({'time_s': str(when+at), 'temperature_degC': value.data()})
                if not range_known:
                    range_known = all(local_minima[i].lo >= I.rational(valid[0]).hi and
                                      local_peaks[i].hi <= I.rational(valid[1]).lo for i in range(n))
                    if not range_known:
                        out['reason'] = 'POWER_MODEL_RANGE_UNRESOLVED'
                        raise Exhausted(out['reason'])
                    for i, witness in enumerate(local_witnesses):
                        t = F(witness['time_s'])-when
                        record_point(i, when+t, panel.value(t)[i])
                end = panel.value(h)
                correction = [I.rational(slopes[i])*(end[n+i]*SCALE + I.rational((ambient-reference)*h)) for i in range(n)]
                additions = {'baseline': I.rational(sum(base)*h), 'activity': I.rational(sum(activity)*h),
                             'external_common': I.rational(external*h),
                             'temperature_correction': sum(correction, I(0))}
                budget.check()
                # Panel commit: preserve only complete covered intervals.
                theta = end[:n]
                for i in range(n):
                    theta_integrals[i] += end[n+i]*SCALE
                    node_energy[i] += I.rational((base[i]+activity[i])*h)+correction[i]
                    if local_peaks[i].lo > peaks[i].lo:
                        witnesses[i] = local_witnesses[i]
                    peaks[i] = I(max(peaks[i].lo, local_peaks[i].lo), max(peaks[i].hi, local_peaks[i].hi))
                    minima[i] = I(min(minima[i].lo, local_minima[i].lo), min(minima[i].hi, local_minima[i].hi))
                for key, value in additions.items():
                    energy_parts[key] += value
                out['covered_until_s'] = str(when+h)
                out['peaks_degC'] = dict(zip(nodes, (v.data() for v in peaks)))
                out['minimum_degC'] = dict(zip(nodes, (v.data() for v in minima)))
                out['peak_witnesses'] = dict(zip(nodes, witnesses))
                out['trace'].append({'time_s': str(when+h), 'segment': segment_index,
                    'temperature_degC': {node: (theta[i]*SCALE+I.rational(ambient)).data() for i, node in enumerate(nodes)}})
                budget.mark('after_panel_commit')
        energy = sum(energy_parts.values(), I(0))
        # Independent accounting identity: sum(C*dtheta + G*integral(theta))
        # equals heat injected. The external common power is added only here.
        heat_balance = sum((I.rational(capacity[i])*(theta[i]*SCALE-I.rational(initial[i]-ambient)) +
                            sum((I.rational(conductance[i][j])*theta_integrals[j] for j in range(n)), I(0))
                            for i in range(n)), I(0)) + energy_parts['external_common']
        if max(energy.lo, heat_balance.lo) > min(energy.hi, heat_balance.hi):
            raise ValueError('internal energy conservation enclosure mismatch')
        accurate = _energy_accuracy(energy, accuracy)
        safe = all(peaks[i].hi <= I.rational(maximum[i]).lo for i in range(n))
        state = 'THERMAL_VIOLATION' if out['violations'] else 'SAFE' if safe and accurate else 'UNRESOLVED'
        reason = 'POINT_WITNESS' if out['violations'] else 'COMPLETE_CONTINUOUS_ENCLOSURE' if state == 'SAFE' else 'ENERGY_ERROR_TARGET' if not accurate else 'TEMPERATURE_LIMIT_UNRESOLVED'
        budget.mark('before_scene_commit')
        out.update(state=state, reason=reason, complete=True, rankable_energy=state == 'SAFE',
                   energy_J=energy.data(), energy_components_J={k: v.data() for k, v in energy_parts.items()},
                   final_temperature_degC={node: (theta[i]*SCALE+I.rational(ambient)).data() for i, node in enumerate(nodes)},
                   node_injected_energy_J=dict(zip(nodes, (v.data() for v in node_energy))),
                   temperature_rise_integrals_Ks=dict(zip(nodes, (v.data() for v in theta_integrals))),
                   conservation_energy_J=heat_balance.data(), energy_accuracy_met=accurate,
                   completed_at_elapsed_s=budget.elapsed)
    except Exhausted as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason=str(error), budget_exhausted=str(error) in ('wall_time_limit', 'panel_limit', 'peak_refinement_limit'))
    except (KeyError, TypeError, ValueError, ZeroDivisionError, ArithmeticError) as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'INVALID_INPUT',
                   reason=str(error), error_type=type(error).__name__)
    out['elapsed_s'] = budget.elapsed
    return out


def evaluate_candidate(instance, candidate, accuracy=None, budget=None):
    """Only all-scene legal+complete+safe results receive a weighted energy.

    Exact weights must be nonnegative and sum to one. Zero-weight scenes still
    must pass all checks. Interrupted/unsafe scenes never yield a usable prefix
    objective. Previously formed violation evidence survives outer interruption.
    """
    budget = budget if budget is not None else Budget()
    out = {'state': 'UNRESOLVED', 'reason': None, 'problem_id': instance.get('id'),
           'scenes': {}, 'violations': [], 'weighted_energy_J': None,
           'safe_upper_bound_J': None, 'rankable_energy': False,
           'numerical_protocol': 'directed-decimal60-taylor18-scaled100-v1',
           'formal_experiment_result': False}
    try:
        budget.check()
        accuracy = _accuracy(accuracy)
        weights = [_q(s['weight']) for s in instance['scenarios']]
        if any(w < 0 for w in weights) or sum(weights) != 1:
            raise ValueError('scenario weights must be nonnegative and sum to one')
        checked = validate_schedule(instance, candidate)
        budget.check()
        if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
            out.update(state='INVALID_SCHEDULE', reason=checked['reason'], legality=checked)
        else:
            out['legality'] = checked
            for scene in instance['scenarios']:
                result = evaluate_piecewise(instance['platform'], scene['entry']['temperature_degC'],
                    scene['maximum_temperature_degC'], checked['scenes'][scene['id']]['segments'],
                    instance['window_ms'], accuracy, budget, scene_id=scene['id'])
                # Transfer existing evidence BEFORE checking outer time. This
                # is not the acceptance of a new post-budget result.
                out['scenes'][scene['id']] = result
                out['violations'].extend(result['violations'])
                budget.check()
                if not result['complete']:
                    break
            if out['violations']:
                out.update(state='THERMAL_VIOLATION', reason='POINT_WITNESS')
            elif len(out['scenes']) != len(instance['scenarios']) or any(r['state'] != 'SAFE' for r in out['scenes'].values()):
                out.update(state='UNRESOLVED', reason='NOT_ALL_SCENES_COMPLETE_AND_SAFE')
            else:
                total = sum((I(*out['scenes'][s['id']]['energy_J'])*I.rational(w)
                             for s, w in zip(instance['scenarios'], weights)), I(0))
                if not _energy_accuracy(total, accuracy):
                    out['reason'] = 'WEIGHTED_ENERGY_ERROR_TARGET'
                else:
                    budget.mark('before_aggregate_commit')
                    out.update(state='SAFE', reason='ALL_SCENES_COMPLETE_AND_SAFE',
                        weighted_energy_J=total.data(), safe_upper_bound_J=str(total.hi),
                        rankable_energy=True, completed_at_elapsed_s=budget.elapsed)
    except Exhausted as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'UNRESOLVED',
                   reason=str(error), budget_exhausted=True)
    except (KeyError, TypeError, ValueError, ZeroDivisionError, ArithmeticError) as error:
        out.update(state='THERMAL_VIOLATION' if out['violations'] else 'INVALID_INPUT',
                   reason=str(error), error_type=type(error).__name__)
    out.update(elapsed_s=budget.elapsed, panels=budget.panels, refinements=budget.refinements)
    return out
