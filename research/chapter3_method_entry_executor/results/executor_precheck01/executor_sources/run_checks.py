"""Freeze executor and run simulations, with all real numerical/process calls blocked."""
import argparse
import io
from pathlib import Path
import sys
import time
import unittest

from .freeze import freeze
from .common import ROOT, read, save, sha, verify_sources
from research.chapter3_formal_input_adapter.run_checks import Guard
from research.chapter3_deadline_reference.run_checks import RecordedResult


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    out=Path(p.parse_args().output).resolve()
    guard=Guard();sys.meta_path.insert(0,guard);sys.addaudithook(guard.audit)
    started=time.monotonic();plan=freeze(out)
    from . import test_executor, test_monitor
    test_executor.FROZEN=out
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(test_executor),
                             unittest.defaultTestLoader.loadTestsFromModule(test_monitor)])
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
    verify_sources(plan)
    passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    receipt={'state':'PASS' if passed else 'FAIL','passed':passed,'tests':result.testsRun,
             'records':result.records,'subtests':result.subtest_records,
             'elapsed_s':time.monotonic()-started,'plan_sha256':sha(out/'plan.json'),
             'input_sha256':sha(out/'common_input.json'),'source_hashes':len(plan['source_sha256']),
             'sources_unchanged':True,'guard_denied':guard.denied,
             'actual_algorithm_calls':0,'actual_process_launches':0,'actual_matlab_starts':0,
             'actual_model_constructions':0,'actual_thermal_integrations':0,
             'simulation_only':True,'authorization_template_is_false':read(out/'authorization_template.json')['authorized'] is False}
    (out/'tests.txt').write_text(log.getvalue(),encoding='utf8');save(out/'checks.json',receipt)
    print({k:receipt[k] for k in ('state','tests','elapsed_s','plan_sha256')})
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
