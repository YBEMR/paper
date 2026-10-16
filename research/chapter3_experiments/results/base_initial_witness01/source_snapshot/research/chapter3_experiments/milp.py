"""Finite-option, full thermal-energy MILP and validated continuous feedback.

All exported rows are <= inequalities. Coefficient and double conversion
errors enlarge rows outwards. intlinprog bounds/status remain solver-reported;
only the common evaluator supplies a safe schedule and system-energy upper
bound. Small explicit start sets are permitted solely for named fixtures.
"""
from bisect import bisect_right
from contextlib import nullcontext, contextmanager
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import math
import hashlib
import json
import time
from sys import intern

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix

from inputs import expand_options
from schedules import validate_schedule
from thermal import I, Budget, Exhausted, _q, evaluate_candidate
from milp_coefficients import Coefficients


_BINARY_BOUNDS = (F(0), F(1))
_EXPORT_CACHE_LIMIT = 4096  # memory policy only; eviction changes no coefficient
_CONDITIONAL_CACHE_LIMIT = 4096  # complete row templates; local to one model
_AFFINE_CACHE_LIMIT = 2048  # pairs of complete rows, not a restriction on modes


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


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
    def __init__(self, instance, budget, progress=None):
        self.instance = deepcopy(instance)
        self.input_sha256 = _digest(self.instance)
        self.budget = budget
        self.names, self.lb, self.ub, self.integer, self.c = [], [], [], [], []
        self.logical_binary = []
        self.deadline_fixed_options = []
        self.energy_bound_certificates = []
        self.formulation = {}
        self.bounds, self.rows, self.scenes, self.shared = [], [], {}, {}
        self.options, self.option_vars, self.feedback_log = [], [], []
        self.coefficients = Coefficients(self.instance['platform'], budget)
        self.excluded_schedules = set()
        self.feedback_identities = set()
        self.progress = progress
        self.construction_costs = {}
        self.construction_detail_costs = {}
        self.row_nonzeros = 0
        self._bound_boxes = {}
        self._bound_magnitudes = {}
        self._coefficient_exports = {}
        self._conditional_templates = {}
        self.template_stats = {'hits': 0, 'misses': 0, 'clears': 0}
        self._fraction_exports = {}
        self._fraction_negatives = {}
        self._bound_signatures = {}
        self._affine_templates = {}
        self.affine_stats = {'hits': 0, 'misses': 0, 'clears': 0}
        self._row_rhs_exports = {}
        self._activity_exports = {}

    def row_rhs(self, rhs, allowance=0):
        # Cache only immutable metadata. Text preserves signed zero/exponents;
        # callers still own separate mutable rhs_interval lists and row dicts.
        if type(rhs) is int:
            key = (rhs, allowance)
        else:
            rhs = _box(rhs)
            key = (str(rhs.lo), str(rhs.hi), allowance)
        result = self._row_rhs_exports.get(key)
        if result is None:
            rhs = _box(rhs)
            result = (_up(F(rhs.hi)+allowance), str(allowance), tuple(rhs.data()))
            if len(self._row_rhs_exports) >= _EXPORT_CACHE_LIMIT:
                self._row_rhs_exports.clear()
            self._row_rhs_exports[key] = result
        return result

    def append_exported(self, exported, rhs, allowance, tag):
        self.budget.check()
        if len(self.rows) % 128 == 0:
            self.report()
        bound, error, interval = self.row_rhs(rhs, allowance)
        self.rows.append({'coef': exported, 'rhs': bound, 'tag': intern(tag),
                          'rounding_allowance': error, 'rhs_interval': list(interval)})
        self.row_nonzeros += len(exported)

    def activity_export(self, index, power):
        """Both original signed coefficient conversions, including box error.

        A returned tuple is valid only for this power and box; identical
        powers on different boxes do not alias. Deadline fixing is applied
        after all original physical rows have been exported.
        """
        self.budget.check()
        power = F(power)
        key = (power, self.bound_signature(index))
        result = self._activity_exports.get(key)
        if result is None:
            negative = -power
            upper, du = self.fraction_export(negative)
            lower, dl = self.coefficient_export(self.fraction_negative(negative))
            magnitude = self.bound_magnitude(index)
            result = (upper, lower, du*magnitude, dl*magnitude)
            if len(self._activity_exports) >= _EXPORT_CACHE_LIMIT:
                self._activity_exports.clear()
            self._activity_exports[key] = result
        return result

    def activity_power_eq(self, target, indices, exports, tag='activity_power'):
        # The target has exact coefficient +/-1. Retain every option column,
        # even when several powers coincide; this is no constraint aggregation.
        upper, lower = {target: 1.0}, {target: -1.0}
        errors_upper, errors_lower = {}, {}
        for position, index in enumerate(indices):
            if position % 128 == 0:
                self.budget.check()
            if index == target:
                raise ValueError('activity target must differ from option variables')
            u, lo, eu, el = exports[index]
            if u: upper[index] = u
            if lo: lower[index] = lo
            for error, groups in ((eu, errors_upper), (el, errors_lower)):
                if error:
                    key = id(error)
                    if key in groups: groups[key][1] += 1
                    else: groups[key] = [error, 1]
        au = sum((error*count for error, count in errors_upper.values()), F(0))
        al = sum((error*count for error, count in errors_lower.values()), F(0))
        self.append_exported(upper, 0, au, tag+'/upper')
        self.append_exported(lower, I('-0'), al, tag+'/lower')

    def bound_signature(self, index):
        # Avoid repeatedly hashing Fraction denominators. Explicit tightening
        # invalidates this cache; the tuple encodes the current rational box.
        if index not in self._bound_signatures:
            lo, hi = self.bounds[index]
            self._bound_signatures[index] = (lo.numerator, lo.denominator, hi.numerator, hi.denominator)
        return self._bound_signatures[index]

    def fraction_export(self, value):
        if value not in self._fraction_exports:
            result = self.coefficient_export(_box(value))
            if len(self._fraction_exports) >= _EXPORT_CACHE_LIMIT:
                self._fraction_exports.clear()
            self._fraction_exports[value] = result
        return self._fraction_exports[value]

    def fraction_negative(self, value):
        if value not in self._fraction_negatives:
            result = -_box(value)
            if len(self._fraction_negatives) >= _EXPORT_CACHE_LIMIT:
                self._fraction_negatives.clear()
            self._fraction_negatives[value] = result
        return self._fraction_negatives[value]

    def bound_box(self, index):
        """Cache the same outward endpoints, local to this model only."""
        if index not in self._bound_boxes:
            low, high = self.bounds[index]
            self._bound_boxes[index] = (I.rational(low) if low == high else
                                     I(I.rational(low).lo, I.rational(high).hi))
        return self._bound_boxes[index]

    def bound_magnitude(self, index):
        if index not in self._bound_magnitudes:
            self._bound_magnitudes[index] = max(abs(v) for v in self.bounds[index])
        return self._bound_magnitudes[index]

    def coefficient_export(self, value):
        key = (value.lo, value.hi)
        if key not in self._coefficient_exports:
            low, high = F(value.lo), F(value.hi)
            nominal = float((low+high)/2)
            exact = F.from_float(nominal)
            result = (nominal, max(abs(low-exact), abs(high-exact)))
            if len(self._coefficient_exports) >= _EXPORT_CACHE_LIMIT:
                self._coefficient_exports.clear()
            self._coefficient_exports[key] = result
        return self._coefficient_exports[key]

    @contextmanager
    def measure_construction(self, section, detail=False):
        """Diagnostic stopwatches only; never create or extend a budget.

        Top-level regions are disjoint. Details are stored separately and can
        nest; never add them to parent totals. Nested observation is subtracted
        for exclusive costs; all costs remain charged to the method deadline.
        """
        start = time.perf_counter()
        observed = getattr(self.progress, 'observation_wall_seconds', 0.0)
        try:
            yield
        finally:
            elapsed = time.perf_counter()-start
            nested = getattr(self.progress, 'observation_wall_seconds', 0.0)-observed
            costs = self.construction_detail_costs if detail else self.construction_costs
            item = costs.setdefault(section,
                {'calls': 0, 'inclusive_s': 0.0, 'nested_observation_s': 0.0, 'exclusive_s': 0.0})
            item['calls'] += 1
            item['inclusive_s'] += elapsed
            item['nested_observation_s'] += nested
            item['exclusive_s'] += max(0.0, elapsed-nested)

    def report(self, stage=None, **detail):
        """Optional observation only; never modifies the encoded domain."""
        self.budget.check()
        if self.progress is not None:
            self.progress(stage, self, detail)

    def var(self, name, lower=0, upper=1, integer=False, cost=0, implied_binary=False):
        if len(self.names) % 128 == 0:
            self.report()
        # The common binary box is exactly representable. Reuse only its
        # immutable rational endpoints; all other bounds keep outward rounding.
        if ((integer or implied_binary) and type(lower) is int and lower == 0
                and type(upper) is int and upper == 1 and type(cost) is int and cost == 0):
            index = len(self.names)
            self.names.append(name)
            self.lb.append(-0.0)
            self.ub.append(1.0)
            self.bounds.append(_BINARY_BOUNDS)
            self.c.append(0.0)
            if integer:
                self.integer.append(index)
            self.logical_binary.append(index)
            return index
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
        if integer or implied_binary:
            self.logical_binary.append(index)
        return index

    def fix_zero_option(self, index):
        """Tighten a proven-late option after building the original rows.

        Existing outward rows remain valid on this smaller box. Invalidate
        per-variable bound caches so subsequent feedback uses current bounds.
        No event, power maximum, physical coefficient, or existing row changes.
        """
        self.budget.check()
        if self.bounds[index] != _BINARY_BOUNDS or not self.names[index].startswith('y:'):
            raise ValueError('deadline fixing requires an original binary option')
        self.ub[index] = 0.0
        self.bounds[index] = (F(0), F(0))
        for cache in (self._bound_boxes, self._bound_magnitudes, self._bound_signatures):
            cache.pop(index, None)
        self.deadline_fixed_options.append(index)

    def le(self, row, rhs, tag):
        """Necessary outer row for interval coefficients on a finite box.

        If exact a*z<=b and a,b lie in supplied intervals, then nominal(a)*z
        <= upper(b)+sum(delta_a*maxabs(z)). Final rhs rounds upwards.
        """
        self.budget.check()
        if len(self.rows) % 128 == 0:
            self.report()
        exported = {}
        error_groups = {}
        for index, value in row.items():
            # Every integer in this range has an exact binary64 representation,
            # so its conversion deviation is zero, irrespective of the box.
            if type(value) is int and abs(value) <= 2**53:
                if value:
                    exported[index] = 1.0 if value == 1 else -1.0 if value == -1 else float(value)
                continue
            if isinstance(value, F):
                nominal, deviation = self.fraction_export(value)
            else:
                value = _box(value)
                if value.lo == value.hi == 0:
                    continue
                if value.lo == value.hi and (value.lo == 1 or value.lo == -1):
                    exported[index] = float(value.lo)
                    continue
                nominal, deviation = self.coefficient_export(value)
            if deviation:
                magnitude = self.bound_magnitude(index)
                # Group repeated exact error products, not coefficients/rows.
                # Holding deviation in the value prevents id reuse even if a
                # conversion cache clears mid-row. Equal values in different
                # objects may remain separate; that changes only work done.
                key = (id(deviation), magnitude.numerator, magnitude.denominator)
                if key in error_groups:
                    error_groups[key][2] += 1
                else:
                    error_groups[key] = [deviation, magnitude, 1]
            if nominal:
                exported[index] = nominal
        allowance = sum((error*magnitude*count for error, magnitude, count in error_groups.values()), F(0)) if error_groups else 0
        bound, error, interval = self.row_rhs(rhs, allowance)
        self.rows.append({'coef': exported, 'rhs': bound, 'tag': intern(tag),
                          'rounding_allowance': error, 'rhs_interval': list(interval)})
        self.row_nonzeros += len(exported)

    def eq(self, row, rhs, tag):
        self.le(row, rhs, tag+'/upper')
        self.le({i: -v if type(v) is int and abs(v) <= 2**53 else
                 self.fraction_negative(v) if isinstance(v, F) else -_box(v)
                 for i, v in row.items()}, -_box(rhs), tag+'/lower')

    def conditional_le(self, row, rhs, gate, tag):
        self.budget.check()
        with self.measure_construction('template_key_and_lookup', detail=True):
            slots, key = self.conditional_key(row, rhs, gate)
            template = self._conditional_templates.get(key)
        if template is not None:
            with self.measure_construction('template_hit_assembly', detail=True):
                self.append_template(template, slots, tag)
            self.template_stats['hits'] += 1
            return
        self.template_stats['misses'] += 1
        with self.measure_construction('template_miss_construction', detail=True):
            self.construct_conditional_template(row, rhs, gate, tag, slots, key)

    def conditional_key(self, row, rhs, gate):
        # Canonical slots preserve insertion order (including zero entries).
        # Keep textual Decimal endpoints: signed zero and exponent spelling
        # can affect the archived interval certificate even when values agree.
        # Bounds are part of the key: no reuse across different thermal/power
        # boxes. Gate position also covers a gate already present in the row.
        indices = tuple(row)
        slots = indices if gate in row else indices+(gate,)
        def token(value):
            if type(value) is int:
                return ('int', value)
            value = _box(value)
            return ('interval', str(value.lo), str(value.hi))
        rhs = _box(rhs)
        key = (tuple((token(value), self.bound_signature(index)) for index, value in row.items()),
               token(rhs), slots.index(gate), self.bound_signature(gate))
        return slots, key

    def append_template(self, template, slots, tag):
        # Same budget/report checkpoints as le(); all copies are charged.
        self.budget.check()
        if len(self.rows) % 128 == 0:
            self.report()
        coefficients, metadata = template
        exported = {slots[position]: value for position, value in coefficients}
        record = dict(metadata, coef=exported, tag=intern(tag),
                      rhs_interval=list(metadata['rhs_interval']))
        self.rows.append(record)
        self.row_nonzeros += len(exported)

    def construct_conditional_template(self, row, rhs, gate, tag, slots, key):
        # This M covers the full residual on the exported variable box, not a
        # guessed scheduling horizon. Interval products include every sign.
        rhs = _box(rhs)
        residual = sum((_box(a)*self.bound_box(j)
                        for j, a in row.items()), I(0))-rhs
        big_m = max(F(0), F(residual.hi))
        lifted = dict(row)
        _plus(lifted, gate, big_m)
        self.le(lifted, rhs+I.rational(big_m), tag)
        self.rows[-1]['big_M'] = str(big_m)
        # Publish only a complete, independently owned template. A budget
        # exception during residual/row construction cannot publish a prefix.
        record = self.rows[-1]
        positions = {index: position for position, index in enumerate(slots)}
        coefficients = tuple((positions[index], value) for index, value in record['coef'].items())
        metadata = {k: v for k, v in record.items() if k not in ('coef', 'tag')}
        metadata['rhs_interval'] = tuple(metadata['rhs_interval'])
        if len(self._conditional_templates) >= _CONDITIONAL_CACHE_LIMIT:
            self._conditional_templates.clear()
            self.template_stats['clears'] += 1
        self._conditional_templates[key] = (coefficients, metadata)

    def conditional_eq(self, row, rhs, gate, tag):
        self.conditional_le(row, rhs, gate, tag+'/upper')
        self.conditional_le({i: -_box(v) for i, v in row.items()}, -_box(rhs), gate, tag+'/lower')

    def affine_conditional_eq(self, target, sources, coefficients, gate, tag):
        """Bind a repeated interval affine propagation/energy equality.

        All coefficients come from Coefficients.get and are interval objects.
        The key snapshots their text, so a changed coefficient cannot reuse a
        stale template. Both directions remain present, with separate budget
        checks. Feedback and generic rows retain conditional_eq/conditional_le.
        """
        self.budget.check()
        if len(coefficients) != len(sources)+1 or not all(isinstance(a, I) for a in coefficients):
            raise ValueError('affine template requires an interval coefficient per source and constant')
        slots = (target, *sources, gate)
        if len(set(slots)) != len(slots):
            # Preserve the original dictionary's overwrite semantics.
            self.conditional_eq({target: 1, **{j: -a for j, a in zip(sources, coefficients[:-1])}},
                                coefficients[-1], gate, tag)
            return
        with self.measure_construction('affine_key_and_lookup', detail=True):
            key = (tuple((str(a.lo), str(a.hi)) for a in coefficients),
                   tuple(self.bound_signature(j) for j in slots))
            pair = self._affine_templates.get(key)
        if pair is not None:
            with self.measure_construction('affine_hit_assembly', detail=True):
                self.append_template(pair[0], slots, tag+'/upper')
                self.append_template(pair[1], slots, tag+'/lower')
            self.affine_stats['hits'] += 1
            return
        self.affine_stats['misses'] += 1
        with self.measure_construction('affine_miss_binding', detail=True):
            self.conditional_eq({target: 1, **{j: -a for j, a in zip(sources, coefficients[:-1])}},
                                coefficients[-1], gate, tag)
            positions = {j: k for k, j in enumerate(slots)}
            pair = []
            for record in self.rows[-2:]:
                values = tuple((positions[j], a) for j, a in record['coef'].items())
                metadata = {k: v for k, v in record.items() if k not in ('coef', 'tag')}
                metadata['rhs_interval'] = tuple(metadata['rhs_interval'])
                pair.append((values, metadata))
            if len(self._affine_templates) >= _AFFINE_CACHE_LIMIT:
                self._affine_templates.clear()
                self.affine_stats['clears'] += 1
            self._affine_templates[key] = tuple(pair)

    def as_solver_dict(self):
        ri, ci, data = [], [], []
        for i, row in enumerate(self.rows):
            if i % 128 == 0:
                self.report()
            for j, value in row['coef'].items():
                if len(data) % 4096 == 0:
                    self.budget.check()
                ri.append(i); ci.append(j); data.append(value)
        n = len(self.names)
        exported = {'c': np.array(self.c), 'A': coo_matrix((data, (ri, ci)), shape=(len(self.rows), n)).tocsr(),
                'b': np.array([r['rhs'] for r in self.rows]), 'Aeq': csr_matrix((0, n)), 'beq': np.empty(0),
                'lb': np.array(self.lb), 'ub': np.array(self.ub), 'intcon': np.array(self.integer, dtype=int)}
        self.budget.check()
        return exported

    def summary(self):
        return {'problem_id': self.instance['id'], 'variables': len(self.names),
                'binary_variables': len(self.integer), 'rows': len(self.rows),
                'options': len(self.options), 'coefficient_sets': self.coefficients.calls,
                'formulation': dict(self.formulation),
                'logical_binary_variables': len(self.logical_binary),
                'deadline_fixed_options': len(self.deadline_fixed_options),
                'events_per_scene': {sid: len(s['events']) for sid, s in self.scenes.items()},
                'objective': 'weighted complete system energy including leakage and idle tail',
                'coefficient_errors': 'outward interval rows; not solver arithmetic certification',
                'optimality_level': 'solver-reported only; external SAFE supplies a feasible upper bound'}


