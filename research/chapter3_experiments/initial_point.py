"""Bounded initial witnesses, numerical completion, and optional MILP entry.

Construction, complete SAFE evaluation and numerical x0 admission are three
separate receipts. Floating matrix-exponential completion proposes values;
it proves neither continuous thermal safety nor mathematical feasibility.
No historical candidate, solver answer, or thermal cache is read here.
"""
from contextlib import nullcontext
from fractions import Fraction as F

import numpy as np
from scipy.linalg import expm

from initial_schedule import iter_initial_candidates
from matlab_bridge import _prepare, InitialPointRejected
from milp import decode, selected_options, evaluate_model_candidate, _digest
from thermal import Exhausted


def _phase(budget, name):
    return getattr(budget, 'phase', lambda _: nullcontext())(name)


def _key(candidate):
    return tuple((sid, tuple(sorted((r['stage_id'], r['unit'], r['opp'],
                                    str(F(r['start_ms']))) for r in rows)))
                 for sid, rows in sorted(candidate['scenes'].items()))


def _propose_vector(model, candidate, budget):
    """Budgeted nominal physical lift, followed by separate admission checks."""
    p = model.instance['platform']; nodes = p['node_order']; n = len(nodes)
    units = {u['id']: u for u in p['units']}
    vector = np.zeros(len(model.names))
    selected = {sid: selected_options(model, candidate, sid) for sid in model.scenes}
    shared = {}
    for choices in selected.values():
        budget.check()
        for option, y in choices:
            vector[y] = 1
            shared[option['shared_stage_id']] = option['unit_id']
    for (stage, unit), column in model.shared.items():
        vector[column] = int(shared.get(stage) == unit)
    ambient = float(F(p['ambient_temperature_degC']))
    reference = float(F(p['reference_temperature_degC']))
    capacity = np.array([float(F(v)) for v in p['heat_capacity_J_per_K']])
    conductance = np.array([[float(F(v)) for v in row] for row in p['conductance_W_per_K']])
    for scene in model.instance['scenarios']:
        budget.check()
        sid = scene['id']; meta = model.scenes[sid]; choices = selected[sid]
        if not meta['theta']:
            raise ValueError('Initial physical point requires the complete thermal-energy model')
        held = dict(scene['entry']['domain_opp'])
        theta = np.array([float(F(t)) for t in scene['entry']['temperature_degC']])-ambient
        vector[meta['theta'][0]] = theta
        for l, (left, right) in enumerate(zip(meta['events'], meta['events'][1:])):
            budget.check()
            active = [o for o, _ in choices if F(o['start_ms'])/1000 <= left < F(o['end_ms'])/1000]
            for domain_id, domain in p['domains'].items():
                starting = [o for o, _ in choices if units[o['unit_id']]['domain_id'] == domain_id
                            and F(o['start_ms'])/1000 == left]
                if starting:
                    held[domain_id] = starting[0]['opp_id']
                vector[meta['start_indicators'][l, domain_id]] = int(bool(starting))
                for opp in domain['opps']:
                    vector[meta['rho'][l, domain_id, opp]] = int(held[domain_id] == opp)
            state = tuple(held[d] for d in p['domains'])
            for possible in meta['states'][l]:
                vector[meta['joint'][l, possible]] = int(state == possible)
            q = [sum((F(o['activity_power_W']) for o in active
                      if units[o['unit_id']]['thermal_node_id'] == node), F(0)) for node in nodes]
            vector[meta['q'][l]] = list(map(float, q))
            base = np.zeros(n); slopes = np.zeros(n)
            for domain_id, domain in p['domains'].items():
                opp = held[domain_id]
                base += float(F(domain['baseline_W'][opp]))*np.array(
                    [float(F(v)) for v in domain['baseline_heat_distribution']])
                for unit in domain['unit_ids']:
                    slopes[nodes.index(units[unit]['thermal_node_id'])] += float(
                        F(domain['local_temperature_slope_W_per_K'][opp]))
            matrix = np.zeros((n+2, n+2))
            matrix[:n, :n] = (np.diag(slopes)-conductance)/capacity[:, None]
            matrix[:n, -1] = (base+np.array(list(map(float, q)))+slopes*(ambient-reference))/capacity
            matrix[n, :n] = slopes
            matrix[n, -1] = (sum(base)+sum(map(float, q))+sum(slopes)*(ambient-reference)
                             +float(F(p['external_common_power_W'])))
            evolved = expm(matrix*float(right-left)) @ np.r_[theta, 0.0, 1.0]
            budget.check()
            theta = evolved[:n]
            vector[meta['theta'][l+1]] = theta
            vector[meta['energy'][l]] = evolved[n]
    budget.check()
    return vector


