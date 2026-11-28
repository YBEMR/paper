"""Twelve registered streams in three process-isolated waves using the frozen warm entry."""
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import FunctionType, SimpleNamespace

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"ch4_quota_warm_confirm"))
import warm_confirm as warm
from warm_confirm import control

WAVES=(("A02","A06","C10","C11"),("A01","A03","A04","A05"),("B07","B08","C09","C12"))
ROOT=warm.ROOT

def main():
    started=time.perf_counter()
    ROOT.mkdir(exist_ok=False)
    control.ROOT=ROOT
    allocated=sorted(os.sched_getaffinity(0))
    cores=allocated[::2][:4]
    assert len({Path(f"/sys/devices/system/cpu/cpu{c}/topology/thread_siblings_list").read_text() for c in cores})==4
    try:
        transfer=warm.prepare(cores)
        reg=Path(os.environ["FAST_SCRATCH"])/"nt/research/m1i_generalization/registration/inputs"
        cases={transfer.m.label(o):o for o in transfer.m.u2.CASES}
        order=[code for wave in WAVES for code in wave]
        assert len(set(order))==len(order)==12 and set(order)==cases.keys()
        for o in cases.values():
            assert o["ambient"]==35 and hashlib.sha256((reg/o["input"]).read_bytes()).hexdigest()==o["input_sha256"]
        control.save(ROOT/"registration.json",dict(waves=WAVES,cores=cores,cases=cases))
    except BaseException:
        control.save(ROOT/"preparation_account.json",dict(passed=False,actual_cpu_s=control.spent(),wall_s=time.perf_counter()-started,error=traceback.format_exc()))
        raise
    os.sched_setaffinity(0,set(allocated))
    native=control.monitored
    env=dict(native.__globals__,subprocess=SimpleNamespace(Popen=warm.WarmChild))
    control.monitored=FunctionType(native.__code__,env,native.__name__,native.__defaults__)
    control.CASES=tuple(order)
    base=control.spent()
    assert base<=240
    control.save(ROOT/"preparation_account.json",dict(passed=True,actual_cpu_s=base,wall_s=time.perf_counter()-started,limit=240))
    print("12 input hashes and warm gate passed",round(base,3),flush=True)
    start=time.perf_counter();errors={}
    try:
        for wave in WAVES:
            if 4500-(control.spent()-base)<4*374+1:
                errors["admission"]="insufficient remaining CPU for the next wave"
                break
            # Fresh lane supervisors each wave. No process which solved one stream
            # can become the ancestor of any subsequent stream or timed cell.
            with ProcessPoolExecutor(4,mp_context=mp.get_context("fork")) as pool:
                futures={code:pool.submit(control.lane,(order.index(code),cpu)) for code,cpu in zip(wave,cores)}
                for code,job in futures.items():
                    try:job.result()
                    except Exception:errors[code]=traceback.format_exc()
            print("closed wave",wave,round(control.spent()-base,2),flush=True)
    finally:
        actual=control.spent()-base
        control.save(ROOT/"formal_account.json",dict(actual_cpu_s=actual,limit=4500,cores=cores,waves=WAVES,
            elapsed_parallel_s=time.perf_counter()-start,errors=errors))
    assert actual<=4500

if __name__=="__main__":main()
