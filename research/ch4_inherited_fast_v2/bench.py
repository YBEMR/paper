"""Fixed candidate replay with exclusive time components and a cumulative CPU ceiling."""
import csv
import ctypes
import json
import math
import os
import resource
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from types import FunctionType, MethodType

from sequence import CASES, FIRST, HERE, recover, sha

from importlib.util import module_from_spec, spec_from_file_location
spec = spec_from_file_location("frozen_round_one", FIRST/"run.py")
v1 = module_from_spec(spec)
spec.loader.exec_module(v1)
from incremental import HEAT_BLOB, Integration, common_rows, continuation, np

ROOT = Path(os.environ["FIXED_RUN"]).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
OUT = ROOT/"receipts"
OUT.mkdir(exist_ok=True)
T = time.perf_counter
PHASES = ("replay","events","identity","checkpoint","integrate","certificate","write")
CPU = min(os.sched_getaffinity(0))


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,sort_keys=True,allow_nan=False)+"\n")
    tmp.replace(path)


def clone(fn, **changes):
    return FunctionType(fn.__code__,dict(fn.__globals__,**changes),fn.__name__,fn.__defaults__,fn.__closure__)


def timed(fn, totals, name):
    def wrapper(*args,**kw):
        t = T()
        result = fn(*args,**kw)
        totals[name] += T()-t
        return result
    return wrapper


class Writes:
    def __init__(self, totals):
        self.savez_compressed = timed(np.savez_compressed,totals,"write")
    def __getattr__(self, name):
        return getattr(np,name)


def instrument(engine, kernel, totals):
    original = engine.cert.__func__
    evaluate = original.__globals__["evaluate"]
    wrapped = clone(evaluate, integrate=kernel,
                    independent_events=timed(evaluate.__globals__["independent_events"],totals,"events"))
    wrapped.__kwdefaults__ = evaluate.__kwdefaults__
    engine.cert = MethodType(clone(original, evaluate=wrapped, np=Writes(totals),
                                   put=timed(original.__globals__["put"],totals,"write")),engine)
    engine.build = timed(engine.build,totals,"events")
    cert = engine.cert
    def certificate(*args,**kw):
        start = T()
        before = sum(totals.values())
        value = cert(*args,**kw)
        totals["certificate"] += T()-start-(sum(totals.values())-before)
        return value
    engine.cert = certificate