def complete_initial_point(model, candidate, evaluation, budget):
    """Propose and check a full vector for an already independently SAFE schedule."""
    budget.check()
    identity = {'input_sha256': _digest(model.instance), 'candidate_sha256': _digest(candidate)}
    if (evaluation.get('state') != 'SAFE' or not evaluation.get('rankable_energy')
            or evaluation.get('evidence_identity') != identity
            or evaluation.get('completed_at_elapsed_s', budget.seconds) >= budget.seconds):
        raise ValueError('A matching complete in-budget SAFE receipt is required before x0 completion')
    try:
        with _phase(budget, 'initial_point_completion'):
            vector = _propose_vector(model, candidate, budget)
        with _phase(budget, 'initial_point_decode_and_row_admission'):
            decoded = decode(model, vector)
            if _key(decoded) != _key(candidate):
                raise ValueError('Initial vector does not decode to its SAFE schedule')
            payload = _prepare(model.as_solver_dict(), x0=vector)
        budget.check()
    except InitialPointRejected as error:
        return {'state': 'INITIAL_POINT_REJECTED', 'x0': None,
                'reason': str(error), 'numerical_acceptance': error.diagnostics,
                'decoded_roundtrip': True, 'completed_at_s': budget.elapsed}
    except ValueError as error:
        return {'state': 'INITIAL_POINT_REJECTED', 'x0': None, 'reason': str(error),
                'decoded_roundtrip': False, 'completed_at_s': budget.elapsed}
    return {'state': 'INITIAL_POINT_READY', 'x0': vector,
            'numerical_acceptance': payload['x0_validation'],
            'decoded_roundtrip': True, 'completed_at_s': budget.elapsed,
            'scope': 'numerical row admission only; SAFE comes from the independent receipt'}


def prepare_initial_witness(model, accuracy, budget, starts=None, max_attempts=3):
    """Stop at first complete SAFE seed; keep it even when vector completion fails."""
    out = {'state': 'UNRESOLVED', 'witness': None, 'x0': None,
           'attempts': [], 'completion': None, 'reason': 'NO_SAFE_INITIAL_WITNESS',
           'remaining_domain': 'retained', 'independently_proven_infeasible': False}
    try:
        iterator = iter_initial_candidates(model.instance, starts, budget, max_attempts)
        while True:
            with _phase(budget, 'initial_schedule_construction'):
                try:
                    attempt = next(iterator)
                except StopIteration:
                    break
            attempt['schedule_completed_at_s'] = budget.elapsed
            out['attempts'].append(attempt)
            if attempt['status'] != 'COMPLETE_LEGAL_CANDIDATE':
                continue
            with _phase(budget, 'initial_continuous_evaluation'):
                evaluation = evaluate_model_candidate(model, attempt['candidate'], accuracy, budget)
            attempt['evaluation'] = evaluation
            safe = (evaluation.get('state') == 'SAFE' and evaluation.get('rankable_energy')
                    and evaluation.get('safe_upper_bound_J') is not None
                    and evaluation.get('completed_at_elapsed_s', budget.seconds) < budget.seconds)
            if not safe:
                budget.check()
                continue
            out['witness'] = {'candidate': attempt['candidate'], 'evaluation': evaluation,
                              'schedule_completed_at_s': attempt['schedule_completed_at_s']}
            completion = complete_initial_point(model, attempt['candidate'], evaluation, budget)
            out['x0'] = completion.pop('x0')
            out['completion'] = completion
            out.update(state=('SAFE_POINT_READY' if out['x0'] is not None else 'SAFE_POINT_REJECTED'),
                       reason=completion['state'])
            break
    except Exhausted as error:
        out.update(state='SAFE_POINT_UNRESOLVED' if out['witness'] else 'UNRESOLVED',
                   reason=str(error))
    except Exception as error:
        out.update(state='SAFE_POINT_REJECTED' if out['witness'] else 'UNRESOLVED',
                   reason=type(error).__name__+': '+str(error))
    out['completed_at_s'] = budget.elapsed
    return out


