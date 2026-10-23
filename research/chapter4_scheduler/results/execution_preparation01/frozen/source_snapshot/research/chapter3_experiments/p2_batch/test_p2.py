"""P2 pure fixtures; mock SAFE values below are not physical research evidence."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import prepare_p2 as r
import p2_entry as p
import p2_dispatch as dispatcher


class InputTests(unittest.TestCase):
    def test_01_only_declared_original_H_high_entry(self):
        for pid in ('base__R1', 'response_R__R1', 'initial_70__R1', 'initial_78__R6'):
            with self.assertRaises(ValueError): p.fresh_input(pid)
            with self.assertRaises(ValueError): p.jobs(pid)
        for pid in p.PROBLEMS:
            d, triple = p.input_declaration(pid); one = triple[2]
            self.assertEqual(one['response_variant'], 'H')
            self.assertEqual((F(one['window_ms']), F(one['start_grid_ms'])), (400, 5))
            for scene in one['scenarios']:
                self.assertEqual(list(map(F, scene['entry']['temperature_degC'])), [78]*4)
                self.assertEqual(list(map(F, scene['maximum_temperature_degC'])), [80]*4)
                self.assertEqual((len(scene['requests']), len(scene['stage_instances']), len(scene['dependencies'])), (2, 6, 4))
                self.assertEqual(scene['entry']['unfinished_work'], [])
            self.assertEqual(len(d['scene_spec']), 2)
            self.assertEqual([len(x) for x in d['first_opened_by_scene'].values()], [2, 2])
            self.assertEqual([len(x) for x in d['linked_opened_by_job']['anchor_linked4'].values()], [4, 4])

    def test_02_exact_twelve_changes_and_all_other_fields_identical(self):
        for pid in p.PROBLEMS:
            c = r.contrast(pid)
            self.assertEqual(len(c['differences']), 12)
            for v in c['differences']:
                if 'temperature_degC' in v['path']:
                    self.assertEqual((F(v['P0']), F(v['P2'])), (50, 78))
            self.assertTrue(c['stage_modes_identical'])
            self.assertFalse(c['thermal_evaluation_performed'])

    def test_03_wrong_entry_limit_response_or_control_rejected(self):
        from inputs import build_instance as original
        import inputs
        for field, value in (('entry', '50'), ('limit', '79'), ('response', 'R'), ('window', '399')):
            def changed(*a, **kw):
                one = original(*a, **kw)
                if field == 'entry': one['scenarios'][0]['entry']['temperature_degC'][0] = value
                elif field == 'limit': one['scenarios'][0]['maximum_temperature_degC'][0] = value
                elif field == 'response': one['response_variant'] = value
                else: one['window_ms'] = value
                return one
            with patch.object(inputs, 'build_instance', side_effect=changed):
                with self.assertRaises(ValueError): p.fresh_input(p.PROBLEMS[0])

    def test_04_mode_or_deadline_drift_not_whitelisted(self):
        original = p.fresh_input
        for kind in ('alpha', 'deadline', 'ablation'):
            def changed(pid, budget=None):
                raw, conf, one = original(pid, budget)
                if kind == 'alpha': one['stage_modes']['A.pre'][0]['alpha'] = '1'
                elif kind == 'deadline': one['scenarios'][0]['requests'][0]['deadline_ms'] = '1'
                else: one['ablation_input'] = False
                return raw, conf, one
            with patch.object(p, 'fresh_input', side_effect=changed):
                with self.assertRaises(ValueError): r.contrast(p.PROBLEMS[0])

    def test_05_slots_rotation_seeds_and_no_reserved_budget(self):
        slots = p.slots()
        self.assertEqual(len(slots), 40)
        self.assertEqual(len({s['slot_id'] for s in slots}), 40)
        self.assertEqual([s['ordinal'] for s in slots], list(range(1, 41)))
        self.assertEqual(sum(s['seconds'] for s in slots), 12000)
        for i, pid in enumerate(p.PROBLEMS):
            self.assertEqual(p.jobs(pid), p.p0.jobs('base__R'+str(i+1)))
            self.assertEqual([x.get('seed') for x in p.jobs(pid) if x['method'] == 'sa'], list(range(101, 106)))
        self.assertEqual(r.empty_ledger()['reserved_method_budget_s'], 0)

    def test_06_exact_scientific_dispatch_and_receipt_lineage(self):
        self.assertEqual(r.lineage_issues(), [])
        self.assertEqual((dispatcher.SECONDS, dispatcher.SCENE_SECONDS, dispatcher.CUT), (300, 60, 10))


class DispatchTests(unittest.TestCase):
    def test_07_all_forty_independent_loaders_and_original_parameters(self):
        from timing import MethodBudget
        import partial_bounds
        retained = []
        with tempfile.TemporaryDirectory() as tmp:
            for slot in p.slots():
                pid = slot['problem_id']; job = next(j for j in p.jobs(pid) if j['id'] == slot['id'])
                definition, _ = p.input_declaration(pid)
                args = {}
                def fake(loader, folder, **kw):
                    args.update(kw)
                    budget = kw.get('budget', MethodBudget(300))
                    config, one = loader(budget)
                    retained.append(one)
                    self.assertEqual(one['id'], pid)
                    self.assertTrue(budget.elapsed >= 0)
                    self.assertEqual(args['seconds'], 300)
                    return {'MOCK_ONLY': True}
                entries = {k: Mock(side_effect=fake) for k in ('whole', 'linked', 'heuristic')}
                entries.update(builder=Mock(), session=Mock())
                with patch.object(partial_bounds, 'independent_lower_bound', return_value={'MOCK_ONLY': True}) as lower:
                    result, identity = dispatcher.execute(job, Path(tmp)/pid, definition, entries)
                self.assertTrue(identity['input_verified']); self.assertTrue(result['MOCK_ONLY'])
                if job['method'] == 'milp':
                    self.assertEqual(args['feedback_kind'], 'conditional')
                    self.assertEqual(args['model_builder'].keywords, {'prefilter_deadlines': True, 'cumulative_precedence': False})
                    self.assertEqual(lower.call_count, 1)
                    self.assertIsNotNone(lower.call_args.args[2])
                elif job['method'] == 'linked_fixed_unit_opp_start':
                    self.assertEqual(args['scene_slice_s'], 60)
                    self.assertEqual(args['shared_deployment'], {'A.pre': 'CPU1', 'A.main': 'NPU0', 'A.post': 'CPU1'})
                    self.assertTrue(args['preeliminate_closed_anchors'])
                    self.assertEqual(args['opened_by_scene'], definition['first_opened_by_scene'])
                    self.assertEqual(args['linked_opened_by_scene'], definition['linked_opened_by_job'][job['id']])
                    self.assertEqual(args['builder_options'], dispatcher.settings()[1])
                    self.assertEqual(args['session_factory'].keywords, {'cut_max_iterations': 10})
                    self.assertEqual(lower.call_count, 0)
                else:
                    self.assertTrue(args['allow_auto_low']); self.assertEqual(args['seed'], job['seed'])
                    self.assertEqual(args['method'], job['method']); self.assertEqual(lower.call_count, 0)
        self.assertEqual(len({id(one) for one in retained}), 40)
        self.assertEqual(len({id(one['scenarios']) for one in retained}), 40)

    def test_08_input_identity_drift_before_method_work(self):
        from timing import MethodBudget
        d, _ = p.input_declaration(p.PROBLEMS[0]); d['input_identities']['input_sha256'] = 'drift'
        def fake(loader, *a, **kw): return loader(MethodBudget(300))
        entries = {k: Mock(side_effect=fake) for k in ('whole', 'linked', 'heuristic')}
        entries.update(builder=Mock(), session=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                dispatcher.execute({'id': 'heft', 'method': 'heft', 'seed': None}, Path(tmp), d, entries)

    def test_09_old_or_undeclared_method_rejected(self):
        d, _ = p.input_declaration(p.PROBLEMS[0])
        with self.assertRaises(ValueError): dispatcher.execute({'id': 'sa106', 'method': 'sa', 'seed': 106}, Path('.'), d, {})


class PreparationTests(unittest.TestCase):
    def report(self):
        return {'protocol': r.PROTOCOL, 'passed': True, 'tests_run': 1, 'errors': 0,
            'failures': 0, 'skipped': 0, 'error': None, 'source_sha256': r.sources(),
            'source_unchanged': True, 'prior_archives_unchanged': True,
            'blocked_calls': {'MOCK_ONLY': 0}, **dict.fromkeys(r.COUNTERS, 0)}

    def test_10_preparation_never_authorizes_execution_and_cannot_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); gate = root/'gate.json'; r.save(gate, self.report())
            out = root/'prepared'; result = r.prepare(out, gate)
            self.assertFalse(result['authorised_to_execute'])
            self.assertEqual(r.admission(out), result)
            self.assertEqual(r.read(out/'ledger.json'), r.empty_ledger())
            self.assertFalse((out/'claims').exists())
            self.assertFalse(r.read(out/'declaration.json')['execution_budget_approved'])
            with self.assertRaises(FileExistsError): r.prepare(out, gate)
            d = r.read(out/'declaration.json'); d['authorised_to_execute'] = True; r.save(out/'declaration.json', d)
            with self.assertRaises(ValueError): r.admission(out)

    def test_11_bad_checks_drift_and_real_call_counter_rejected(self):
        for key, value in (('passed', False), ('source_sha256', {}), ('prior_archives_unchanged', False),
                ('research_calls', 1), ('thermal_evaluations', 1), ('blocked_calls', {'heat': 1}), ('skipped', 1)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); g = self.report(); g[key] = value; r.save(root/'gate.json', g)
                with self.assertRaises(ValueError): r.prepare(root/'no_output', root/'gate.json')
                self.assertFalse((root/'no_output').exists())

    def test_12_input_snapshot_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); r.save(root/'gate.json', self.report()); out = root/'prepared'
            r.prepare(out, root/'gate.json')
            path = out/'inputs'/p.PROBLEMS[0]/'instance.json'
            obj = r.read(path); obj['scenarios'][0]['entry']['temperature_degC'][0] = '50'; r.save(path, obj)
            with self.assertRaises(ValueError): r.admission(out)

    def test_13_run_cli_refused(self):
        with self.assertRaises(SystemExit) as error: r.main(['run'])
        self.assertEqual(error.exception.code, 2)


class ReceiptTests(unittest.TestCase):
    def test_14_bound_P2_full_safety_receipt_and_cross_condition_rejection(self):
        # Reuse the archived receipt-contract fixture, replacing identity and entry only.
        from test_p0 import ReceiptTests as OriginalReceiptTests
        import audit_heuristic
        old, candidate, ev = OriginalReceiptTests().receipt('base__R1')
        definition, _ = p.input_declaration(p.PROBLEMS[0])
        ev['problem_id'] = p.PROBLEMS[0]
        candidate['problem_id'] = p.PROBLEMS[0]
        for scene in ev['scenes'].values():
            scene['peaks_degC'] = {node: ['78', '78'] for node in scene['peaks_degC']}
        self.assertEqual(audit_heuristic.receipt_issues(ev, candidate, definition), [])
        ev['problem_id'] = 'response_R__R1'
        self.assertTrue(audit_heuristic.receipt_issues(ev, candidate, definition))
        ev['problem_id'] = p.PROBLEMS[0]
        sid = next(iter(ev['scenes']))
        ev['scenes'][sid]['peaks_degC']['CPU1'] = ['80', '81']
        self.assertTrue(audit_heuristic.receipt_issues(ev, candidate, definition))
