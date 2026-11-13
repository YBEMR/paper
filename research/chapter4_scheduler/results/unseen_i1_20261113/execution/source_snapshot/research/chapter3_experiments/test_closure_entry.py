"""Artificial lifecycle checks only: no solver, thermal integration or process."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from research.chapter3_experiments import closure_entry as e


class ClosureChecks(unittest.TestCase):
    def run_fake(self, mode='normal'):
        from research.chapter3_method_entry_executor import monitor
        with tempfile.TemporaryDirectory(dir=e.b.EXP, prefix='closure_mock_') as tmp:
            self.assertTrue(Path(tmp).resolve().is_relative_to(e.b.EXP.resolve()))
            root=Path(tmp);out=root/'run';plan=root/'plan.json';approval=root/'approval.json'
            plan.write_text('{}');approval.write_text('{}')
            calls=[]
            def slot(plan_path,approval_path,plan_value,output,job,kind,*args):
                calls.append((job['id'],kind))
                if kind=='method':
                    state='TECHNICAL_FAILURE' if mode=='failure' else 'NORMAL_TIME_LIMIT'
                    return dict(status=state,worker=dict(safe=dict(preserved=mode!='no_safe')))
                if job['case'].endswith('_no_limit'):
                    return dict(status='SAFETY_FAILURE',worker=dict(state='THERMAL_VIOLATION',error=None),
                        returncode=0,error=None,monitor=dict(cleanup_verified_observed_tree=True))
                return dict(status='NORMAL_COMPLETION')
            with patch.object(e,'OUTPUT',out),patch.object(e.b,'RESULTS',root),\
                 patch.object(e.b,'authorize',return_value={}),patch.object(e,'verify_sources'),\
                 patch.object(e.b,'run_slot',side_effect=slot),\
                 patch.object(monitor,'default_host_probe',return_value={}),\
                 patch.object(monitor,'host_gate',return_value={'passed':True}):
                result=e.run(plan,approval,out)
                with self.assertRaises(ValueError):e.run(plan,approval,out)
            return result,calls

    def test_all_ten_jobs_and_one_post_each_expected_unsafe_continues(self):
        result,calls=self.run_fake()
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual((result['method_attempts'],result['post_attempts']),(10,10))
        self.assertEqual([name for name,kind in calls if kind=='method'],[j['id'] for j in e.JOBS])
        self.assertEqual(len(set(calls)),20)
        self.assertEqual([j['seed'] for j in e.JOBS if j['method']=='sa'],list(range(101,106)))

    def test_normal_timeout_without_candidate_continues_no_post(self):
        result,calls=self.run_fake('no_safe')
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual((result['method_attempts'],result['post_attempts']),(10,0))
        self.assertEqual(len(calls),10)

    def test_technical_failure_stops_without_retry(self):
        result,calls=self.run_fake('failure')
        self.assertEqual(result['state'],'STOPPED')
        self.assertEqual(result['method_attempts'],1)
        self.assertEqual(len(calls),1)

    def test_expected_violation_does_not_cover_failure_or_full_method(self):
        post=dict(status='SAFETY_FAILURE',worker=dict(state='THERMAL_VIOLATION'),returncode=0,
                  monitor=dict(cleanup_verified_observed_tree=True))
        self.assertTrue(e.expected_ablation_violation(e.JOBS[3],post))
        self.assertFalse(e.expected_ablation_violation(e.JOBS[0],post))
        self.assertFalse(e.expected_ablation_violation(e.JOBS[3],dict(post,watchdog_fired=True)))
        self.assertFalse(e.expected_ablation_violation(e.JOBS[3],dict(post,error='fixture')))
        self.assertFalse(e.expected_ablation_violation(e.JOBS[3],dict(post,returncode=2)))


if __name__=='__main__':unittest.main()