def add_energy_lower_bound(model, target, sources, gates, source_rows, onehot_rows,
                           *, scene=None, interval=None):
    """Add a disjunctive affine bound implied by exported integer-state rows.

    Read binary64 rows/bounds as exact rationals, including their old outward
    allowances. For -E+a_h*z+g_h*w_h<=b_h, w_h=1 implies E>=a_h*z+g_h-b_h.
    A common slope beta and a signed box minimum give E>=beta*z+delta_h.
    Integer one-hot states then imply E>=beta*z+sum(delta_h*w_h). Exporting
    this inequality outwards preserves even the old enclosure's integer points.
    It is a relaxation strengthening, not a certificate of solver arithmetic.
    """
    model.budget.check()
    sources, gates, source_rows = list(sources), list(gates), list(source_rows)
    if not gates or len(gates) != len(source_rows):
        raise ValueError('one source energy row per state required')
    if len({target, *sources, *gates}) != 1+len(sources)+len(gates):
        raise ValueError('energy target, sources and gates must be distinct')
    membership = getattr(model, '_energy_gate_membership', None)
    if membership is None or membership[0] != len(model.logical_binary):
        membership = (len(model.logical_binary), frozenset(model.logical_binary))
        model._energy_gate_membership = membership
    if any(j not in membership[1] or model.lb[j] != 0 or model.ub[j] != 1 for j in gates):
        raise ValueError('logical binary gates on [0,1] required')
    if len(onehot_rows) != 2:
        raise ValueError('exact one-hot row pair required')
    for row_index, sign in zip(onehot_rows, (1.0, -1.0)):
        record = model.rows[row_index]
        if record['coef'] != {j: sign for j in gates} or record['rhs'] != sign:
            raise ValueError('state sum must equal one without row allowance')
    coefficients, constants = [], []
    for gate, row_index in zip(gates, source_rows):
        model.budget.check()
        record = model.rows[row_index]
        row = record['coef']
        if row.get(target) != -1.0 or set(row)-{target, gate, *sources}:
            raise ValueError('expected exported lower energy row with coefficient -1')
        coefficients.append([F.from_float(float(row.get(j, 0.0))) for j in sources])
        constants.append(F.from_float(float(row.get(gate, 0.0)))-F.from_float(float(record['rhs'])))
    boxes = [(F.from_float(float(model.lb[j])), F.from_float(float(model.ub[j]))) for j in sources]
    beta = [min(row[k] for row in coefficients) for k in range(len(sources))]
    offsets = []
    for row, constant in zip(coefficients, constants):
        model.budget.check()
        offsets.append(constant+sum((min((a-b)*lo, (a-b)*hi)
                       for a, b, (lo, hi) in zip(row, beta, boxes)), F(0)))
    cut = {target: -1, **dict(zip(sources, beta)), **dict(zip(gates, offsets))}
    row_index = len(model.rows)
    model.le(cut, 0, 'energy_state_lower_bound')
    model.energy_bound_certificates.append({
        'scene': scene, 'interval': interval, 'target': target, 'sources': sources,
        'gates': gates, 'source_rows': source_rows, 'onehot_rows': list(onehot_rows),
        'cut_row': row_index, 'common_slopes': list(map(str, beta)),
        'state_offsets': list(map(str, offsets)),
        'scope': 'all old exported integer-state points on existing variable boxes; not original LP equivalence'})


