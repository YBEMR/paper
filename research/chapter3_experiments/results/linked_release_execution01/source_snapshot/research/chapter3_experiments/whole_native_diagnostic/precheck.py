"""K168 prepare-only checks; stdlib-only, no scientific imports or calls.

Use a fresh --out. Hand-written JSON fixtures test the new management layer.
One real preparation only hashes/reads frozen sources and archived JSON; it
does not construct fresh research inputs, a model, a payload or a candidate.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import prepare as manager
import recipe


REPO = Path(__file__).resolve().parents[3]
OUT = None


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n',
                    encoding='utf8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ScientificGuardViolation(KeyboardInterrupt):
    pass


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.folder = OUT / 'fixtures' / self._testMethodName
        self.folder.mkdir(parents=True, exist_ok=False)
        self.repo = self.folder / 'fake_repo'
        self.repo.mkdir()
        raw = {'fixture': 'raw, not a research input'}
        config = {'fixture': 'effective, not a research input'}
        instance = {'id': 'beta_1.0__R2', 'response_variant': 'H',
                    'settings': {'deadline_beta': '1.0'},
                    'window_ms': '400', 'start_grid_ms': '5',
                    'execution_rules': {'idle_policy': 'auto_low_immediate_v1',
                                        'idle_holds_last_opp': False},
                    'scenarios': [dict(id=name,
                        entry={'temperature_degC': ['50', '50']},
                        maximum_temperature_degC=['80', '80']) for name in ('AB', 'AC')]}
        identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                              map(manager.canonical, (raw, config, instance))))
        self.records = {
            manager.BASE + 'config_v01.json': raw,
            manager.OLD_CALL + 'input_config.json': config,
            manager.OLD_CALL + 'input_instance.json': instance,
            manager.ORIGINAL_DECLARATION: {'inputs': {'beta_1.0__R2': {
                'input_identities': identities}}},
            manager.OLD + 'ledger.json': {'consumed_old': 16,
                'remaining_old': 24, 'old_budget_must_not_authorize': True},
            'old_claim.json': {'authorized': True, 'budget_s': 600,
                               'scope': 'unrelated expired fixture claim'}}
        for name, value in self.records.items():
            write(self.repo / name, value)
        self.source = self.repo / 'unimported_source.txt'
        self.source.write_text('fixture source, never executable\n', encoding='utf8')
        self.protocol = self.repo / manager.PROTOCOL_FILE
        self.protocol.parent.mkdir(parents=True, exist_ok=True)
        self.protocol.write_text('fixture protocol: preparation only\n', encoding='utf8')
        self.source_map = {'unimported_source.txt': self.source}
        self.artifact_map = {name: self.repo / name for name in self.records}
        self.artifact_map[manager.PROTOCOL_FILE] = self.protocol
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(manager, 'source_paths',
                                             lambda root: self.source_map))
        self.stack.enter_context(patch.object(manager, 'artifact_paths',
                                             lambda root: self.artifact_map))

    def prepare(self, name='prepared'):
        destination = self.folder / name
        declaration = manager.prepare(self.repo, destination)
        return destination, declaration

    def test_normal_prepare_is_pending_and_consumes_nothing(self):
        destination, declaration = self.prepare()
        self.assertTrue(manager.validate(self.repo, declaration)['passed'])
        self.assertEqual(declaration['plan']['status'], 'PENDING_USER_CONFIRMATION')
        self.assertFalse(declaration['plan']['authorized'])
        self.assertFalse(declaration['plan']['execution_ready'])
        self.assertIsNone(declaration['approval'])
        self.assertEqual(declaration['research_calls_consumed'], 0)
        self.assertEqual(declaration['native_requests_consumed'], 0)
        ledger = read(destination / 'ledger.json')
        self.assertEqual(ledger['reserved_method_seconds'], 0)
        self.assertEqual(ledger['research_calls_consumed'], 0)
        self.assertIsNone(ledger['claim'])
        self.assertEqual(ledger['remaining_original_campaign'], 24)
        self.assertFalse(declaration['input_contract']['new_input_construction'])
        self.assertFalse(declaration['input_contract']['old_answer_or_vector_loaded'])

    def test_run_rejects_old_claim_and_fabricated_approval(self):
        destination, declaration = self.prepare()
        protected = [destination / 'ledger.json', self.repo / (manager.OLD + 'ledger.json'),
                     self.repo / 'old_claim.json']
        before = {str(path): sha(path) for path in protected}
        for kwargs in ({'old_claim': read(self.repo / 'old_claim.json')},
                       {'approval': {'approved': True}, 'restart': True},
                       {'declaration': declaration, 'authorized': True}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(PermissionError, 'PENDING_USER_CONFIRMATION'):
                    manager.request_run(destination, **kwargs)
        self.assertEqual(before, {str(path): sha(path) for path in protected})

    def test_limits_and_model_contract_are_fixed(self):
        _, declaration = self.prepare()
        plan = declaration['plan']
        self.assertEqual([plan[key] for key in
            ('research_call_limit', 'native_request_limit', 'max_outer_rounds')], [1, 1, 1])
        self.assertEqual(plan['budget']['method_seconds'], 300)
        self.assertEqual(plan['budget']['post_heat_seconds'], 0)
        self.assertFalse(plan['budget']['reuse_old_campaign_budget'])
        self.assertFalse(plan['retry'])
        self.assertFalse(plan['extend_budget'])
        self.assertFalse(plan['resume_original_24'])
        self.assertEqual(plan['condition'], {
            'response': 'H', 'entry_degC': 50, 'limit_degC': 80,
            'deadline_beta': '1.0', 'window_ms': 400, 'start_grid_ms': 5,
            'idle_policy': 'auto_low_immediate_v1',
            'workload': 'complete_AB_AC_three_Stage_chains'})
        self.assertEqual(plan['native_options']['CutMaxIterations'], 10)
        self.assertEqual(plan['native_options']['ConstraintTolerance'], '1e-9')
        self.assertEqual(plan['native_options']['IntegerTolerance'], '1e-6')
        for field, changed in (('research_call_limit', 2), ('native_request_limit', 2),
                               ('max_outer_rounds', 2), ('authorized', True)):
            bad = deepcopy(declaration)
            bad['plan'][field] = changed
            bad['plan_sha256'] = manager.canonical(bad['plan'])
            self.assertFalse(manager.validate(self.repo, bad)['passed'])
        bad = deepcopy(declaration)
        bad['plan']['budget']['method_seconds'] = 301
        bad['plan_sha256'] = manager.canonical(bad['plan'])
        self.assertFalse(manager.validate(self.repo, bad)['passed'])

    def test_source_protocol_and_input_drift_are_rejected(self):
        _, declaration = self.prepare()
        for path in (self.source, self.protocol,
                     self.repo / (manager.OLD_CALL + 'input_instance.json')):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b' ')
                result = manager.validate(self.repo, declaration)
                self.assertFalse(result['passed'], str(path))
            finally:
                path.write_bytes(original)
        self.assertTrue(manager.validate(self.repo, declaration)['passed'])

    def test_existing_output_is_not_overwritten(self):
        destination, _ = self.prepare()
        originals = {str(path): sha(path) for path in destination.iterdir() if path.is_file()}
        with self.assertRaises(FileExistsError):
            manager.prepare(self.repo, destination)
        self.assertEqual(originals, {str(path): sha(path) for path in destination.iterdir()
                                     if path.is_file()})

    def test_input_identity_error_cannot_create_prepared_or_reserved_budget(self):
        original_path = self.repo / manager.ORIGINAL_DECLARATION
        original = read(original_path)
        original['inputs']['beta_1.0__R2']['input_identities']['input_sha256'] = '0' * 64
        write(original_path, original)
        destination = self.folder / 'rejected_prepare'
        with self.assertRaisesRegex(ValueError, 'canonical identity mismatch'):
            manager.prepare(self.repo, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(read(self.repo / (manager.OLD + 'ledger.json'))['consumed_old'], 16)

    def test_recipe_binds_only_one_request_and_does_not_execute_dependencies(self):
        called = {'context': 0, 'whole': 0, 'builder': 0, 'session': 0, 'diagnostic': 0}

        class FakeContext:
            def __init__(self, *, session_factory):
                called['context'] += 1
                self.factory = session_factory

            def session_factory(self, *args, **kwargs):
                called['session'] += 1
                raise AssertionError('No session is permitted in preparation')

            def solve_formal_diagnostic(self, *args, **kwargs):
                called['diagnostic'] += 1
                raise AssertionError('No diagnostic is permitted in preparation')

        def whole(*args, **kwargs):
            called['whole'] += 1
            raise AssertionError('No whole call is permitted in preparation')

        def builder(*args, **kwargs):
            called['builder'] += 1
            raise AssertionError('No model build is permitted in preparation')

        def session(*args, **kwargs):
            called['session'] += 1
            raise AssertionError('No native session is permitted in preparation')

        context, bound, limits = recipe.make_bindings(dict(
            context=FakeContext, whole=whole, builder=builder, session=session))
        self.assertIs(bound.func, whole)
        self.assertEqual(bound.keywords['seconds'], 300)
        self.assertEqual(bound.keywords['feedback_kind'], 'conditional')
        self.assertIs(bound.keywords['model_builder'].func, builder)
        self.assertEqual(bound.keywords['model_builder'].keywords,
                         {'prefilter_deadlines': True, 'cumulative_precedence': False})
        self.assertEqual(bound.keywords['diagnostic_solver'].keywords['max_rounds'], 1)
        self.assertIs(context.factory.func, session)
        self.assertEqual(context.factory.keywords, {'cut_max_iterations': 10})
        self.assertEqual((limits['research_method_calls'], limits['native_requests'],
                          limits['actual_max_rounds']), (1, 1, 1))
        self.assertEqual(called, {'context': 1, 'whole': 0, 'builder': 0,
                                  'session': 0, 'diagnostic': 0})


def run(out):
    global OUT
    OUT = Path(out).resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    blocked = {'scientific_import': 0, 'scientific_code_entry': 0, 'process_launch': 0}
    scientific_modules = {'numpy', 'scipy', 'milp', 'matlab_bridge', 'thermal',
        'initial_point', 'initial_schedule', 'inputs', 'whole_augmented',
        'augmented_method', 'augmented_payload', 'scene_adapter', 'formal_milp'}
    scientific_loaded_at_start = sorted(name for name in sys.modules
        if name.split('.')[0] in scientific_modules)
    forbidden_functions = {
        'inputs.py': {'build_instance', 'expand_options', 'load_config'},
        'milp.py': {'build_model', 'Model.__init__', 'evaluate_model_candidate'},
        'milp_coefficients.py': {'Coefficients.__init__'},
        'matlab_bridge.py': {'MatlabSession.__init__', 'MatlabSession.solve'},
        'thermal.py': {'evaluate_candidate', 'evaluate_piecewise'},
        'initial_point.py': {'_propose_vector', 'complete_initial_point', 'prepare_initial_witness'},
        'initial_schedule.py': {'iter_initial_candidates'},
        'augmented_method.py': {'build_live_augmented_payload'},
        'augmented_payload.py': {'build_augmented_payload'},
        '_milp.py': {'milp'}, '_linprog.py': {'linprog'},
        'subprocess.py': {'Popen.__init__', 'run', 'check_output'}}
    active = {'value': True}

    def fail(kind, message):
        blocked[kind] += 1
        raise ScientificGuardViolation(message)

    def audit(event, args):
        if not active['value']:
            return
        if event == 'import' and str(args[0]).split('.')[0] in scientific_modules:
            fail('scientific_import', 'Forbidden scientific import: ' + str(args[0]))
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.posix_spawn'):
            fail('process_launch', 'Forbidden process audit event: ' + event)

    def profile(frame, event, arg):
        if event != 'call':
            return
        filename = Path(frame.f_code.co_filename).name
        qualname = getattr(frame.f_code, 'co_qualname', frame.f_code.co_name)
        if (qualname in forbidden_functions.get(filename, set())
                or frame.f_code.co_name in forbidden_functions.get(filename, set())):
            kind = 'process_launch' if filename == 'subprocess.py' else 'scientific_code_entry'
            fail(kind, 'Forbidden original/captured code entry: ' + filename + ':' + qualname)

    source_files = [Path(__file__), Path(manager.__file__), Path(recipe.__file__),
                    REPO / manager.PROTOCOL_FILE]
    before = {str(path): sha(path) for path in source_files}
    old_ledgers = [REPO / (manager.OLD + 'ledger.json'),
                   REPO / (manager.BASE + 'results/deadline_execution01/ledger.json')]
    old_before = {str(path): sha(path) for path in old_ledgers}
    previous_profile = sys.getprofile()
    sys.addaudithook(audit)
    log = io.StringIO()
    real = {'performed': False}
    try:
        sys.setprofile(profile)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PreparationTests)
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        # Exactly one true repository preparation; only static archived JSON
        # and source hashes, not a fresh input/model or a scientific call.
        declaration = manager.prepare(REPO, OUT / 'real_preparation')
        verified = manager.validate(REPO, declaration)
        real = {'performed': True, 'validation': verified,
                'declaration_sha256': sha(OUT / 'real_preparation/declaration.json'),
                'source_count': len(declaration['source_sha256']),
                'artifact_count': len(declaration['artifact_sha256']),
                'scientific_work_performed': declaration['scientific_work_performed'],
                'consumed': declaration['research_calls_consumed']}
    except ScientificGuardViolation as error:
        result = unittest.TestResult()
        result.errors.append(('guard_abort', str(error)))
        log.write('\nABORTED: ' + str(error) + '\n')
    except Exception as error:
        result = locals().get('result', unittest.TestResult())
        result.errors.append(('real_prepare', repr(error)))
        log.write('\nREAL_PREPARATION_ERROR: ' + repr(error) + '\n')
    finally:
        sys.setprofile(previous_profile)
        active['value'] = False
    after = {str(path): sha(path) for path in source_files}
    old_after = {str(path): sha(path) for path in old_ledgers}
    checks = {'protocol': 'K168-prepare-only-management-precheck-v1',
              'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'test_successful': result.wasSuccessful(),
              'real_preparation': real, 'source_sha256_before': before,
              'source_sha256_after': after, 'source_unchanged': before == after,
              'old_ledger_sha256_before': old_before, 'old_ledger_sha256_after': old_after,
              'old_ledgers_unchanged': old_before == old_after,
              'guard': {'strategy': 'stdlib-only; reject science imports, real function filename/qualname profile guard including captured defaults, and process audit hooks; abort suite on attempted entry',
                        'blocked_attempts': blocked, 'all_attempts_zero': not any(blocked.values()),
                        'scientific_modules_loaded_at_start': scientific_loaded_at_start,
                        'research_calls': 0, 'new_real_inputs_or_models': 0,
                        'original_R2_payload_transformations': 0,
                        'solver_calls': 0, 'thermal_or_post_evaluations': 0},
              'scope': 'Preparation management only, not execution-chain acceptance, native compatibility, fault repair, safety or performance evidence'}
    checks['passed'] = (checks['test_successful'] and checks['source_unchanged']
        and checks['old_ledgers_unchanged'] and checks['guard']['all_attempts_zero']
        and not scientific_loaded_at_start
        and real.get('validation', {}).get('passed') is True)
    write(OUT / 'checks.json', checks)
    (OUT / 'unittest.txt').write_text(log.getvalue(), encoding='utf8')
    print(json.dumps({'passed': checks['passed'], 'tests': result.testsRun,
                      'failures': len(result.failures), 'errors': len(result.errors),
                      'guard_zero': checks['guard']['all_attempts_zero'],
                      'real_preparation': real.get('performed'),
                      'checks': str(OUT / 'checks.json')}))
    return 0 if checks['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().out))
