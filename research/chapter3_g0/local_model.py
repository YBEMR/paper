"""Controlled G0 local builder with separately gated wiring seams.

Imports perform no work. The numerical suffix is inherited verbatim from the
archived builder; real G0 construction, coefficient generation and solvers
remain disabled pending separately approved scientific entry. Wiring tests
must explicitly inject a fake Model factory and finite handwritten options.
"""
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib
import importlib
import json
import sys

SOURCE_BUILD_SHA256 = '7c140a6507f472a88197759cc3c8ba61be55c61e772c1cb5104ac1016af1d02a'
PROTECTED_SUFFIX_SHA256 = '88d8a3c97782341c1000a41aabce1393e2154d027b1abe807a8c735099985d66'
MANUAL_ORIGIN = 'MANUAL_PRESTORED_COEFFICIENT_ROW_REPLAY'


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


def inherited_source_check():
    """Text/hash protection, without importing or executing production code."""
    path = Path(__file__).parents[1] / 'chapter3_experiments' / 'milp.py'
    source = path.read_text(encoding='utf-8')
    original = source[source.index('def build_model('):source.index('\n\ndef logical_candidate_diagnostics')]
    suffix = original[original.index('    model.options = options\n'):]
    local = Path(__file__).read_text(encoding='utf-8')
    local = local[local.index('def build_local_model('):local.index('\n\ndef assert_view_receipt')]
    local_suffix = local[local.index('    model.options = options\n'):]
    return {
        'source_builder_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'source_builder_matches': hashlib.sha256(original.encode()).hexdigest() == SOURCE_BUILD_SHA256,
        'numerical_suffix_sha256': hashlib.sha256(suffix.encode()).hexdigest(),
        'numerical_suffix_exact_text': suffix == local_suffix,
        'numerical_suffix_matches': hashlib.sha256(suffix.encode()).hexdigest() == PROTECTED_SUFFIX_SHA256,
        'scope': 'text inheritance only; not real-model, solver or thermal verification',
    }


def _kernel():
    directory = Path(__file__).parents[1] / 'chapter3_experiments'
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    kernel = importlib.import_module('milp')
    if Path(kernel.__file__).resolve() != (directory / 'milp.py').resolve():
        raise ValueError('unexpected numerical kernel source')
    return kernel


@dataclass(frozen=True)
class ManualReplay:
    options: list
    coefficients: object
    input_sha256: str
    config_sha256: str
    source_kind: str = MANUAL_ORIGIN


def _manual_model(kernel, instance, budget, progress, coefficients):
    # No call to Model.__init__: it would create real Coefficients.
    model = object.__new__(kernel.Model)
    model.instance = deepcopy(instance)
    model.input_sha256 = _digest(model.instance)
    model.budget = budget
    model.names, model.lb, model.ub, model.integer, model.c = [], [], [], [], []
    model.logical_binary = []
    model.deadline_fixed_options = []
    model.energy_bound_certificates = []
    model.formulation = {}
    model.bounds, model.rows, model.scenes, model.shared = [], [], {}, {}
    model.options, model.option_vars, model.feedback_log = [], [], []
    model.coefficients = coefficients
    model.excluded_schedules = set()
    model.feedback_identities = set()
    model.progress = progress
    model.construction_costs = {}
    model.construction_detail_costs = {}
    model.row_nonzeros = 0
    model._bound_boxes = {}
    model._bound_magnitudes = {}
    model._coefficient_exports = {}
    model._conditional_templates = {}
    model.template_stats = {'hits': 0, 'misses': 0, 'clears': 0}
    model._fraction_exports = {}
    model._fraction_negatives = {}
    model._bound_signatures = {}
    model._affine_templates = {}
    model.affine_stats = {'hits': 0, 'misses': 0, 'clears': 0}
    model._row_rhs_exports = {}
    model._activity_exports = {}
    return model


