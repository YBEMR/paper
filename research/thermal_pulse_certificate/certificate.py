"""K.33: TP-1 a_n b_c sufficient pulse/gap certificate; no trajectory search."""
from copy import deepcopy
from fractions import Fraction as F
from math import factorial
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'thermal_pressure_precheck'))
import adapter as a

INPUT_SHA = 'b18d3af442ad080243af747fd073f6664f294afbde663a40b691008d96b9b488'
PROOF = HERE.parent / 'thermal_pressure_diagnostic/SUSTAINED_ROUTE.md'


def expected_bundle():
    if a.cp.sha(a.HERE / 'input.json') != INPUT_SHA:
        raise ValueError('approved_TP1_input_hash_changed')
    return a.bundle(a.load(), 'a_n', 'b_c')


def identities():
    out = a.identities()
    for p in [HERE / 'certificate.py', HERE / 'precheck.py', HERE / 'run.py',
              HERE / 'README.md', PROOF]:
        out[str(p.relative_to(a.old.REPO))] = a.cp.sha(p)
    return out


def binding(b):
    return dict(a.joint.binding(b), pulse_sources=identities())


def rational_tree(x):
    if isinstance(x, F):
        return f'{x.numerator}/{x.denominator}'
    if isinstance(x, dict):
        return {k: rational_tree(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rational_tree(v) for v in x]
    return x


def derive(c, semantics, budget):
    """Fail closed to this approved instance, then derive every numerical bound."""
    ref = expected_bundle()
    for key in ['platform', 'fixed_plans']:
        a.v1.require(a.joint.digest(c[key]) == a.joint.digest(ref['candidate'][key]),
                     'unsupported_pulse_' + key)
    a.v1.require(a.joint.digest(semantics) == a.joint.digest(ref['candidate']['semantics']),
                 'unsupported_pulse_semantics')
    a.v1.require(a.joint.digest(c['initial_states']) == a.joint.digest(ref['safety']['initial_states']),
                 'unsupported_pulse_initial_scope')
    # Proof does not use the Cartesian certificate box or instantaneous fragment set.
    a.v1.require(not c.get('witness_requests') and not c.get('thermal_witness'),
                 'use_explicit_counterexample_interface')
    budget.checkpoint('pulse_scope_checked')

    plans, p = c['fixed_plans'], c['platform']
    periods = [F(v['period_us']) / 1000000 for v in plans.values()]
    switches = [F(v['minimum_switch_interval_us']) / 1000000 for v in plans.values()]
    spans = {m: a.v2.span(v) / 1000000 for m, v in plans.items()}
    delay = max(spans.values())
    a.v1.require(2 * delay < min(periods) <= min(switches), 'backlog_induction_not_closed')
    rate = 1 / min(periods) + 1 / min(switches)
    pulse = next(s for s in plans['A']['stages'] if s['unit'] == 'N0')
    duration = F(pulse['duration_us']) / 1000000
    start_gap = min(periods) - delay
    cross_stay_gap = min(switches) - delay
    a.v1.require(start_gap > duration and cross_stay_gap >= start_gap, 'pulse_gap_not_closed')
    per_round = {m: sum((F(s['activity_increment_W']) * F(s['duration_us']) / 1000000
                        for s in v['stages'] if s['unit'] == 'C0'), F(0))
                 for m, v in plans.items()}
    # Releases in any interval h: <= 3 + rate*h. Intersecting work has r >= a-2*delay.
    count_burst = F(4)
    a.v1.require(3 + rate * 2 * delay <= count_burst, 'arrival_burst_not_closed')
    rho, burst = max(per_round.values()) * rate, max(per_round.values()) * count_burst
    theta0 = max(F(s['temperature_box_C'][0][1]) - F(p['ambient_C']) for s in c['initial_states'])
    base_c = max(F(o['base_W']) for o in p['opps']['C0'].values())
    leak_c = max(F(o['leak_W_per_K']) for o in p['opps']['C0'].values())
    decay_c = F(p['G_W_per_K'][0][0]) - leak_c
    coupling = -F(p['G_W_per_K'][0][1])
    forcing_c = base_c + coupling * (F(p['temperature_limit_C'][1]) - F(p['ambient_C']))
    a.v1.require(decay_c > 0 and forcing_c / decay_c <= theta0, 'CPU_comparison_not_closed')
    rise_c = theta0 + rho / decay_c + burst / F(p['C_J_per_K'][0])
    rounded_rise_c = F(16)  # An explicit proved envelope, not a floating-point round-up.
    a.v1.require(rise_c < rounded_rise_c, 'CPU_envelope_not_closed')

    n = p['opps']['N0']['H']
    decay_n = F(p['G_W_per_K'][1][1]) - F(n['leak_W_per_K'])
    thermal_rate = decay_n / F(p['C_J_per_K'][1])
    idle_rise = (F(n['base_W']) + coupling * rounded_rise_c) / decay_n
    a.v1.require(all(F(s['temperature_box_C'][1][1]) - F(p['ambient_C']) <= idle_rise
                     for s in c['initial_states']), 'NPU_initial_envelope_not_closed')
    # e^(.9) < 5/2 via a finite sum and geometric tail; e^(.7) > 2 via a finite sum.
    z = thermal_rate * duration
    exp_upper = sum((z ** k / factorial(k) for k in range(5)), F(0)) + z ** 5 / factorial(5) / (1 - z / 6)
    exp07_lower = sum((F(7, 10) ** k / factorial(k) for k in range(5)), F(0))
    a.v1.require(z == F(9, 10) and exp_upper < F(5, 2), 'pulse_exponential_bound_failed')
    a.v1.require(exp07_lower > 2 and thermal_rate * start_gap > 20 * F(7, 10),
                 'gap_exponential_bound_failed')
    pulse_decay_lower, cycle_decay_upper = F(2, 5), F(1, 2 ** 20)
    rise_n = idle_rise + F(pulse['activity_increment_W']) / decay_n * (1 - pulse_decay_lower) / (1 - cycle_decay_upper)
    upper = [F(p['ambient_C']) + rise_c, F(p['ambient_C']) + rise_n]
    a.v1.require(all(t < F(limit) for t, limit in zip(upper, p['temperature_limit_C'])),
                 'first_hit_contradiction_not_closed')
    budget.checkpoint('pulse_bounds_ready')
    return dict(status='pass', proof='K32 coupled first-hit comparison, release envelope and pulse recurrence',
                scope='all declared initial blocks; t>=0; all real admissible switches; arbitrary dwell',
                round_spans_s=spans, maximum_round_delay_s=delay, release_rate_per_s=rate,
                maximum_pulse_s=duration, minimum_start_gap_s=start_gap,
                minimum_idle_gap_s=start_gap-duration, cross_stay_start_gap_lower_s=cross_stay_gap,
                CPU_activity_per_round_J=per_round, CPU_activity_rho_W=rho, CPU_activity_burst_J=burst,
                CPU_temperature_upper_C=upper[0], CPU_comparison_envelope_C=F(p['ambient_C'])+rounded_rise_c,
                NPU_idle_rise_K=idle_rise, NPU_temperature_upper_C=upper[1],
                temperature_limits_C=list(map(F, p['temperature_limit_C'])),
                exp_pulse_upper=exp_upper, exp07_lower=exp07_lower,
                pulse_decay_lower=pulse_decay_lower, cycle_decay_upper=cycle_decay_upper,
                proof_scope='sufficient for this fixed candidate only; not a feasible-set definition')


def verify_pulse(c, semantics, budget=None):
    budget = budget or a.v2.Budget(seconds=20)
    out = dict(status='unresolved', input_status='unchecked', coverage='incomplete',
               budget_status='within_limit', method='pulse_gap_sufficient', optimality='not_evaluated')
    phase = 'input'
    try:
        budget.checkpoint('pulse_start')
        a.v2.validate(c, semantics)
        out['input_status'] = 'valid'; phase = 'proof'
        deadline = a.v2.deadline_certificate(c, semantics, budget)
        a.v1.require(deadline['status'] == 'pass', 'deadline_not_proved')
        proof = derive(c, semantics, budget)
        budget.checkpoint('before_pulse_commit')
        out.update(status='sustained_safe', coverage='all_declared_processes_certified',
                   deadline=rational_tree(deadline), thermal_certificate=rational_tree(proof))
    except a.v2.Exhausted as exc:
        out.update(budget_status='exhausted', reason=str(exc))
    except (a.v1.Invalid, ValueError, KeyError, TypeError) as exc:
        out.update(reason=str(exc), status='input_invalid' if phase == 'input' else 'unresolved')
    except (MemoryError, ArithmeticError) as exc:
        out.update(reason=type(exc).__name__ + ': ' + str(exc), numerical_or_resource_status='unresolved')
    out['elapsed_s'] = time.monotonic() - budget.start
    return out


def verify_sustained(c, semantics, budget=None):
    """Keep the old box/true-witness outcome; supplement only its unresolved state."""
    budget = budget or a.v2.Budget(seconds=20)
    basic = a.v2.verify(c, semantics, budget)
    if basic['status'] == 'violation':
        return basic  # Already committed real counterexample survives outer interruption.
    if basic['status'] != 'unresolved':
        return basic
    pulse = verify_pulse(c, semantics, budget)
    return dict(pulse, basic_result=basic)


def evaluate_safety_bundle(b, budget=None):
    """Current sustained-safety receipt; energy remains explicitly unavailable."""
    budget = budget or a.v2.Budget(seconds=20)
    out = dict(id=b.get('id'), status='unresolved', budget_status='within_limit',
               certified_candidate_energy={'status': 'unavailable', 'reason': 'safety_only_no_energy_evaluation'})
    try:
        a.joint.validate_bundle(b, budget)
        bind = binding(b)
        out['binding'] = bind
        s = verify_sustained(a.joint.safety_input(b), b['candidate']['semantics'], budget)
        if s['status'] == 'violation':
            out.update(status='candidate_violation', safety_receipt=a.joint.receipt('sustained_safety', bind, s))
        budget.checkpoint('safety_receiver')
        out.update(status='certified_safety_only' if s['status'] == 'sustained_safe' else out['status'],
                   safety_receipt=a.joint.receipt('sustained_safety', bind, s))
        budget.checkpoint('before_safety_receiver_commit')
    except a.v2.Exhausted as exc:
        if out['status'] != 'candidate_violation':
            out['status'] = 'unresolved'; out.pop('safety_receipt', None)
        out.update(budget_status='exhausted', reason=str(exc))
    except (a.v1.Invalid, KeyError, ValueError, TypeError) as exc:
        out.update(status='input_invalid', reason=str(exc))
    except (MemoryError, ArithmeticError) as exc:
        if out['status'] != 'candidate_violation':
            out['status'] = 'unresolved'; out.pop('safety_receipt', None)
        out.update(reason=type(exc).__name__ + ': ' + str(exc))
    out['elapsed_s'] = time.monotonic() - budget.start
    return out
