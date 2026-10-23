"""Independent synthetic-only tests of K171 replay helper gates, no scientific calls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'replay.py'
REPO = HERE.parents[4]
BLOCKED = []
FORBIDDEN = {'numpy', 'scipy', 'matlab', 'thermal', 'milp', 'inputs', 'schedules',
    'formal_milp', 'method_runner', 'linked_method', 'scene_adapter', 'partial_bounds',
    'milp_coefficients', 'subprocess', 'socket'}

def audit(event, args):
    if event == 'import' and args and str(args[0]).split('.')[0] in FORBIDDEN:
        BLOCKED.append({'kind': 'import', 'value': str(args[0])})
        raise RuntimeError('Forbidden import in pure fixture: ' + str(args[0]))
    if event in {'subprocess.Popen', 'os.system', 'os.spawn', 'os.exec', 'socket.connect'}:
        BLOCKED.append({'kind': 'process_or_network', 'value': event})
        raise RuntimeError('Forbidden process/network in pure fixture: ' + event)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

sys.addaudithook(audit)
spec = importlib.util.spec_from_file_location('K171_replay_pure_helpers', SOURCE)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

def update(index=1, **changes):
    row = {'source_update_index': index, 'case_id': 'toy_R1', 'input_sha256': 'toy_input',
        'call_directory': 'toy_same_call', 'state': 'SAFE', 'complete_global': True,
        'evidence_verified': True, 'formed_at_s': '1', 'committed_at_s': '2',
        'transferred_at_s': '3', 'observer_completed_at_s': '4', 'upper_J': '5/2'}
    row.update(changes)
    return row

def select(rows, build='10'):
    return replay.select_timely_upper(rows, case_id='toy_R1', input_sha256='toy_input',
        call_directory='toy_same_call', build_at_s=build)

def bound(value):
    return {'lower_bound_J': str(value), 'legacy_conditioned_lower_bound_J': '1/2',
        'capacity_lower_bound_J': '1', 'forced_residency_lower_bound_J': str(value)}

class PureHelpers(unittest.TestCase):
    def test_same_call_global_delivered_is_eligible(self):
        result = select([update()])
        self.assertEqual(result['upper']['upper_J'], '5/2')
        self.assertEqual(result['upper']['available_at_s_exact'], '4')
        self.assertFalse(result['production_pruning_authorized'])

    def test_future_final_U_does_not_replace_timely_U(self):
        rows = [update(1, upper_J='5/2'), update(2, upper_J='1', transferred_at_s='11', observer_completed_at_s='12')]
        result = select(rows)
        self.assertEqual(result['upper']['source_update_index'], 1)
        self.assertEqual(result['admitted_indices'], [1])
        self.assertEqual(result['rejected'][0]['reason'], 'NOT_DELIVERED_BEFORE_BUILD')

    def test_each_distinct_identity_mismatch_is_rejected(self):
        for field, val in [('case_id', 'other_R'), ('input_sha256', 'other_input'), ('call_directory', 'other_call')]:
            with self.subTest(field=field):
                row = update(**{field: val})
                self.assertIsNone(select([row])['upper'])

    def test_local_SAFE_is_not_global_U(self):
        for changes in ({'complete_global': False}, {'evidence_verified': False}, {'state': 'UNRESOLVED'}):
            with self.subTest(changes=changes):
                self.assertIsNone(select([update(**changes)])['upper'])

    def test_missing_four_timestamps_fail_closed(self):
        for name in ('formed_at_s', 'committed_at_s', 'transferred_at_s', 'observer_completed_at_s'):
            with self.subTest(name=name):
                row = update()
                del row[name]
                result = select([row])
                self.assertIsNone(result['upper'])
                self.assertEqual(result['rejected'][0]['reason'], 'MISSING_OR_INVALID_EXACT_FIELDS')

    def test_no_readable_global_U_gives_no_exclusion(self):
        row = update(formed_at_s='1', committed_at_s='2', transferred_at_s='9', observer_completed_at_s='11')
        upper = select([row])['upper']
        result = replay.strict_decision(bound('100'), upper)
        self.assertFalse(result['excludable'])
        self.assertEqual(result['state'], 'NO_TIMELY_SAFE_U')

    def test_negative_or_nonexact_time_and_energy_rejected(self):
        for changes in ({'formed_at_s': '-1'}, {'upper_J': '-1'}, {'upper_J': 'NaN'}, {'committed_at_s': 'Inf'}):
            with self.subTest(changes=changes):
                self.assertIsNone(select([update(**changes)])['upper'])

    def test_budget_boundary_does_not_make_new_U_eligible(self):
        row = update(transferred_at_s='300', observer_completed_at_s='300')
        self.assertIsNone(select([row], build='301')['upper'])

    def test_exact_build_equality_is_not_prior_delivery(self):
        row = update(observer_completed_at_s='10')
        self.assertIsNone(select([row], build='10')['upper'])

    def test_noncause_order_fails_closed(self):
        row = update(formed_at_s='2', committed_at_s='1', transferred_at_s='3', observer_completed_at_s='4')
        result = select([row])
        self.assertIsNone(result['upper'])
        self.assertEqual(result['rejected'][0]['reason'], 'NONCAUSAL_EVIDENCE_TIMES')

    def test_best_eligible_U_not_latest_future_U(self):
        rows = [update(1, upper_J='3'), update(2, upper_J='2'),
            update(3, upper_J='1', observer_completed_at_s='20')]
        self.assertEqual(select(rows)['upper']['source_update_index'], 2)

    def test_exact_tie_is_kept(self):
        result = replay.strict_decision(bound('5/2'), update())
        self.assertEqual(result['state'], 'KEEP_TIE')
        self.assertFalse(result['excludable'])

    def test_sub_float_strict_margin_is_preserved(self):
        from fractions import Fraction
        value = Fraction(5, 2) + Fraction(1, 10**90)
        result = replay.strict_decision(bound(str(value)), update())
        self.assertTrue(result['excludable'])
        self.assertEqual(Fraction(result['difference_J']), Fraction(1, 10**90))
        self.assertFalse(result['production_pruning_authorized'])

    def test_closed_or_filtered_modes_are_not_countable(self):
        base = {'opened': True, 'domain_verified': True, 'remaining_option_count': 1}
        for changes in ({'opened': False}, {'domain_verified': False}, {'remaining_option_count': 0},
                        {'remaining_option_count': -1}, {'remaining_option_count': True}, {'remaining_option_count': '1'}):
            with self.subTest(changes=changes):
                row = dict(base, **changes)
                self.assertFalse(replay.mode_is_countable(row))
        self.assertTrue(replay.mode_is_countable(base))

    def test_global_witness_need_not_satisfy_child(self):
        result = replay.strict_decision(bound('3'), update(), witness_compatible=False, witness_upper_J='1')
        self.assertTrue(result['excludable'])

    def test_compatible_SAFE_warm_contradiction_stops(self):
        with self.assertRaises(ValueError):
            replay.strict_decision(bound('3'), update(), witness_compatible=True, witness_upper_J='5/2')
        with self.assertRaises(ValueError):
            replay.strict_decision(bound('3'), update(), witness_compatible=True)

    def test_compatible_warm_is_preserved_at_tie_or_below(self):
        for value in ('2', '5/2'):
            with self.subTest(value=value):
                result = replay.strict_decision(bound(value), update(), witness_compatible=True, witness_upper_J='5/2')
                self.assertFalse(result['excludable'])

def main():
    started = time.perf_counter()
    before = sha(SOURCE)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PureHelpers)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    after = sha(SOURCE)
    payload = {'protocol': 'K171-independent-pure-helper-fixtures-v1',
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'source_path': SOURCE.relative_to(REPO).as_posix(), 'source_sha256_before': before,
        'source_sha256_after': after, 'source_unchanged': before == after,
        'test_only_synthetic_identity_and_arithmetic': True, 'forbidden_attempts': BLOCKED,
        'scientific_modules_loaded': sorted(k for k in sys.modules if k.split('.')[0] in FORBIDDEN),
        'new_models': 0, 'solver_calls': 0, 'thermal_or_candidate_evaluations': 0,
        'bound_API_calls': 0, 'research_calls': 0, 'wall_s': time.perf_counter() - started,
        'passed': result.wasSuccessful() and before == after and not BLOCKED}
    target = HERE / 'helper_checks_run01.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps(payload, ensure_ascii=False))
    assert payload['passed']

if __name__ == '__main__':
    main()
