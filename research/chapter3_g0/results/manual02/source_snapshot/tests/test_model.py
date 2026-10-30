"""A16/A19 artificial numerical and model-view boundary acceptance."""
from copy import deepcopy
from fractions import Fraction
from types import SimpleNamespace

from ..budget import G0Budget, ScopeExhausted
from ..contract import derive_deployment
from ..local_domain import make_condition
from ..local_model import (inherited_source_check, build_local_model, _digest,
    prepare_view_initial_point, apply_view_feedback)
from .fixtures import bundle, FakeClock
from .model_replay import replay_rows


def _options(instance, candidate, sid):
    """Write exact hand options; do not enumerate production input choices."""
    scene = next(s for s in instance['scenarios'] if s['id'] == sid)
    stages = {s['id']: s for s in scene['stage_instances']}
    requests = {r['id']: r for r in scene['requests']}
    result = []
    for row in candidate['scenes'][sid]:
        stage = stages[row['stage_id']]
        mode = next(m for m in instance['stage_modes'][stage['shared_stage_id']]
                    if m['unit_id'] == row['unit'] and m['opp_id'] == row['opp'])
        start = Fraction(row['start_ms'])
        request = requests[stage['request_id']]
        result.append(dict(deepcopy(mode), option_id='MANUAL:'+row['stage_id'],
            scenario_id=sid, stage_instance_id=row['stage_id'], request_id=stage['request_id'],
            start_ms=str(start), end_ms=str(start+Fraction(mode['duration_ms'])),
            request_deadline_ms=request['deadline_ms']))
    return result


def A16(ctx):
    config, instance, anchor = bundle(n=4, scene_ids=('X',), shape='diamond')
    deployment = derive_deployment(config, instance, anchor)
    opened = [row['stage_id'] for row in anchor['scenes']['X'][:2]]
    condition = make_condition(config, instance, anchor, deployment, 'X', opened, phase=2)
    protected = inherited_source_check()
    ctx.check(protected['source_builder_matches'], 'original builder hash unchanged')
    ctx.check(protected['numerical_suffix_exact_text'] and protected['numerical_suffix_matches'],
              '238-line numerical suffix is exact original text, not a re-derived surrogate')
    options = _options(instance, anchor, 'X')
    clock = FakeClock(0)
    plain, eplain = replay_rows(config, instance, condition, options,
        G0Budget(100, clock=clock), strengthen=False)
    cut, ecut = replay_rows(config, instance, condition, options,
        G0Budget(100, clock=clock), strengthen=True)
    # This is a 2-open/2-closed fixed-device domain also expressible by old C.
    # It does not call old C: original inherited rows are replayed independently
    # with the same explicit hand options, with/without the existing cut switch.
    ctx.check(plain.names == cut.names and plain.bounds == cut.bounds and
              plain.c == cut.c and plain.integer == cut.integer,
              'same manual domain retains columns, bounds, objective and integrality')
    ctx.check(plain.rows == cut.rows[:len(plain.rows)],
              'existing lower-bound switch leaves every earlier exported row identical')
    ctx.check(len(cut.rows) > len(plain.rows) and cut.energy_bound_certificates,
              'original energy cuts append genuine certificate rows')
    ctx.check(eplain['real_entry_calls'] == ecut['real_entry_calls'] == 0,
              'real Model constructor/build/coefficient/thermal entry sentinels untouched')
    ctx.check(plain.instance['platform'] == instance['platform'] and
              plain.instance['window_ms'] == instance['window_ms'] and
              plain.instance['scenarios'][0]['weight'] == '1',
              'model view preserves physical input and W; local objective unweighted')
    ctx.check(plain.preprocessing['objective_weights'] == {'X': '1'} and
              cut.preprocessing['formal_experiment_result'] is False,
              'source weights/provenance remain explicit and manual')
    # Independent exact box maximum: (1/3)*[0,2] - 1/7 <= 11/21.
    a = cut.var('MANUAL_ROW:a', 0, 2)
    gate = cut.var('MANUAL_ROW:gate', integer=True)
    cut.conditional_le({a: Fraction(1,3)}, Fraction(1,7), gate, 'MANUAL_BIG_M')
    record = cut.rows[-1]
    exact_m = Fraction(11,21)
    actual_m = Fraction(record['big_M'])
    ctx.check(actual_m >= exact_m and actual_m-exact_m < Fraction(1,10**30),
              'outward Big-M encloses independent exact 11/21 box residual')
    # Every rounding export is explicitly covered by its advertised allowance.
    allowance = Fraction(record['rounding_allowance'])
    a_error = abs(Fraction.from_float(record['coef'][a])-Fraction(1,3))*2
    gate_error = abs(Fraction.from_float(record['coef'][gate])-actual_m)
    ctx.check(allowance >= a_error+gate_error,
              'float coefficient deviations over exact variable boxes are covered')
    ctx.check(Fraction.from_float(record['rhs']) >= Fraction(record['rhs_interval'][1])+allowance,
              'exported RHS rounds outward including allowance')
    ctx.check(plain.scenes['X']['events'][0] == 0 and
              plain.scenes['X']['events'][-1] == Fraction(instance['window_ms'])/1000,
              'manual row event horizon covers 0 through original W')
    return {'plain': eplain, 'strengthened': ecut, 'independent_big_M': str(exact_m),
            'exported_big_M': str(actual_m), 'rounding_allowance': str(allowance),
            'comparison_scope': 'manual old-C-expressible fixed-device row domain; no old algorithm run'}