def build_local_model(config, instance, *, condition, budget, manual=False,
                      manual_backend=None, coefficient_factory=None,
                      wiring_permit=None, wiring_dependencies=None,
                      starts=None, include_physics=True, progress=None,
                      fix_late_options=True, aggregate_opp_locks=True,
                      relax_auxiliary_integrality=False,
                      strengthen_energy_lower_bounds=False,
                      prefilter_deadlines=True, cumulative_precedence=False,
                      preeliminate_closed_anchors=True):
    """Manual replay, or a capability-gated and explicitly wired front end.

    A later real entry must use original Coefficients, never this injection
    seam. All returned rows carry manual provenance and are not scientific
    results. Original arithmetic is reused without an original model build.
    """
    wiring = None
    if wiring_permit is not None:
        if manual or manual_backend is not None or coefficient_factory is not None:
            raise ValueError('manual and separately gated wiring profiles cannot mix')
        from ..chapter3_g0_real_entry.model_backend import resolve_build_dependencies
        wiring = resolve_build_dependencies(wiring_permit, wiring_dependencies)
    elif manual is not True:
        raise RuntimeError('REAL_G0_CONSTRUCTION_DISABLED_PENDING_SEPARATE_APPROVAL')
    if coefficient_factory is not None:
        raise ValueError('factory injection disabled; provide labelled prestored rows')
    if wiring is None:
        if not isinstance(manual_backend, ManualReplay) or manual_backend.source_kind != MANUAL_ORIGIN:
            raise ValueError('explicit labelled manual backend required')
        if (manual_backend.input_sha256 != _digest(instance) or
                manual_backend.config_sha256 != _digest(config)):
            raise ValueError('manual replay input/config identity mismatch')
    if starts is not None:
        raise ValueError('G0 uses declared original start domain; no override')
    for value in (include_physics, fix_late_options, aggregate_opp_locks,
                  relax_auxiliary_integrality, strengthen_energy_lower_bounds,
                  prefilter_deadlines, cumulative_precedence, preeliminate_closed_anchors):
        if type(value) is not bool:
            raise ValueError('builder switches require bool')
    from .local_domain import validate_condition, filter_options
    condition = validate_condition(config, instance, condition, budget=budget)
    protected = inherited_source_check()
    if not all(protected[key] for key in (
            'source_builder_matches', 'numerical_suffix_exact_text', 'numerical_suffix_matches')):
        raise ValueError('non-whitelisted original builder/source drift')
    budget.check()
    if wiring is None:
        kernel = _kernel()
        from control_policy import AUTO_LOW_IMMEDIATE_V1, resolve_idle_policy
        from scene_adapter import make_scene_instance
    else:
        kernel = wiring['kernel']
        AUTO_LOW_IMMEDIATE_V1 = wiring['auto_low_policy']
        resolve_idle_policy = wiring['resolve_idle_policy']
        make_scene_instance = wiring['make_scene_instance']
    _plus = kernel._plus
    add_energy_lower_bound = kernel.add_energy_lower_bound
    add_cumulative_precedence = kernel.add_cumulative_precedence
    idle_policy = resolve_idle_policy(instance)
    if resolve_idle_policy(config) != idle_policy:
        raise ValueError('MILP instance/config control policies must match')
    auto_low = idle_policy == AUTO_LOW_IMMEDIATE_V1
    sid = condition['scene_id']
    normalized = deepcopy(condition['d0_all'])
    view = make_scene_instance(instance, sid, unweighted=True)
    for shared, modes in view['stage_modes'].items():
        view['stage_modes'][shared] = [mode for mode in modes if mode['unit_id'] == normalized[shared]]
    if wiring is None:
        model = _manual_model(kernel, view, budget, progress, manual_backend.coefficients)
    else:
        model = wiring['model_factory'](view, budget, progress=progress)
        if model.budget is not budget or _digest(model.instance) != _digest(view):
            raise ValueError('wired Model factory changed view or root budget')
    model.formulation = dict(fix_late_options=bool(fix_late_options),
                             aggregate_opp_locks=bool(aggregate_opp_locks),
                             relax_auxiliary_integrality=bool(relax_auxiliary_integrality))
    if strengthen_energy_lower_bounds:
        model.formulation['energy_lower_bounds'] = True
    if cumulative_precedence:
        model.formulation['cumulative_precedence'] = True
    if auto_low:
        model.formulation['idle_policy'] = idle_policy
    adapted = True
    model.preprocessing = {
        'source_input_sha256': _digest(instance),
        'fixed_deployment': deepcopy(normalized),
        'fixed_scene_id': sid,
        'prefilter_deadlines': bool(prefilter_deadlines),
        'objective_weights': {scene['id']: scene['weight'] for scene in instance['scenarios']},
        'numeric_scope': ('manual row replay only; no scientific model execution'
                          if wiring is None else 'gated '+wiring['kind']+' model wiring'),
        'options_before_deadline_filter': None, 'deadline_removed_count': 0,
        'empty_stage_option_sets': [], 'fixed_idle_domains': {},
        'manual_origin': MANUAL_ORIGIN if wiring is None else None,
        'wiring_profile': None if wiring is None else wiring['kind'],
        'formal_experiment_result': False,
        'source_text_protection': protected,
    }
    model.formulation.update(prefilter_deadlines=bool(prefilter_deadlines),
        fixed_deployment=True, fixed_scene_id=sid, fixed_device_neighborhood=True,
        g0_condition_sha256=condition['condition_sha256'])
    model.neighborhood_condition = deepcopy(condition)
    model.preprocessing['neighborhood_condition_sha256'] = condition['condition_sha256']
    energy_specs, energy_onehot_rows = [], {}
    auxiliary = dict(integer=not relax_auxiliary_integrality,
                     implied_binary=relax_auxiliary_integrality)
    model.report('option_expansion')
    p = model.instance['platform']
    nodes = p['node_order']; n = len(nodes)
    units = {unit['id']: unit for unit in p['units']}
    domains = p['domains']
    options = (deepcopy(manual_backend.options) if wiring is None else
               wiring['expand_options'](model.instance, config, budget=budget))
    if any(option['scenario_id'] != sid for option in options):
        raise ValueError('manual rows must belong to original requested scene')
    options, model.neighborhood_stats = filter_options(
        config, instance, options, condition, budget=budget, preeliminate=False, scene_ids=[sid])
    model.preprocessing['options_before_deadline_filter'] = len(options)
    if prefilter_deadlines:
        retained = []
        for position, option in enumerate(options):
            if position % 128 == 0:
                budget.check()
            if F(option['end_ms']) <= F(option['request_deadline_ms']):
                retained.append(option)
        model.preprocessing['deadline_removed_count'] = len(options)-len(retained)
        options = retained
    if preeliminate_closed_anchors:
        model.report('closed_anchor_preelimination')
        options, stats = filter_options(config, instance, options, condition,
            budget=budget, preeliminate=True, scene_ids=[sid])
        model.preprocessing['closed_anchor_preelimination'] = stats
        model.formulation['preeliminate_closed_anchors'] = True
    model.options = options
    model.report('mode_variables')
    model.option_vars = [model.var('y:'+o['option_id'], integer=True) for o in options]
    # These indices retain the original option order and exact rational times.
    # They replace repeated parsing/filtering, not any constraint or choice.
    option_start, option_end, option_power = {}, {}, {}
    options_by_scene = {scene['id']: [] for scene in model.instance['scenarios']}
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
    for shared, modes in model.instance['stage_modes'].items():
        shared_by_stage[shared] = []
        for unit in sorted({m['unit_id'] for m in modes}):
            model.shared[shared, unit] = model.var('x:'+shared+':'+unit, **auxiliary)
            shared_by_stage[shared].append((unit, model.shared[shared, unit]))
        model.eq({v: 1 for _, v in shared_by_stage[shared]}, 1, 'shared_unique')
    for scene in model.instance['scenarios']:
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
            if adapted and not choices:
                # Keep the exact contradictory one-hot rows. An empty local
                # set is not an input/thermal error and is never silently lost.
                model.preprocessing['empty_stage_option_sets'].append(stage['id'])
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
        events = sorted({F(0), F(model.instance['window_ms'])/1000} |
                        set(starting_at) | set(ending_at))
        K = len(events)-1
        meta = {'events': events, 'rho': {}, 'joint': {}, 'theta': [], 'q': [], 'energy': [],
                'active': [], 'options': scene_options, 'stage_options': stage_options,
                'start_indicators': {}, 'states': []}
        model.scenes[sid] = meta
        fixed_idle = ({did: 'L' if auto_low else scene['entry']['domain_opp'][did] for did in domains
                       if not any(unit_domain[o['unit_id']] == did for o, y in scene_options)}
                      if adapted else {})
        if adapted:
            model.preprocessing['fixed_idle_domains'][sid] = fixed_idle
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
                    held = int(opp == fixed_idle[domain_id]) if domain_id in fixed_idle else None
                    bounds = {} if held is None else {'lower': held, 'upper': held}
                    meta['rho'][l, domain_id, opp] = model.var(f'rho:{sid}:{l}:{domain_id}:{opp}', **bounds, **auxiliary)
                rhos = {meta['rho'][l, domain_id, opp]: 1 for opp in domain['opps']}
                model.eq(rhos, 1, 'domain_unique')
                starting = starts_by_domain[domain_id]
                trigger = model.var(f'J:{sid}:{l}:{domain_id}', upper=int(bool(starting)), **auxiliary)
                meta['start_indicators'][l, domain_id] = trigger
                for y in starting:
                    model.le({y: 1, trigger: -1}, 0, 'start_or_lower')
                model.le({trigger: 1, **{y: -1 for y in starting}}, 0, 'start_or_upper')
                if auto_low:
                    # A non-L state needs active work at that same OPP.
                    # Together with the active locks and one-hot rows, this
                    # forces L exactly when the whole domain is empty.
                    for opp in domain['opps']:
                        if opp != 'L':
                            model.le({meta['rho'][l, domain_id, opp]: 1,
                                      **{y: -1 for o, y in active_by_domain[domain_id]
                                         if o['opp_id'] == opp}},
                                     0, 'auto_opp_active_support')
                else:
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
                if auto_low:
                    # Every selected active OPP is possible; idle is always L.
                    possible.append(sorted({'L'} | {
                        o['opp_id'] for o, y in active_by_domain[domain_id]}))
                else:
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
    if cumulative_precedence:
        model.report('cumulative_precedence', scene=None, interval=None, control_state=None)
        with model.measure_construction('cumulative_precedence'):
            for scene in model.instance['scenarios']:
                budget.check()
                add_cumulative_precedence(model, scene['id'],
                    model.scenes[scene['id']]['stage_options'], option_start, option_end,
                    dependencies=scene['dependencies'])
                model.cumulative_precedence_stats['complete'] = False
        model.cumulative_precedence_stats['complete'] = True
    model.report('complete', scene=None, interval=None, control_state=None)
    return model


