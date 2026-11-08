"""Guarded artificial new-lifecycle/launcher checks. Zero real research calls."""
from contextlib import ExitStack
import importlib.abc
import io
import json
from pathlib import Path
import sys
import time
import traceback
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.mechanism_check.run import save,sha


def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--out",required=True,type=Path);args=p.parse_args();out=args.out.resolve()
    out.relative_to(REPO/"research/chapter4_scheduler/results")
    out.mkdir(parents=True,exist_ok=False)
    own=sorted(Path(__file__).parent.glob("*.py"));before={str(p.relative_to(REPO)):sha(p) for p in own}
    forbidden=[];stream=io.StringIO();fatal=None;result=None
    def deny(name):
        def call(*args,**kwargs):forbidden.append(name);raise AssertionError("FORBIDDEN_REAL_CALL:"+name)
        return call
    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.rsplit(".",1)[-1] in ("milp","matlab_bridge") or fullname.startswith(("scipy.optimize","matlab.engine","gurobipy","pulp","cvxpy")):
                forbidden.append("import:"+fullname);raise AssertionError("FORBIDDEN_SOLVER_IMPORT:"+fullname)
    import thermal,heft_method
    guard=Guard();sys.meta_path.insert(0,guard);start=time.monotonic()
    try:
        with ExitStack() as stack:
            for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate",
                    "subprocess.Popen","os.system","socket.create_connection","socket.socket.connect"):
                stack.enter_context(patch(target,side_effect=deny(target)))
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName("research.chapter4_scheduler.validation.test_validation"))
    except BaseException:fatal=traceback.format_exc()
    finally:sys.meta_path.remove(guard)
    after={str(p.relative_to(REPO)):sha(p) for p in own}
    record={"passed":result is not None and result.wasSuccessful() and not fatal and not forbidden and before==after,
        "tests_run":result.testsRun if result else 0,"wall_s":time.monotonic()-start,"fatal":fatal,"forbidden_calls":forbidden,
        "source_sha256":before,"source_bytes_unchanged":before==after,"evidence_kind":"ARTIFICIAL_FIXTURES_AND_MOCK_RECEIPTS_ONLY",
        "real_HEFT_calls":0,"real_thermal_evaluations":0,"real_optimization_calls":0}
    save(out/"checks.json",record);(out/"test_output.txt").write_text(stream.getvalue()+(fatal or ""),encoding="utf-8")
    print(json.dumps(record),flush=True)
    return not record["passed"]


if __name__=="__main__":sys.exit(main())
