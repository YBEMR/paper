"""P0 pure tests; all candidate/solver/heat actions remain mocked or blocked."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_p0 as p
import dispatch
import audit_heuristic
import audit_linked
import audit_whole


class ScopeTests(unittest.TestCase):
    def test_01_exact_five_problems_and_forty_slots(self):
        rows=p.slots()
        self.assertEqual(len(rows),40)
        self.assertEqual(len({r['slot_id'] for r in rows}),40)
        self.assertEqual([r['ordinal'] for r in rows],list(range(1,41)))
        self.assertEqual(sum(r['seconds'] for r in rows),12000)

    def test_02_rotation_and_seed_order(self):
        expected=[['whole_milp','anchor_linked4','heft','sa101','sa102','sa103','sa104','sa105'],
            ['anchor_linked4','heft','sa101','sa102','sa103','sa104','sa105','whole_milp'],
            ['heft','sa101','sa102','sa103','sa104','sa105','whole_milp','anchor_linked4'],
            ['sa101','sa102','sa103','sa104','sa105','whole_milp','anchor_linked4','heft']]
        for i,pid in enumerate(p.PROBLEMS):
            self.assertEqual([j['id'] for j in p.jobs(pid)],expected[i%4])

    def test_03_reject_out_of_scope(self):
        for pid in ('base__R0','base__R6','heat78__R1','resources_CPU__R1',None):
            with self.assertRaises(ValueError):p.jobs(pid)
            with self.assertRaises(ValueError):p.fresh_input(pid)

    def test_04_exact_declared_source_derivation(self):
        self.assertEqual(p.lineage_issues(),[])
        self.assertEqual(len(p.read(p.BASE)['source_sha256']),178)
        for name,h in p.read(p.BASE)['source_sha256'].items():
            self.assertEqual(p.sha(p.REPO/name),h)

    def test_05_five_real_input_identities_and_full_domain(self):
        ids=[]
        for pid in p.PROBLEMS:
            d,triples=p.input_declaration(pid);raw,config,instance=triples
            self.assertEqual(instance['id'],pid)
            self.assertEqual(len(instance['scenarios']),2)
            self.assertEqual([len(s['stage_instances']) for s in instance['scenarios']],[6,6])
            self.assertEqual([len(v) for v in d['first_opened_by_scene'].values()],[2,2])
            self.assertEqual([len(v) for v in d['linked_opened_by_job']['anchor_linked4'].values()],[4,4])
            self.assertEqual(d['input_sha256'],p.canonical(instance));ids.append(d['input_sha256'])
            self.assertNotEqual(raw,config)
        self.assertEqual(len(set(ids)),5)

    def test_06_r1_exact_old_pilot_input_not_old_output(self):
        self.assertEqual(p.input_declaration('base__R1')[0]['input_identities'],
                         p.read(p.BASE)['input_identities'])

    def test_07_inputs_reloaded_independently(self):
        a=p.fresh_input('base__R2');b=p.fresh_input('base__R2')
        self.assertEqual(a,b)
        self.assertIsNot(a[1],b[1]);self.assertIsNot(a[2],b[2])
        a[2]['id']='mutated'
        self.assertEqual(b[2]['id'],'base__R2')

    def test_08_test_only_consumption_exact_once(self):
        ledger=p.MockLedger()
        for s in p.slots():ledger.consume(s);ledger.complete('NORMAL_COMPLETION')
        self.assertEqual(len(ledger.consumed),40)
        with self.assertRaises((ValueError,IndexError)):ledger.consume(p.slots()[0])

    def test_09_duplicate_and_reordered_rejected(self):
        ledger=p.MockLedger()
        with self.assertRaises(ValueError):ledger.consume(p.slots()[1])
        ledger.consume(p.slots()[0])
        with self.assertRaises(ValueError):ledger.consume(p.slots()[0])

    def test_10_stop_on_real_failure_not_deadline(self):
        for status in ('TECHNICAL_FAILURE_CONFIRMED','NUMERICAL_UNRESOLVED','UNKNOWN'):
            ledger=p.MockLedger();ledger.consume(p.slots()[0]);ledger.complete(status)
            with self.assertRaises(ValueError):ledger.consume(p.slots()[1])
        for status in p.NORMAL:
            ledger=p.MockLedger();ledger.consume(p.slots()[0]);ledger.complete(status)
            ledger.consume(p.slots()[1])

    def test_11_plan_is_still_unapproved(self):
        plan=p.read(p.PLAN)
        self.assertIs(plan['authorised_to_execute'],False)
        self.assertEqual(plan['status'],'DRAFT_NOT_EXECUTABLE')


class DispatchTests(unittest.TestCase):
    def test_12_all_forty_mock_dispatches_are_fresh_and_unmodified(self):
        from timing import MethodBudget
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            seen=[]
            def fake(loader,folder,**kw):
                self.assertEqual(kw['seconds'],300)
                budget=kw.get('budget') or MethodBudget(300)
                config,instance=loader(budget)
                seen.append((instance['id'],str(folder),kw,config))
                return {'MOCK_ONLY':True}
            entries={k:Mock(side_effect=fake) for k in ('whole','linked','heuristic')}
            entries.update(builder=Mock(),session=Mock())
            with patch('partial_bounds.independent_lower_bound',return_value={'MOCK_ONLY':True}) as lower:
                for slot in p.slots():
                    pid=slot['problem_id'];d,_=p.input_declaration(pid)
                    job=next(j for j in p.jobs(pid) if j['id']==slot['id'])
                    out=root/pid;out.mkdir(exist_ok=True)
                    result,identity=dispatch.execute(job,out,d,entries)
                    self.assertEqual(result,{'MOCK_ONLY':True})
                    self.assertTrue(identity['input_verified'])
                self.assertEqual(lower.call_count,5)
            self.assertEqual(len(seen),40)
            self.assertEqual(len({v[1] for v in seen}),40)
            for pid,folder,kw,config in seen:
                self.assertIn(pid,folder)
                if 'shared_deployment' in kw:
                    self.assertTrue(kw['preeliminate_closed_anchors'])
                    self.assertEqual(kw['scene_slice_s'],60)
                    self.assertEqual(kw['shared_deployment'],{'A.pre':'CPU1','A.main':'NPU0','A.post':'CPU1'})
                    self.assertEqual(sorted(map(len,kw['opened_by_scene'].values())),[2,2])
                    self.assertEqual(sorted(map(len,kw['linked_opened_by_scene'].values())),[4,4])
                if 'allow_auto_low' in kw:self.assertIs(kw['allow_auto_low'],True)
            self.assertEqual([c.kwargs['seed'] for c in entries['heuristic'].call_args_list if c.kwargs['method']=='sa'],
                             list(range(101,106))*5)

    def test_13_fresh_identity_mismatch_refuses_dispatch(self):
        from timing import MethodBudget
        d,_=p.input_declaration('base__R2')
        d['input_identities']['input_sha256']='not-R2'
        def fake(loader,*a,**kw):return loader(MethodBudget(300))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                dispatch.execute(p.METHODS[2],Path(temp),d,{'heuristic':fake,'session':Mock()})

    def test_14_method_not_declared_is_rejected(self):
        d,_=p.input_declaration('base__R1')
        with self.assertRaises(ValueError):dispatch.execute({'id':'sa999','method':'sa','seed':999},None,d,{})


class ReceiptTests(unittest.TestCase):
    def receipt(self,pid):
        d,_=p.input_declaration(pid)
        candidate={'scenes':{sid:[] for sid in d['scene_spec']}}
        ev={'problem_id':pid,'state':'SAFE','rankable_energy':True,
            'legality':{'state':'SCHEDULE_VALID_THERMAL_UNCHECKED'},'completed_at_elapsed_s':10.,
            'weighted_energy_J':['1','1'],'safe_upper_bound_J':'1',
            'scenes':{sid:{'state':'SAFE','rankable_energy':True,'complete':True,
                'covered_until_s':definition['window_s'],'trace':[{'time_s':definition['window_s']}],
                'peaks_degC':{node:['50','50'] for node in definition['limits']}}
                for sid,definition in d['scene_spec'].items()}}
        return d,candidate,ev

    def test_15_receipt_synthetic_positive_all_five_not_physical_evidence(self):
        for pid in p.PROBLEMS:
            d,c,e=self.receipt(pid)
            self.assertEqual(audit_heuristic.receipt_issues(e,c,d),[])

    def test_16_cross_problem_receipt_rejected(self):
        for pid in p.PROBLEMS[1:]:
            d,c,e=self.receipt(pid);e['problem_id']='base__R1'
            self.assertTrue(audit_heuristic.receipt_issues(e,c,d))

    def test_17_full_window_deadline_peak_checks_preserved(self):
        d,c,e=self.receipt('base__R3');sid=next(iter(e['scenes']))
        for field,value in [('completed_at_elapsed_s',300),('rankable_energy',False)]:
            v=deepcopy(e);v[field]=value
            self.assertTrue(audit_heuristic.receipt_issues(v,c,d))
        v=deepcopy(e);v['scenes'][sid]['covered_until_s']='0.3'
        self.assertTrue(audit_heuristic.receipt_issues(v,c,d))
        v=deepcopy(e);v['scenes'][sid]['peaks_degC']['CPU1']=['80','81']
        self.assertTrue(audit_heuristic.receipt_issues(v,c,d))

    def test_18_old_heft_archive_is_identically_classified(self):
        from run_heuristic_followup import result_records as old
        folder=p.ROOT/'results/four_method_comparison01/heft'
        r=p.read(folder/'result.json');d=p.read(p.BASE);d['problem_id']='base__R1'
        a=old(r,d,input_valid=True,source_valid=True)
        b=audit_heuristic.result_records(r,d,input_valid=True,source_valid=True)
        self.assertEqual(a,b)

    def test_19_old_linked_archive_is_identically_classified(self):
        from run_four_method_comparison import result_records as old
        folder=p.ROOT/'results/four_method_comparison01/anchor_linked4'
        r=p.read(folder/'result.json');d=p.read(p.BASE);d['problem_id']='base__R1'
        job=p.METHODS[1]
        a=old(job,r,d,folder,input_valid=True,source_valid=True)
        b=p.result_records(job,r,d,folder,input_valid=True,source_valid=True)
        self.assertEqual(a['execution'],b['execution'])
        self.assertEqual(a['context'],b['context'])
        self.assertEqual(a['usable_U_J'],b['usable_U_J'])

    def test_20_old_whole_archive_is_identically_classified(self):
        from four_whole_status import result_records as old
        folder=p.ROOT/'results/four_method_comparison01/whole_milp'
        r=p.read(folder/'result.json');d=p.read(p.BASE);d['problem_id']='base__R1'
        a=old(r,d,folder,input_valid=True,source_valid=True)
        b=audit_whole.result_records(r,d,folder,input_valid=True,source_valid=True)
        self.assertEqual(a,b)


class PreparationTests(unittest.TestCase):
    def report(self):
        return {'protocol':p.PROTOCOL,'passed':True,'tests_run':1,'errors':0,'failures':0,
                'skipped':0,'error':None,'source_sha256':p.sources(),'source_unchanged':True,
                'blocked_calls':{'MOCK_ONLY':0},'research_calls':0,'native_calls':0,
                'physical_models':0,'thermal_evaluations':0}

    def test_21_draft_prepare_and_snapshot_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);gate=folder/'mock_checks.json';p.save(gate,self.report())
            out=folder/'prepared';summary=p.prepare(out,gate)
            self.assertEqual(summary['slots'],40);self.assertFalse(summary['authorised_to_execute'])
            self.assertEqual(p.read(out/'ledger.json')['consumed'],0)
            self.assertFalse(p.read(out/'authorization.example.json')['approved'])
            self.assertEqual(p.admission(out),summary)
            with self.assertRaises(FileExistsError):p.prepare(out,gate)
            d=p.read(out/'declaration.json');d['inputs']['base__R2']['input_sha256']='drift'
            p.save(out/'declaration.json',d)
            with self.assertRaises(ValueError):p.admission(out)

    def test_22_failure_source_drift_and_bad_gate_rejected(self):
        for key,value in [('passed',False),('research_calls',1),('source_sha256',{}),
                          ('blocked_calls',{'heat':1}),('skipped',1)]:
            with tempfile.TemporaryDirectory() as temp:
                folder=Path(temp);g=self.report();g[key]=value;p.save(folder/'gate.json',g)
                with self.assertRaises(ValueError):p.prepare(folder/'no_output',folder/'gate.json')
                self.assertFalse((folder/'no_output').exists())


# Reuse the 22 detailed K152 cutoff regressions against the derived whole checker.
# This test-only module patch cannot reach a real method or alter production modules.
import test_four_whole_status as legacy_tests
class DerivedWholeCutoffTests(legacy_tests.WholeResultAuditTests):
    def setUp(self):
        patcher=patch.object(legacy_tests,'audit',audit_whole)
        patcher.start();self.addCleanup(patcher.stop)
        super().setUp()
        self.d['problem_id']='base__R1'
