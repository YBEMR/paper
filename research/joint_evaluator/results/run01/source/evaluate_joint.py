"""One fixed candidate, finite U1 energy and sustained V2 safety. No optimizer."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'v2_evaluator'))
import verify as v2
v1 = v2.v1
from run_v1 import aggregate_energy


def canonical(x):
    """Typed, exact numeric identity: 12 == 12.0, but '12' is a string."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return [type(x).__name__, x]
    if isinstance(x, (int, Decimal, F)):
        q = F(x)
        return ['rational', q.numerator, q.denominator]
    if isinstance(x, dict):
        return ['dict', [[k, canonical(x[k])] for k in sorted(x)]]
    if isinstance(x, list):
        return ['list', [canonical(v) for v in x]]
    raise v1.Invalid('unsupported_identity_type: ' + type(x).__name__)


def digest(x):
    return hashlib.sha256(json.dumps(canonical(x), ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def sources():
    return {'evaluate_joint.py': Path(__file__),
            'v2_verify.py': ROOT.parent / 'v2_evaluator/verify.py',
            'v1_evaluate.py': ROOT.parent / 'v1_evaluator/evaluate.py',
            'v1_interval.py': ROOT.parent / 'v1_evaluator/interval.py',
            'v1_run_v1.py': ROOT.parent / 'v1_evaluator/run_v1.py'}


def binding(b):
    return dict(candidate_sha256=digest(b['candidate']),
                safety_scope_sha256=digest(b['safety']['initial_states']),
                safety_analysis_sha256=digest(b['safety']),
                evaluation_sha256=digest(b['evaluation']),
                source_sha256={k: hashlib.sha256(p.read_bytes()).hexdigest()
                               for k, p in sources().items()})


def require(ok, reason):
    v1.require(ok, reason)


def safety_input(b):
    c = deepcopy(b['candidate'])
    c.pop('semantics')
    c.update(deepcopy(b['safety']))
    c['id'] = b['id']
    return c


def validate_bundle(b, budget):
    v2.exact_numbers(b)
    require(set(b) <= {'id', 'candidate', 'safety', 'evaluation', 'provenance'}
            and {'id', 'candidate', 'safety', 'evaluation'} <= set(b), 'bundle_fields')
    require(set(b['candidate']) == {'platform', 'fixed_plans', 'semantics'}, 'single_candidate_required')
    require(set(b['safety']) <= {'initial_states', 'certificate_box_C', 'fragment_superset',
                                'witness_requests', 'thermal_witness'}
            and {'initial_states', 'certificate_box_C', 'fragment_superset'} <= set(b['safety']),
            'safety_fields_no_candidate_override')
    require(set(b['evaluation']) == {'paths', 'weights', 'accuracy', 'window_policy'},
            'evaluation_fields_no_candidate_override')
    require(b['evaluation']['window_policy'] == 'W1 common window; full deadlines; endpoint release excluded', 'unsupported_window_policy')
    c = safety_input(b)
    v2.validate(c, b['candidate']['semantics'])
    require(b['candidate']['semantics']['release_at_window_end'] == 'excluded; no shutdown implied', 'window_endpoint_semantics')
    paths, weights = b['evaluation']['paths'], b['evaluation']['weights']
    require(bool(paths) and len(paths) == len(weights), 'path_weight_count')
    require(all(F(w) >= 0 for w in weights) and sum(map(F, weights)) == 1, 'weights_nonnegative_sum_one')
    ids = [p['trace']['id'] for p in paths]
    require(len(set(ids)) == len(ids), 'duplicate_path_id')
    require(len({F(p['trace']['window_us']) for p in paths}) == 1, 'W1_common_window_required')
    acc = b['evaluation']['accuracy']
    require(Decimal(acc['temperature_enclosure_width_C']) > 0
            and Decimal(acc['energy_enclosure_width_J']) > 0, 'accuracy_target')
    membership = []
    for p in paths:
        budget.check()
        require(set(p) == {'entry_state', 'trace'}, 'path_fields')
        entry, tr = p['entry_state'], p['trace']
        require(set(entry) == set(c['initial_states'][0]), 'complete_entry_state_required')
        require(set(tr) == {'id', 'initial_mode', 'initial_release_us', 'initial_temperature_C',
                            'initial_opps', 'initial_unfinished_work', 'switch_requests', 'window_us'},
                'trace_fields')
        temps = entry['temperature_box_C']
        require(all(len(t) == 2 and t[0] == t[1] for t in temps), 'finite_energy_needs_point_entry')
        matches = []
        for k, declared in enumerate(c['initial_states']):
            discrete = all(entry[key] == declared[key] for key in declared if key != 'temperature_box_C')
            contained = len(temps) == len(declared['temperature_box_C']) and all(
                lo <= a <= z <= hi for (a, z), (lo, hi) in zip(temps, declared['temperature_box_C']))
            if discrete and contained:
                matches.append(k)
        require(bool(matches), 'energy_entry_outside_safety_scope:' + tr['id'])
        require(tr['initial_mode'] == entry['actual_mode']
                and tr['initial_opps'] == entry['held_opps']
                and tr['initial_temperature_C'] == [t[0] for t in temps]
                and tr['initial_unfinished_work'] == entry['unfinished_work']
                and tr['initial_release_us'] == entry['next_release_us'], 'trace_entry_mismatch:' + tr['id'])
        # Checks all transition times/edges and every released deadline against W1.
        # A deadline violation in the resulting schedule is valid input, not a scope error.
        v1.expand(b['candidate'], tr, budget)
        membership.append(dict(trace_id=tr['id'], matching_entry_blocks=matches,
                               transitions_and_window='valid', scope='finite path included in declared process domain'))
    budget.checkpoint('input_validated')
    return membership


def receipt(kind, bind, result):
    return dict(kind=kind, binding=deepcopy(bind), result=result)


def assemble(b, bind, energy, safety, membership):
    """Private run receipts only; no disk cache or historical-result import."""
    rejected = dict(status='identity_mismatch', certified_candidate_energy={
        'status': 'unavailable', 'reasons': ['input_or_source_identity_mismatch']})
    if binding(b) != bind or energy['binding'] != bind or safety['binding'] != bind:
        return rejected
    if energy['kind'] != 'finite_energy' or safety['kind'] != 'sustained_safety':
        return rejected
    e, s = energy['result'], safety['result']
    reasons = []
    if s['status'] != 'sustained_safe':
        reasons.append('sustained_status:' + s['status'])
    if e['aggregate']['status'] != 'valid':
        reasons.append('finite_paths_not_all_complete_valid')
    # Independent interfaces disagreeing is an anomaly, not a ranked candidate.
    finite_violation = any(r.get('execution_status') == 'deadline_violation'
                           or r.get('thermal', {}).get('known_violations') for r in e['traces'].values())
    conflict = s['status'] == 'sustained_safe' and finite_violation
    if conflict:
        reasons.append('safety_certificate_vs_contained_path_conflict')
    objective = dict(status='unavailable', reasons=reasons)
    if not reasons:
        objective = dict(status='available', energy_J=e['aggregate']['energy_J'],
                         meaning='U1 weighted finite-window energy of a sustained-certified fixed candidate')
    status = ('evidence_conflict' if conflict else 'certified_candidate' if not reasons
              else 'candidate_violation' if s['status'] == 'violation' or finite_violation
              else 'unresolved')
    return dict(id=b['id'], status=status, binding=bind, membership=membership,
                sustained_safety=s, finite_path_energy=e, certified_candidate_energy=objective,
                optimality='not_evaluated', refined_layer='not_implemented')


def evaluate_bundle(bundle, budget=None):
    budget = budget or v2.Budget()
    out = dict(id=bundle.get('id'), status='unresolved', certified_candidate_energy={'status': 'unavailable'},
               budget_status='within_limit', safety_receipt=None, energy_receipt=None)
    phase = 'input'
    try:
        budget.checkpoint('start')
        b = deepcopy(bundle)
        membership = validate_bundle(b, budget)
        bind = binding(b); out.update(binding=bind, membership=membership)
        phase = 'evaluation'
        s = v2.verify(safety_input(b), b['candidate']['semantics'], budget)
        budget.checkpoint('safety_returned')
        safety = receipt('sustained_safety', bind, s)
        out['safety_receipt'] = safety
        if s['status'] == 'violation':
            out['status'] = 'candidate_violation'
        x = deepcopy(b['candidate']); x['accuracy'] = b['evaluation']['accuracy']
        traces = {}
        for p in b['evaluation']['paths']:
            budget.checkpoint('before_path')
            r = v1.evaluate_trace(x, p['trace'], budget)
            budget.checkpoint('path_returned')
            traces[p['trace']['id']] = r
            out['partial_traces'] = deepcopy(traces)
            if r.get('execution_status') == 'deadline_violation' or r.get('thermal', {}).get('known_violations'):
                out['status'] = 'candidate_violation'
        probe = dict(trace_ids=[p['trace']['id'] for p in b['evaluation']['paths']], weights=b['evaluation']['weights'])
        aggregate = aggregate_energy(probe, traces)
        aggregate['scope'] = 'specified U1 paths only; not steady-state or all-process mean energy'
        budget.checkpoint('energy_ready')
        energy = receipt('finite_energy', bind, dict(traces=traces, aggregate=aggregate))
        out['energy_receipt'] = energy
        budget.checkpoint('before_assembly')
        combined = assemble(b, bind, energy, safety, membership)
        budget.checkpoint('before_commit')
        out = dict(combined, budget_status='within_limit')
    except v2.Exhausted as exc:
        out.update(reason=str(exc), budget_status='exhausted')
    except (MemoryError, ArithmeticError) as exc:
        out.update(reason=type(exc).__name__ + ': ' + str(exc), numerical_or_resource_status='unresolved')
    except (v1.Invalid, KeyError, ValueError, TypeError) as exc:
        out.update(reason=str(exc), status='input_invalid' if phase == 'input' else 'unresolved')
    # Receipts retain verified evidence on interruption, but no candidate energy is issued.
    out['diagnostic'] = dict(elapsed_s=time.monotonic()-budget.start,
                             fragments=budget.fragments, panels=budget.panels,
                             peak_refinements=budget.refinements)
    return out
