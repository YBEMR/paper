"""Pure fake continuation lifecycle; every scientific/process seam is forbidden.

Invented SAFE-shaped JSON here is not scientific evidence. No HEFT, legality
checker, thermal integrator, solver or child process may run in these tests.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from . import controller as c


SLOTS = [dict(ordinal=1, problem_id='base__R1', view='H'),
         dict(ordinal=2, problem_id='base__R1', view='R'),
         dict(ordinal=3, problem_id='base__R2', view='R'),
         dict(ordinal=4, problem_id='base__R2', view='H')]


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3] / '.runtime'
        root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='h02_resume_fake_', dir=root)
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.core = self.repo / 'research/chapter3_experiments'
        self.old = self.core / 'results/response_information_execution01'
        self.out = self.core / 'results/response_information_resume01'
        self.pre = self.core / 'results/response_information_resume_precheck01'
        self.pre.mkdir(parents=True)
        self.trace, self.roots, self.jobs = [], [], []
        self.no_safe, self.fail_plan, self.fail_audit = set(), set(), set()
        self.reject_recovery = False
        self.raw = {'reason':'DECLARED_SEARCH_COMPLETED', 'safe_candidate':{'MOCK_ONLY':'original-final-best'}}
        oldfiles = {
            'terminal.json': {'stopped': True, 'slots': [{'MOCK_ONLY':'old_failure'}]},
            'ledger/slot_1.claim.json': {'MOCK_ONLY': 'old120-consumed'},
            'slot_1/planner_public/job.json': {'packet': self.packet(SLOTS[0])},
            'slot_1/planner_public/method/result.json': self.raw,
            'slot_1/controller_private/truth_H.json': {'MOCK_ONLY':'sealed-H'},
            'slot_1/controller_private/static_contract.json': {'passed':True,'MOCK_ONLY':True},
        }
        hashes = {}
        for relative, value in oldfiles.items():
            path = self.old / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            c.atomic_json(path, value)
            hashes[path.relative_to(self.repo).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.declaration = {'prior_sha256':hashes, 'recovered_candidate_semantic_sha256':'original-best-semantic'}
        c.atomic_json(self.pre / 'execution_declaration.json', self.declaration)
        self.policy = {'slots':deepcopy(SLOTS)}
        self.gate = {'authorization_id':'H02_MOCK_ONLY_RESUME',
                     'allowed_run_directory':str(self.out),
                     'authority_store':str(self.repo / 'MOCK_authority')}
        owner = self
        class FakeRoot:
            def __init__(self, seconds):
                self.limit_s = seconds
                self.origin = 1000 + len(owner.roots) * 1000
                self.elapsed = 0.0
                owner.roots.append(self)
                owner.trace.append(('root', seconds, self.origin))
            def check(self):
                owner.trace.append(('check', self.limit_s, self.origin))
                if self.elapsed >= self.limit_s:
                    raise c.RootBudgetExpired('MOCK_ROOT_EXPIRED')
        self.patches = ExitStack(); self.addCleanup(self.patches.close)
        replacements = dict(CORE=self.core, PRE=self.pre, OLD=self.old, OUT=self.out,
            policy_files=lambda:(deepcopy(self.policy),deepcopy(self.gate)),
            require_research_authorization=lambda gate,policy:True,
            verify_runtime_freeze=lambda:{'MOCK_ONLY':'freeze'}, RootClock=FakeRoot,
            verify_final_export=self.verify, frozen_candidate=self.freeze,
            build_bundle=self.bundle, supervise=self.supervise,
            prepare_public_slot=self.prepare)
        for name, value in replacements.items():
            self.patches.enter_context(patch.object(c,name,value))
        # Subprocess and every actual mathematical entry remain guarded even if
        # a future controller edit accidentally bypasses our explicit fake seams.
        import subprocess
        self.forbidden = Mock(side_effect=AssertionError('SCIENTIFIC_OR_REAL_PROCESS_FORBIDDEN'))
        self.patches.enter_context(patch.object(subprocess,'Popen',self.forbidden))
        import h02_pair_b0.backends as backends
        self.patches.enter_context(patch.object(backends,'resolve_real_bindings',self.forbidden))
        self.patches.enter_context(patch.object(backends,'planner_chain',self.forbidden))
        self.patches.enter_context(patch.object(backends,'audit_chain',self.forbidden))

    @staticmethod
    def packet(slot):
        return {'problem_id':slot['problem_id'],'view':slot['view'],
                'MOCK_ONLY_ordinal':slot['ordinal']}

    def verify(self,packet,raw):
        ordinal = packet['MOCK_ONLY_ordinal']
        self.trace.append(('export',ordinal))
        if ordinal == 1:
            self.assertEqual(raw,self.raw)
            if self.reject_recovery:
                raise ValueError('MOCK_RECOVERY_EXPORT_INVALID')
        return {'technical_details':[], 'best':None if ordinal in self.no_safe else {'MOCK_ONLY':ordinal}}

    def freeze(self,packet,raw,truth,contract,runtime):
        self.trace.append(('freeze',packet['MOCK_ONLY_ordinal']))
        return {'candidate_semantic_sha256':'original-best-semantic',
                'candidate_json':json.dumps(raw['safe_candidate']),
                'problem_id':packet['problem_id'],'view':packet['view'],
                'MOCK_ONLY':True}

    def bundle(self,path):
        self.assertTrue(self.roots)
        self.trace.append(('bundle',self.roots[-1].limit_s,self.roots[-1].origin))
        return {'bundle_sha256':'MOCK_ONLY_BUNDLE'}

    def prepare(self,root,slot,callroot):
        self.assertEqual(root.limit_s,120)
        self.assertIs(root,self.roots[-1])
        self.trace.append(('prepare',slot['ordinal'],root.limit_s,root.origin))
        private=callroot/'controller_private';private.mkdir()
        return self.packet(slot),{'MOCK_ONLY':'sealed-H'}, {'passed':True}, private

    def supervise(self,job,info,bundle,output,policy):
        self.jobs.append(deepcopy(job))
        ordinal,kind = job['ordinal'],job['kind']
        self.trace.append((kind,ordinal,job['limit_s'],job['root_origin']))
        self.assertEqual(job['limit_s'],120 if kind == 'planner' else 60)
        self.assertEqual(job['root_origin'],self.roots[-1].origin)
        if (kind == 'planner' and ordinal in self.fail_plan) or (kind == 'audit' and ordinal in self.fail_audit):
            return {'watchdog_killed':False,'returncode':3}
        if kind == 'planner':
            raw={'reason':'DECLARED_SEARCH_COMPLETED','safe_candidate':{'MOCK_ONLY':ordinal}}
            payload={'raw_method_result':raw}
        else:
            payload={'audit_status':'MOCK_ONLY_TRUE_H_SAFE_SHAPE','stop_required':False,'usable_as_research_evidence':False}
        c.atomic_json(output/'worker_return.json',{'job_sha256':c.sha(job),'payload':payload})
        return {'watchdog_killed':False,'returncode':0}

    def calls(self):
        return [(job['kind'],job['ordinal'],job['limit_s']) for job in self.jobs]

    def test_exact_order_no_plan1_and_aggregate_720_includes_old120(self):
        result=c.run(self.out)
        self.assertFalse(result['stopped'])
        self.assertEqual(self.calls(), [('audit',1,60),('planner',2,120),('audit',2,60),
            ('planner',3,120),('audit',3,60),('planner',4,120),('audit',4,60)])
        self.assertEqual([root.limit_s for root in self.roots],[60,120,60,120,60,120,60])
        self.assertEqual(120+sum(job['limit_s'] for job in self.jobs),720)
        self.assertEqual(result['prior_plans_consumed'],1)
        self.assertTrue(result['first_planner_not_rerun'])
        self.forbidden.assert_not_called()

    def test_recovery_reuses_exact_original_best_no_new_plan(self):
        result=c.run(self.out)
        first=self.jobs[0]
        self.assertEqual(first['kind'],'audit')
        self.assertEqual(json.loads(first['token']['candidate_json']),self.raw['safe_candidate'])
        recovery=c.load_json(self.out/'slot_1/controller_private/recovery.json')
        self.assertTrue(recovery['original_planning_120s_still_consumed'])
        self.assertFalse(recovery['new_search_or_thermal_evaluation'])
        self.assertEqual(recovery['new_planner_calls'],0)
        self.assertEqual(result['slots'][0]['planning_source'],'K177 frozen raw; no replan')

    def test_recovery_export_failure_stops_before_any_new_science(self):
        self.reject_recovery=True
        result=c.run(self.out)
        self.assertTrue(result['stopped']);self.assertEqual(self.jobs,[])
        self.assertTrue((self.out/'ledger/STOP.json').exists())
        self.forbidden.assert_not_called()

    def test_first_post_process_failure_stops_remaining_plans(self):
        self.fail_audit={1}
        result=c.run(self.out)
        self.assertTrue(result['stopped']);self.assertEqual(self.calls(),[('audit',1,60)])
        self.assertTrue((self.out/'ledger/audit_1.claim.json').exists())
        self.assertFalse((self.out/'slot_2').exists())

    def test_plan2_failure_stops_without_post2_or_plan3(self):
        self.fail_plan={2}
        result=c.run(self.out)
        self.assertTrue(result['stopped'])
        self.assertEqual(self.calls(),[('audit',1,60),('planner',2,120)])
        self.assertTrue((self.out/'ledger/slot_2.claim.json').exists())

    def test_plan_no_safe_skips_unique_post_and_keeps_order(self):
        self.no_safe={2}
        result=c.run(self.out)
        self.assertFalse(result['stopped'])
        self.assertEqual(self.calls(), [('audit',1,60),('planner',2,120),
            ('planner',3,120),('audit',3,60),('planner',4,120),('audit',4,60)])
        self.assertEqual(result['slots'][1]['plan_status'],'PLAN_NO_SAFE')
        self.assertFalse((self.out/'ledger/audit_2.claim.json').exists())

    def test_fresh_output_and_global_claim_disallow_second_run(self):
        c.run(self.out)
        count=len(self.jobs)
        with self.assertRaisesRegex(ValueError,'FRESH_FIXED_RESUME_DIRECTORY_REQUIRED'):
            c.run(self.out)
        self.assertEqual(len(self.jobs),count)

    def test_existing_global_claim_disallows_first_launch(self):
        store=Path(self.gate['authority_store']);store.mkdir()
        c.atomic_json(store/(self.gate['authorization_id']+'.claim.json'),{'MOCK_ONLY':'already consumed'})
        with self.assertRaises(FileExistsError):c.run(self.out)
        self.assertEqual(self.jobs,[]);self.assertFalse(self.out.exists())

    def test_prior_bytes_drift_disallows_resume_before_new_claim(self):
        path=self.old/'slot_1/planner_public/method/result.json'
        path.write_text('{"MOCK_ONLY":"changed"}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'OLD_EVIDENCE_DRIFT'):c.run(self.out)
        self.assertEqual(self.jobs,[]);self.assertFalse(self.out.exists())

    def test_prepare_and_bundle_charged_to_current_immutable_root(self):
        c.run(self.out)
        prepared=[row for row in self.trace if row[0]=='prepare']
        self.assertEqual([(r[1],r[2]) for r in prepared],[(2,120),(3,120),(4,120)])
        for row in prepared:
            job=next(j for j in self.jobs if j['kind']=='planner' and j['ordinal']==row[1])
            self.assertEqual(job['root_origin'],row[3])
        for job in self.jobs:
            self.assertIn(('bundle',job['limit_s'],job['root_origin']),self.trace)


if __name__=='__main__':
    unittest.main()
