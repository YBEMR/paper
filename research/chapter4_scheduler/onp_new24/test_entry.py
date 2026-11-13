"""Only mocks; never generate U07-U10 or call a real evaluator in preflight."""
import ast
from contextlib import redirect_stdout
import inspect
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from . import run, inputs
from ..onp import method as filtered
from ..blocking import method as original, core
from ..i1.initializer import run_heft_i1
from ..tests.test_method import FakeClock
from timing import MethodBudget


class EntryTests(unittest.TestCase):
    def cases(self):
        return [{'case_id': c, 'root_id': c[:3], 'stages_per_scene': 24} for c in run.CASES]

    def test_fixed_roots_order_and_budget(self):
        p = inputs.fixed_plan()
        self.assertEqual(p['roots'], [{'root_id': r, 'seed': s} for r, s in inputs.ROOTS])
        self.assertEqual(p['namespace'], 'ch4-independent-onp24-v1')
        self.assertEqual(p['scales'], [24])
        self.assertEqual([(s['case_id'], s['arm']) for s in run.slots(self.cases())], list(run.ORDER))
        self.assertEqual(run.BUDGETS['method_s'], 300)
        self.assertEqual(run.BUDGETS['I1_new_work_admission_s'], 180)
        self.assertEqual(run.BUDGETS['post_s'], 60)
        with self.assertRaises(ValueError):
            run.slots(self.cases() + self.cases()[:1])
        with self.assertRaises(ValueError):
            run.slots([{**c, 'stages_per_scene': 12} for c in self.cases()])

    def test_all_frozen_536_sources_unchanged(self):
        old = run.read(run.OLD / 'plan.json')
        self.assertEqual(len(old['source_sha256']), 536)
        for n, h in old['source_sha256'].items():
            self.assertEqual(run.sha(run.REPO / n), h, n)

    def test_plan_precedes_mock_generation_and_bindings_restore(self):
        previous = (inputs.ROOTS, inputs.NAMESPACE, inputs.fixed_plan)
        parent = run.REPO / '.runtime'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='onp-unseen-entry-') as tmp:
            out = Path(tmp) / 'generated'
            seen = []
            def fake(catalog, config, root, seed, plan):
                self.assertEqual(run.read(out / 'input_plan.json'), inputs.fixed_plan())
                seen.append((root, seed))
                return {'config': {'MOCK_ONLY': True}, 'instance': {'MOCK_ONLY': True}}, {'metrics': {'MOCK_ONLY': True}}
            with patch.object(inputs, 'construct', side_effect=fake):
                result = inputs.build_inputs(out)
                with self.assertRaises(FileExistsError):
                    inputs.build_inputs(out)
            self.assertEqual(seen, list(inputs.ROOTS))
            self.assertEqual(len(result['cases']), 4)
            self.assertEqual(result['counters']['thermal_evaluations'], 0)
        self.assertEqual(previous, (inputs.ROOTS, inputs.NAMESPACE, inputs.fixed_plan))

    def test_exact_shared_I1_evaluator_root_and_correct_route(self):
        parent = run.REPO / '.runtime'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='onp-unseen-dispatch-') as tmp:
            for arm in ('HEFT', 'ON', 'ON_P', 'OFF_P'):
                b = MethodBudget(300, clock=FakeClock())
                ev, seen, old = object(), [], core.reconstruct
                def stub(loader, folder, **kw):
                    Path(folder).mkdir()
                    seen.append(kw)
                    return 'MOCK_ONLY'
                with patch('research.chapter4_scheduler.validation.lifecycle.execute_heft', side_effect=stub) as h, \
                     patch.object(original, 'execute_reconstruction', side_effect=stub) as o, \
                     patch.object(filtered, 'execute_reconstruction', side_effect=stub) as p:
                    self.assertEqual(run.dispatch(arm, None, Path(tmp) / arm, b, original.Bindings(None, ev, 'REAL_CORE')), 'MOCK_ONLY')
                self.assertEqual((h.call_count, o.call_count, p.call_count),
                                 (1, 0, 0) if arm == 'HEFT' else ((0, 1, 0) if arm == 'ON' else (0, 0, 1)))
                kw = seen[0]
                self.assertIs(kw['bindings'].initializer, run_heft_i1)
                self.assertIs(kw['bindings'].evaluator, ev)
                self.assertIs(kw['budget'], b)
                self.assertEqual(kw['bindings'].kind, 'REAL_I1')
                if arm != 'HEFT':
                    self.assertEqual(kw['allow_blocking_edges'], arm.startswith('ON'))
                self.assertIs(core.reconstruct, old)
        with self.assertRaises(ValueError):
            run.dispatch('SA', None, None, None, None)

    def test_controller_only_changes_worker_module(self):
        before = inspect.getsource(run.frozen.batch).replace('research.chapter4_scheduler.onp.run', 'research.chapter4_scheduler.onp_new24.run')
        self.assertEqual(ast.dump(ast.parse(before)), ast.dump(ast.parse(inspect.getsource(run.batch))))

    def controller(self, technical):
        parent = run.REPO / '.runtime'
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent, prefix='onp-unseen-controller-') as tmp:
            out = Path(tmp)
            plan = {'cases': self.cases(), 'slots': run.slots(self.cases()), 'subject_commit': 'MOCK_ONLY'}
            run.save(out / 'plan.json', plan)
            def fake(command, **kw):
                sid = command[command.index('--slot') + 1]
                if not technical:
                    run.save(out / 'calls' / sid / 'method_return.json',
                             {'normal_stop': True, 'has_SAFE_archive': False, 'terminal': 'NORMAL_NO_SAFE'})
                return subprocess.CompletedProcess(command, int(technical), 'MOCK_ONLY', '')
            with patch.object(run, 'verify'), patch.object(run.subprocess, 'run', side_effect=fake) as launch, redirect_stdout(io.StringIO()):
                self.assertEqual(run.batch(out), int(technical))
            self.assertEqual(launch.call_count, 1 if technical else 16)
            b, s = run.read(out / 'batch_return.json'), run.read(out / 'summary.json')
            self.assertEqual(b['retry_count'], 0)
            self.assertEqual(len(s['rows']), 16)
            self.assertEqual(s['protocol'], run.PROTOCOL)
            self.assertEqual(sum(x['status'] == 'NOT_RUN_TECHNICAL_STOP' for x in b['slots']), 15 if technical else 0)

    def test_normal_no_SAFE_keeps_all_slots(self):
        self.controller(False)

    def test_technical_failure_stops_without_retry(self):
        self.controller(True)

    def test_reuses_dispatch_and_metrics_without_edits(self):
        self.assertIs(run.dispatch, run.previous.dispatch)
        self.assertIs(run.metrics, run.previous.metrics)

    def test_balanced_order_and_distinct_roots(self):
        from collections import Counter
        self.assertEqual(len(set(inputs.ROOTS)), 4)
        self.assertEqual(len({seed for _, seed in inputs.ROOTS}), 4)
        sequences = [[arm for case, arm in run.ORDER if case == c] for c in run.CASES]
        expected = {'HEFT', 'ON', 'ON_P', 'OFF_P'}
        for position in range(4):
            self.assertEqual({seq[position] for seq in sequences}, expected)
        edges = Counter((seq[i], seq[i+1]) for seq in sequences for i in range(3))
        self.assertEqual(len(edges), 12)
        self.assertEqual(set(edges.values()), {1})

    def test_generation_failure_retained_without_retry(self):
        parent = run.REPO / '.runtime'
        with tempfile.TemporaryDirectory(dir=parent, prefix='onp-scale-failure-') as tmp:
            out = Path(tmp) / 'generation'
            with patch.object(inputs, 'construct', side_effect=RuntimeError('MOCK_ONLY')) as gen:
                with self.assertRaisesRegex(RuntimeError, 'MOCK_ONLY'):
                    inputs.build_inputs(out)
            self.assertEqual(gen.call_count, 1)
            failed = run.read(out / 'generation_failure.json')
            self.assertEqual(failed['case_id'], 'U07__n24')
            self.assertEqual(failed['retry_count'], 0)
            self.assertEqual(failed['replacement_count'], 0)
            self.assertFalse((out / 'U08__n24').exists())

    def test_direct24_only_changes_scale_of_frozen_construct(self):
        from ..i1 import new_inputs
        before = inspect.getsource(new_inputs.construct).replace('__n12', '__n24').replace('scale=12,', 'scale=24,')
        before = before.replace('[12,12]', '[24,24]').replace('TWELVE_STAGES', 'TWENTYFOUR_STAGES')
        self.assertEqual(ast.dump(ast.parse(before)), ast.dump(ast.parse(inspect.getsource(inputs.construct))))

    def test_separate_manual_direct24_fixture(self):
        from research.chapter3_workload_calibration.profiles import load_catalog
        p = inputs.fixed_plan()
        p['namespace'] = 'ONP_NEW24_MANUAL_TEST_ONLY'
        config = run.read(inputs.original.SOURCE_CONFIG)
        catalog = load_catalog(inputs.original.SOURCE_CONFIG)
        with patch('heft_method.run_heft', side_effect=AssertionError('HEFT_FORBIDDEN')):
            adapted, evidence = inputs.construct(catalog, config, 'TEST_ONLY', 1, p)
        self.assertEqual(evidence['metrics']['stages_per_scene'], [24, 24])
        self.assertEqual(evidence['metrics']['shared_stage_identities'], 32)
        self.assertEqual(evidence['static_check']['state'], 'SCHEDULE_VALID_THERMAL_UNCHECKED')
        self.assertIsNone(evidence['adaptation_receipt']['formal_initial_solution'])
        self.assertIsNone(evidence['adaptation_receipt']['fixed_deployment'])
        raw = evidence['unprojected_eight_scene_bundle']
        self.assertEqual(raw['provenance']['scale'], 24)
        self.assertEqual(raw['time_contract']['derivation']['axis'], 'BASE')
        self.assertIsNone(raw['time_contract']['derivation']['parent_contract_hash'])


if __name__ == '__main__':
    unittest.main()
