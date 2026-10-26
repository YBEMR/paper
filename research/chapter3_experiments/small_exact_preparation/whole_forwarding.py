"""Pure K193 wrapper forwarding fixture; no numerical model or native call."""
from copy import deepcopy
from functools import partial
from pathlib import Path
import json
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import contract as c


def audit():
    # Import only. Instantiation/calls of these scientific engines are blocked.
    import formal_milp as formal
    import run_warm_diagnostic as warm
    import milp
    import thermal
    instance = json.loads(c.INPUT.read_bytes())
    config = json.loads(c.CONFIG.read_bytes())
    expected = dict(fix_late_options=True, aggregate_opp_locks=True,
        relax_auxiliary_integrality=True, strengthen_energy_lower_bounds=True,
        include_physics=True, prefilter_deadlines=True, cumulative_precedence=False,
        fixed_deployment=None, fixed_shared_deployment=None, fixed_scene_id=None,
        neighborhood_condition=None, preeliminate_closed_anchors=False)
    explicit = {k: v for k, v in expected.items() if k not in warm.FLAGS}
    seen = {}
    budget_token = object()

    def loader(budget):
        if budget is not budget_token:
            raise AssertionError('Root budget was not forwarded to input loader')
        return deepcopy(config), deepcopy(instance)

    def builder(view, cfg, **kwargs):
        if view != instance or cfg != config:
            raise AssertionError('Whole wrapper changed frozen instance or config')
        if kwargs.pop('budget') is not budget_token:
            raise AssertionError('Builder did not inherit root budget')
        kwargs.pop('progress')
        if kwargs != expected or 'starts' in kwargs:
            raise AssertionError('Whole builder flags differ from declared common-domain path')
        seen['final_builder_flags'] = kwargs
        return 'PURE_FIXTURE_MODEL_NOT_A_NUMERIC_MODEL'

    def native_forbidden(*args, **kwargs):
        raise AssertionError('Real scientific operation forbidden in forwarding fixture')

    def fake_execute(input_loader, out, **kwargs):
        if kwargs['seconds'] != 300 or kwargs['construct_only'] is not False:
            raise AssertionError('Wrong root budget/lifecycle')
        cfg, view = input_loader(budget_token)
        kwargs['model_builder'](view, cfg, budget=budget_token, progress=None)
        if kwargs['session_factory'].keywords != {'cut_max_iterations': 10}:
            raise AssertionError('Session cut option drift')
        seen['session_constructor_called'] = False
        seen['solve_callback_called'] = False
        return {'state': 'PURE_FIXTURE_ONLY', 'reason': 'NO_EVALUATION_OR_SOLVER'}

    with tempfile.TemporaryDirectory(dir=HERE) as folder:
        with patch.object(warm, 'execute_milp', side_effect=fake_execute), \
             patch.object(milp, 'build_model', side_effect=native_forbidden), \
             patch.object(thermal, 'evaluate_candidate', side_effect=native_forbidden):
            formal.execute_formal_milp(loader, Path(folder), seconds=300,
                model_builder=partial(builder, **explicit), feedback_kind='conditional',
                session_factory=partial(native_forbidden, cut_max_iterations=10))
    if 'final_builder_flags' not in seen:
        raise AssertionError('Whole forwarding fixture never reached fake builder')
    return {'state': 'PURE_FORWARDING_PASS', **seen,
        'formal_wrapper_and_warm_wrapper_exercised': True,
        'numerical_model_built': False, 'formal_small_domain_launcher_ready': False,
        'MATLAB_starts': 0, 'optimizer_calls': 0, 'thermal_integrations': 0,
        'scope': 'argument and input forwarding only; not real model feasibility or full lifecycle acceptance'}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
