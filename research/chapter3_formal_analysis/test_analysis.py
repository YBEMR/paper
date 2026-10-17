"""Synthetic archive tests only: no research scheduling or thermal evaluation."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze_formal as a


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


if __name__ == '__main__':
    unittest.main()
