"""Physical interchange and source bindings. Each native stack lives in a separate process."""
import csv
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
NT = Path(os.environ["U1_NT"]).resolve() / "research"
THREE = Path(os.environ["U1_THREE"]).resolve() / "research"
FOUR = Path(os.environ["U1_FOUR"]).resolve() / "research/chapter4_cross_analysis_v5/formal_runner/v1"
OUT = Path(os.environ["U1_OUT"]).resolve()
REG = NT / "m1i_generalization/registration"
CASES = ("A03", "A06", "C10", "C12")
CUTS = (10, 30, 60, 180)

def raw(o):
    def native(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        return str(v)
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=native, allow_nan=False).encode()

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw(obj) + b"\n")
    tmp.replace(path)

def read(p):
    return json.loads(p.read_bytes())

def sha(b):
    return hashlib.sha256(b).hexdigest()

def table(rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=rows[0], lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()

def item(code):
    return next(r for r in read(REG / "cases.json")["cases"] if r["case"].startswith(code + "_"))

def setup(method):
    if method == "NT":
        sys.path.insert(0, str(NT / "m1i_generalization"))
        import adapter
        from runner import timed_run
        return adapter
    if method == "Q4":
        sys.path.insert(0, str(FOUR))
        import preflight
        return preflight
    sys.path.insert(0, str(THREE / "chapter3_final_evaluation"))
    import setup_inputs
    import trial
    return setup_inputs

def problem(method, api, obj, dest):
    label = obj["case"]
    if method == "NT":
        engine = api.flow(obj, dest)
        p = engine.p
    else:
        api.CFG["instances"][label] = [list(obj["word"]), 1, 35, 1]
        if method == "Q4":
            engine = api.Engine(label, dest)
            p = engine.p
        else:
            p = api.problem(label)
            engine = None
    body = (REG / "inputs" / obj["input"]).read_bytes()
    assert table(p.req) == body and sha(body) == obj["input_sha256"]
    assert p.horizon == obj["horizon_ticks"] and all(r["deadline_ms"] - r["release_ms"] == 300 for r in p.req)
    return p, engine

def witness(code):
    obj = item(code)
    src = NT / "m1i_generalization/data/evidence" / obj["case"]
    with tarfile.open(src / "runs.tar.xz", "r|xz") as tar:
        for m in tar:
            if m.name == "r1-NT/run.json":
                run = json.load(tar.extractfile(m))
                key = run["records"][0]["cert"]["plan_sha256"]
                break
        else:
            raise ValueError("Frozen first NT record missing")
    with tarfile.open(src / "physical.tar.xz", "r|xz") as tar:
        for m in tar:
            if m.name == key + "/plan.json":
                body = tar.extractfile(m).read()
                assert sha(body.strip()) == key
                return json.loads(body), key
    raise ValueError(key)

def decode(plan):
    return [tuple(r) for r in plan["rows"]], frozenset(map(tuple, plan["low"]))

def cfg(rows):
    return bytes(k + 10 * (u == 3) for u, k, _ in rows[1::3])

def verify_seed(p, plan):
    from construct import assemble
    from fifo import Compact
    from model import event_arrays, independent_events
    from validation import common_grid
    rows, low = decode(plan)
    genes = tuple(row[:2] for row in rows[1::3])
    assert Compact(p).replay(genes) is not None and assemble(p, genes) == rows
    a, sw, _ = event_arrays(p, rows, low)
    b, check = independent_events(p, rows, low)
    x,y = common_grid(a,b)
    assert sw == check and np.array_equal(x,y)
    return rows, low

def audit(code, method):
    dest = OUT / "interface" / code / method
    obj = item(code)
    api = setup(method)
    p, engine = problem(method, api, obj, dest)
    plan = read(OUT / "interface" / code / "witness.json")
    rows, low = decode(plan)
    config = cfg(rows)
    from model import event_arrays, independent_events, transitions
    from heat import evaluate
    # Use the complete preserved schedule, including idle decisions across window boundaries.
    if method == "NT":
        quotas = []
        regenerated = b""
        for j, ids in enumerate(engine.eng.groups):
            arr = np.array([config[i] for i in ids])
            types = engine.kinds[ids]
            gpu, npu = set(arr[arr<10]), set(arr[arr>=10]-10)
            assert len(gpu)<=1 and len(npu)<=1
            g,n = next(iter(gpu),0),next(iter(npu),0)
            a,b = (int(sum(types==t)) for t in (0,1))
            x,y = (int(sum((arr>=10)&(types==t))) for t in (0,1))
            regenerated += engine.extension(types,a,b,g,n,x,y)
            quotas.append([j,g,n,x,y])
        assert regenerated == config
        cert, trace = engine.certify(config)
        assert cert["plan_sha256"] == sha(raw(plan))
        save(dest/"quotas.json",quotas)
    elif method == "Proposed":
        from construct import idle_plan
        verify_seed(p, plan)
        native_default = idle_plan(p, rows)[1]
        api.g1io.OUT = dest / "physical"
        key, cert = api.g1io.assess(p,(rows,low))
        with np.load(api.g1io.OUT/"certificates"/(key+".npz")) as f:
            trace = f["events"]
    else:
        replay = engine.replay(tuple(row[:2] for row in rows[1::3]))
        assert replay is not None
        native_default = frozenset(replay["low"])
        assert engine.build(tuple(row[:2] for row in rows[1::3]),replay)["rows"] == rows
        met = evaluate(p,(rows,low),cert=True,trace=True)
        trace = np.asarray(met.pop("events"))
        cert = {"metrics":met}
        save(dest/"certificate.json",cert)
        np.savez_compressed(dest/"trace.npz",events=trace)
    events, sw, _ = event_arrays(p,rows,low)
    independent,check = independent_events(p,rows,low)
    assert sw == check and np.array_equal(events,independent) and np.array_equal(events,trace[:,:14])
    assert trace[0,0]==0 and trace[-1,1]==p.horizon and np.array_equal(trace[:-1,1],trace[1:,0])
    met = cert["metrics"]
    physical = dict(req=sha(table(p.req)),rows=sha(raw(rows)),low=sha(raw(sorted(low))),switches=sw,
                    events=sha(events.tobytes()),trace=sha(trace.tobytes()),segments=len(trace),
                    E_J=met["E_J"],bounds=met["E_bounds"],status=met["status"],peak_hi=met["peak_hi"],
                    initial=p.initial.tolist(),horizon=p.horizon,boundaries=p.boundaries,options=len(p.options[1]),
                    ambient=p.ta,cap=p.cap.tolist(),G=p.G.tolist(),
                    profile=sha(raw(sorted((str(k),list(map(str,v))) for k,v in p.exact.items()))))
    save(dest/"audit.json",dict(physical=physical,quota_config_sha256=sha(config),
                                default_idle_differences=0 if method=="NT" else len(low ^ native_default),
                                archived_plan=sha(raw(plan))))