def A19(ctx):
    _, instance, anchor = bundle(n=4, scene_ids=('X', 'Y'))
    view = deepcopy(instance)
    view['scenarios'] = [deepcopy(instance['scenarios'][0])]
    view['scenarios'][0]['weight'] = '1'
    candidate = {'scenes': {'X': deepcopy(anchor['scenes']['X'])}}
    clock = FakeClock(3)
    budget = G0Budget(20, clock=clock)
    clock.advance(2)
    model = SimpleNamespace(instance=view, budget=budget)
    evaluation = {'state':'SAFE', 'rankable_energy':True, 'problem_id':view['id'],
        'evidence_identity':{'input_sha256':_digest(view), 'candidate_sha256':_digest(candidate)},
        'completed_at_elapsed_s':1.0}
    calls = {'complete':0, 'feedback':0}

    def complete(m, c, e, b):
        ctx.check(m is model and c is candidate and b is budget,
                  'model/candidate/root passed intact to completion')
        calls['complete'] += 1
        return {'state':'INITIAL_POINT_READY','x0':[1.0], 'scope':'FAKE_MANUAL_NO_EXPONENTIAL'}

    def feedback(m, c, e):
        calls['feedback'] += 1
        return {'state':'FEEDBACK_ADDED','rows_added':1,'scope':'FAKE_MANUAL_NO_THERMAL'}

    out = prepare_view_initial_point(model, candidate, evaluation, budget, completer=complete)
    ctx.check(out['state'] == 'INITIAL_POINT_READY' and calls['complete'] == 1,
              'matching model-view receipt actually reaches fake completer')
    wrong = deepcopy(evaluation)
    wrong['evidence_identity']['input_sha256'] = _digest(instance)
    ctx.rejects(lambda: prepare_view_initial_point(model,candidate,wrong,budget,completer=complete),
                'original multi-scene receipt cannot stand in for model view')
    wrong = deepcopy(evaluation);wrong['evidence_identity']['candidate_sha256']='wrong'
    ctx.rejects(lambda: prepare_view_initial_point(model,candidate,wrong,budget,completer=complete),
                'candidate identity mismatch rejected before fake completion')
    wrong = deepcopy(evaluation);wrong['problem_id']='other'
    ctx.rejects(lambda: prepare_view_initial_point(model,candidate,wrong,budget,completer=complete),
                'problem identity mismatch rejected')
    ctx.rejects(lambda: prepare_view_initial_point(model,candidate,evaluation,
        G0Budget(20,clock=clock),completer=complete),'different root object rejected')
    for timestamp in (None, -1.0, 3.0, 20.0):
        wrong = deepcopy(evaluation);wrong['completed_at_elapsed_s']=timestamp
        ctx.rejects(lambda e=wrong: prepare_view_initial_point(model,candidate,e,budget,completer=complete),
                    'missing/negative/future/cutoff timestamp rejected')
    with budget.scope('manual-slot', 3.0, kind='slot'):
        clock.advance(1)
        ctx.rejects(lambda: prepare_view_initial_point(model,candidate,evaluation,budget,completer=complete),
                    'expired effective slot cannot complete x0',exceptions=(ScopeExhausted,ValueError))
    violation = deepcopy(evaluation);violation['state']='THERMAL_VIOLATION'
    result = apply_view_feedback(model,candidate,violation,feedback=feedback)
    ctx.check(result['rows_added']==1 and calls['feedback']==1,
              'matching strict model-view identity reaches fake feedback')
    wrong = deepcopy(violation);wrong['evidence_identity']['input_sha256']=_digest(instance)
    ctx.rejects(lambda: apply_view_feedback(model,candidate,wrong,feedback=feedback),
                'wrong full-input envelope never reaches feedback')
    ctx.check(calls == {'complete':1,'feedback':1},'all rejected receipts leave fake counts unchanged')
    ctx.rejects(lambda: prepare_view_initial_point(model,candidate,evaluation,budget),
                'real x0 default is disabled',exceptions=(RuntimeError,))
    ctx.rejects(lambda: apply_view_feedback(model,candidate,violation),
                'real feedback default is disabled',exceptions=(RuntimeError,))
    ctx.rejects(lambda: build_local_model({}, {}, condition={}, budget=budget),
                'real builder entry is disabled before input/backend access',exceptions=(RuntimeError,))
    return {'kind':'MANUAL_MODEL_VIEW_GATE', 'calls':calls, 'real_x0':0,
            'real_feedback':0,'real_builds':0,'thermal_integrations':0}