def build_model(instance, config, starts=None, budget=None, include_physics=True, progress=None,
                *, fix_late_options=True, aggregate_opp_locks=True,
                relax_auxiliary_integrality=False, strengthen_energy_lower_bounds=False):
    """Build an equivalent finite-domain formulation with budget checks.

    Exact deadline fixing and unit/OPP aggregation are enabled by default.
    Auxiliary integrality relaxation remains an explicit independent variant.
    Energy lower-bound cuts are a separate, default-off precheck variant.
    The switches change representation, never the input option/event catalog.

    Optional ``progress(stage, model, detail)`` receives phase boundaries and
    periodic counts; it must not mutate the model. Budget expiry propagates,
    so a partially generated model is never returned as a solver-ready one.
    """
    budget = budget if budget is not None else Budget()
    budget.check()
    model = Model(instance, budget, progress)
    model.formulation = dict(fix_late_options=bool(fix_late_options),
                             aggregate_opp_locks=bool(aggregate_opp_locks),
                             relax_auxiliary_integrality=bool(relax_auxiliary_integrality))
    if strengthen_energy_lower_bounds:
        model.formulation['energy_lower_bounds'] = True
    energy_specs, energy_onehot_rows = [], {}
    auxiliary = dict(integer=not relax_auxiliary_integrality,
                     implied_binary=relax_auxiliary_integrality)
    model.report('option_expansion')
    p = model.instance['platform']
    nodes = p['node_order']; n = len(nodes)
    units = {u['id']: u for u in p['units']}
    domains = p['domains']
    if starts is not None and not instance['id'].startswith('fixture_'):
        raise ValueError('explicit reduced start sets are fixture-only; production domain must not be trimmed')
    options = expand_options(instance, config, budget=budget)
    if starts is not None:
        start_sets = {(sid, stage): set(map(F, values))
                      for sid, stages in starts.items() for stage, values in stages.items()}
        options = [o for o in options if F(o['start_ms']) in start_sets[o['scenario_id'], o['stage_instance_id']]]
    model.options = options
    model.report('mode_variables')
    model.option_vars = [model.var('y:'+o['option_id'], integer=True) for o in options]
    # These indices retain the original option order and exact rational times.
    # They replace repeated parsing/filtering, not any constraint or choice.
    option_start, option_end, option_power = {}, {}, {}
    options_by_scene = {scene['id']: [] for scene in instance['scenarios']}
    for position, (option, y) in enumerate(zip(options, model.option_vars)):
        if position % 128 == 0:
            budget.check()
        option_start[y] = F(option['start_ms'])/1000
        option_end[y] = F(option['end_ms'])/1000
        option_power[y] = F(option['activity_power_W'])
        options_by_scene[option['scenario_id']].append((option, y))
    unit_domain = {uid: unit['domain_id'] for uid, unit in units.items()}
    unit_node = {uid: unit['thermal_node_id'] for uid, unit in units.items()}
    activity_exports = None
    model.report('shared_mapping')
    shared_by_stage = {}
    for shared, modes in instance['stage_modes'].items():
        shared_by_stage[shared] = []
        for unit in sorted({m['unit_id'] for m in modes}):
            model.shared[shared, unit] = model.var('x:'+shared+':'+unit, **auxiliary)
            shared_by_stage[shared].append((unit, model.shared[shared, unit]))
        model.eq({v: 1 for _, v in shared_by_stage[shared]}, 1, 'shared_unique')
    for scene in instance['scenarios']:
        budget.check()
        model.report('scene_constraints', scene=scene['id'], interval=None)
        sid = scene['id']; scene_options = options_by_scene[sid]
        stage_options = {s['id']: [] for s in scene['stage_instances']}
        starting_at, ending_at = {}, {}
        for position, (o, y) in enumerate(scene_options):
            if position % 128 == 0:
                budget.check()
            stage_options[o['stage_instance_id']].append((o, y))
            starting_at.setdefault(option_start[y], []).append(position)
            ending_at.setdefault(option_end[y], []).append(position)
        deadlines = {r['id']: F(r['deadline_ms'])/1000 for r in scene['requests']}
        for stage in scene['stage_instances']:
            choices = stage_options[stage['id']]
            model.eq({y: 1 for o, y in choices}, 1, 'stage_unique')
            for unit, x in shared_by_stage[stage['shared_stage_id']]:
                model.eq({x: -1, **{y: 1 for o, y in choices if o['unit_id'] == unit}}, 0, 'shared_link')
            # Every Stage belongs to its request; all must finish by deadline.
            deadline = deadlines[stage['request_id']]
            model.le({y: option_end[y] for o, y in choices}, deadline, 'request_deadline')
        for before, after in scene['dependencies']:
            row = {y: option_end[y] for o, y in stage_options[before]}
            for o, y in stage_options[after]:
                _plus(row, y, -option_start[y])
            model.le(row, 0, 'dependency')
        model.report('event_topology')
        events = sorted({F(0), F(instance['window_ms'])/1000} |
                        set(starting_at) | set(ending_at))
        K = len(events)-1
        meta = {'events': events, 'rho': {}, 'joint': {}, 'theta': [], 'q': [], 'energy': [],
                'active': [], 'options': scene_options, 'stage_options': stage_options,
                'start_indicators': {}, 'states': []}
        model.scenes[sid] = meta
        model.report('control_state', intervals_total=K)
        active_positions = set()
        prefix_opps = {did: {scene['entry']['domain_opp'][did]} for did in domains}
        active_nodes = []
        for l, (left, right) in enumerate(zip(events, events[1:])):
            model.report(interval=l)
            # Half-open execution: ends disappear before starts at the same
            # instant. Sorting positions exactly preserves the old scan order.
            active_positions.difference_update(ending_at.get(left, ()))
            active_positions.update(starting_at.get(left, ()))
            active = [scene_options[position] for position in sorted(active_positions)]
            meta['active'].append(active)
            active_by_unit = {uid: [] for uid in units}
            active_by_domain = {did: [] for did in domains}
            active_by_node = {node: [] for node in nodes}
            for pair in active:
                o, y = pair
                active_by_unit[o['unit_id']].append(pair)
                active_by_domain[unit_domain[o['unit_id']]].append(pair)
                active_by_node[unit_node[o['unit_id']]].append(pair)
            active_nodes.append(active_by_node)
            starts_by_domain = {did: [] for did in domains}
            for position in starting_at.get(left, ()):
                o, y = scene_options[position]
                did = unit_domain[o['unit_id']]
                starts_by_domain[did].append(y)
                prefix_opps[did].add(o['opp_id'])
            for unit in units:
                model.le({y: 1 for o, y in active_by_unit[unit]}, 1, 'unit_mutex')
            possible = []
            for domain_id, domain in domains.items():
                for opp in domain['opps']:
                    meta['rho'][l, domain_id, opp] = model.var(f'rho:{sid}:{l}:{domain_id}:{opp}', **auxiliary)
                rhos = {meta['rho'][l, domain_id, opp]: 1 for opp in domain['opps']}
                model.eq(rhos, 1, 'domain_unique')
                starting = starts_by_domain[domain_id]
                trigger = model.var(f'J:{sid}:{l}:{domain_id}', upper=int(bool(starting)), **auxiliary)
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
                if aggregate_opp_locks:
                    by_unit_opp = {}
                    for o, y in active_by_domain[domain_id]:
                        by_unit_opp.setdefault((o['unit_id'], o['opp_id']), []).append(y)
                    for (unit, opp), indices in by_unit_opp.items():
                        model.le({**{y: 1 for y in indices}, meta['rho'][l, domain_id, opp]: -1},
                                 0, 'unit_opp_aggregate_lock')
                else:
                    for o, y in active_by_domain[domain_id]:
                        model.le({y: 1, meta['rho'][l, domain_id, o['opp_id']]: -1}, 0, 'active_locks_opp')
                # Necessary prefix reachability only: an OPP cannot be held
                # before any possible Stage using it has started.
                possible.append(sorted(prefix_opps[domain_id]))
            states = list(product(*possible))
            meta['states'].append(states)
            for state in states:
                meta['joint'][l, state] = model.var(f'w:{sid}:{l}:{state}', **auxiliary)
            if strengthen_energy_lower_bounds:
                energy_onehot_rows[sid, l] = (len(model.rows), len(model.rows)+1)
            model.eq({meta['joint'][l, state]: 1 for state in states}, 1, 'joint_unique')
            for di, (domain_id, domain) in enumerate(domains.items()):
                for opp in domain['opps']:
                    model.eq({meta['rho'][l, domain_id, opp]: -1,
                              **{meta['joint'][l, state]: 1 for state in states if state[di] == opp}}, 0, 'joint_marginal')
        if not include_physics:
            continue
        model.report('physical_variables', interval=None)
        ambient = F(p['ambient_temperature_degC']); reference = F(p['reference_temperature_degC'])
        valid_low, valid_high = map(F, p['power_model_temperature_range_degC'])
        temp_upper = [min(valid_high, F(v)) for v in scene['maximum_temperature_degC']]
        for l in range(K+1):
            meta['theta'].append([model.var(f'theta:{sid}:{l}:{node}', valid_low-ambient, temp_upper[i]-ambient)
                                  for i, node in enumerate(nodes)])
        for i in range(n):
            model.eq({meta['theta'][0][i]: 1}, F(scene['entry']['temperature_degC'][i])-ambient, 'entry_temperature')
        model.report('thermal_energy_rows')
        if activity_exports is None:
            with model.measure_construction('activity_export_preparation'):
                activity_exports = {y: model.activity_export(y, power) for y, power in option_power.items()}
        state_power = {}
        for l, (left, right) in enumerate(zip(events, events[1:])):
            model.report(interval=l)
            with model.measure_construction('activity_power_variables_and_rows'):
                qmax = []
                meta['q'].append([])
                for node in nodes:
                    active_node = active_nodes[l][node]
                    maximum = max([option_power[y] for o, y in active_node]+[F(0)])
                    qmax.append(maximum)
                    qv = model.var(f'q:{sid}:{l}:{node}', 0, maximum)
                    meta['q'][l].append(qv)
                    model.activity_power_eq(qv, (y for o, y in active_node), activity_exports)
            states = meta['states'][l]
            with model.measure_construction('power_upper_and_energy_variable'):
                for state in states:
                    if state not in state_power:
                        base, slopes = model.coefficients.power(state)
                        state_power[state] = sum(base)+sum(lam*(upper-reference) for lam, upper in zip(slopes, temp_upper))+F(p['external_common_power_W'])
                # qmax is common to all states; arithmetic is exact rational.
                power_upper = max(state_power[s] for s in states)+sum(qmax)
                ev = model.var(f'energy:{sid}:{l}', 0, power_upper*(right-left), cost=F(scene['weight']))
                meta['energy'].append(ev)
            sources = meta['theta'][l]+meta['q'][l]
            energy_source_rows = []
            for state in states:
                model.report(control_state=list(state))
                gate = meta['joint'][l, state]
                with model.measure_construction('coefficient_lookup_and_generation'):
                    coeff = model.coefficients.get(state, right-left)
                with model.measure_construction('thermal_conditional_rows'):
                    for i, row in enumerate(coeff['temperature']):
                        model.affine_conditional_eq(meta['theta'][l+1][i], sources, row, gate, 'thermal_propagation')
                    row = coeff['energy']
                    model.affine_conditional_eq(ev, sources, row, gate, 'complete_energy')
                    if strengthen_energy_lower_bounds:
                        energy_source_rows.append(len(model.rows)-1)
            if strengthen_energy_lower_bounds:
                energy_specs.append((sid, l, ev, sources,
                    [meta['joint'][l, state] for state in states], energy_source_rows))
    if fix_late_options:
        model.report('deadline_fixing', scene=None, interval=None, control_state=None)
        for option, y in zip(model.options, model.option_vars):
            model.budget.check()
            if F(option['end_ms']) > F(option['request_deadline_ms']):
                model.fix_zero_option(y)
    if strengthen_energy_lower_bounds:
        model.report('energy_lower_bounds', scene=None, interval=None, control_state=None)
        with model.measure_construction('energy_lower_bounds'):
            for sid, l, ev, sources, gates, rows in energy_specs:
                add_energy_lower_bound(model, ev, sources, gates, rows, energy_onehot_rows[sid, l],
                                       scene=sid, interval=l)
    model.report('complete', scene=None, interval=None, control_state=None)
    return model