class _InitialSession:
    """Inject this call's admitted x0 once, without constraining later rounds."""
    def __init__(self, session, x0):
        self.session, self.x0, self.first = session, x0, True
        self.workdir = session.workdir

    @property
    def event_consumer(self):
        return self.session.event_consumer

    @event_consumer.setter
    def event_consumer(self, value):
        self.session.event_consumer = value

    def solve(self, model, **kwargs):
        if self.first:
            self.first = False
            return self.session.solve(model, x0=self.x0, **kwargs)
        return self.session.solve(model, **kwargs)


def solve_with_initial_witness(model, session, accuracy, budget, starts=None, max_attempts=3,
                               checkpoint=None):
    """Complete operational entry; all initialization uses this method's budget."""
    initial = prepare_initial_witness(model, accuracy, budget, starts, max_attempts)
    public = {k: v for k, v in initial.items() if k != 'x0'}
    witness = initial['witness']
    checkpoint_status = {'requested': checkpoint is not None, 'completed': False}
    if checkpoint is not None:
        try:
            with _phase(budget, 'initial_receipt_checkpoint'):
                checkpoint(public)
            checkpoint_status.update(completed=True, completed_at_s=budget.elapsed)
        except Exception as error:
            checkpoint_status.update(error=type(error).__name__+': '+str(error),
                                     completed_at_s=budget.elapsed)
    result = {'state': 'UNRESOLVED', 'safe_candidate': None, 'safe_upper_bound_J': None,
              'evaluation': None, 'reason': initial['reason'], 'rounds': [], 'feedback': [],
              'independently_proven_optimal': False, 'independently_proven_infeasible': False,
              'remaining_domain': 'retained', 'solver_diagnostic': None}
    if initial['state'] == 'SAFE_POINT_READY' and budget.remaining > 0:
        from diagnostic_search import solve_diagnostic
        try:
            solved = solve_diagnostic(model, _InitialSession(session, initial['x0']), accuracy, budget)
        except Exception as error:
            solved = {'state': 'UNRESOLVED', 'safe_upper_bound_J': None,
                      'reason': 'INITIALISED_SOLVER_INTERRUPTED' if isinstance(error, Exhausted)
                                else 'INITIALISED_SOLVER_INTERFACE_ERROR',
                      'error': type(error).__name__+': '+str(error),
                      'independently_proven_optimal': False,
                      'independently_proven_infeasible': False}
        result.update(solved)
        result['solver_diagnostic'] = solved
    milp_upper = result.get('safe_upper_bound_J')
    milp_evaluation = result.get('evaluation')
    result['safe_solution_source'] = 'MILP_candidate' if milp_upper is not None else None
    if witness and (milp_upper is None or F(witness['evaluation']['safe_upper_bound_J']) <= F(milp_upper)):
        result.update(state='SAFE', safe_candidate=witness['candidate'],
                      safe_upper_bound_J=witness['evaluation']['safe_upper_bound_J'],
                      evaluation=witness['evaluation'], safe_solution_source='initial_constructor')
    result.update(initialisation=public, milp_safe_upper_bound_J=milp_upper,
                  initial_checkpoint=checkpoint_status,
                  initial_safe_upper_bound_J=witness['evaluation']['safe_upper_bound_J'] if witness else None,
                  first_initial_safe_s=witness['evaluation']['completed_at_elapsed_s'] if witness else None,
                  elapsed_s=budget.elapsed,
                  attribution='initial constructor and subsequent MILP progress are recorded separately')
    result['milp_improved_initial_upper_bound'] = bool(witness and milp_upper is not None
        and F(milp_upper) < F(witness['evaluation']['safe_upper_bound_J']))
    before = witness['evaluation'].get('weighted_energy_J') if witness else None
    after = milp_evaluation.get('weighted_energy_J') if milp_evaluation else None
    result['strict_energy_improvement_certified'] = bool(before and after
        and F(after[1]) < F(before[0]))
    return result
