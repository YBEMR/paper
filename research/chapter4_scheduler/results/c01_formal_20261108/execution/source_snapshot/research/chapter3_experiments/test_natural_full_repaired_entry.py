"""Pure wiring checks for the one fixed repaired formal comparison."""
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
import inspect
import sys
import unittest
from unittest.mock import patch

from research.chapter3_experiments import natural_full_repaired_entry as entry


class RepairedEntryChecks(unittest.TestCase):
    def setUp(self):
        names = ('ENTRY', 'WORKER_MODULE', 'PREPARATION', 'validate_plan', 'freeze', 'native_session_factory')
        self.original_bindings = {name: getattr(entry.base, name) for name in names}
        entry.configure()

    def tearDown(self):
        for name, value in self.original_bindings.items():
            setattr(entry.base, name, value)

    def plan(self):
        p = deepcopy(entry.base.read(entry.OLD_PLAN))
        p.update(numerical_representation=entry.REPRESENTATION,
                 representation_adapter=entry.ADAPTER, representation_helper=entry.HELPER)
        for rel in (entry.ENTRY, entry.BASE_ENTRY, entry.ADAPTER, entry.HELPER):
            p['source_sha256'][rel] = 'pure-test-no-execution'
        return p

    def test_only_new_entry_paths_change(self):
        self.assertEqual(entry.base.WORKER_MODULE, 'research.chapter3_experiments.natural_full_repaired_entry')
        self.assertIn('WORKER_MODULE', inspect.getsource(entry.base.run_slot))
        self.assertEqual(entry.base.PREPARATION.name, 'natural_full_repaired_preparation01')
        old = entry.base.read(entry.OLD_PLAN)
        self.assertEqual((entry.base.INPUT, entry.base.CONFIG), (old['input_file'], old['config_file']))
        self.assertEqual(entry.base.JOBS, old['jobs'])
        self.assertEqual(entry.base.SCOPE, old['scope'])
        self.assertEqual(entry.base.BUILDER_FLAGS, old['builder_flags'])

    def test_frozen_representation_and_scope_required(self):
        entry.validate_plan(self.plan())
        for key, value in [('numerical_representation', 'unchanged_old_rows'),
                           ('cut_max_iterations', 9), ('jobs', [entry.base.JOBS[0]]),
                           ('input_file', 'different.json')]:
            p = self.plan(); p[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                entry.validate_plan(p)

    def test_factory_keeps_existing_session_options_and_attaches_once(self):
        session = SimpleNamespace(close=lambda: None)
        calls = []
        fake = ModuleType('research.chapter3_experiments.numeric_case_diagnostic.equality_session')
        fake.attach = lambda s: calls.append(s) or s
        def native(*args, **kw):
            self.assertEqual(args, ('fake-output',))
            self.assertEqual(kw, {'budget': 'fake-root', 'total_budget_s': 300})
            return session
        with patch.object(entry, '_native_factory_original', return_value=native), \
             patch.dict(sys.modules, {fake.__name__: fake}):
            got = entry.native_session_factory(self.plan())('fake-output', budget='fake-root', total_budget_s=300)
        self.assertIs(got, session)
        self.assertEqual(calls, [session])

    def test_attach_failure_cleans_original_session(self):
        closed = []
        session = SimpleNamespace(close=lambda: closed.append(True))
        fake = ModuleType('research.chapter3_experiments.numeric_case_diagnostic.equality_session')
        def reject(s):
            raise ValueError('fixture attachment failure')
        fake.attach = reject
        with patch.object(entry, '_native_factory_original', return_value=lambda: session), \
             patch.dict(sys.modules, {fake.__name__: fake}), self.assertRaises(ValueError):
            entry.native_session_factory(self.plan())()
        self.assertEqual(closed, [True])


if __name__ == '__main__':
    unittest.main()
