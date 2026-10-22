"""Pure accounting, active-prefix and receipt-provenance fixtures only."""
from copy import deepcopy
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_joint_terminal as joint


class JointAccountingTests(unittest.TestCase):
    def setUp(self):
        self.slots = [{'slot_id': 'MOCK_ONLY_'+str(i), 'ordinal': i, 'seconds': 300}
                      for i in range(1, 41)]

    def total(self, count):
        return joint.combined_consumption(self.slots, self.slots[2:],
                                          self.slots[:2], self.slots[2:2+count])

    def test_01_original_two_are_charged_even_before_continuation(self):
        self.assertEqual(self.total(0)['consumed_total'], 2)
        self.assertEqual(self.total(0)['reserved_method_seconds'], 600)

    def test_02_full_total_is40_and12000(self):
        result = self.total(38)
        self.assertEqual(result['consumed_total'], 40)
        self.assertEqual(result['reserved_method_seconds'], 12000)
        self.assertEqual(result['unstarted_remaining'], 0)

    def test_03_partial_consumption_not_filled_in(self):
        result = self.total(7)
        self.assertEqual((result['consumed_total'], result['unstarted_remaining']), (9, 31))

    def test_04_remaining_slot_reorder_rejected(self):
        wrong = deepcopy(self.slots[2:]); wrong[0], wrong[1] = wrong[1], wrong[0]
        with self.assertRaises(ValueError):
            joint.combined_consumption(self.slots, wrong, self.slots[:2], [])

    def test_05_first_two_cannot_be_replayed(self):
        with self.assertRaises(ValueError):
            joint.combined_consumption(self.slots, self.slots[2:], self.slots[:2], self.slots[:2])

    def test_06_claims_must_be_prefix(self):
        with self.assertRaises(ValueError):
            joint.combined_consumption(self.slots, self.slots[2:], self.slots[:2], self.slots[3:4])

    def test_07_budget_change_rejected(self):
        self.slots[3]['seconds'] = 301
        with self.assertRaises(ValueError): self.total(2)

    def test_08_duplicate_original_slot_rejected(self):
        self.slots[-1] = deepcopy(self.slots[0])
        with self.assertRaises(ValueError): self.total(0)

    def test_09_active_slot_never_selected(self):
        status = {'completed_new': 2, 'active': {'slot_id': self.slots[4]['slot_id']}}
        self.assertEqual(joint.selected_prefix(self.slots[2:], status), self.slots[2:4])

    def test_10_inconsistent_active_completed_prefix_rejected(self):
        status = {'completed_new': 2, 'active': {'slot_id': self.slots[2]['slot_id']}}
        with self.assertRaises(ValueError): joint.selected_prefix(self.slots[2:], status)

    def test_11_invalid_completed_count_rejected(self):
        for invalid in (-1, 39, True, None, '2'):
            with self.assertRaises(ValueError):
                joint.selected_prefix(self.slots[2:], {'completed_new': invalid})

    def test_12_terminal_scan_refuses_running_campaign_before_read(self):
        with tempfile.TemporaryDirectory(dir=joint.a.REPO/'.runtime') as tmp:
            with patch.object(joint.r, 'OUT', Path(tmp)), \
                 patch.object(joint.safe_io, 'read_small', side_effect=AssertionError('Must not read live status')):
                with self.assertRaisesRegex(RuntimeError, 'supervisor terminal absent'):
                    joint.audit()

    def test_13_audit_contains_no_live_ledger_access(self):
        self.assertNotIn('ledger.json', inspect.getsource(joint.audit))


class ReceiptProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=joint.a.REPO/'.runtime')
        self.addCleanup(self.temp.cleanup)
        self.raw_path = Path(self.temp.name)/'raw.json'
        self.raw_path.write_text('{"MOCK_ONLY":true}', encoding='ascii')
        self.sources = {'original_240_manifest_MOCK_ONLY': 'original_hash'}
        self.raw = {'safe_candidate': {'MOCK_ONLY': True},
                    'aggregation': {'weighted_energy_J': ['8/10', '9/10']}}
        self.definition = {'input_sha256': 'MOCK_INPUT'}
        provenance = {'raw_result_sha256': joint.a.sha(self.raw_path),
            'input_sha256': 'MOCK_INPUT', 'candidate_sha256': joint.a.canonical(self.raw['safe_candidate']),
            'source_sha256': self.sources, 'post_seconds': 60, 'new_U': False, 'no_search_or_repair': True}
        self.post = {'post_provenance': provenance, 'weighted_energy_J': ['85/100', '95/100']}
        self.claim = {'provenance': deepcopy(provenance), 'no_retry': True}
        self.info = {'passed': True, 'new_U': False}

    def checks(self):
        # This fixture only exercises provenance and interval arithmetic. It
        # explicitly does not claim to construct or thermally verify a receipt.
        with patch.object(joint.a, 'receipt_checks', return_value=[]):
            return joint.post_checks(self.post, self.claim, self.info, self.raw,
                                     self.raw_path, self.definition, self.sources)

    def test_14_original_physical_manifest_accepted(self):
        self.assertTrue(all(self.checks().values()))

    def test_15_new_admin_manifest_cannot_replace_original_physical_source(self):
        changed = dict(self.sources, NEW_ADMIN_ONLY='new_hash')
        self.post['post_provenance']['source_sha256'] = changed
        self.claim['provenance']['source_sha256'] = changed
        self.assertFalse(self.checks()['bound_raw_input_candidate_source'])

    def test_16_new_U_or_search_in_post_rejected(self):
        self.post['post_provenance']['new_U'] = True
        self.assertFalse(self.checks()['post_60s_no_search_or_repair'])
        self.info['new_U'] = True
        self.assertFalse(self.checks()['passed_without_new_U'])

    def test_17_changed_candidate_rejected(self):
        self.raw['safe_candidate'] = {'DIFFERENT_MOCK': True}
        self.assertFalse(self.checks()['bound_raw_input_candidate_source'])

    def test_18_disjoint_energy_interval_rejected(self):
        self.post['weighted_energy_J'] = ['91/100', '95/100']
        self.assertFalse(self.checks()['energy_intervals_overlap'])

    def test_19_no_U_is_not_zero_and_needs_no_extra_post(self):
        marker = {'state': 'NOT_APPLICABLE_NO_USABLE_U', 'passed': True, 'new_U': False}
        folder = Path(self.temp.name)
        self.assertTrue(all(dict(joint.a.no_U_checks(None, marker, folder, complete=True)).values()))
        self.assertFalse(dict(joint.a.no_U_checks('0', marker, folder, complete=True))['no_U_not_fabricated_as_zero'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
