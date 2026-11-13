"""SA adapter unit checks: mock receipts, guarded original-SA fixture replay."""
from contextlib import ExitStack
from datetime import datetime,timezone
import importlib.abc
import io
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
    out.relative_to(REPO/"research/chapter4_scheduler/results");out.mkdir(parents=True,exist_ok=False)
    files=[Path(__file__),Path(__file__).with_name("sa_adapter.py"),Path(__file__).with_name("test_sa_adapter.py")]
    before={p.relative_to(REPO).as_posix():sha(p) for p in files}
    forbidden=[];synthetic_calls=[];stream=io.StringIO();result=None;fatal=None
    def deny(label):
        def call(*args,**kwargs):forbidden.append(label);raise AssertionError("FORBIDDEN_RESEARCH_CALL:"+label)
        return call
    class Guard(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname.rsplit(".",1)[-1] in ("milp","matlab_bridge") or fullname.startswith(("scipy.optimize","matlab.engine","gurobipy","pulp","cvxpy")):
                forbidden.append("import:"+fullname);raise AssertionError("FORBIDDEN_SOLVER_IMPORT:"+fullname)
    import thermal,heft_method,sa_method
    original_sa=sa_method.run_sa
    def synthetic_sa(instance,*args,**kwargs):
        if instance.get("id")!="pure_lifecycle_fixture":
            forbidden.append("SA_on_nonfixture");raise AssertionError("ONLY_ARTIFICIAL_INPUT_ALLOWED")
        synthetic_calls.append({"fixture":instance["id"],"seed":kwargs.get("seed")})
        return original_sa(instance,*args,**kwargs)
    guard=Guard();sys.meta_path.insert(0,guard);started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    try:
        with ExitStack() as stack:
            for target in ("thermal.evaluate_candidate","thermal.evaluate_piecewise","heft_method.run_heft","heft_method.build_heft_candidate",
                    "subprocess.Popen","os.system","socket.create_connection","socket.socket.connect"):
                stack.enter_context(patch(target,side_effect=deny(target)))
            stack.enter_context(patch("sa_method.run_sa",side_effect=synthetic_sa))
            suite=unittest.defaultTestLoader.loadTestsFromName("research.chapter4_scheduler.validation.test_sa_adapter")
            result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    except BaseException:fatal=traceback.format_exc()
    finally:sys.meta_path.remove(guard)
    after={p.relative_to(REPO).as_posix():sha(p) for p in files}
    record={"started_utc":started,"ended_utc":datetime.now(timezone.utc).isoformat(),"wall_s":time.monotonic()-clock,
        "passed":result is not None and result.wasSuccessful() and not fatal and not forbidden and before==after,
        "tests_run":result.testsRun if result else 0,"fatal":fatal,"forbidden_calls":forbidden,
        "failures":[{"test":str(t),"trace":trace} for t,trace in result.failures] if result else [],
        "errors":[{"test":str(t),"trace":trace} for t,trace in result.errors] if result else [],
        "source_sha256":before,"source_bytes_unchanged":before==after,
        "original_SA_on_synthetic_mock_receipts":synthetic_calls,"real_workload_SA_calls":0,"real_thermal_integrations":0,
        "evidence_kind":"ARTIFICIAL_FIXTURES_AND_INVENTED_RECEIPTS; ORIGINAL_SA_DIFFERENTIAL_REPLAY_IS_NOT_RESEARCH_EVIDENCE"}
    save(out/"checks.json",record);(out/"test_output.txt").write_text(stream.getvalue()+(fatal or ""),encoding="utf-8")
    print({k:record[k] for k in ("passed","tests_run","wall_s","forbidden_calls","original_SA_on_synthetic_mock_receipts")},flush=True)
    return not record["passed"]


if __name__=="__main__":sys.exit(main())
