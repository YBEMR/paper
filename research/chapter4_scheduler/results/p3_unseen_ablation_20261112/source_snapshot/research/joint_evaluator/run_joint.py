"""Integration prechecks; separate immutable outputs, no parameter tuning."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch

import evaluate_joint as j

ROOT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    with p.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, default=j.v1.encode)
        f.write('\n')


def short(r):
    return {k: r[k] for k in ['status', 'reason', 'budget_status', 'certified_candidate_energy'] if k in r}


def precheck(output):
    output.mkdir(parents=True, exist_ok=False)
    src = j.sources() | {'run_joint.py': Path(__file__)}
    source_hashes = {k: sha(p) for k, p in src.items()}
    oldfiles = [p for folder in ['v1_precheck_draft', 'v2_precheck_draft', 'v1_evaluator', 'v2_evaluator']
                for p in (ROOT.parent / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    originals = {str(p.relative_to(ROOT.parent)): sha(p) for p in oldfiles}
    (output / 'source').mkdir()
    for k, p in src.items():
        (output / 'source' / k).write_bytes(p.read_bytes())
    for k in ['inputs.json', 'expected.json']:
        (output / k).write_bytes((ROOT / k).read_bytes())
    package = j.v1.load(ROOT / 'inputs.json')
    cases = {b['id']: b for b in package['cases']}
    checks, derived = [], {}

    def check(name, condition, details=None):
        checks.append(dict(name=name, passed=bool(condition), details=details))

    results = {}
    # Compute actual results before reading expected statuses.
    for name, b in cases.items():
        r = j.evaluate_bundle(b)
        results[name] = r
        save(output / (name + '.json'), r)
        print(name, r['status'], flush=True)
    expected = j.v1.load(ROOT / 'expected.json')
    for name, e in expected.items():
        r = results[name]
        check(name + '_status_contract', r['status'] == e['status']
              and r.get('sustained_safety', {}).get('status') == e['safety']
              and r.get('finite_path_energy', {}).get('aggregate', {}).get('status') == e['aggregate']
              and r['certified_candidate_energy']['status'] == e['objective'])
        check(name + '_unavailable_has_no_candidate_energy', e['objective'] == 'available'
              or 'energy_J' not in r['certified_candidate_energy'])

    b14, b12 = cases['J14'], cases['J12']
    r14, r12 = results['J14'], results['J12']
    check('12_vs_14_distinct_identity', r14['binding']['candidate_sha256'] != r12['binding']['candidate_sha256'])
    check('same_two_paths_can_have_same_energy_but_different_sustained_status',
          r14['finite_path_energy']['aggregate']['energy_J'] == r12['finite_path_energy']['aggregate']['energy_J']
          and r14['status'] != r12['status'])
    check('prefix_energy_never_aggregated', 'energy_J' not in results['J12_late']['finite_path_energy']['aggregate']
          and results['J12_late']['finite_path_energy']['traces']['F3']['energy_scope'] == 'prefix_to_failed_deadline')
    check('deadline_changes_same_F3_finish_not_release',
          results['J12_late']['finite_path_energy']['traces']['F3']['failure']['lateness_us'] == 1000
          and any(q['finish_us'] == 54000 and q['deadline_us'] == 55000
                  for q in results['J14_late']['finite_path_energy']['traces']['F3']['requests']))

    def receipts(r):
        return (j.receipt('finite_energy', r['binding'], r['finite_path_energy']),
                j.receipt('sustained_safety', r['binding'], r['sustained_safety']))
    e14, s14 = receipts(r14); e12, s12 = receipts(r12)
    for name, b, r, e, s in [('cross_12_energy_14_certificate', b12, r12, e12, s14),
                              ('cross_14_energy_12_certificate', b14, r14, e14, s12)]:
        mixed = j.assemble(b, r['binding'], e, s, r['membership'])
        check(name, mixed['status'] == 'identity_mismatch' and 'energy_J' not in mixed['certified_candidate_energy'])
        derived[name] = mixed

    # Every relevant identity dimension must prevent stale receipt reuse.
    mutations = {
        'deadline_only': lambda b: b['candidate']['fixed_plans']['A'].__setitem__('relative_deadline_us', 12000),
        'activity_power': lambda b: b['candidate']['fixed_plans']['A']['stages'][0].__setitem__('activity_increment_W', 1),
        'duration': lambda b: b['candidate']['fixed_plans']['A']['stages'][0].__setitem__('duration_us', 1000),
        'mapping': lambda b: b['candidate']['fixed_plans']['A']['stages'][0].__setitem__('unit', 'N0'),
        'shared_domain': lambda b: b['candidate']['platform']['units']['C0'].__setitem__('frequency_domain', 'DN'),
        'RC': lambda b: b['candidate']['platform']['C_J_per_K'].__setitem__(0, D('0.03')),
        'semantics': lambda b: b['candidate']['semantics'].__setitem__('temperature_continuity', False),
        'initial_scope': lambda b: b['safety']['initial_states'][0]['temperature_box_C'][0].__setitem__(1, 34),
        'certificate': lambda b: b['safety']['certificate_box_C'][0].__setitem__(1, 58),
        'weights': lambda b: b['evaluation'].__setitem__('weights', [D('0.4'), D('0.6')]),
        'path': lambda b: b['evaluation']['paths'][0]['trace']['switch_requests'][0].__setitem__('time_us', 46000),
        'window': lambda b: b['evaluation']['paths'][0]['trace'].__setitem__('window_us', 81000),
        'accuracy': lambda b: b['evaluation']['accuracy'].__setitem__('energy_enclosure_width_J', D('0.000000001'))}
    for name, mutate in mutations.items():
        b = deepcopy(b14); mutate(b)
        r = j.assemble(b, r14['binding'], e14, s14, r14['membership'])
        check('stale_receipt_' + name, r['status'] == 'identity_mismatch')
    s = deepcopy(s14); s['binding']['source_sha256']['v2_verify.py'] = 'wrong'
    check('source_mismatch_rejected', j.assemble(b14, r14['binding'], e14, s, r14['membership'])['status'] == 'identity_mismatch')
    check('numeric_identity_exact_not_spelling', j.digest(12) == j.digest(D('12.0'))
          and j.digest(12) != j.digest('12') and j.digest(12) != j.digest(D('12.00000000000000000001')))

    def reject(name, change):
        b = deepcopy(b14); change(b)
        with patch.object(j.v1, 'evaluate_trace', side_effect=AssertionError('invalid path reached thermal evaluator')):
            r = j.evaluate_bundle(b)
        derived[name] = short(r)
        check(name, r['status'] == 'input_invalid' and 'energy_J' not in r['certified_candidate_energy'], r.get('reason'))
    reject('outside_temperature_scope', lambda b: b['evaluation']['paths'][0]['entry_state']['temperature_box_C'][0].__setitem__(slice(None), [36, 36]))
    reject('temperature_trace_disagrees_with_entry', lambda b: b['evaluation']['paths'][0]['trace']['initial_temperature_C'].__setitem__(0, 31))
    reject('mode_trace_disagrees_with_entry', lambda b: b['evaluation']['paths'][0]['trace'].__setitem__('initial_mode', 'B'))
    reject('OPP_trace_disagrees_with_entry', lambda b: b['evaluation']['paths'][0]['trace']['initial_opps'].__setitem__('C0', 'L'))
    reject('entry_missing_phase', lambda b: b['evaluation']['paths'][0]['entry_state'].pop('phase_us'))
    reject('entry_pending_work', lambda b: b['evaluation']['paths'][0]['entry_state'].__setitem__('unfinished_work', ['old']))
    reject('entry_nonzero_clock', lambda b: b['evaluation']['paths'][0]['entry_state'].__setitem__('saturated_switch_age_us', 1))
    reject('too_early_switch', lambda b: b['evaluation']['paths'][0]['trace']['switch_requests'][0].__setitem__('time_us', 39999))
    reject('illegal_transition', lambda b: b['evaluation']['paths'][0]['trace']['switch_requests'][0].__setitem__('to_mode', 'A'))
    reject('W1_tail_truncates_deadline', lambda b: [p['trace'].__setitem__('window_us', 70000) for p in b['evaluation']['paths']])
    reject('unequal_windows', lambda b: b['evaluation']['paths'][0]['trace'].__setitem__('window_us', 81000))
    reject('bad_weight_sum', lambda b: b['evaluation'].__setitem__('weights', [D('0.5'), D('0.4')]))
    reject('negative_weight', lambda b: b['evaluation'].__setitem__('weights', [-1, 2]))
    reject('duplicate_path', lambda b: b['evaluation']['paths'][1]['trace'].__setitem__('id', 'F1'))
    reject('nested_candidate_override', lambda b: b['safety'].__setitem__('fixed_plans', b12['candidate']['fixed_plans']))
    reject('float_is_not_exact', lambda b: b['candidate']['platform'].__setitem__('external_power_W', 0.5))
    reject('zero_weight_does_not_drop_invalid_path', lambda b: (b['evaluation'].__setitem__('weights', [0, 1]),
           b['evaluation']['paths'][0]['trace']['switch_requests'][0].__setitem__('time_us', 1)))

    # Validate a non-first initial block and a real noninteger switch without thermal reruns.
    b = deepcopy(b14)
    for p in b['evaluation']['paths']:
        p['entry_state']['held_opps']['C0'] = 'L'; p['trace']['initial_opps']['C0'] = 'L'
        p['entry_state']['temperature_box_C'] = [[35, 35], [35, 35]]; p['trace']['initial_temperature_C'] = [35, 35]
    b['evaluation']['paths'][0]['trace']['switch_requests'][0]['time_us'] = D('45000.5')
    m = j.validate_bundle(b, j.v2.Budget())
    check('upper_boundary_nonfirst_entry_and_continuous_switch_supported', all(v['matching_entry_blocks'] == [1] for v in m))
    derived['nonfirst_entry_membership'] = m

    def hook_at(target, exc=j.v2.Exhausted):
        def hook(name):
            if name == target:
                raise exc('injected_' + target)
        return hook
    for point in ['start', 'input_validated', 'safety_returned', 'before_path', 'path_returned', 'energy_ready', 'before_assembly', 'before_commit']:
        r = j.evaluate_bundle(b14, j.v2.Budget(hook=hook_at(point)))
        check('interrupt_' + point, r['status'] == 'unresolved' and r['budget_status'] == 'exhausted'
              and 'energy_J' not in r['certified_candidate_energy'])
        derived['interrupt_' + point] = short(r)
    r = j.evaluate_bundle(b12, j.v2.Budget(hook=hook_at('before_path')))
    check('verified_violation_retained_on_interrupt', r['status'] == 'candidate_violation'
          and r['safety_receipt']['result']['status'] == 'violation' and 'energy_J' not in r['certified_candidate_energy'])

    # The inner verifier has committed its witness, but the receiving layer has
    # not yet accepted the return. Exercise real inner code, not a fake violation.
    def receiving_boundary(name, bundle, inner_point=None, outer_error=None):
        budget = j.v2.Budget(); observed = {}
        def boundary_hook(point):
            if point == inner_point:
                budget.start -= 1000
            if point == 'safety_returned' and outer_error:
                raise outer_error('injected_receiving_boundary')
        budget.hook = boundary_hook
        actual = j.v2.verify
        def capture(*args):
            inner = actual(*args)
            observed.update(status=inner['status'], budget_status=inner['budget_status'],
                            has_witness=bool((inner.get('witness') or {}).get('real_violation')))
            if inner_point is None and outer_error is None:
                budget.start -= 1000  # Delivery delay after an on-time inner return.
            return inner
        with patch.object(j.v2, 'verify', side_effect=capture), patch.object(
                j.v1, 'evaluate_trace', side_effect=AssertionError('energy evaluation after interruption')):
            r = j.evaluate_bundle(bundle, budget)
        kept = (r.get('safety_receipt') or {}).get('result', {})
        check(name, observed.get('has_witness') and r['status'] == 'candidate_violation'
              and kept.get('transfer_scope') == 'committed_counterexample_only'
              and kept.get('witness', {}).get('real_violation') is True
              and 'energy_J' not in json.dumps(kept, default=j.v1.encode)
              and 'energy_J' not in r['certified_candidate_energy']
              and not r.get('energy_receipt') and not r.get('partial_traces'))
        derived[name] = dict(inner=observed, outer=r)
        return r
    boundary = receiving_boundary('inner_deadline_commit_then_expiry', b12, 'witness_committed')
    check('deadline_witness_details_survive_receiving_boundary',
          boundary['safety_receipt']['result']['witness']['failure']['lateness_us'] == 1000
          and boundary['budget_status'] == 'exhausted')
    receiving_boundary('deadline_on_time_return_then_delivery_expiry', b12)
    receiving_boundary('deadline_receiving_gate_interruption', b12, outer_error=j.v2.Exhausted)
    receiving_boundary('deadline_receiving_gate_memory_error', b12, outer_error=MemoryError)

    # Existing B3 thermal fixture; used only for the same evidence-transfer boundary.
    v2package = j.v1.load(ROOT.parent / 'v2_precheck_draft/inputs.json')
    c3 = next(c for c in v2package['fixtures'] if c['id'] == 'B3')
    thermal_bundle = deepcopy(b14)
    thermal_bundle['id'] = 'thermal_receiving_boundary'
    thermal_bundle['candidate'] = {k: deepcopy(c3[k]) for k in ['platform', 'fixed_plans']}
    thermal_bundle['candidate']['semantics'] = deepcopy(v2package['semantics'])
    thermal_bundle['safety'] = {k: deepcopy(v) for k,v in c3.items()
                                if k not in ['id', 'purpose', 'platform', 'fixed_plans']}
    tr = j.v2.witness_trace(c3, v2package['semantics'])
    entry = deepcopy(c3['initial_states'][0])
    entry['temperature_box_C'] = [[t,t] for t in tr['initial_temperature_C']]
    thermal_bundle['evaluation']['paths'] = [dict(entry_state=entry, trace=tr)]
    thermal_bundle['evaluation']['weights'] = [1]
    boundary = receiving_boundary('inner_thermal_commit_then_expiry', thermal_bundle, 'witness_committed')
    check('thermal_witness_details_survive_without_energy', bool(
          boundary['safety_receipt']['result']['witness']['thermal']['known_violations']))
    derived['thermal_boundary_input'] = thermal_bundle

    budget = j.v2.Budget(); actual = j.v2.verify
    def late_safe(*args):
        r = actual(*args); budget.start -= 1000; return r
    with patch.object(j.v2, 'verify', side_effect=late_safe):
        late = j.evaluate_bundle(b14, budget)
    check('late_safe_return_not_promoted', late['status'] == 'unresolved'
          and late['safety_receipt'] is None and 'energy_J' not in late['certified_candidate_energy'])
    derived['late_safe_return'] = short(late)

    def path_boundary(name, bundle, inside_thermal=False):
        budget = j.v2.Budget()
        actual_trace, actual_thermal = j.v1.evaluate_trace, j.v1.thermal
        observed = {}
        def delay_trace(*args):
            r = actual_trace(*args)
            observed.update(execution_status=r.get('execution_status'),
                            has_deadline=bool(r.get('failure')),
                            has_thermal=bool(r.get('thermal', {}).get('known_violations')))
            budget.start -= 1000
            return r
        def delay_thermal(*args):
            r = actual_thermal(*args); budget.start -= 1000; return r
        if inside_thermal:
            with patch.object(j.v1, 'thermal', side_effect=delay_thermal):
                r = j.evaluate_bundle(bundle, budget)
        else:
            with patch.object(j.v1, 'evaluate_trace', side_effect=delay_trace):
                r = j.evaluate_bundle(bundle, budget)
        kept = r.get('path_violation_receipts', {})
        check(name, r['status'] == 'candidate_violation' and r['budget_status'] == 'exhausted'
              and bool(kept) and 'energy_J' not in json.dumps(kept, default=j.v1.encode)
              and 'energy_J' not in r['certified_candidate_energy'] and not r.get('energy_receipt')
              and not r.get('partial_traces'))
        derived[name] = dict(input=bundle, observed_return=observed, outer=r)
    no_hint12 = deepcopy(cases['J12_late']); no_hint12['safety']['witness_requests'] = []
    no_hint3 = deepcopy(thermal_bundle); no_hint3['safety'].pop('thermal_witness')
    path_boundary('finite_deadline_return_then_expiry', no_hint12)
    path_boundary('finite_thermal_return_then_expiry', no_hint3)
    path_boundary('finite_inner_thermal_committed_before_expiry', no_hint3, inside_thermal=True)
    probe = dict(status='unresolved', safety_receipt=None)
    j.retain_path_violation(probe, {}, b14['evaluation']['paths'][0]['trace'],
                           dict(input_status='valid', execution_status='deadline_violation',
                                rankable_energy=True, thermal={'status': 'violation'}))
    check('labels_without_concrete_witness_not_retained', probe == dict(status='unresolved', safety_receipt=None))
    for exc in [MemoryError, ArithmeticError]:
        r = j.evaluate_bundle(b14, j.v2.Budget(hook=hook_at('before_path', exc)))
        check('resource_' + exc.__name__, r['status'] == 'unresolved' and 'energy_J' not in r['certified_candidate_energy'])
    r = j.evaluate_bundle(b14, j.v2.Budget(seconds=-1))
    check('real_expired_budget', r['budget_status'] == 'exhausted' and r['status'] == 'unresolved')

    r = deepcopy(r14['finite_path_energy']['traces']['F1'])
    r['thermal'].update(status='unresolved', precision_met=False)
    with patch.object(j.v1, 'evaluate_trace', return_value=r):
        bad = j.evaluate_bundle(b14)
    check('unresolved_path_not_averaged_despite_safety_certificate', bad['status'] == 'unresolved'
          and 'energy_J' not in bad['finite_path_energy']['aggregate'] and 'energy_J' not in bad['certified_candidate_energy'])
    derived['numerical_path_unresolved'] = short(bad)
    r = deepcopy(r14['finite_path_energy']['traces']['F1'])
    r.update(execution_status='deadline_violation', rankable_energy=False)
    with patch.object(j.v1, 'evaluate_trace', return_value=r):
        bad = j.evaluate_bundle(b14)
    check('certificate_path_contradiction_is_anomaly', bad['status'] == 'evidence_conflict'
          and 'energy_J' not in bad['certified_candidate_energy'])

    # Delayed return may not introduce a new budget-valid energy record.
    budget = j.v2.Budget()
    def late(*args):
        budget.start -= 1000
        return deepcopy(r14['finite_path_energy']['traces']['F1'])
    with patch.object(j.v1, 'evaluate_trace', side_effect=late):
        bad = j.evaluate_bundle(b14, budget)
    check('late_path_return_not_committed', bad['budget_status'] == 'exhausted'
          and not bad.get('partial_traces') and 'energy_J' not in bad['certified_candidate_energy'])

    # Independent interval arithmetic check and historical equality only after execution.
    from interval import I
    e = r14['finite_path_energy']
    independent = sum((I(*e['traces'][p['trace']['id']]['thermal']['energy_J']) * I(w)
                       for p, w in zip(b14['evaluation']['paths'], b14['evaluation']['weights'])), I(0))
    check('weighted_interval_preserved', independent.data() == e['aggregate']['energy_J'])
    old = j.v1.load(ROOT.parent / 'v1_evaluator/results/run05/weighted_energy.json')
    check('12ms_finite_mean_historical_consistency', r12['finite_path_energy']['aggregate']['energy_J'] == old['energy_J'])
    check('all_legacy_bytes_unchanged', originals == {str(p.relative_to(ROOT.parent)): sha(p) for p in oldfiles})
    check('source_bytes_unchanged', source_hashes == {k: sha(p) for k, p in src.items()})
    check('no_historical_result_input_in_core', all(s not in (ROOT/'evaluate_joint.py').read_text(encoding='utf-8') for s in ['results/run', 'expected.json', 'inputs.json']))
    save(output / 'derived_checks.json', derived)
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(), checks=checks,
                  passed=sum(x['passed'] for x in checks), total=len(checks),
                  all_passed=all(x['passed'] for x in checks), sources=source_hashes,
                  original_files=originals, input_sha256=sha(ROOT/'inputs.json'),
                  expected_sha256=sha(ROOT/'expected.json'),
                  environment=dict(python=sys.version, platform=platform.platform()),
                  scope='integration prechecks only; no optimization or benefit comparison')
    save(output / 'precheck.json', report)
    print(str(report['passed']) + '/' + str(report['total']), flush=True)
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['precheck'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(precheck(args.output))
