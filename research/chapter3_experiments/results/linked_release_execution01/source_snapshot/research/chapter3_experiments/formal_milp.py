"""Shared formal MILP lifecycle and a single-factor heat-feedback ablation.

Both variants inherit the same model flags, constructor, admitted x0, live
candidate recorder, 50-round cap and one absolute method clock.  The only
algorithmic difference is the row added after a certified thermal violation.
No native solver or research workload is run merely by importing this module.
"""
from fractions import Fraction as F
from functools import partial
import time

from diagnostic_search import Recorder
from initial_point import solve_with_initial_witness
from matlab_bridge import (MatlabSession, NUMERICAL_CONSISTENCY_CONFLICT,
                           NUMERICAL_CONSISTENCY_UNRESOLVED)
from milp import (_digest, add_thermal_feedback, build_model, selected_options)
from run_warm_diagnostic import execute_warm
from schedules import validate_schedule
from thermal import Exhausted


FEEDBACK_KINDS = ('conditional', 'assignment')
OUTER_ROUND_LIMIT = 50


def _require_kind(kind):
    if kind not in FEEDBACK_KINDS:
        raise ValueError('feedback_kind must be conditional or assignment')


def _checked_thermal_witnesses(model, candidate, evaluation):
    """Check ownership, legality and strict, timely point evidence, not a tolerance."""
    model.budget.check()
    if evaluation.get('state') != 'THERMAL_VIOLATION' or not evaluation.get('violations'):
        return []
    identity = {'input_sha256': _digest(model.instance),
                'candidate_sha256': _digest(candidate)}
    if evaluation.get('evidence_identity') != identity:
        raise ValueError('thermal feedback receipt identity mismatch')
    checked = validate_schedule(model.instance, candidate)
    if (checked['state'] != 'SCHEDULE_VALID_THERMAL_UNCHECKED'
            or evaluation.get('legality') != checked
            or evaluation.get('problem_id') != model.instance['id']):
        raise ValueError('thermal feedback requires the matching complete legal schedule')
    scenes = {scene['id']: scene for scene in model.instance['scenarios']}
    nodes = model.instance['platform']['node_order']
    end = F(model.instance['window_ms'])/1000
    for witness in evaluation['violations']:
        scene = scenes[witness['scene_id']]
        index = nodes.index(witness['node'])
        low, high = map(F, witness['temperature_degC'])
        limit = F(scene['maximum_temperature_degC'][index])
        formed = witness.get('formed_at_elapsed_s')
        if (F(witness['limit_degC']) != limit or low <= limit or low > high
                or not F(0) <= F(witness['time_s']) <= end
                or not isinstance(formed, (int, float)) or isinstance(formed, bool)
                or not 0 <= formed < model.budget.seconds):
            raise ValueError('thermal feedback lacks a strict in-budget point witness')
    model.budget.check()
    return evaluation['violations']


def add_assignment_feedback(model, candidate, evaluation):
    """Delete each violated scene's complete Stage/mode/start assignment.

    Every scene Stage has one option. Thus sum(selected y) <= N-1 removes
    this full scene schedule only, independently of choices in other scenes.
    A different mode/start in this scene satisfies the row. Auxiliary physical
    vectors for the failed schedule are also removed. A shared deployment is
    never itself excluded: it can admit a different scene schedule.
    """
    witnesses = _checked_thermal_witnesses(model, candidate, evaluation)
    if not witnesses:
        return {'state': 'NO_VALID_EXCLUSION', 'rows_added': 0, 'actions': []}
    before = len(model.rows)
    actions = []
    scenes = {scene['id']: scene for scene in model.instance['scenarios']}
    for sid in dict.fromkeys(witness['scene_id'] for witness in witnesses):
        choices = selected_options(model, candidate, sid)
        expected = len(scenes[sid]['stage_instances'])
        columns = [column for _, column in choices]
        if len(choices) != expected or len(set(columns)) != expected or not expected:
            raise ValueError('scene exclusion must cover each executed Stage exactly once')
        signature = (sid, tuple(sorted(columns)))
        if signature in model.excluded_schedules:
            continue
        model.le({column: 1 for column in columns}, expected-1,
                 'certified_scene_assignment_exclusion')
        model.excluded_schedules.add(signature)
        actions.append({'type': 'scene_assignment_exclusion', 'scene': sid,
                        'selected_option_ids': [option['option_id'] for option, _ in choices],
                        'selected_columns': columns,
                        'scope': 'one complete scene mode/start assignment; not shared deployment'})
    result = {'state': 'FEEDBACK_ADDED' if actions else 'NO_NEW_FEEDBACK',
              'rows_added': len(model.rows)-before, 'actions': actions}
    model.feedback_log.append(result)
    return result


