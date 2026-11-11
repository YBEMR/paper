"""Pure structural regression suite; no model building or thermal integration.

Run directly with --output to preserve every complete assignment and deletion
proof, or use unittest discovery. The older test_option_support.py retains
the separate physical integration checks and is not called by this suite.
"""
import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest

import option_support as support
from option_support_test_oracle import enumerate_all, fixtures

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


class OptionSupportStructuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.started_utc = datetime.now(timezone.utc).isoformat()
        cls.started = time.monotonic()
        cls.records = []
        cls.declared = fixtures()
        cls.totals = dict(cases=len(cls.declared), cartesian_before=0,
                          cartesian_after=0, legal_before=0, legal_after=0,
                          deletions_checked=0)

        def check_time():
            if time.monotonic() - cls.started > 60:
                raise TimeoutError('Pure structural suite exceeded 60 seconds')

        for name, case, options in cls.declared:
            original = deepcopy((case, options))
            before_all, before = enumerate_all(case, options, check_time)
            kept, proof = support.propagate_option_support(case, options)
            after_all, after = enumerate_all(case, kept, check_time)
            replay = support.verify_option_support_report(case, options, kept, proof)
            cls.records.append(dict(name=name, before_candidates=before_all,
                after_candidates=after_all, legal_before=before, legal_after=after,
                retained_option_ids=[o['option_id'] for o in kept], proof=proof,
                replay=replay, input_unchanged=(case, options) == original,
                sets_equal=before == after))
            for key, value in [('cartesian_before', len(before_all)),
                               ('cartesian_after', len(after_all)),
                               ('legal_before', len(before)),
                               ('legal_after', len(after)),
                               ('deletions_checked', replay['checked_deletions'])]:
                cls.totals[key] += value
        cls.byname = {r['name']: r for r in cls.records}

    def test_complete_legal_sets_and_no_input_mutation(self):
        for record in self.records:
            with self.subTest(catalogue=record['name']):
                self.assertTrue(record['sets_equal'])
                self.assertTrue(record['input_unchanged'])
                self.assertTrue(record['replay']['passed'])
        self.assertEqual(self.totals, dict(cases=266, cartesian_before=342,
            cartesian_after=221, legal_before=186, legal_after=186,
            deletions_checked=512))

    def test_equality_noninteger_end_and_five_ms_boundary(self):
        self.assertEqual(len(self.byname['equality_fraction']['legal_before']), 2)
        self.assertEqual(len(self.byname['five_ms_start_fractional_end']['legal_before']), 2)

    def test_shared_mapping_does_not_share_frequency_or_start(self):
        shared = self.byname['shared_device_distinct_mode_start']['legal_before']
        self.assertIn(('aH', 'bM'), shared)
        self.assertIn(('aM', 'bH'), shared)
        self.assertEqual(self.byname['scenarios_independent_frequency']['legal_before'], [('a', 'b')])
        self.assertTrue(self.byname['same_scene_shared_device_distinct_start']['legal_before'])

    def test_multiple_rounds_empty_domains_and_resource_limit(self):
        self.assertGreaterEqual(self.byname['interaction_multiround']['proof']
            ['round_count_including_fixed_point_check'], 4)
        self.assertEqual(self.byname['empty_domain']['proof']['logical_feasibility'],
                         'INFEASIBLE_BY_EMPTY_OPTION_DOMAIN')
        self.assertEqual(self.byname['no_common_device']['proof']['retained_option_count'], 0)
        negative = self.byname['nonempty_but_resource_infeasible']
        self.assertEqual(negative['proof']['retained_option_count'], 2)
        self.assertFalse(negative['legal_before'])

    def test_tampered_proof_is_rejected(self):
        _, case, options = next(r for r in self.declared if r[0] == 'interaction_multiround')
        kept, proof = support.propagate_option_support(case, options)
        for field in ('initial_domain_sha256', 'final_domain_sha256', 'retained_options_sha256'):
            bad = deepcopy(proof); bad[field] = 'tampered'
            with self.subTest(field=field), self.assertRaises(ValueError):
                support.verify_option_support_report(case, options, kept, bad)
        bad = deepcopy(proof)
        bad['rounds'][0]['deletions'][0]['rule'] = 'unproven_resource_pair'
        with self.assertRaises(ValueError):
            support.verify_option_support_report(case, options, kept, bad)

    def test_malformed_catalogue_is_rejected(self):
        _, case, options = self.declared[0]
        for change in [lambda o: o.append(deepcopy(o[0])),
                       lambda o: o[0].update(start_ms=0.0),
                       lambda o: o[0].update(end_ms='0'),
                       lambda o: o[0].update(stage_instance_id='unknown')]:
            bad = deepcopy(options); change(bad)
            with self.subTest(change=repr(change)), self.assertRaises((ValueError, TypeError)):
                support.propagate_option_support(case, bad)

    def test_budget_interruption_does_not_mutate_inputs(self):
        _, case, options = self.declared[1]
        original = deepcopy((case, options))

        class Interrupted(Exception):
            pass

        class Stop:
            calls = 0

            def check(self):
                self.calls += 1
                if self.calls >= 4:
                    raise Interrupted('test-only interruption')

        with self.assertRaises(Interrupted):
            support.propagate_option_support(case, options, Stop())
        self.assertEqual((case, options), original)

    def test_milp_switch_source_contract_without_building_model(self):
        tree = ast.parse((HERE / 'milp.py').read_text())
        build = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_model')
        defaults = dict(zip([a.arg for a in build.args.kwonlyargs], build.args.kw_defaults))
        self.assertIs(defaults['propagate_support'].value, False)
        guards = [n for n in build.body if isinstance(n, ast.If)
                  and ast.unparse(n.test) == 'propagate_support']
        self.assertEqual(len(guards), 1)
        guard = guards[0]
        imports = [n for n in guard.body if isinstance(n, ast.ImportFrom)]
        self.assertTrue(any(n.module == 'option_support' for n in imports))
        calls = [n for n in ast.walk(guard) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'propagate_option_support']
        self.assertEqual(len(calls), 1)
        reports = [n for n in ast.walk(build) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute) and n.func.attr == 'report'
                   and n.args and isinstance(n.args[0], ast.Constant)]
        mode_line = next(n.lineno for n in reports if n.args[0].value == 'mode_variables')
        self.assertLess(calls[0].lineno, mode_line)
        # Execute only the exact source guard, without importing milp or creating
        # a model. This verifies strict bool acceptance and the default contract;
        # it is deliberately not an end-to-end model equivalence test.
        first = build.body[1] if isinstance(build.body[0], ast.Expr) else build.body[0]
        self.assertIsInstance(first, ast.If)
        self.assertIn('type(propagate_support) is not bool', ast.unparse(first.test))
        code = compile(ast.fix_missing_locations(ast.Module(body=[first], type_ignores=[])), 'milp-bool-guard', 'exec')
        for value in (False, True):
            exec(code, {'propagate_support': value})
        for value in (0, 1, None, 'false', []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exec(code, {'propagate_support': value})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat(); begin = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OptionSupportStructuralTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    cls = OptionSupportStructuralTests
    for name, value in [('declared_fixture_inputs.json',
                         [dict(name=n, instance=c, options=o) for n, c, o in getattr(cls, 'declared', [])]),
                        ('complete_schedule_sets_and_proofs.json', getattr(cls, 'records', []))]:
        with (args.output / name).open('x') as f:
            json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
    receipt = dict(started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(),
        wall_s=time.monotonic()-begin, tests_run=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), passed=result.wasSuccessful(),
        totals=getattr(cls, 'totals', None), command=[sys.executable, *sys.argv],
        environment=dict(python=sys.version, platform=sys.platform),
        source_sha256={str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [Path(__file__).resolve(), HERE/'option_support.py',
                                 HERE/'option_support_test_oracle.py', HERE/'milp.py']},
        thermal_calls=0, model_builds=0, solver_calls=0,
        loaded_modules_have_no_milp_or_thermal=not any(n in sys.modules for n in ('milp', 'thermal')),
        scope='Complete finite structural schedules and source-level switch contract; no physical certificate')
    with (args.output/'results.json').open('x') as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