def logical_candidate_diagnostics(model, values, integer_tolerance=1e-6):
    """Inspect every logical binary, including auxiliaries omitted from intcon.

    This checks numerical binary membership, not the solver's physical state.
    The decoded schedule and continuous trajectory are independently rebuilt.
    """
    report = {'vector_valid': False, 'accepted': False, 'reason': None,
              'integer_tolerance': integer_tolerance, 'families': {}}
    try:
        values = np.asarray(values, dtype=float).reshape(-1)
    except (ValueError, TypeError, OverflowError):
        report['reason'] = 'invalid solver vector'; return report
    if len(values) != len(model.names) or not np.all(np.isfinite(values)):
        report['reason'] = 'invalid solver vector'; return report
    report['vector_valid'] = True
    for i in model.logical_binary:
        name = model.names[i]
        family = name.split(':', 1)[0]
        item = report['families'].setdefault(family, {'count': 0,
            'max_integrality_error': 0.0, 'worst_variable': None,
            'outside_binary_count': 0, 'nonintegral_count': 0})
        value = float(values[i]); rounded = round(value)
        error = abs(value-rounded)
        item['count'] += 1
        if item['worst_variable'] is None or error > item['max_integrality_error']:
            item.update(max_integrality_error=error, worst_variable=name)
        item['nonintegral_count'] += int(error > integer_tolerance)
        item['outside_binary_count'] += int(rounded not in (0, 1))
    if any(x['outside_binary_count'] for x in report['families'].values()):
        report['reason'] = 'logical solver value outside binary range'
    elif any(x['nonintegral_count'] for x in report['families'].values()):
        report['reason'] = 'nonintegral solver candidate'
    else:
        report['accepted'] = True
    return report


