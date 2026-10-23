"""Five pure continuation checks. No planner, thermal evaluator or process."""
from copy import deepcopy
from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from research.chapter4_scheduler import resume_execution as r


class ResumeScope(unittest.TestCase):
    def setUp(self):
        runtime = REPO / '.runtime'
        runtime.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='k184_pure_', dir=runtime)
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        self.patcher = patch.object(r, 'OUT', self.out)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.d = r.make_declaration(self.out)
        self.path = self.out / 'declaration.json'
        r.write_new(self.path, self.d)
        r.write_new(self.out / 'batch.claim.json', {
            'declaration_sha256': r.sha(self.path),
            'deadline_utc': self.d['calendar_deadline_utc'],
            'not_scientific': False})
        self.context = patch.object(r, 'check_context', return_value=(self.d, self.out))
        self.context.start()
        self.addCleanup(self.context.stop)

    def test_exact_unstarted_scope_and_original_deadline(self):
        self.assertTrue(r.validate(self.d))
        self.assertTrue(r.verify_files(self.d))
        self.assertEqual(len(self.d['slots']), 7)
        self.assertEqual(self.d['slots'][0]['slot_id'], 'base__R1__HEFT')
        self.assertEqual(self.d['budgets']['method_total_s'], 2100)
        self.assertEqual(self.d['budgets']['post_total_s'], 420)
        self.assertEqual(self.d['calendar_deadline_utc'],
                         r.read(r.OLD / 'batch.claim.json')['deadline_utc'])

    def test_used_slot_deadline_extension_and_budget_refund_rejected(self):
        old = r.read(r.OLD / 'declaration.json')
        variants = []
        value = deepcopy(self.d); value['slots'][0] = old['slots'][0]; variants.append(value)
        value = deepcopy(self.d)
        value['calendar_deadline_utc'] = (datetime.fromisoformat(value['calendar_deadline_utc'])
                                        + timedelta(seconds=1)).isoformat()
        variants.append(value)
        value = deepcopy(self.d); value['budgets']['method_total_s'] = 2400; variants.append(value)
        for value in variants:
            with self.subTest(value=value['calendar_deadline_utc'], slots=value['slots'][0]['slot_id']):
                with self.assertRaises(ValueError):
                    r.validate(value)

    def test_out_of_order_and_duplicate_claim_rejected(self):
        first, second = self.d['slots'][:2]
        with self.assertRaises((OSError, ValueError)):
            r.claim_slot(self.path, second['slot_id'])
        folder = r.claim_slot(self.path, first['slot_id'])
        self.assertTrue((folder / 'slot.claim.json').is_file())
        with self.assertRaises(FileExistsError):
            r.claim_slot(self.path, first['slot_id'])

    def test_appcontainer_worker_denied(self):
        slot = self.d['slots'][0]
        r.claim_slot(self.path, slot['slot_id'])
        with patch.object(r, 'execution_context', return_value={'token_is_appcontainer': True}):
            with self.assertRaisesRegex(ValueError, 'host context'):
                r.load_active(self.path, slot['slot_id'])

    def test_post_can_load_active_until_unique_terminal(self):
        slot = self.d['slots'][0]
        folder = r.claim_slot(self.path, slot['slot_id'])
        with patch.object(r, 'execution_context', return_value={'token_is_appcontainer': False}):
            for _ in range(2):  # method and its one post share the active slot
                self.assertEqual(r.load_active(self.path, slot['slot_id'])[1], slot)
            with self.assertRaises(ValueError):
                r.load_active(self.path, 'base__R1__C')
            r.write_new(folder / 'terminal.json', {'continue_allowed': True})
            with self.assertRaises(ValueError):
                r.load_active(self.path, slot['slot_id'])


if __name__ == '__main__':
    here = Path(__file__).resolve().parent
    stream = io.StringIO()
    with patch.object(subprocess, 'Popen', side_effect=AssertionError('No native calls in pure checks')):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ResumeScope))
    log = stream.getvalue()
    with (here / 'test_output.txt').open('x', encoding='utf-8') as output:
        output.write(log)
    receipt = {'protocol': 'K184-five-pure-continuation-checks-v1',
        'passed': result.wasSuccessful(), 'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'control_sha256': r.sha(r.__file__), 'test_source_sha256': r.sha(__file__),
        'new_research_calls': 0, 'new_thermal_integrations': 0,
        'new_native_processes': 0, 'new_optimization_solves': 0,
        'scope': 'metadata, once-only claims, host denial and post lifecycle only; not algorithm evidence'}
    r.write_new(here / 'checks.json', receipt)
    print(log)
    raise SystemExit(0 if receipt['passed'] else 2)
