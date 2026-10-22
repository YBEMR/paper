"""Pure fixtures for combined-slot accounting and retained evidence provenance."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import analyse_combined_deadline as c
import test_pure as old


def declarations():
    slots = [{'ordinal':i, 'slot_id':f'slot{i}', 'seconds':300} for i in range(1,41)]
    return {'slots':slots}, {'slots':deepcopy(slots[2:]), 'prior_consumed':2,
        'remaining_calls':38,'campaign_call_limit':40,'seconds_each':300,
        'campaign_reserved_method_s':12000,'calendar_was_not_reset':True}


def repair_fixture():
    slot, record, raw = old.summary_fixture()
    record['slot_id'] = 'beta_1.0__R1__anchor_linked4'
    record['state'] = 'BLOCKED'
    record.pop('postcheck')
    record['records']['execution']['execution_status'] = 'TECHNICAL_FAILURE_CONFIRMED'
    record['records']['context']['hard_errors'] = [c.MARKER_ERROR]
    audit = {'protocol':'K163-root-cutoff-cancel-overwrite-adapter-v1',
        'applied':True,'original_execution':deepcopy(record['records']['execution']),
        'original_context_hard_errors':[c.MARKER_ERROR],
        'derived_execution_status':c.NORMAL_CUTOFF,
        'new_safe_evaluation':False,'late_candidate_accepted':False}
    review = {'protocol':'K163-read-only-cancel-repair-review-v1',
        'passed':True,'checks':{'all_verified':True},'slot_id':record['slot_id'],
        'new_research_calls':0,'new_thermal_evaluations':0,'new_safe_U':False,
        'original_data_modified':False,'cancel_overwrite_audit':audit,
        'original_U_J':'1','derived_U_J':'1'}
    post = {'state':'PASSED','passed':True,'checks':{'complete_safe':True},'new_U':False,
        'original_U_J':'1','research_repeated':False,'delayed_original_once_only_post':True,
        'original_slot_files_unchanged':True,'new_safe_formation_or_U':False}
    return slot,record,raw,review,post


class CombinedPureTests(unittest.TestCase):
    def row(self, slot, record, raw):
        return c.a.summary_row(slot,record,raw,c.HERE/'_fixture_no_source',old.instance(),
            lambda path:self.fail('Pure fixture cannot read an archive'))

    def test_roster_exact_two_plus_38(self):
        original, resume = declarations()
        result=c.roster(original,resume)
        self.assertEqual(len(result),40)
        self.assertEqual([v['ordinal'] for v in result],list(range(1,41)))
        result[0]['ordinal']=99
        self.assertEqual(original['slots'][0]['ordinal'],1)

    def test_roster_rejects_retries_or_missing_slots(self):
        for mutation in ('retry','missing','budget','calendar'):
            original,resume=declarations()
            if mutation=='retry':resume['slots'][0]=deepcopy(original['slots'][0])
            elif mutation=='missing':resume['slots'].pop()
            elif mutation=='budget':resume['seconds_each']=600
            else:resume['calendar_was_not_reset']=False
            with self.assertRaises(ValueError):c.roster(original,resume)

    def test_no_U_not_applicable_is_never_SAFE(self):
        slot,record,raw=old.summary_fixture(U=None)
        raw['evaluation']={};raw.pop('safe_candidate')
        record['records']['context']['safe_receipt']=None
        record['postcheck']={'state':'NOT_APPLICABLE_NO_USABLE_U','passed':True,'new_U':False}
        row=self.row(slot,record,raw);row.update(sealed=True,claim_exists=True)
        counts=c.summarize_counts([row])
        self.assertIsNone(row['safe_U_J'])
        self.assertIsNone(row['comparison_safe_U_J'])
        self.assertFalse(row['comparison_usable'])
        self.assertEqual(counts['comparison_eligible_SAFE'],0)
        self.assertEqual(counts['normal_without_safe_U'],1)
        self.assertEqual(counts['post_not_applicable_no_U'],1)

    def test_derived_second_preserves_raw_record_and_U(self):
        slot,record,raw,review,post=repair_fixture();snapshot=deepcopy(record)
        view=c.corrected_old_second(record,review,post)
        row=self.row(slot,view,raw)
        c.provenance(row,record,view,segment='original_1_2',record_source='old/result',
            post_source='repair/post',correction_source='repair/review')
        self.assertEqual(record,snapshot)
        self.assertEqual(row['raw_execution_status'],'TECHNICAL_FAILURE_CONFIRMED')
        self.assertEqual(row['derived_execution_status'],c.NORMAL_CUTOFF)
        self.assertEqual(row['raw_post_state'],None)
        self.assertEqual(row['effective_post_state'],'PASSED')
        self.assertTrue(row['comparison_usable'])
        self.assertTrue(row['original_usable_U_preserved'])
        self.assertFalse(row['new_safe_U_from_analysis'])

    def test_repair_rejects_changed_U_unmatched_fault_late_post(self):
        for kind in ('U','fault','review','late','unpassed'):
            _,record,_,review,post=repair_fixture()
            if kind=='U':review['derived_U_J']='.99'
            elif kind=='fault':record['records']['context']['hard_errors'].append('ANOTHER_ERROR')
            elif kind=='review':review['checks']['all_verified']=False
            elif kind=='late':post['new_safe_formation_or_U']=True
            else:post['passed']=False
            with self.assertRaises(ValueError):c.corrected_old_second(record,review,post)

    def test_stored_K164_adapter_keeps_original_status(self):
        slot,record,raw=old.summary_fixture()
        record['records']['cancel_overwrite_audit']={'applied':True,
            'original_execution':{'execution_status':'TECHNICAL_FAILURE_CONFIRMED'},
            'original_context_hard_errors':[c.MARKER_ERROR]}
        row=self.row(slot,record,raw)
        c.provenance(row,record,record,segment='continuation_3_40',record_source='new/result',post_source='new/post')
        self.assertTrue(row['classification_derived'])
        self.assertEqual(row['stored_execution_status'],'NORMAL_COMPLETION')
        self.assertEqual(row['raw_execution_status'],'TECHNICAL_FAILURE_CONFIRMED')

    def test_40_counts_keep_active_and_unstarted_separate(self):
        slot,record,raw=old.summary_fixture();good=self.row(slot,record,raw)
        good.update(sealed=True,claim_exists=True)
        active=self.row(slot,{},{});active.update(slot_state='CLAIMED_UNSEALED_NOT_READ',sealed=False,claim_exists=True)
        unstarted=self.row(slot,{},{});unstarted.update(sealed=False,claim_exists=False)
        rows=[deepcopy(good) for _ in range(10)]+[active]+[deepcopy(unstarted) for _ in range(29)]
        counts=c.summarize_counts(rows)
        self.assertEqual(counts['declared'],40);self.assertEqual(counts['sealed'],10)
        self.assertEqual(counts['claimed'],11);self.assertEqual(counts['unsealed_claims'],1)
        self.assertEqual(counts['not_started'],29)
        self.assertEqual(counts['comparison_eligible_SAFE'],10)

    def test_P0_missing_U_omits_difference_not_zero(self):
        slot,record,raw=old.summary_fixture(U=None)
        row=self.row(slot,record,raw)
        prior={'rows':[{'problem_id':'base__R1','method':'heft','comparison_usable':True,'safe_U_J':2}]}
        comparison=c.compare_P0([row],prior)[0]
        self.assertEqual(comparison['P0_safe_U_J'],2)
        self.assertIsNone(comparison['deadline_safe_U_J'])
        self.assertIsNone(comparison['deadline_minus_P0_U_J'])

    def test_SA_declared_five_including_unstarted_no_U(self):
        slot,record,raw=old.summary_fixture();rows=[]
        for i in range(101,106):
            s={**slot,'id':'sa'+str(i),'method':'sa','seed':i}
            r=deepcopy(record);v=deepcopy(raw)
            if i==103:
                r['records']['usable_U_J']=None;r['postcheck']={'passed':True,'state':'NOT_APPLICABLE_NO_USABLE_U'}
                v['evaluation']={};v.pop('safe_candidate')
            if i>=104:r={};v={}
            row=self.row(s,r,v);row.update(sealed=i<=103,claim_exists=i<=103);rows.append(row)
        cohort=c.combined_cohorts(rows)[0]
        self.assertEqual(cohort['SA_declared_n'],5)
        self.assertEqual(cohort['SA_sealed_n'],3)
        self.assertEqual(cohort['SA_safe_n'],2)
        self.assertEqual(cohort['SA_no_U_sealed_n'],1)
        self.assertEqual(cohort['SA_missing_or_unusable_n'],3)
        self.assertEqual(cohort['SA_median_J'],1)

    def test_final_analysis_requires_terminal_before_any_reads(self):
        with patch.object(c.Path,'is_file',return_value=False):
            with self.assertRaisesRegex(ValueError,'Final analysis requires'):
                c.collect(prefix=False)

    def test_outputs_refuse_old_frozen_directory(self):
        with self.assertRaisesRegex(ValueError,'frozen read-only'):
            c.write_outputs(c.OLD/'not_allowed',{},plots=False)


if __name__=='__main__':
    unittest.main(verbosity=2)
