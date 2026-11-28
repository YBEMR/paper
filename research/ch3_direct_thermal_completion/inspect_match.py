"""Keep the initial independent HOT ordinary replay separate from the archived arm."""
import hashlib
import json
from pathlib import Path
import numpy as np
from prepare import ROOT, OUT


def audit(fixed, rows):
    r = next(r for r in rows if r["case"]=="C10" and r["point"]["status"]=="HOT")
    expected = r["history"]["ordinary"]["point"]
    assert expected and r["history"]["ordinary"]["completed"]
    case = r["case"]
    folder = OUT/"checkpoint"/case/r["seed"]/"ordinary/evidence"
    fresh = next(folder.glob("*/"+expected["plan"]))
    replay_cert = json.loads((fresh/"certificate.json").read_bytes())
    assert fixed.m.endpoint(replay_cert)==expected
    store = fixed.Store(case,None)
    try:
        ix = store.index["plans"][expected["plan"]]
        historical_plan = store.data(ix["archive"],expected["plan"]+"/plan")
        historical_cert = store.data(ix["archive"],expected["plan"]+"/certificate")
        assert hashlib.sha256(historical_cert).hexdigest()==ix["cert_sha"]
        assert historical_plan==(fresh/"plan.json").read_bytes()
        assert fixed.m.endpoint(json.loads(historical_cert))==expected
        raw = b"".join(store.data(store.index["blocks"][k],"blocks/"+k) for k in ix["blocks"])
        assert hashlib.sha256(raw).hexdigest()==ix["trace_sha"]
        archived = np.frombuffer(raw,dtype=np.float64).reshape(ix["shape"])
    finally:
        store.close()
    with np.load(fresh/"trace.npz") as data:
        replay = data["events"]
    assert replay.shape==archived.shape
    assert np.array_equal(replay[:,:14],archived[:,:14])
    assert np.isfinite(replay).all() and np.isfinite(archived).all()
    residual = np.abs(replay-archived)
    note = dict(case=case,stage="ordinary",plan=expected["plan"],seed=r["seed"],
                endpoint_exact_match=True,physical_plan_bytes_exact_match=True,
                event_projection_exact_match=True,certificate_bytes_match=(fresh/"certificate.json").read_bytes()==historical_cert,
                archive_trace_sha256=ix["trace_sha"], replay_trace_sha256=hashlib.sha256(replay.tobytes()).hexdigest(),
                shape=list(archived.shape), unequal_entries=np.count_nonzero(replay!=archived,axis=0).tolist(),
                maximum_abs_difference_by_column=residual.max(axis=0).tolist(),
                max_temperature_trace_delta_C=float(residual[:,14:22].max()),
                replay_source_run=46140803688,replay_used_as_historical_input=False,
                historical_stage_source="archived_complete",certified_endpoint=expected)
    (OUT/"checkpoint/match.json").write_text(json.dumps(note,indent=2)+"\n")
    print("C10 match-check",note,flush=True)