def digest_output(values):
    from hashlib import sha256
    import struct
    h = sha256()
    for value in values:
        a = np.asarray(value)
        h.update(a.dtype.str.encode())
        h.update(repr(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def one(v, original, resume, obj, seq, configs, truth, case, rep, mode):
    cpu_start = time.process_time()
    label = f"{case}-{rep}-{mode}"
    dest = ROOT/"physical"/label
    mgr = v.m
    eng,flow = mgr.build(obj,dest)
    # Both actual call sites rebuild the candidate; search also checks the causal ledger.
    for machine in (eng,flow.eng):
        machine.out = dest
        assert machine.cert.__func__.__globals__["evaluate"].__globals__["integrate"] is original
    totals = Counter()
    tick = T()
    kernel = Integration(mode,original,resume,(case,obj["input_sha256"],HEAT_BLOB,obj["horizon_ticks"]))
    setup = T()-tick
    kernel.times = totals
    for machine in (eng,flow.eng):
        instrument(machine,kernel,totals)
    results = []
    for ordinal,(delivery,stage,key,detail) in enumerate(seq):
        config = configs[key]
        kernel.ordinal = ordinal
        totals.clear()
        start = T()
        if stage == "search":
            d,trace = flow.certify(mgr.u2.encoded(config))
        else:
            r = eng.replay(config)
            assert r is not None
            d,trace = eng.cert(config,r)
        duration = T()-start
        totals["replay"] = duration - sum(totals.values())
        assert all(x>=0 for x in totals.values())
        # An independent reader can verify both timed returns and their exact files.
        evidence = dest/"evidence"/obj["case"]/key
        assert sha((evidence/"plan.json").read_bytes().strip()) == key == d["plan_sha256"]
        disk = json.loads((evidence/"certificate.json").read_bytes())
        cert = json.loads(v.m.raw(d))
        assert cert == disk
        observed_s = cert.pop("cert_s")
        cert_digest = sha(json.dumps(cert,sort_keys=True,separators=(",",":")).encode())
        trace_digest = sha(trace.tobytes())
        assert cert_digest == truth[key]["certificate"] and trace_digest == truth[key]["trace"]
        with np.load(evidence/"trace.npz") as data:
            assert sha(data["events"].tobytes()) == trace_digest
        out = kernel.latest
        kernel_digest = digest_output(out)
        if mode == "incremental":
            assert kernel.source is None or kernel.source < ordinal
        results.append(dict(case=case,rep=rep,method=mode,ordinal=ordinal,stage=stage,detail=detail,
            original_delivery_s=delivery,plan=key,status=cert["metrics"]["status"],cert_sha=cert_digest,
            trace_sha=trace_digest,event_sha=sha(trace[:,:14].tobytes()),all_kernel_fields_sha=kernel_digest,
            energy_bounds=cert["metrics"]["E_bounds"],peak_hi=cert["metrics"]["peak_hi"],
            peak_lo=cert["metrics"]["peak_lo"],minimum_lo=out[3].tolist(),minimum_hi=out[4].tolist(),
            panels=int(out[-1]),entries=kernel.rows,reused=kernel.reused,source_ordinal=kernel.source,
            cache_bytes=kernel.storage,elapsed=duration,native_cert_s=observed_s,
            **{p:totals[p] for p in PHASES}))
        kernel.latest = None
        del out, trace, d
    cache_bytes = kernel.storage
    tick = T()
    kernel.history.clear()
    release = T()-tick
    save(OUT/(label+".json"),dict(case=case,rep=rep,method=mode,setup=setup,release=release,
            maxrss_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            cache_bytes=cache_bytes,cpu=CPU,worker_cpu_s=time.process_time()-cpu_start,rows=results))


def cpu_used():
    return sum(u.ru_utime+u.ru_stime for u in
               (resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)))


def main():
    budget = ROOT/"budget.json"
    prior = json.loads(budget.read_text())["charged"] if budget.exists() else 0.
    assert prior < 598
    # Reserve a second for exiting and writing the budget receipt.
    resource.setrlimit(resource.RLIMIT_CPU,(math.floor(599-prior),math.ceil(599-prior)))
    def record(state):
        save(budget,dict(limit=600,charged=prior+cpu_used(),state=state))
    record("preparing")
    try:
        v = v1.initialize(CPU)
        import heat
        original = heat.integrate
        lib = ROOT/"clock.so"
        subprocess.run(["cc","-O2","-shared","-fPIC",str(HERE/"clock.c"),"-o",str(lib)],check=True)
        resume = continuation(original,lib)
        # Warm only on a neutral synthetic event before target sequence exposure.
        ev = np.zeros((2,14))
        ev[:,0] = [0,2]
        ev[:,1] = [2,4]
        initial = np.full(4,35.)
        args = (ev,initial,np.eye(4),np.ones(4),35.,np.empty(0,np.int64),True)
        inc = Integration("incremental",original,resume,"neutral")
        inc.times = Counter()
        inc.ordinal=0
        a = original(*args)
        for ordinal in range(2):
            inc.ordinal=ordinal
            assert digest_output(a)==digest_output(inc(*args))
        inputs = {k:recover(k) for k in CASES}
        record("ready")
        for rep in range(1,4):
            for i,case in enumerate(CASES):
                modes=("full","incremental") if (i+rep)%2 else ("incremental","full")
                obj = next(o for o in v.m.u2.CASES if v.m.label(o)==case)
                for mode in modes:
                    receipt=OUT/f"{case}-{rep}-{mode}.json"
                    if receipt.exists():
                        continue
                    remaining=599-prior-cpu_used()
                    assert remaining>1
                    child=os.fork()
                    if child==0:
                        try:
                            soft=max(1,math.floor(remaining))
                            resource.setrlimit(resource.RLIMIT_CPU,(soft,soft))
                            assert os.sched_getaffinity(0)=={CPU}
                            one(v,original,resume,obj,*inputs[case],case,rep,mode)
                        except BaseException:
                            traceback.print_exc()
                            os._exit(1)
                        os._exit(0)
                    _,status=os.waitpid(child,0)
                    record("running")
                    if status:
                        raise RuntimeError((case,rep,mode,status))
                    print(case,rep,mode,round(prior+cpu_used(),2),flush=True)
                first,second=[json.loads((OUT/f"{case}-{rep}-{m}.json").read_bytes()) for m in modes]
                assert [r["all_kernel_fields_sha"] for r in first["rows"]]==[r["all_kernel_fields_sha"] for r in second["rows"]]
        record("complete")
    except BaseException:
        record("stopped")
        raise


if __name__=="__main__":
    main()