def decode(model, values, integer_tolerance=1e-6):
    report = logical_candidate_diagnostics(model, values, integer_tolerance)
    if not report['accepted']:
        raise ValueError(report['reason'])
    values = np.asarray(values, dtype=float).reshape(-1)
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
    if evaluation.get('evidence_identity') != {'input_sha256': _digest(model.instance),
                                              'candidate_sha256': _digest(candidate)}:
        raise ValueError('feedback receipt does not belong to this input and candidate')
    checked = validate_schedule(model.instance, candidate)
    if checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('feedback requires legal candidate')
    if evaluation.get('problem_id') != model.instance['id'] or evaluation.get('legality') != checked:
        raise ValueError('feedback legality receipt mismatch')
    initial_rows = len(model.rows)
    actions = []
    for witness in evaluation['violations']:
        sid, node, when = witness['scene_id'], witness['node'], F(witness['time_s'])
        scene = next(s for s in model.instance['scenarios'] if s['id'] == sid)
        node_index = model.coefficients.nodes.index(node)
        if F(witness['limit_degC']) != F(scene['maximum_temperature_degC'][node_index]):
            raise ValueError('feedback temperature limit mismatch')
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


def evaluate_model_candidate(model, candidate, accuracy, budget=None):
    """Bind an independent evaluator receipt to full input and candidate."""
    identity = {'input_sha256': _digest(model.instance), 'candidate_sha256': _digest(candidate)}
    result = evaluate_candidate(model.instance, candidate, accuracy, budget if budget is not None else model.budget)
    result['evidence_identity'] = identity
    return result


