"""Synthetic archive tests only: no research scheduling or thermal evaluation."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_formal as a
import audit_entry_temperature as t


def receipt(upper='2', at=3, lower=None):
    return {'state': 'SAFE', 'rankable_energy': True,
            'weighted_energy_J': [lower or upper, upper], 'safe_upper_bound_J': upper,
            'completed_at_elapsed_s': at,
            'scenes': {'AB': {'state': 'SAFE', 'complete': True,
                'energy_components_J': {'baseline': ['1', '1'], 'activity': ['1/5', '1/5'],
                    'external_common': ['3/10', '3/10'], 'temperature_correction': ['1/2', '1/2']}}},
            'legality': {'scenes': {'AB': {'rows': [{'end_ms': '100'}], 'segments': [
                {'start_ms': '0', 'end_ms': '100', 'baseline_by_node_W': {'C': '1'},
                 'activity_by_node_W': {'C': '2'}, 'external_common_power_W': '3/10'},
                {'start_ms': '100', 'end_ms': '1000', 'baseline_by_node_W': {'C': '1'},
                 'activity_by_node_W': {'C': '0'}, 'external_common_power_W': '3/10'}]}}}}


def result(upper='2', at=3, lower='1'):
    return {'state': 'SAFE', 'reason': 'SYNTHETIC_ONLY', 'safe_upper_bound_J': upper,
            'certified_lower_bound_J': lower, 'evaluation': receipt(upper, at),
            'timing': {'limit_s': 300, 'method_elapsed_s': 10, 'phases_exclusive_s': {'search': 9}},
            'input_sha256': 'same-input', 'independently_proven_optimal': False,
            'independently_proven_infeasible': False}


def job(method='heft', seed=None, problem='base__R1'):
    return {'call_id': problem+'__'+method+('' if seed is None else '__seed'+str(seed)),
            'problem_id': problem, 'method': method, 'seed': seed, 'seconds': 300}


def row(method='heft', seed=None, upper='2', problem='base__R1', state='SAFE'):
    r = result(upper)
    if state != 'SAFE': r.update(state=state, safe_upper_bound_J=None, evaluation=None)
    return a.call_row(job(method, seed, problem),
        {'returncode': 0, 'technical_check': {'passed': True}, 'process_wall_s': 11}, r,
        {'window_ms': '1000', 'scenarios': [{'id': 'AB', 'weight': '1'}]}, Path('not-created'), False)


def auditable_saved_result():
    j = job('sa', 103)
    instance = {'id': j['problem_id'], 'window_ms': '1000', 'scenarios': [{'id': 'AB', 'weight': '1'}]}
    r = result()
    r.update(problem_id=j['problem_id'], method='sa', seed=103,
             input_sha256=a.canonical_hash(instance), safe_candidate={'scenes': {'AB': []}})
    r['evaluation']['problem_id'] = j['problem_id']
    r['evaluation']['scenes']['AB']['covered_until_s'] = '1'
    r['evaluation']['legality'].update(state='SCHEDULE_VALID_THERMAL_UNCHECKED', problem_id=j['problem_id'])
    r['evaluations'] = [{'accepted_safe': True, 'source': 'synthetic',
                         'candidate': deepcopy(r['safe_candidate']), 'evaluation': deepcopy(r['evaluation'])}]
    return j, instance, r


def continuation_fixture():
    jobs = []
    for condition in ('base', 'initial_78', 'response_R'):
        for sample in ('R1', 'R2', 'R3', 'R4', 'R5'):
            for method in a.METHODS:
                if method == 'assignment' and condition == 'response_R':
                    continue
                for seed in a.SEEDS if method == 'sa' else (None,):
                    jobs.append(job(method, seed, condition+'__'+sample))
    old = {'manifest': {'jobs': jobs,
        'input_sha256': {j['problem_id']: 'synthetic-input' for j in jobs},
        'first_technical_case': 'base__R1'}, 'source_sha256': {
            'research/chapter3_experiments/run_formal_comparison.py': 'old',
            'research/chapter3_experiments/thermal.py': 'same'}}
    calls = [{'job': j, 'returncode': 0 if i < 4 else 1,
              'technical_check': {'passed': i < 4}} for i, j in enumerate(jobs[:5])]
    new = {'manifest': {**deepcopy(old['manifest']), 'jobs': deepcopy(jobs[5:]),
        'continuation_only': True, 'already_invoked': 5},
        'source_sha256': {**old['source_sha256'],
            'research/chapter3_experiments/run_formal_comparison.py': 'atomic-io',
            'research/chapter3_experiments/run_formal_continuation.py': 'continuation'},
        'source_version_change': 'Archival atomic publication and continuation selection only; algorithms, input and safety unchanged.'}
    return old, new, calls


def write_synthetic_continuation(root):
    """Only tiny invented archives; never invoke a scheduling method."""
    prior, current = root/'old', root/'continued'
    prior.mkdir(); current.mkdir()
    old, new, calls = continuation_fixture()
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    for call in calls:
        j = call['job']
        _, instance, raw = auditable_saved_result()
        raw.update(method=j['method'], seed=j['seed'])
        if call['returncode'] == 0: raw['call_id'] = j['call_id']
        save(prior/(j['call_id']+'.claim.json'), j)
        save(prior/j['call_id']/'result.json', raw)
        save(prior/j['call_id']/'input_instance.json', instance)
        (prior/(j['call_id']+'.stdout.txt')).write_text('synthetic only', encoding='utf-8')
        old['manifest']['input_sha256'][j['problem_id']] = a.canonical_hash(instance)
    new['manifest']['input_sha256'] = deepcopy(old['manifest']['input_sha256'])
    save(prior/'declaration.json', old)
    save(prior/'calls.json', calls)
    save(prior/'stop.json', {'reason': 'TECHNICAL_CHECK_FAILED', 'call': calls[-1]})
    save(prior/'source_integrity.json', {'unchanged': True})
    identity = {'previous_batch': str(prior.resolve()),
        'original_manifest_sha256': a.canonical_hash(old['manifest']),
        'source_sha256': old['source_sha256'],
        'invoked_call_ids': [c['job']['call_id'] for c in calls],
        'technical_passed': 4, 'technical_failed': 1,
        'files_sha256': {p.relative_to(prior).as_posix(): a.hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in prior.rglob('*') if p.is_file()}}
    new['prior_batch_identity'] = identity
    new['manifest']['prior_batch_identity'] = deepcopy(identity)
    save(current/'declaration.json', new)
    new_calls = []
    for j in new['manifest']['jobs'][:3]:
        _, instance, raw = auditable_saved_result()
        raw.update(call_id=j['call_id'], method=j['method'], seed=j['seed'])
        save(current/j['call_id']/'result.json', raw)
        save(current/j['call_id']/'input_instance.json', instance)
        save(current/(j['call_id']+'.claim.json'), j)
        new_calls.append({'job': j, 'returncode': 0, 'technical_check': {'passed': True}})
    save(current/'calls.json', new_calls)
    return prior, current, old, new


def entry_pair_fixture():
    cold = {'id': 'base__R1', 'condition_id': 'base', 'experiment_group': 'baseline', 'sample_id': 'R1',
        'settings': {'initial_temperature_degC': '50', 'start_grid_ms': '5'},
        'platform': {'node_order': ['CPU1', 'NPU0'], 'heat_capacity': ['1', '2']},
        'window_ms': '1000', 'stage_modes': {'A': [{'unit': 'NPU0', 'activity_power_W': '2'}]},
        'scenarios': [{'id': 'AB', 'weight': '1', 'entry': {'temperature_degC': ['50', '50'],
            'domain_opp': {'CPU': 'L', 'NPU': 'L'}, 'unfinished_work': []},
            'maximum_temperature_degC': ['80', '80'], 'deadline_ms': '100'}]}
    hot = deepcopy(cold)
    hot.update(id='initial_78__R1', condition_id='initial_78', experiment_group='entry_temperature')
    hot['settings']['initial_temperature_degC'] = '78'
    hot['scenarios'][0]['entry']['temperature_degC'] = ['78', '78']
    candidate = {'shared_deployment': {'A': 'NPU0'}, 'scenes': {'AB': [
        {'stage_id': 'A', 'unit': 'NPU0', 'opp': 'H', 'start_ms': '0'}]}}
    cold_receipt = receipt()
    cold_receipt['problem_id'] = cold['id']
    cold_receipt['scenes']['AB']['covered_until_s'] = '1'
    cold_receipt['legality'].update(state='SCHEDULE_VALID_THERMAL_UNCHECKED', problem_id=cold['id'])
    witness = {'scene_id': 'AB', 'node': 'NPU0', 'time_s': '1/10',
               'temperature_degC': ['81', '81.001'], 'limit_degC': '80', 'formed_at_elapsed_s': 5}
    hot_receipt = {'state': 'THERMAL_VIOLATION', 'rankable_energy': False, 'problem_id': hot['id'],
        'legality': {'state': 'SCHEDULE_VALID_THERMAL_UNCHECKED', 'problem_id': hot['id']},
        'violations': [witness], 'scenes': {'AB': {'complete': False}}}
    old_result = {'evaluations': [{'accepted_safe': True, 'candidate': candidate, 'evaluation': cold_receipt}]}
    hot_result = {'evaluations': [{'accepted_safe': False, 'candidate': deepcopy(candidate), 'evaluation': hot_receipt}]}
    return cold, old_result, hot, hot_result


class ArchiveAnalysisTests(unittest.TestCase):
    def test_safe_requires_complete_inbudget_receipt(self):
        r = receipt()
        self.assertTrue(a.safe_receipt(r, 300))
        r['completed_at_elapsed_s'] = 300
        self.assertFalse(a.safe_receipt(r, 300))
        r['completed_at_elapsed_s'] = 299
        r['scenes']['AB']['complete'] = False
        self.assertFalse(a.safe_receipt(r, 300))

    def test_missing_unresolved_energy_is_not_zero(self):
        r = row(state='UNRESOLVED')
        self.assertFalse(r['safe'])
        self.assertIsNone(r['U_J'])
        self.assertIsNone(r['first_safe_at_s'])

    def test_controller_technical_failure_is_not_success(self):
        r = a.call_row(job(), {'returncode': 0, 'technical_check': {'passed': False}},
                       result(), None, Path('none'), False)
        self.assertEqual(r['call_state'], 'TECHNICAL_CHECK_FAILED')
        self.assertFalse(r['safe'])

    def test_worker_archival_failure_preserves_SAFE_only_in_audit_tier(self):
        j, instance, raw = auditable_saved_result()
        out = a.call_row(j, {'returncode': 1, 'technical_check': {'passed': False}}, raw,
                         instance, Path('none'), True, a.canonical_hash(instance))
        self.assertEqual(out['call_state'], 'TECHNICAL_CHECK_FAILED')
        self.assertFalse(out['safe'])
        self.assertIsNone(out['U_J'])
        self.assertTrue(out['audit_preserved_safe_evidence']['preserved'])
        self.assertEqual(out['audit_preserved_safe_evidence']['U_J'], '2')
        sa = a.aggregate([out])['sa_per_problem'][0]
        self.assertEqual(sa['safe_seeds'], 0)
        self.assertIsNone(sa['U_median_J'])

    def test_audit_rejects_wrong_frozen_identity(self):
        j, instance, raw = auditable_saved_result()
        evidence = a.preserved_safe_evidence(raw, instance, j, 'wrong-hash')
        self.assertFalse(evidence['preserved'])
        self.assertIsNone(evidence['U_J'])

    def test_audit_rejects_late_SAFE_even_if_archive_complete(self):
        j, instance, raw = auditable_saved_result()
        raw['evaluation']['completed_at_elapsed_s'] = 300
        raw['evaluations'][0]['evaluation'] = deepcopy(raw['evaluation'])
        evidence = a.preserved_safe_evidence(raw, instance, j, a.canonical_hash(instance))
        self.assertFalse(evidence['preserved'])

    def test_saved_but_not_controller_accepted_does_not_enter_success(self):
        r = a.call_row(job(), None, result(), None, Path('none'), False)
        self.assertEqual(r['call_state'], 'RESULT_SAVED_AWAITING_CONTROLLER')
        self.assertFalse(r['safe'])
        self.assertEqual(r['safe_timeline'], [])
        self.assertIsNone(r['certified_L0_J'])

    def test_missing_record_after_stop_not_infeasible(self):
        r = a.call_row(job(), None, None, None, Path('none'), True)
        self.assertEqual(r['call_state'], 'NOT_RUN_AFTER_STOP')
        self.assertFalse(r['independently_proven_infeasible'])

    def test_controller_success_but_archive_missing_is_not_complete(self):
        r = a.call_row(job(), {'returncode': 0, 'technical_check': {'passed': True}},
                       None, None, Path('none'), False)
        self.assertEqual(r['call_state'], 'ARCHIVE_RESULT_MISSING')
        self.assertFalse(r['safe'])

    def test_certified_gap_has_U_denominator(self):
        r = row(upper='4')
        self.assertEqual(F(r['certified_gap_U_denominator']), F(3, 4))

    def test_invalid_bound_not_clamped_to_zero(self):
        r = result('2', lower='3')
        r['diagnostic'] = {'solver_progress': [{'method_elapsed_s': 8,
            'values': {'lowerbound': 4, 'relativegap': -5}}]}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertTrue(out['certified_bound_above_U_anomaly'])
        self.assertIsNone(out['certified_gap_U_denominator'])
        self.assertTrue(out['solver_reported_bound_above_U_anomaly'])
        self.assertEqual(out['solver_reported_relativegap_native'], -5)

    def test_solver_native_fields_remain_uncertified(self):
        r = result()
        r['rounds'] = [{'budget_valid': True, 'output': {'lowerbound': 1.5,
            'relativegap': 25}, 'exitflag': 1, 'intlinprog_entered': True}]
        records = a.solver_records(r, 300)
        self.assertFalse(records[0]['independently_certified'])
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertTrue(out['integer_solver_entered'])
        self.assertFalse(out['independently_proven_optimal'])
        self.assertEqual(out['solver_reported_relativegap_native'], 25)

    def test_late_solver_progress_not_in_budget_aggregate(self):
        r = result()
        r['diagnostic'] = {'solver_progress': [
            {'method_elapsed_s': 200, 'values': {'lowerbound': 1}},
            {'method_elapsed_s': 300, 'values': {'lowerbound': 9}}]}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertEqual(out['solver_reported_lowerbound_J'], 1)
        self.assertFalse(out['solver_reported_records'][-1]['received_in_budget'])

    def test_later_round_callback_not_overwritten_by_old_final_output(self):
        r = result()
        r['diagnostic'] = {'solver_progress': [
            {'request': 'request_000001', 'method_elapsed_s': 20,
             'values': {'lowerbound': .5, 'relativegap': 75}},
            {'request': 'request_000002', 'method_elapsed_s': 250,
             'values': {'lowerbound': 1.5, 'relativegap': 25}}]}
        r['rounds'] = [
            {'request_number': 1, 'budget_valid': True,
             'output': {'lowerbound': 1, 'relativegap': 50}},
            {'request_number': 2, 'budget_valid': False, 'output': {'lowerbound': 1.8}}]
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertEqual(out['solver_reported_lowerbound_J'], 1.5)
        self.assertEqual(out['solver_reported_relativegap_native'], 25)
        self.assertIsNone(out['solver_reported_records'][-1]['at_s'])

    def test_initial_vs_MILP_strict_interval_attribution(self):
        r = result('3', at=20)
        r['initialisation'] = {'witness': {'evaluation': receipt('5', 5, '4.9')}}
        r['diagnostic'] = {'evaluations': [{'accepted_safe': True,
            'source': 'round1', 'evaluation': receipt('3', 20, '2.9')}]}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertEqual(out['first_safe_at_s'], 5)
        self.assertTrue(out['strict_MILP_seed_improvement_from_receipts'])

    def test_first_legal_includes_constructor_but_MILP_time_separate(self):
        r = result()
        r['initialisation'] = {'attempts': [
            {'status': 'COMPLETE_LEGAL_CANDIDATE', 'schedule_completed_at_s': 2},
            {'status': 'COMPLETE_LEGAL_CANDIDATE', 'schedule_completed_at_s': 300}]}
        r['diagnostic'] = {'first_legal_candidate_s': 7}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertEqual(out['first_legal_at_s'], 2)
        self.assertEqual(out['first_MILP_legal_at_s'], 7)

    def test_overlapping_energy_intervals_do_not_prove_improvement(self):
        r = result('3.99', at=20)
        r['initialisation'] = {'witness': {'evaluation': receipt('4', 5, '3.9')}}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertFalse(out['strict_MILP_seed_improvement_from_receipts'])

    def test_historical_violation_preserved_after_final_SAFE_and_deduplicated(self):
        r = result()
        witness = {'node': 'CPU1', 'time_s': '1/10', 'formed_at_elapsed_s': 5,
                   'temperature_degC': ['81', '81.01'], 'limit_degC': '80'}
        late = {**witness, 'formed_at_elapsed_s': 300}
        r['violations'] = [deepcopy(witness)]
        r['diagnostic'] = {'evaluations': [{'evaluation': {'state': 'THERMAL_VIOLATION',
            'violations': [witness, late]}}]}
        out = a.call_row(job('milp'), {'returncode': 0, 'technical_check': {'passed': True}},
                         r, None, Path('none'), False)
        self.assertEqual(out['thermal_violation_witnesses'], 1)

    def test_SA_median_not_best_and_failures_retained(self):
        rows = [row('sa', seed, str(energy), state='SAFE' if energy else 'UNRESOLVED')
                for seed, energy in zip(a.SEEDS, (1, 3, 5, 0, 0))]
        out = a.aggregate(rows)['sa_per_problem'][0]
        self.assertEqual(out['safe_fraction'], .6)
        self.assertEqual(F(out['U_median_J']), 3)
        self.assertEqual(out['expected_seeds'], 5)
        self.assertEqual(len(out['seeds']), 5)
        self.assertIsNone(out['seeds'][-1]['U_J'])

    def test_missing_HEFT_leaves_normalization_missing(self):
        pairs = a.aggregate([row('milp'), row('heft', state='UNRESOLVED')])['HEFT_normalized_common_success']
        self.assertTrue(all(r['ratio_U_over_HEFT_U'] is None for r in pairs))

    def test_normalization_uses_same_problem_HEFT(self):
        rows = [row('heft', upper='4'), row('milp', upper='2'),
                row('heft', upper='8', problem='base__R2'), row('milp', upper='2', problem='base__R2')]
        ratios = [F(r['ratio_U_over_HEFT_U']) for r in a.aggregate(rows)['HEFT_normalized_common_success']
                  if r['method'] == 'milp']
        self.assertEqual(ratios, [F(1, 2), F(1, 4)])

    def test_tail_only_constant_terms_split_no_temperature_interpolation(self):
        parts = row()['saved_energy_parts']
        self.assertTrue(parts['available'])
        self.assertEqual(F(parts['weighted_constant_terms_by_period_J']['tail']['baseline']), F(9, 10))
        self.assertEqual(F(parts['weighted_constant_terms_by_period_J']['tail']['activity']), 0)
        self.assertEqual(F(parts['weighted_components_J']['temperature_correction'][1]), F(1, 2))
        self.assertIsNone(parts['tail_total_energy_J'])
        self.assertFalse(parts['temperature_correction_split_available'])

    def test_segment_component_mismatch_is_reported(self):
        r = result()
        r['evaluation']['legality']['scenes']['AB']['segments'][0]['activity_by_node_W']['C'] = '3'
        parts = a.energy_parts(r, {'window_ms': '1000', 'scenarios': [{'id': 'AB', 'weight': '1'}]})
        self.assertFalse(parts['available'])

    def test_input_identity_mismatch_reported(self):
        x, y = row(), row('milp')
        y['input_sha256'] = 'changed'
        self.assertEqual(a.aggregate([x, y])['input_identity_mismatches'], ['base__R1'])

    def test_end_to_end_synthetic_archive_is_read_only(self):
        # A local temporary synthetic archive, never the research directory.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root/'archive'; source.mkdir()
            jobs = [job(), job('sa', 101)]
            (source/'declaration.json').write_text(json.dumps({'manifest': {'jobs': jobs}}))
            (source/'calls.json').write_text(json.dumps([
                {'job': jobs[0], 'returncode': 0, 'technical_check': {'passed': True}}]))
            case = source/jobs[0]['call_id']; case.mkdir()
            (case/'result.json').write_text(json.dumps(result()))
            (case/'input_instance.json').write_text(json.dumps(
                {'window_ms': '1000', 'scenarios': [{'id': 'AB', 'weight': '1'}]}))
            before = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*') if p.is_file()}
            report = a.analyze(source)
            out = root/'analysis'; out.mkdir(); a.save_tables(report, out)
            a.plots(report, out)
            after = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(report['safe_calls'], 1)
            self.assertEqual(report['call_states'], {'COMPLETED': 1, 'PENDING': 1})
            self.assertFalse(report['formal_batch_complete'])
            self.assertTrue((out/'timeline.csv').is_file())
            self.assertTrue((out/'paired_energy_HEFT_normalized.png').is_file())
            self.assertTrue((out/'first_SAFE.png').is_file())
            self.assertTrue((out/'R1_safe_U_and_bounds.png').is_file())

    def test_continuation_manifest_exact_original_115(self):
        old, new, calls = continuation_fixture()
        coverage = a._merge_manifest_checks(old, new, [c['job'] for c in calls], calls)
        self.assertTrue(coverage['passed'])
        self.assertEqual(coverage['original_problems'], 15)
        self.assertEqual(coverage['continuation_calls'], 110)

    def test_continuation_rejects_original_failed_SA103_retry(self):
        old, new, calls = continuation_fixture()
        new['manifest']['jobs'][0] = deepcopy(calls[-1]['job'])
        with self.assertRaises(ValueError):
            a._merge_manifest_checks(old, new, [c['job'] for c in calls], calls)

    def test_continuation_rejects_duplicate_and_missing_ID(self):
        old, new, calls = continuation_fixture()
        new['manifest']['jobs'][1] = deepcopy(new['manifest']['jobs'][0])
        with self.assertRaises(ValueError):
            a._merge_manifest_checks(old, new, [c['job'] for c in calls], calls)

    def test_continuation_rejects_reordering_changed_budget_or_input(self):
        for change in ('order', 'budget', 'input'):
            with self.subTest(change=change):
                old, new, calls = continuation_fixture()
                if change == 'order':
                    new['manifest']['jobs'][0:2] = reversed(new['manifest']['jobs'][0:2])
                elif change == 'budget':
                    new['manifest']['jobs'][0]['seconds'] = 301
                else:
                    new['manifest']['input_sha256']['base__R1'] = 'changed'
                with self.assertRaises(ValueError):
                    a._merge_manifest_checks(old, new, [c['job'] for c in calls], calls)

    def test_explicit_continuation_merge_keeps_old_failure_and_source_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            prior, current, old, new = write_synthetic_continuation(Path(temp))
            old_before = {p.relative_to(prior).as_posix(): p.read_bytes()
                          for p in prior.rglob('*') if p.is_file()}
            report = a.analyze(current, prior)
            self.assertEqual(report['expected_calls'], 115)
            self.assertEqual(len(report['rows']), 115)
            self.assertEqual(report['controller_finished_calls'], 8)
            self.assertEqual(report['call_states'], {'COMPLETED': 7, 'TECHNICAL_CHECK_FAILED': 1, 'PENDING': 107})
            self.assertEqual(report['safe_calls'], 7)
            self.assertEqual(report['technical_passed_calls'], 7)
            self.assertEqual(report['technical_failed_calls'], 1)
            self.assertEqual(report['audit_preserved_safe_calls'], 8)
            self.assertEqual(report['first_technical_case_completed_calls'], 7)
            self.assertFalse(report['first_technical_case_complete'])
            failed = next(r for r in report['rows'] if r['seed'] == 103 and r['problem_id'] == 'base__R1')
            self.assertEqual(failed['call_state'], 'TECHNICAL_CHECK_FAILED')
            self.assertFalse(failed['safe'])
            self.assertTrue(failed['audit_preserved_safe_evidence']['preserved'])
            self.assertEqual(failed['source_batch'], str(prior.resolve()))
            self.assertEqual(report['rows'][5]['source_batch'], str(current.resolve()))
            self.assertNotEqual(failed['source_version_fingerprint'], report['rows'][5]['source_version_fingerprint'])
            sa = report['sa_per_problem'][0]
            self.assertEqual(sa['safe_seeds'], 4)
            self.assertEqual(sa['expected_seeds'], 5)
            self.assertEqual(old_before, {p.relative_to(prior).as_posix(): p.read_bytes()
                                         for p in prior.rglob('*') if p.is_file()})

    def test_final_report_distinguishes_115_terminated_114_technical_and_SAFE_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prior, current, old, new = write_synthetic_continuation(root)
            original, continuation = a._analyze_one(prior), a._analyze_one(current)
            # Synthetic aggregation fixture: other 107 calls terminate legally
            # UNRESOLVED, so technical pass does not mean another SAFE result.
            for record in continuation['rows']:
                if record['call_state'] == 'PENDING':
                    record['call_state'] = 'COMPLETED'
                    record['result_state'] = 'UNRESOLVED'
            continuation['controller_finished_calls'] = 110
            coverage = a._continuation_provenance(current, prior, new, old)
            combined = a._join_analyses(original, continuation, coverage)
            self.assertTrue(combined['all_declared_calls_terminated'])
            self.assertFalse(combined['formal_batch_complete'])
            self.assertEqual(combined['technical_passed_calls'], 114)
            self.assertEqual(combined['technical_failed_calls'], 1)
            self.assertEqual(combined['safe_calls'], 7)
            base_sa = next(r for r in combined['condition_method_success']
                           if r['condition'] == 'base' and r['method'] == 'sa')
            self.assertEqual(base_sa['invoked_calls'], 25)
            self.assertEqual(base_sa['terminal_calls'], 25)
            self.assertEqual(base_sa['completed_calls'], 24)
            self.assertTrue(base_sa['batch_execution_finished'])
            self.assertTrue(base_sa['rate_is_final'])
            self.assertFalse(base_sa['technical_acceptance_complete'])
            out = root/'summary'; out.mkdir()
            a.save_tables(combined, out)
            text = (out/'summary.md').read_text(encoding='utf-8')
            self.assertIn('全部原调用已执行结束=True；技术通过114/115', text)
            self.assertIn('控制器正常通过且有SAFE：7次', text)
            self.assertIn('base R1正式SA样本：技术通过4/5个种子', text)
            self.assertIn('原SA103继续为技术失败', text)
            self.assertIn('不补入正式SA样本', text)
            self.assertIn('不是已知真实最优差距', text)
            self.assertIn('MILP初始构造器', text)
            self.assertIn('反馈次数与新增行数只统计实际外层反馈', text)

    def test_candidate_receipt_audit_separates_budget_and_numerical_unresolved(self):
        raw = {'evaluations': [
            {'evaluation': {'state': 'UNRESOLVED', 'reason': 'wall_time_limit', 'budget_exhausted': True}},
            {'evaluation': {'state': 'UNRESOLVED', 'reason': 'TEMPERATURE_LIMIT_UNRESOLVED'}},
            {'evaluation': {'state': 'UNRESOLVED', 'reason': 'NUMERICAL_ERROR', 'error_type': 'ArithmeticError'}},
            {'evaluation': {'state': 'THERMAL_VIOLATION', 'violations': [
                {'temperature_degC': ['81', '81.1'], 'limit_degC': '80', 'formed_at_elapsed_s': 5}]}},
            {'evaluation': receipt()}]}
        counts = a.candidate_receipt_counts(raw, 'heft', 300)
        self.assertEqual(counts['evaluation_state_counts'], {'UNRESOLVED': 3, 'THERMAL_VIOLATION': 1, 'SAFE': 1})
        self.assertEqual(counts['unresolved_reason_counts']['wall_time_limit'], 1)
        self.assertNotIn('wall_time_limit', counts['nonbudget_unresolved_reason_counts'])
        self.assertEqual(counts['numerical_error_receipts'], 1)
        self.assertEqual(counts['strict_violation_evaluation_records'], 1)

    def test_continuation_rejects_changed_old_record_or_missing_hash(self):
        for change in ('old_record', 'missing_hash'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                prior, current, old, new = write_synthetic_continuation(Path(temp))
                if change == 'old_record':
                    (prior/'calls.json').write_text('[]', encoding='utf-8')
                else:
                    del new['prior_batch_identity']['files_sha256']['calls.json']
                    new['manifest']['prior_batch_identity'] = deepcopy(new['prior_batch_identity'])
                    (current/'declaration.json').write_text(json.dumps(new), encoding='utf-8')
                with self.assertRaises(ValueError):
                    a.analyze(current, prior)

    def test_continuation_rejects_undeclared_method_source_change(self):
        with tempfile.TemporaryDirectory() as temp:
            prior, current, old, new = write_synthetic_continuation(Path(temp))
            new['source_sha256']['research/chapter3_experiments/thermal.py'] = 'not-io-change'
            (current/'declaration.json').write_text(json.dumps(new), encoding='utf-8')
            with self.assertRaises(ValueError):
                a.analyze(current, prior)

    def test_continuation_requires_explicit_correct_prior_directory_and_version_declaration(self):
        for change in ('directory', 'version'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                prior, current, old, new = write_synthetic_continuation(Path(temp))
                if change == 'directory':
                    new['prior_batch_identity']['previous_batch'] = str(current.resolve())
                    new['manifest']['prior_batch_identity'] = deepcopy(new['prior_batch_identity'])
                else:
                    new.pop('source_version_change')
                (current/'declaration.json').write_text(json.dumps(new), encoding='utf-8')
                with self.assertRaises(ValueError):
                    a.analyze(current, prior)

    def test_entry_pair_matches_same_candidate_SAFE_to_strict_violation(self):
        fixture = entry_pair_fixture()
        found = t.pair_saved_results(*fixture, sample='R1')
        self.assertTrue(found['input_checks']['passed'])
        self.assertEqual(found['common_candidate_count'], 1)
        self.assertEqual(found['status'], 'MATCHED_SAFE_TO_STRICT_VIOLATION')
        evidence = found['matched_candidates'][0]
        self.assertEqual(evidence['hot_strict_witnesses'][0]['node'], 'NPU0')
        self.assertEqual(evidence['hot_strict_witnesses'][0]['time_s'], '1/10')

    def test_entry_pair_does_not_strip_nonentry_changes(self):
        for change in ('power', 'deadline', 'entry_opp', 'capacity'):
            with self.subTest(change=change):
                cold, old, hot, new = entry_pair_fixture()
                if change == 'power': hot['stage_modes']['A'][0]['activity_power_W'] = '3'
                if change == 'deadline': hot['scenarios'][0]['deadline_ms'] = '101'
                if change == 'entry_opp': hot['scenarios'][0]['entry']['domain_opp']['NPU'] = 'H'
                if change == 'capacity': hot['platform']['heat_capacity'][0] = '4'
                found = t.pair_saved_results(cold, old, hot, new, sample='R1')
                self.assertEqual(found['status'], 'NONENTRY_INPUT_MISMATCH_OR_UNSUPPORTED_ENTRY')
                self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_requires_identical_candidate_content(self):
        cold, old, hot, new = entry_pair_fixture()
        new['evaluations'][0]['candidate']['scenes']['AB'][0]['start_ms'] = '5'
        found = t.pair_saved_results(cold, old, hot, new, sample='R1')
        self.assertEqual(found['common_candidate_count'], 0)
        self.assertEqual(found['status'], 'NO_MATCHING_SAVED_EVIDENCE')
        self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_strictness_not_tolerance(self):
        for bounds in (['80', '80.001'], ['79.999', '80.001']):
            with self.subTest(bounds=bounds):
                cold, old, hot, new = entry_pair_fixture()
                new['evaluations'][0]['evaluation']['violations'][0]['temperature_degC'] = bounds
                found = t.pair_saved_results(cold, old, hot, new, sample='R1')
                self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_rejects_late_cold_SAFE_or_hot_witness(self):
        for part in ('cold', 'hot'):
            with self.subTest(part=part):
                cold, old, hot, new = entry_pair_fixture()
                if part == 'cold': old['evaluations'][0]['evaluation']['completed_at_elapsed_s'] = 300
                else: new['evaluations'][0]['evaluation']['violations'][0]['formed_at_elapsed_s'] = 300
                found = t.pair_saved_results(cold, old, hot, new, sample='R1')
                self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_rejects_incomplete_cold_receipt_or_wrong_witness_identity(self):
        for change in ('cold_incomplete', 'limit', 'node', 'time', 'scene'):
            with self.subTest(change=change):
                cold, old, hot, new = entry_pair_fixture()
                witness = new['evaluations'][0]['evaluation']['violations'][0]
                if change == 'cold_incomplete': old['evaluations'][0]['evaluation']['scenes']['AB']['complete'] = False
                if change == 'limit': witness['limit_degC'] = '79'
                if change == 'node': witness['node'] = 'missing'
                if change == 'time': witness['time_s'] = '2'
                if change == 'scene': witness['scene_id'] = 'missing'
                found = t.pair_saved_results(cold, old, hot, new, sample='R1')
                self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_reports_conflicting_hot_receipts_without_acceptance(self):
        cold, old, hot, new = entry_pair_fixture()
        additional = deepcopy(old['evaluations'][0])
        additional['evaluation']['problem_id'] = hot['id']
        additional['evaluation']['legality']['problem_id'] = hot['id']
        new['evaluations'].append(additional)
        found = t.pair_saved_results(cold, old, hot, new, sample='R1')
        self.assertEqual(found['status'], 'RECEIPT_CONFLICT_REQUIRES_REVIEW')
        self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_reports_conflicting_cold_receipts_without_acceptance(self):
        cold, old, hot, new = entry_pair_fixture()
        additional = deepcopy(new['evaluations'][0])
        additional['evaluation']['problem_id'] = cold['id']
        additional['evaluation']['legality']['problem_id'] = cold['id']
        old['evaluations'].append(additional)
        found = t.pair_saved_results(cold, old, hot, new, sample='R1')
        self.assertEqual(found['status'], 'RECEIPT_CONFLICT_REQUIRES_REVIEW')
        self.assertEqual(found['matched_candidates'], [])

    def test_entry_pair_file_audit_is_read_only_and_retains_visitation_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cold, old, hot, new = entry_pair_fixture()
            rows = []
            for condition, instance, result in (('base', cold, old), ('initial_78', hot, new)):
                j = job('heft', problem=instance['id'])
                folder = root/condition/j['call_id']; folder.mkdir(parents=True)
                sha = a.canonical_hash(instance)
                result.update(call_id=j['call_id'], method='heft', seed=None,
                              problem_id=j['problem_id'], input_sha256=sha)
                (folder/'input_instance.json').write_text(json.dumps(instance), encoding='utf-8')
                (folder/'result.json').write_text(json.dumps(result), encoding='utf-8')
                rows.append({**j, 'call_state': 'COMPLETED', 'condition': condition, 'sample': 'R1',
                             'seconds_limit': 300, 'source_batch': str(folder.parent),
                             'source_version_fingerprint': condition+'-source', 'input_sha256': sha})
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            report = t.audit_pairs({'rows': rows})
            self.assertEqual(report['matched_candidate_count'], 1)
            self.assertIn('not an exhaustive or unbiased', report['limits'][0])
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes()
                                      for p in root.rglob('*') if p.is_file()})


if __name__ == '__main__':
    unittest.main()
