"""Pure checks of the small-domain contract; no production evaluator import."""
from copy import deepcopy
from fractions import Fraction as Q
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

import design_static as d


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(d.SOURCE.read_bytes())
        cls.instance, _ = d.make_domain(cls.original)

    def test_original_source_bytes(self):
        self.assertEqual(hashlib.sha256(d.SOURCE.read_bytes()).hexdigest(), d.SOURCE_SHA256)

    def test_twelve_executions_nine_shared_identities(self):
        self.assertEqual(sum(len(s['stage_instances']) for s in self.instance['scenarios']), 12)
        self.assertEqual(len(self.instance['stage_modes']), 9)
        self.assertEqual(self.instance['scenarios'], self.original['scenarios'])

    def test_physical_fields_verbatim(self):
        for key in ('platform', 'execution_rules', 'settings', 'response_variant', 'window_ms', 'start_grid_ms'):
            self.assertEqual(self.instance[key], self.original[key])

    def test_modes_are_original_subsets(self):
        for key, modes in self.instance['stage_modes'].items():
            self.assertTrue(all(m in self.original['stage_modes'][key] for m in modes))
            if key.endswith('.main'):
                self.assertEqual(len(modes), 4)
                self.assertEqual({m['opp_id'] for m in modes}, {'M', 'H'})
                self.assertEqual(len({m['unit_id'] for m in modes}), 2)
            else:
                self.assertEqual(len(modes), 1)

    def test_all_starts_on_original_grid(self):
        for scene in self.instance['scenarios']:
            starts = self.instance['start_domain']['by_scene_stage_ms'][scene['id']]
            self.assertEqual(set(starts), {s['id'] for s in scene['stage_instances']})
            for stage in scene['stage_instances']:
                for start in starts[stage['id']]:
                    self.assertEqual(Q(start) % 5, 0)
                    self.assertGreaterEqual(Q(start), 0)
                    self.assertLessEqual(Q(start), 400)
                if stage['chain_position'] == 1:
                    self.assertEqual(len(starts[stage['id']]), 2)

    def test_half_open_boundary_not_overlap(self):
        self.assertFalse(d.overlap({'start': Q(0), 'end': Q(5)}, {'start': Q(5), 'end': Q(6)}))
        self.assertTrue(d.overlap({'start': Q(0), 'end': Q(5)}, {'start': Q(4), 'end': Q(6)}))

    def test_shared_cpu_opp_conflict(self):
        scene = {'requests': [{'id': 'a', 'release_ms': '0', 'deadline_ms': '10'},
                              {'id': 'b', 'release_ms': '0', 'deadline_ms': '10'}],
                 'dependencies': []}
        rows = [dict(id='a', request_id='a', start=Q(0), end=Q(5), unit_id='CPU1', domain_id='CPU', opp_id='H'),
                dict(id='b', request_id='b', start=Q(0), end=Q(5), unit_id='CPU2', domain_id='CPU', opp_id='M')]
        self.assertFalse(d.is_legal(rows, scene))
        rows[1]['opp_id'] = 'H'
        self.assertTrue(d.is_legal(rows, scene))
        rows[1]['unit_id'] = 'CPU1'
        self.assertFalse(d.is_legal(rows, scene))

    def test_dependencies_and_deadlines(self):
        scene = {'requests': [{'id': 'r', 'release_ms': '0', 'deadline_ms': '10'}],
                 'dependencies': [['a', 'b']]}
        rows = [dict(id='a', request_id='r', start=Q(0), end=Q(5), unit_id='CPU1', domain_id='CPU', opp_id='H'),
                dict(id='b', request_id='r', start=Q(5), end=Q(10), unit_id='GPU0', domain_id='GPU', opp_id='H')]
        self.assertTrue(d.is_legal(rows, scene))
        broken = deepcopy(rows)
        broken[1]['start'] = Q(4)
        self.assertFalse(d.is_legal(broken, scene))
        rows[1]['end'] = Q(11)
        self.assertFalse(d.is_legal(rows, scene))


if __name__ == '__main__':
    started = time.perf_counter()
    stream = io.StringIO()
    run = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Contract))
    text = stream.getvalue()
    (d.HERE / 'pure_tests.txt').write_text(text, encoding='utf-8')
    receipt = {'passed': run.wasSuccessful(), 'tests_run': run.testsRun,
               'failures': len(run.failures), 'errors': len(run.errors),
               'wall_s': time.perf_counter() - started,
               'scope': 'Exact domain contract and synthetic timing/resource checks only',
               'optimization_calls': 0, 'thermal_integrations': 0,
               'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), d.HERE / 'design_static.py')},
               'original_input_sha256': d.SOURCE_SHA256}
    (d.HERE / 'precheck.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(text, end='')
    sys.exit(0 if run.wasSuccessful() else 1)