def assert_view_receipt(model, candidate, evaluation):
    """Reject a full-input PARTIAL envelope before numerical x0/feedback."""
    expected = {'input_sha256': _digest(model.instance), 'candidate_sha256': _digest(candidate)}
    if evaluation.get('evidence_identity') != expected:
        raise ValueError('model-view receipt identity mismatch')
    if evaluation.get('problem_id') != model.instance['id']:
        raise ValueError('model-view problem identity mismatch')
    return expected


def _assert_view_time(model, evaluation, budget):
    if model.budget is not budget:
        raise ValueError('model-view completion must use the same root budget object')
    formed = evaluation.get('completed_at_elapsed_s')
    if (isinstance(formed, bool) or not isinstance(formed, (int, float)) or
            not 0 <= formed <= budget.elapsed or
            formed >= getattr(budget, 'effective_deadline_elapsed_s', budget.seconds)):
        raise ValueError('model-view formation time is missing, future or outside cutoff')


def prepare_view_initial_point(model, candidate, evaluation, budget, *, completer=None):
    assert_view_receipt(model, candidate, evaluation)
    _assert_view_time(model, evaluation, budget)
    if evaluation.get('state') != 'SAFE' or not evaluation.get('rankable_energy'):
        raise ValueError('matching model-view SAFE required')
    if completer is None:
        raise RuntimeError('REAL_X0_COMPLETION_DISABLED')
    budget.check()
    result = completer(model, candidate, evaluation, budget)
    budget.check()
    return result


def apply_view_feedback(model, candidate, evaluation, *, feedback=None):
    assert_view_receipt(model, candidate, evaluation)
    _assert_view_time(model, evaluation, model.budget)
    if feedback is None:
        raise RuntimeError('REAL_THERMAL_FEEDBACK_DISABLED')
    model.budget.check()
    return feedback(model, candidate, evaluation)