def solve_formal_diagnostic(model, session, accuracy, budget, *,
                            feedback_kind='conditional', max_rounds=OUTER_ROUND_LIMIT,
                            recorder_factory=Recorder):
    """One common outer loop; no variant-specific candidates or initialization."""
    _require_kind(feedback_kind)
    recorder = recorder_factory(model, accuracy, budget, session.workdir.parent)
    session.event_consumer = recorder.poll
    result = {'state': 'UNRESOLVED', 'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'rounds': [], 'feedback': [], 'feedback_kind': feedback_kind,
              'outer_round_limit': max_rounds, 'independently_proven_optimal': False,
              'independently_proven_infeasible': False, 'remaining_domain': 'retained',
              'reason': None}
    try:
        for iteration in range(max_rounds):
            budget.check()
            with budget.phase('matrix_export'):
                solver_input = model.as_solver_dict()
            budget.check()
            with budget.phase('solver_transport_and_solve'):
                returned = session.solve(solver_input, remaining_s=budget.remaining, budget=budget)
            result['rounds'].append(returned)
            budget.check()
            if not returned.get('budget_valid'):
                result['reason'] = 'SOLVER_RETURN_AFTER_BUDGET'; break
            if (returned.get('numerical_consistency') or {}).get('state') == NUMERICAL_CONSISTENCY_CONFLICT:
                result.update(reason=NUMERICAL_CONSISTENCY_UNRESOLVED,
                              numerical_consistency=returned['numerical_consistency'])
                break
            if not returned.get('x'):
                result['reason'] = ('SOLVER_REPORTED_INFEASIBLE' if returned.get('exitflag') == -2
                                    else 'NO_INTEGER_CANDIDATE'); break
            if not returned.get('accepted_for_evaluation'):
                result['reason'] = 'SOLVER_INTERFACE_ERROR'; break
            candidate, evaluation = recorder.assess(returned['x'], f'round{iteration+1}:final')
            if evaluation is None:
                result['reason'] = 'NUMERICAL_CANDIDATE_ANOMALY'; break
            result['evaluation'] = evaluation
            if (evaluation['state'] == 'SAFE' and evaluation.get('rankable_energy')
                    and evaluation.get('completed_at_elapsed_s', budget.seconds) < budget.seconds):
                result['reason'] = ('SAFE_ENGINEERING_CONVERGENCE' if returned.get('exitflag') == 1
                                    else 'SAFE_INCUMBENT')
                break
            if evaluation['state'] != 'THERMAL_VIOLATION':
                result['reason'] = 'EVALUATION_UNRESOLVED'; break
            budget.check()
            with budget.phase('thermal_feedback'):
                # Check the same receipt preconditions for BOTH variants.
                if not _checked_thermal_witnesses(model, candidate, evaluation):
                    feedback = {'state': 'NO_VALID_EXCLUSION', 'rows_added': 0}
                elif feedback_kind == 'conditional':
                    feedback = add_thermal_feedback(model, candidate, evaluation)
                else:
                    feedback = add_assignment_feedback(model, candidate, evaluation)
            feedback['completed_at_elapsed_s'] = budget.elapsed
            feedback['within_budget'] = budget.elapsed < budget.seconds
            result.setdefault('feedback' if feedback['within_budget'] else
                              'late_feedback_diagnostics', []).append(feedback)
            budget.check()
            if not feedback['rows_added']:
                result['reason'] = 'FEEDBACK_UNRESOLVED'; break
        else:
            result['reason'] = 'OUTER_ROUND_LIMIT'
    except Exhausted as error:
        result['reason'] = str(error)
    except MemoryError:
        result['reason'] = 'RESOURCE_LIMIT'
    except Exception as error:
        result.update(reason='INTERFACE_ERROR', error=f'{type(error).__name__}: {error}')
    finally:
        session.event_consumer = None
        result['diagnostic'] = recorder.summary()
        if recorder.best is not None:
            result.update(state='SAFE', safe_candidate=recorder.best['candidate'],
                          safe_upper_bound_J=recorder.best['evaluation']['safe_upper_bound_J'],
                          evaluation=recorder.best['evaluation'])
        result['elapsed_s'] = budget.elapsed
    return result


def execute_formal_milp(input_loader, out, *, seconds,
                        feedback_kind='conditional', clock=time.monotonic,
                        model_builder=build_model, session_factory=MatlabSession,
                        diagnostic_solver=None):
    """Fresh invocation, no shared cache/witness, with a caller-declared budget.

    This entry is prepared for later frozen comparisons. Calling it does not
    itself authorize an experiment list or choose its wall-clock budget.
    """
    _require_kind(feedback_kind)
    selected_solver = solve_formal_diagnostic if diagnostic_solver is None else diagnostic_solver
    solver = partial(solve_with_initial_witness,
        diagnostic_solver=partial(selected_solver, feedback_kind=feedback_kind))
    result = execute_warm(input_loader, out, seconds=seconds, clock=clock,
                          model_builder=model_builder, session_factory=session_factory,
                          solver=solver)
    result.update(feedback_kind=feedback_kind, outer_round_limit=OUTER_ROUND_LIMIT,
                  comparison_role=('full_thermal_feedback' if feedback_kind == 'conditional'
                                   else 'certified_scene_assignment_exclusion_ablation'))
    # execute_warm archived the formed receipt already. These fixed labels
    # carry no newly computed witness, objective or solver evidence.
    import json
    from pathlib import Path
    (Path(out)/'result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return result
