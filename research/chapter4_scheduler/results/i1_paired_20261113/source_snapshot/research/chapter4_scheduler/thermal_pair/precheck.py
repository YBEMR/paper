"""Guarded temperature-pair input/worker tests; no real research calls."""
from contextlib import ExitStack
from datetime import datetime,timezone
import io
from pathlib import Path
import shutil
import sys
import time
import traceback
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import read,save,sha


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True,type=Path);args=parser.parse_args()
    out=args.out.resolve();out.relative_to(REPO/"research/chapter4_scheduler/results");out.mkdir(parents=True,exist_ok=False)
    paths=sorted(Path(__file__).parent.glob("*.py"));before={p.relative_to(REPO).as_posix():sha(p) for p in paths}
    snapshot=out/"source_snapshot";snapshot.mkdir()
    for p in paths:shutil.copyfile(p,snapshot/p.name)
    forbidden=[];stream=io.StringIO();fatal=None;result=None
    def deny(name):
        def call(*args,**kwargs):forbidden.append(name);raise AssertionError("FORBIDDEN_RESEARCH_CALL:"+name)
        return call
    import thermal,heft_method,sa_method
    started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    try:
        with ExitStack() as stack:
            for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate",
                           "sa_method.run_sa","subprocess.Popen","os.system","socket.create_connection","socket.socket.connect"):
                stack.enter_context(patch(target,side_effect=deny(target)))
            suite=unittest.defaultTestLoader.loadTestsFromName("research.chapter4_scheduler.thermal_pair.test_pair")
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    except BaseException:fatal=traceback.format_exc()
    after={p.relative_to(REPO).as_posix():sha(p) for p in paths}
    record={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
        "passed":result is not None and result.wasSuccessful() and not fatal and not forbidden and before==after,
        "tests_run":result.testsRun if result else 0,"fatal":fatal,"forbidden_calls":forbidden,
        "failures":[{"test":str(t),"trace":trace} for t,trace in result.failures] if result else [],
        "errors":[{"test":str(t),"trace":trace} for t,trace in result.errors] if result else [],
        "source_sha256":before,"source_bytes_unchanged":before==after,"real_method_calls":0,"real_thermal_integrations":0,
        "evidence_kind":"PINNED_REAL_INPUT_READS_AND_ARTIFICIAL_ALGORITHM_RECEIPTS_ONLY"}
    save(out/"checks.json",record);(out/"test_output.txt").write_text(stream.getvalue()+(fatal or ""))
    print({k:record[k] for k in ("passed","tests_run","wall_s","fatal","forbidden_calls")},flush=True)
    return not record["passed"]


if __name__=="__main__":sys.exit(main())
