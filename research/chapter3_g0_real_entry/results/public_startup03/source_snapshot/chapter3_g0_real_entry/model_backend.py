"""Gated bindings for G0 Model/options, warm x0 and continuous feedback.

Importing this module loads no scientific dependency. The current stage has
only SIMULATION capabilities; all executable tests require fake dependencies.
Native bindings are defined lazily for a separately approved future entry.
"""
from copy import deepcopy
from pathlib import Path
import importlib
import sys

from .gating import require_permit, require_simulation_dependencies


BUILDER_FLAGS = {
    'include_physics': True,
    'fix_late_options': True,
    'aggregate_opp_locks': True,
    'relax_auxiliary_integrality': True,
    'strengthen_energy_lower_bounds': True,
    'prefilter_deadlines': True,
    'cumulative_precedence': False,
    'preeliminate_closed_anchors': True,
}


def _legacy_module(name):
    directory = Path(__file__).resolve().parents[1] / 'chapter3_experiments'
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    module = importlib.import_module(name)
    if Path(module.__file__).resolve().parent != directory.resolve():
        raise ImportError('wrong legacy source for '+name)
    return module


def resolve_build_dependencies(permit, dependencies):
    kind = require_permit(permit)
    require_simulation_dependencies(permit, dependencies)
    if kind == 'SIMULATION':
        required = ('kernel','model_factory','expand_options','make_scene_instance',
                    'resolve_idle_policy','auto_low_policy')
        if not isinstance(dependencies, dict) or set(required)-set(dependencies):
            raise ValueError('explicit complete simulation model dependencies required')
        resolved = {key: dependencies[key] for key in required}
        for key in ('model_factory','expand_options','make_scene_instance','resolve_idle_policy'):
            if not callable(resolved[key]):
                raise ValueError('invalid simulation dependency: '+key)
    else:
        # No REAL permit can be created by this stage's gating implementation.
        # A future permit must select these exact production factories; callers
        # may never inject stored/manual coefficients into this branch.
        if dependencies is not None:
            raise ValueError('real model dependencies cannot be replaced')
        kernel = _legacy_module('milp')
        control = _legacy_module('control_policy')
        scene = _legacy_module('scene_adapter')
        inputs = _legacy_module('inputs')
        resolved = dict(kernel=kernel, model_factory=kernel.Model,
            expand_options=inputs.expand_options, make_scene_instance=scene.make_scene_instance,
            resolve_idle_policy=control.resolve_idle_policy,
            auto_low_policy=control.AUTO_LOW_IMMEDIATE_V1)
    resolved['kind'] = kind
    return resolved


def _evaluation_dependencies(permit, dependencies):
    kind = require_permit(permit)
    require_simulation_dependencies(permit, dependencies)
    required = ('evaluate_model_candidate','complete_initial_point',
                'checked_thermal_witnesses','add_thermal_feedback')
    if kind == 'SIMULATION':
        if not isinstance(dependencies, dict) or any(not callable(dependencies.get(k)) for k in required):
            raise ValueError('explicit simulation evaluation/x0/feedback dependencies required')
        return {key: dependencies[key] for key in required}
    if dependencies is not None:
        raise ValueError('real evaluation dependencies cannot be replaced')
    kernel = _legacy_module('milp')
    return dict(evaluate_model_candidate=kernel.evaluate_model_candidate,
        complete_initial_point=_legacy_module('initial_point').complete_initial_point,
        checked_thermal_witnesses=_legacy_module('formal_milp')._checked_thermal_witnesses,
        add_thermal_feedback=kernel.add_thermal_feedback)


def build(config, instance, condition, budget, *, dependencies=None, permit, progress=None):
    """Use exact frozen flags; native Model/options are capability-gated."""
    require_permit(permit)
    from ..chapter3_g0.local_model import build_local_model
    return build_local_model(config, instance, condition=condition, budget=budget,
        progress=progress, wiring_permit=permit, wiring_dependencies=dependencies,
        **BUILDER_FLAGS)


def prepare(model, anchor, budget, bridge, *, dependencies=None, permit, scope=None):
    """Real-shape view evaluation -> provenance gate -> numerical x0 admission.

    The completer consumes the untouched original view receipt. A rejected x0
    returns None and never deletes the inherited complete global SAFE.
    """
    deps = _evaluation_dependencies(permit, dependencies)
    if model.budget is not budget or bridge.budget is not budget:
        raise ValueError('prepare requires the model and bridge root budget')
    budget.check()
    raw = deps['evaluate_model_candidate'](model, anchor, bridge.accuracy, budget)
    wrapped = bridge.bind_model_view(model.instance, anchor, raw, scope=scope)
    checked = bridge.validate_model_view(model.instance, anchor, wrapped, scope=scope)
    if checked.get('state') in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
        raise ArithmeticError('CERTIFIED_ANCHOR_MODEL_VIEW_CONFLICT')
    if checked.get('state') != 'SAFE':
        return dict(state='MODEL_VIEW_UNRESOLVED', x0=None,
                    evaluation=wrapped, raw_evaluation=deepcopy(raw))
    budget.check()
    completion = deps['complete_initial_point'](model, anchor, raw, budget)
    budget.check()
    state = completion.get('state')
    x0 = completion.get('x0')
    if state != 'INITIAL_POINT_READY' and x0 is not None:
        raise ValueError('numerically rejected initial vector must be absent')
    if state == 'INITIAL_POINT_READY' and x0 is None:
        raise ValueError('ready initial point must include its numerical vector')
    return dict(state=state, x0=x0, evaluation=wrapped, raw_evaluation=deepcopy(raw),
                completion=deepcopy({k:v for k,v in completion.items() if k!='x0'}))


def feedback(model, candidate, evaluation, budget, bridge, *, dependencies=None, permit,
             scope=None):
    """Only timely strict model-view witnesses reach the unchanged row kernel."""
    deps = _evaluation_dependencies(permit, dependencies)
    if model.budget is not budget or bridge.budget is not budget:
        raise ValueError('feedback requires the model and bridge root budget')
    checked = bridge.validate_model_view(model.instance, candidate, evaluation, scope=scope)
    budget.check()
    raw = deepcopy({key:value for key,value in checked.items() if key!='g0_context'})
    witnesses = deps['checked_thermal_witnesses'](model, candidate, raw)
    if not witnesses:
        return {'state':'NO_STRICT_THERMAL_FEEDBACK','added':False}
    budget.check()
    result = deps['add_thermal_feedback'](model, candidate, raw)
    budget.check()
    return result