def solve_with_feedback(model, session, accuracy, budget=None, max_rounds=50):
    budget = budget if budget is not None else model.budget
    phase = getattr(budget, 'phase', lambda name: nullcontext())
    authorized_seconds = budget.seconds
    result = {'state': 'UNRESOLVED', 'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'rounds': [], 'feedback': [], 'independently_proven_optimal': False,
              'independently_proven_infeasible': False, 'remaining_domain': 'retained', 'reason': None}
    try:
        for iteration in range(max_rounds):
            budget.check()
            with phase('matrix_export'):
                solver_input = model.as_solver_dict()
            budget.check()
            with phase('solver_transport_and_solve'):
                kwargs = {'remaining_s': max(0, budget.seconds-budget.elapsed)}
                if hasattr(budget, 'deadline'):
                    kwargs['budget'] = budget
                returned = session.solve(solver_input, **kwargs)
            result['rounds'].append(returned)
            budget.check()
            if not returned.get('budget_valid', False):
                result['reason'] = 'SOLVER_RETURN_AFTER_BUDGET'; break
            if not returned.get('x'):
                result['reason'] = 'SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag') == -2 else 'NO_INTEGER_CANDIDATE'
                break
            if not returned.get('accepted_for_evaluation', False):
                result['reason'] = 'SOLVER_INTERFACE_ERROR'; break
            try:
                with phase('decode_and_legality'):
                    candidate = decode(model, returned['x'])
            except ValueError as error:
                result['reason'] = 'NUMERICAL_CANDIDATE_ANOMALY: '+str(error); break
            with phase('continuous_thermal_energy_evaluation'):
                evaluation = evaluate_model_candidate(model, candidate, accuracy, budget)
            # Preserve evaluator evidence even if the deadline just elapsed.
            result['evaluation'] = evaluation
            if evaluation['state'] == 'SAFE' and evaluation.get('rankable_energy') and evaluation['completed_at_elapsed_s'] < authorized_seconds:
                result.update(state='SAFE', safe_candidate=candidate,
                              safe_upper_bound_J=evaluation['safe_upper_bound_J'],
                              reason='SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag') == 1 else 'SAFE_INCUMBENT')
                budget.check()  # Existing in-budget evidence is already saved.
                break
            if evaluation['state'] != 'THERMAL_VIOLATION':
                result['reason'] = 'EVALUATION_UNRESOLVED'; break
            budget.check()
            with phase('thermal_feedback'):
                feedback = add_thermal_feedback(model, candidate, evaluation)
            feedback['completed_at_elapsed_s'] = budget.elapsed
            feedback['within_budget'] = feedback['completed_at_elapsed_s'] < authorized_seconds
            if feedback['within_budget']:
                result['feedback'].append(feedback)
            else:
                result.setdefault('late_feedback_diagnostics', []).append(feedback)
            budget.check()
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
