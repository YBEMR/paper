"""Pure five-slot launcher tests: no scientific processes or actual evaluations."""
from contextlib import redirect_stdout
import io
import shutil
import subprocess
import unittest
from unittest.mock import patch
import uuid

from . import run
from .initializer import run_heft_i1
from research.chapter4_scheduler.method import Bindings


class RunnerTests(unittest.TestCase):
    def cases(self):
        return [{'case_id':f'{r}__n{n}','root_id':r,'stages_per_scene':n} for r in ('U01','U02') for n in (6,12)]

    def test_exact_five_slots_and_no_search_route(self):
        slots=run.slots(self.cases())
        self.assertEqual([(s['case_id'],s['arm']) for s in slots],list(run.ORDER))
        self.assertEqual(len(slots),5)
        for arm in ('ON','OFF','SA','HEFT_I1'):
            with self.assertRaises(ValueError):run.dispatch(arm,None,None,None,None)

    def test_I1_dispatch_binds_exact_shared_function_and_original_evaluator_root(self):
        evaluator,root,loader=object(),object(),object()
        original=Bindings(object(),evaluator,'REAL_CORE')
        with patch('research.chapter4_scheduler.validation.lifecycle.execute_heft',return_value='MOCK_ONLY') as execute:
            self.assertEqual(run.dispatch('I1',loader,'folder',root,original),'MOCK_ONLY')
        args=execute.call_args
        self.assertIs(args.kwargs['budget'],root)
        self.assertIs(args.kwargs['bindings'].initializer,run_heft_i1)
        self.assertIs(args.kwargs['bindings'].evaluator,evaluator)
        self.assertEqual(args.kwargs['bindings'].kind,'REAL_I1')

    def test_controller_failure_preserves_all_slots_and_no_retry(self):
        parent=run.REPO.parent.resolve()
        out=parent/('mock_i1_runner_'+uuid.uuid4().hex)
        out.mkdir()
        try:
            plan={'cases':self.cases(),'slots':run.slots(self.cases()),'subject_commit':'MOCK_ONLY'}
            run.save(out/'plan.json',plan)
            with patch.object(run,'verify'),patch.object(run.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'MOCK_ONLY','FAILURE')) as launch,redirect_stdout(io.StringIO()):
                self.assertEqual(run.batch(out),1)
            self.assertEqual(launch.call_count,1)
            command=run.read(out/'calls'/plan['slots'][0]['id']/'method_command_started.json')['argv']
            self.assertEqual(command,launch.call_args.args[0])
            self.assertEqual(command[3],'research.chapter4_scheduler.i1.run')
            final=run.read(out/'batch_return.json')
            self.assertEqual(len(final['slots']),5)
            self.assertEqual(final['retry_count'],0)
            self.assertEqual(sum(s['status']=='NOT_RUN_TECHNICAL_STOP' for s in final['slots']),4)
            self.assertEqual(len(run.read(out/'summary.json')['rows']),5)
        finally:
            assert out.resolve().is_relative_to(parent) and out.name.startswith('mock_i1_runner_')
            shutil.rmtree(out)


if __name__=='__main__':unittest.main()
