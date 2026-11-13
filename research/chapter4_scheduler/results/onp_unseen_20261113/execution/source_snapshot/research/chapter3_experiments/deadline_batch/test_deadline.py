"""Deadline preparation fixtures; mocked energies are not research results."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import prepare_deadline as r
import deadline_entry as p
import deadline_dispatch as dispatcher


class InputTests(unittest.TestCase):
    def test_01_only_declared_deadline_ids(self):
        for pid in ('base__R1', 'response_R__R1', 'initial_78__R1', 'beta_0.8__R1', 'beta_1.0__R6'):
            with self.assertRaises(ValueError): p.fresh_input(pid)
            with self.assertRaises(ValueError): p.jobs(pid)
        for pid in p.PROBLEMS:
            d, (_, _, one) = p.input_declaration(pid)
            self.assertEqual(one['response_variant'], 'H')
            self.assertEqual(F(one['settings']['deadline_beta']), 1)
            self.assertEqual((F(one['window_ms']), F(one['start_grid_ms'])), (400, 5))
            for scene in one['scenarios']:
                self.assertEqual(list(map(F, scene['entry']['temperature_degC'])), [50]*4)
                self.assertEqual(list(map(F, scene['maximum_temperature_degC'])), [80]*4)
                self.assertEqual((len(scene['requests']), len(scene['stage_instances']), len(scene['dependencies'])), (2, 6, 4))
            self.assertEqual([len(v) for v in d['first_opened_by_scene'].values()], [2, 2])
            self.assertEqual([len(v) for v in d['linked_opened_by_job']['anchor_linked4'].values()], [4, 4])

    def test_02_exact_deadline_table_and_thirteen_changes(self):
        expected = [('95', '121', '110'), ('76', '145.2', '110'),
                    ('114', '96.8', '110'), ('95', '96.8', '132'), ('95', '145.2', '88')]
        for pid, values in zip(p.PROBLEMS, expected):
            contrast = r.contrast(pid)
            self.assertEqual(len(contrast['differences']), 13)
            self.assertTrue(contrast['stage_modes_identical'])
            self.assertFalse(contrast['thermal_evaluation_performed'])
            deadlines = {v['application']: F(v['relative_deadline_ms']) for v in contrast['deadlines']}
            self.assertEqual(deadlines, dict(zip('ABC', map(F, values))))
            for v in contrast['deadlines']:
                self.assertEqual(F(v['deadline_ms'])-F(v['release_ms']), F(v['CPU_H_reference_chain_ms']))
            for v in contrast['differences']:
                if v['path'].endswith('deadline_ms'):
                    self.assertEqual(F(v['Deadline'])/F(v['P0']), F(10, 13))

    def test_03_wrong_response_temperature_grid_or_deadline_rejected(self):
        from inputs import build_instance as original
        import inputs
        for field in ('response', 'entry', 'limit', 'grid', 'deadline'):
            def changed(*args, **kw):
                one = original(*args, **kw)
                if field == 'response': one['response_variant'] = 'R'
                elif field == 'entry': one['scenarios'][0]['entry']['temperature_degC'][0] = '78'
                elif field == 'limit': one['scenarios'][0]['maximum_temperature_degC'][0] = '90'
                elif field == 'grid': one['start_grid_ms'] = '1'
                else: one['scenarios'][0]['requests'][0]['deadline_ms'] = '94'
                return one
            with patch.object(inputs, 'build_instance', side_effect=changed):
                with self.assertRaises(ValueError): p.fresh_input(p.PROBLEMS[0])

    def test_04_unwhitelisted_mode_reference_and_ablation_changes_rejected(self):
        original = p.fresh_input
        for field in ('mode', 'reference', 'ablation', 'release'):
            def changed(pid, budget=None):
                raw, conf, one = original(pid, budget)
                if field == 'mode': one['stage_modes']['A.pre'][0]['alpha'] = '1'
                elif field == 'reference': one['scenarios'][0]['requests'][0]['reference_CPU_H_chain_ms'] = '94'
                elif field == 'release': one['scenarios'][0]['requests'][0]['release_ms'] = '1'
                else: one['ablation_input'] = True
                return raw, conf, one
            with patch.object(p, 'fresh_input', side_effect=changed):
                with self.assertRaises(ValueError): r.contrast(p.PROBLEMS[0])

    def test_05_forty_slots_and_same_method_rotation(self):
        rows = p.slots()
        self.assertEqual(len(rows), 40)
        self.assertEqual(len({v['slot_id'] for v in rows}), 40)
        self.assertEqual([v['ordinal'] for v in rows], list(range(1, 41)))
        self.assertEqual(sum(v['seconds'] for v in rows), 12000)
        for i, pid in enumerate(p.PROBLEMS):
            self.assertEqual(p.jobs(pid), p.p0.jobs('base__R'+str(i+1)))
            self.assertEqual([v['seed'] for v in p.jobs(pid) if v['method'] == 'sa'], list(range(101, 106)))
        self.assertEqual(r.empty_ledger()['reserved_method_budget_s'], 0)

    def test_06_exact_dispatch_lineage_and_prior_sources(self):
        self.assertEqual(r.lineage_issues(), [])
        self.assertEqual(len(r.read(r.BASE)['source_sha256']), 224)
        self.assertTrue(all(r.sources()[name] == digest
                            for name, digest in r.read(r.BASE)['source_sha256'].items()))
        self.assertEqual((dispatcher.SECONDS, dispatcher.SCENE_SECONDS, dispatcher.CUT), (300, 60, 10))


class DispatchTests(unittest.TestCase):
    def test_07_forty_independent_loaders_same_scientific_arguments(self):
        from timing import MethodBudget
        import partial_bounds
        retained = []
        with tempfile.TemporaryDirectory() as tmp:
            for slot in p.slots():
                pid = slot['problem_id']
                job = next(v for v in p.jobs(pid) if v['id'] == slot['id'])
                definition, _ = p.input_declaration(pid)
                args = {}
                def fake(loader, folder, **kw):
                    args.update(kw)
                    budget = kw.get('budget') or MethodBudget(300)
                    config, one = loader(budget)
                    retained.append(one)
                    self.assertEqual(one['id'], pid)
                    self.assertEqual(F(one['settings']['deadline_beta']), 1)
                    self.assertEqual(args['seconds'], 300)
                    return {'MOCK_ONLY': True}
                entries = {k: Mock(side_effect=fake) for k in ('whole', 'linked', 'heuristic')}
                entries.update(builder=Mock(), session=Mock())
                with patch.object(partial_bounds, 'independent_lower_bound', return_value={'MOCK_ONLY': True}) as lower:
                    result, identity = dispatcher.execute(job, Path(tmp)/pid, definition, entries)
                self.assertTrue(identity['input_verified'])
                self.assertTrue(result['MOCK_ONLY'])
                if job['method'] == 'milp':
                    self.assertEqual(args['feedback_kind'], 'conditional')
                    self.assertEqual(args['model_builder'].keywords,
                                     {'prefilter_deadlines': True, 'cumulative_precedence': False})
                    self.assertEqual(lower.call_count, 1)
                elif job['method'] == 'linked_fixed_unit_opp_start':
                    self.assertEqual(args['scene_slice_s'], 60)
                    self.assertEqual(args['shared_deployment'], {'A.pre':'CPU1', 'A.main':'NPU0', 'A.post':'CPU1'})
                    self.assertTrue(args['preeliminate_closed_anchors'])
                    self.assertEqual(args['opened_by_scene'], definition['first_opened_by_scene'])
                    self.assertEqual(args['linked_opened_by_scene'], definition['linked_opened_by_job'][job['id']])
                    self.assertEqual(args['builder_options'], dispatcher.settings()[1])
                    self.assertEqual(args['session_factory'].keywords, {'cut_max_iterations': 10})
                    self.assertEqual(lower.call_count, 0)
                else:
                    self.assertTrue(args['allow_auto_low'])
                    self.assertEqual(args['seed'], job['seed'])
                    self.assertEqual(args['method'], job['method'])
                    self.assertEqual(lower.call_count, 0)
        self.assertEqual(len({id(v) for v in retained}), 40)
        self.assertEqual(len({id(v['scenarios']) for v in retained}), 40)

    def test_08_identity_drift_stops_before_method_work(self):
        from timing import MethodBudget
        d, _ = p.input_declaration(p.PROBLEMS[0])
        d['input_identities']['input_sha256'] = 'wrong'
        def fake(loader, *args, **kw): return loader(MethodBudget(300))
        entries = {k: Mock(side_effect=fake) for k in ('whole', 'linked', 'heuristic')}
        entries.update(builder=Mock(), session=Mock())
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                dispatcher.execute({'id':'heft', 'method':'heft', 'seed':None}, Path(tmp), d, entries)

    def test_09_unknown_method_rejected(self):
        d, _ = p.input_declaration(p.PROBLEMS[0])
        with self.assertRaises(ValueError):
            dispatcher.execute({'id':'sa106', 'method':'sa', 'seed':106}, Path('.'), d, {})


class PreparationTests(unittest.TestCase):
    def gate(self):
        return {'protocol': r.PROTOCOL, 'passed': True, 'tests_run': 1, 'errors': 0,
            'failures': 0, 'skipped': 0, 'error': None, 'source_sha256': r.sources(),
            'source_unchanged': True, 'prior_archives_unchanged': True,
            'blocked_calls': {'MOCK_ONLY': 0}, **dict.fromkeys(r.COUNTERS, 0)}

    def test_10_prepare_stays_unapproved_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            r.save(root/'checks.json', self.gate())
            out = root/'prepared'
            result = r.prepare(out, root/'checks.json')
            self.assertFalse(result['authorised_to_execute'])
            self.assertEqual(r.admission(out), result)
            self.assertEqual(r.read(out/'ledger.json'), r.empty_ledger())
            self.assertFalse((out/'claims').exists())
            self.assertFalse(r.read(out/'declaration.json')['execution_budget_approved'])
            with self.assertRaises(FileExistsError): r.prepare(out, root/'checks.json')
            d = r.read(out/'declaration.json')
            d['authorised_to_execute'] = True
            r.save(out/'declaration.json', d)
            with self.assertRaises(ValueError): r.admission(out)

    def test_11_failed_drift_or_consumed_precheck_cannot_prepare(self):
        for key, value in (('passed',False), ('source_sha256',{}), ('prior_archives_unchanged',False),
                           ('research_calls',1), ('thermal_evaluations',1), ('blocked_calls',{'heat':1}), ('skipped',1)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                gate = self.gate()
                gate[key] = value
                r.save(root/'gate.json', gate)
                with self.assertRaises(ValueError): r.prepare(root/'absent', root/'gate.json')
                self.assertFalse((root/'absent').exists())

    def test_12_input_and_ledger_tampering_rejected(self):
        for kind in ('input', 'ledger'):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                r.save(root/'gate.json', self.gate())
                out = root/'prepared'
                r.prepare(out, root/'gate.json')
                if kind == 'input':
                    path = out/'inputs'/p.PROBLEMS[0]/'instance.json'
                    obj = r.read(path)
                    obj['scenarios'][0]['requests'][0]['deadline_ms'] = '123.5'
                else:
                    path = out/'ledger.json'
                    obj = r.read(path)
                    obj['consumed'] = 1
                r.save(path, obj)
                with self.assertRaises(ValueError): r.admission(out)

    def test_13_run_cli_is_not_an_authorization(self):
        with self.assertRaises(SystemExit) as error: r.main(['run'])
        self.assertEqual(error.exception.code, 2)
