"""Pure synthetic no-U audit tests; fabricated records are not research data."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import audit_terminal as a


class NoURecordTests(unittest.TestCase):
    def setUp(self):
        root = a.REPO/'.runtime/deadline_audit_tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.post = {'state': 'NOT_APPLICABLE_NO_USABLE_U', 'passed': True, 'new_U': False}

    def check(self, usable=None, post=None, complete=True):
        return dict(a.no_U_checks(usable, self.post if post is None else post,
                                 self.folder, complete=complete))

    def test_01_normal_no_U_has_no_ranked_zero_or_new_post(self):
        self.assertTrue(all(self.check().values()))

    def test_02_zero_is_not_absence_of_U(self):
        self.assertFalse(self.check(usable='0')['no_U_not_fabricated_as_zero'])
        self.assertFalse(self.check(usable=0)['no_U_not_fabricated_as_zero'])

    def test_03_missing_or_wrong_completion_marker_rejected(self):
        for bad in ({}, {'state': 'PASSED', 'passed': True, 'new_U': False},
                    {'state': 'NOT_APPLICABLE_NO_USABLE_U', 'passed': False, 'new_U': False}):
            self.assertFalse(self.check(post=bad)['no_U_no_extra_post'])

    def test_04_no_U_with_extra_post_receipt_rejected(self):
        (self.folder/'postcheck.json').write_text('{"MOCK_ONLY":true}', encoding='utf-8')
        self.assertFalse(self.check()['no_U_no_extra_post'])

    def test_05_no_U_with_extra_post_claim_rejected(self):
        (self.folder/'postcheck.claim.json').write_text('{"MOCK_ONLY":true}', encoding='utf-8')
        self.assertFalse(self.check()['no_U_no_extra_post'])

    def test_06_no_post_energy_backfill(self):
        bad = dict(self.post, new_U=True)
        self.assertFalse(self.check(post=bad)['no_U_no_extra_post'])

    def test_07_stopped_partial_slot_need_not_invent_post(self):
        self.assertEqual(self.check(post={}, complete=False), {'no_U_not_fabricated_as_zero': True})

    def test_08_running_campaign_is_not_scanned(self):
        with patch.object(a, 'ROOT', self.folder):
            with self.assertRaisesRegex(RuntimeError, 'Supervisor terminal absent'):
                a.audit()

    def test_09_real_archive_cannot_be_replaced_by_synthetic_override(self):
        with self.assertRaisesRegex(ValueError, 'TEST_ONLY/P1 fixture mode'):
            a.audit(_fixture_folder=self.folder)


if __name__ == '__main__':
    unittest.main(verbosity=2)
