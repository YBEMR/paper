"""TP-1 input and evidence adapters. No research diagnostic is run here."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import itertools
import math
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'thermal_history_diagnostic'))
import diagnostic as old

cp, joint, v1, v2 = old.cp, old.joint, old.v1, old.v2
SOURCE = HERE.parent / 'thermal_history_diagnostic/input.json'
SOURCE_SHA = '6cc32e35b787d12d94af6182fa987b9025e4030a0aee8187d70bb549f537e707'


def load():
    x = old.read(HERE / 'input.json')
    if cp.sha(SOURCE) != SOURCE_SHA:
        raise ValueError('historical_input_changed')
    expected = deepcopy(old.read(SOURCE)['problem'])
    expected['platform']['C_J_per_K'] = [F(1, 50), F(1, 50000)]
    expected['platform']['G_W_per_K'] = [[F(21, 200), F(-1, 200)], [F(-1, 200), F(1, 50)]]
    for mode in expected['modes'].values():
        for stage in mode['stages']:
            for option in stage['options']:
                if option['unit'] == 'N0':
                    option['activity_increment_W'] = 1
    if joint.digest(expected) != joint.digest(x['problem']):
        raise ValueError('unapproved_problem_change')
    if x['version'] != 'TP-1' or x['historical_input_sha256'] != SOURCE_SHA:
        raise ValueError('input_identity')
    return x


def bundle(x, a, b):
    out = old.candidate(x, a, b)
    c = joint.safety_input(out)
    _, possible = v2.domain_info(c)
    units, choices = v2.fragment_options(c, possible)
    out['safety']['fragment_superset'] = [
        dict(held_opps={u: pair[0] for u, pair in zip(units, key)},
             activity_W={u: pair[1] for u, pair in zip(units, key)})
        for key in itertools.product(*choices)]
    out['safety']['certificate_box_C'] = [[25, 50], [25, 50]]
    out['safety'].pop('witness_requests', None)
    out['safety'].pop('thermal_witness', None)
    return out


def proof_only(b):
    return v2.verify(joint.safety_input(b), b['candidate']['semantics'], v2.Budget(seconds=20))


def thermal(p, initial, segments, accuracy, budget):
    """Identical constant-state intervals, subdivided with norm*h <= 1/4.

    The old panel_count can hit its 1/2 boundary after Decimal rounding.
    This local wrapper leaves the physical event times and old sources intact.
    Preparation is charged to the same caller budget.
    """
    refined = []
    for seg in segments:
        budget.check()
        matrix = v1.coeff_matrix(p, seg)
        upper_norm = max(sum(F(v.magnitude) for v in row) for row in matrix)
        duration = F(seg['end_us'])-F(seg['start_us'])
        count = max(1, math.ceil(4*upper_norm*duration/1000000))
        for k in range(count):
            budget.check()
            part = deepcopy(seg)
            part['start_us'] = F(seg['start_us'])+duration*k/count
            part['end_us'] = F(seg['start_us'])+duration*(k+1)/count
            refined.append(part)
    return v1.thermal(p, initial, refined, accuracy, budget)


def single_mode_path(b, mode):
    """Bind the requested mode to its own declared entry, never entry zero."""
    entry = next(deepcopy(e) for e in b['safety']['initial_states']
                 if e['actual_mode'] == mode and e['held_opps'] == {'C0': 'H', 'N0': 'H'})
    entry['temperature_box_C'] = [[30, 30], [30, 30]]
    tr = dict(id=mode+'_only', initial_mode=mode, initial_release_us=entry['next_release_us'],
              initial_temperature_C=[30, 30], initial_opps=deepcopy(entry['held_opps']),
              initial_unfinished_work=[], switch_requests=[], window_us=80000)
    return dict(entry_state=entry, trace=tr)


def validate_probe(b, path):
    probe = deepcopy(b)
    probe['evaluation']['paths'] = [path]
    probe['evaluation']['weights'] = [1]
    return joint.validate_bundle(probe, v2.Budget(seconds=20))


def finite_evidence(result):
    """Internal evaluator receipt only; no promotion to sustained safety."""
    thermal = result.get('thermal', {})
    witness = deepcopy(thermal.get('known_violations', []))
    deadline = result.get('failure') if result.get('execution_status') == 'deadline_violation' else None
    valid = result.get('input_status') == 'valid'
    safe = (valid and result.get('execution_status') == 'valid'
            and result.get('rankable_energy') is True and thermal.get('complete') is True
            and thermal.get('precision_met') is True and thermal.get('status') == 'safe'
            and 'energy_J' in thermal)
    out = dict(status='violation' if valid and (witness or deadline) else 'finite_safe' if safe else 'unresolved',
               sustained_safety='not_inferred', known_violations=witness if valid else [],
               deadline_failure=deadline if valid else None)
    if safe:
        out['safe_energy_J'] = deepcopy(thermal['energy_J'])
    # Complete unsafe energies may be diagnostic, but never a safe score.
    if valid and thermal.get('complete') is True and 'energy_J' in thermal:
        out['diagnostic_energy_J'] = deepcopy(thermal['energy_J'])
    return out


def aggregate(results, weights, sustained_status):
    if len(results) != len(weights) or not results or any(F(w) < 0 for w in weights) or sum(map(F, weights)) != 1:
        raise ValueError('weight_contract')
    evidence = [finite_evidence(r) for r in results]
    if sustained_status != 'sustained_safe' or any(e['status'] != 'finite_safe' for e in evidence):
        return dict(status='not_aggregable', reason='sustained_certificate_or_complete_safe_paths_missing', paths=evidence)
    energy = sum((v1.I(*e['safe_energy_J'])*v1.I.rational(F(w)) for e, w in zip(evidence, weights)), v1.I(0))
    return dict(status='valid_safe_U1', energy_J=energy.data(), paths=evidence)


def identities():
    paths = [HERE/'input.json', HERE/'adapter.py', HERE/'precheck.py', SOURCE,
             old.SOURCE, Path(old.__file__), Path(cp.__file__)] + list(joint.sources().values())
    return {str(p.relative_to(old.REPO)): cp.sha(p) for p in paths}
