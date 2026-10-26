"""Pure lifecycle fixtures: injected receipts, zero physical evaluation."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import precheck as p


def safe(view, candidate, **kwargs):
    return {'state': 'SAFE', 'scenes': {s['id']: {'complete': True}
                                      for s in view['scenarios']}}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.directory = Path(self.temp.name) / 'frozen'
        self.protocol = p.freeze(Path(os.path.relpath(self.directory, Path.cwd())))
        self.identity = p.digest(self.directory / 'precheck_protocol.json')

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, fake):
        return p.execute(self.directory, expected_protocol_sha256=self.identity, evaluator=fake)

    def test_one_witness_plus_four_fixed_costs_and_exclusive_claim(self):
        seen = []
        def fake(view, candidate, **kwargs):
            self.assertEqual(p.validate_schedule(view, candidate)['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
            seen.append((len(view['scenarios']), kwargs['budget'].seconds))
            return safe(view, candidate)
        terminal = self.execute(fake)
        self.assertEqual(terminal['state'], 'PRECHECK_COMPLETE')
        self.assertEqual(terminal['calls_consumed'], 5)
        self.assertEqual(terminal['scene_trajectories'], 6)
        self.assertEqual(seen, [(2, 60), (1, 15), (1, 15), (1, 15), (1, 15)])
        self.assertEqual(sum(x['group_count'] for x in terminal['cost_estimate']['group_terms']), 1550)
        with self.assertRaises(FileExistsError): self.execute(fake)

    def test_unsafe_witness_stops_without_searching_other_seed(self):
        out = self.execute(lambda *a, **k: {'state': 'THERMAL_VIOLATION', 'scenes': {}})
        self.assertEqual(out['calls_consumed'], 1)
        self.assertFalse(out['full_witness_SAFE'])
        self.assertIsNone(out['cost_estimate'])

    def test_first_unresolved_cost_stops_remaining(self):
        def fake(view, candidate, **kwargs):
            return safe(view, candidate) if len(view['scenarios']) == 2 else {'state': 'UNRESOLVED', 'scenes': {}}
        out = self.execute(fake)
        self.assertEqual(out['calls_consumed'], 2)
        self.assertTrue(out['full_witness_SAFE'])
        self.assertIsNone(out['cost_estimate'])

    def test_exception_consumes_attempt_without_retry(self):
        def fail(*a, **k): raise ValueError('fixture_failure')
        out = self.execute(fail)
        self.assertEqual(out['calls_consumed'], 1)
        self.assertEqual(out['receipts_formed'], 0)
        self.assertIn('fixture_failure', out['reason'])

    def test_late_SAFE_receipt_is_not_precheck_pass(self):
        def fake(view, candidate, **kwargs):
            kwargs['budget'].deadline = p.time.monotonic() - 1
            return safe(view, candidate)
        out = self.execute(fake)
        self.assertEqual(out['state'], 'STOPPED')
        self.assertEqual(out['calls_consumed'], 1)
        self.assertFalse(out['full_witness_SAFE'])
        self.assertIsNone(out['cost_estimate'])

    def test_input_drift_rejected_before_claim(self):
        with (self.directory / 'restricted_input.json').open('a') as stream: stream.write(' ')
        with self.assertRaisesRegex(ValueError, 'drift'): self.execute(safe)
        self.assertFalse((self.directory / 'execution_claim.json').exists())

    def test_protocol_drift_rejected_before_claim(self):
        with (self.directory / 'precheck_protocol.json').open('a') as stream: stream.write(' ')
        with self.assertRaisesRegex(ValueError, 'Protocol identity'): self.execute(safe)
        self.assertFalse((self.directory / 'execution_claim.json').exists())

    def test_single_scene_projection_preserves_physics_and_explicit_domain(self):
        instance = json.loads((self.directory / 'restricted_input.json').read_bytes())
        original = deepcopy(instance)
        samples = json.loads((self.directory / 'cost_samples.json').read_bytes())
        for sample in samples:
            sid = sample['scene_id']
            view = p.single_scene_view(instance, sid)
            self.assertEqual(view['platform'], instance['platform'])
            self.assertEqual(view['execution_rules'], instance['execution_rules'])
            self.assertEqual(view['scenarios'][0]['entry'], next(s for s in instance['scenarios'] if s['id'] == sid)['entry'])
            self.assertEqual(view['scenarios'][0]['weight'], '1')
            self.assertEqual(set(view['start_domain']['by_scene_stage_ms']), {sid})
            self.assertEqual(p.validate_schedule(view, sample['candidate'])['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertEqual(instance, original)

    def test_cost_samples_selected_without_thermal_results(self):
        counts = json.loads((self.directory / 'domain_counts.json').read_bytes())
        samples = json.loads((self.directory / 'cost_samples.json').read_bytes())
        self.assertEqual([s['group_count'] for s in samples], [450, 650, 90, 360])
        self.assertEqual(len(samples), 4)
        self.assertEqual(counts['scene_evaluations_for_full_coverage'], 1550)
        self.assertFalse((self.directory / 'execution_claim.json').exists())

    def test_absolute_root_deadline_cannot_be_refilled(self):
        now = [10.0]
        budget = p.CappedBudget(15, 12, clock=lambda: now[0])
        self.assertEqual(budget.deadline, 12)
        now[0] = 12
        with self.assertRaises(p.Exhausted): budget.check()


if __name__ == '__main__':
    with patch('subprocess.Popen', side_effect=AssertionError('Native process forbidden')):
        unittest.main(verbosity=2)
