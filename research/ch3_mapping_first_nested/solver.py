"""Evaluate one mapping from scratch through the frozen ordinary and thermal DP."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "ch3_integrated_quality_v3"))
from hot import f, m, valid


def evaluate(eng, flow, mapping, dest, emit):
    assert len(mapping) == len(eng.p.req) and set(mapping) <= {2, 3}
    # solve() partitions by device. Every frequency slot is overwritten by DP.
    cfg = tuple((device, 0) for device in mapping)
    guide = None
    for stage in ("ordinary", "thermal"):
        if stage == "thermal" and guide is None:
            return
        thermal = stage == "thermal"
        eng.out = dest / stage
        candidate = m.optimize(eng, flow, cfg, guide, dest, stage, thermal)
        if candidate is None:
            steps = f.readlog(dest / "events.jsonl")
            last = next(e for e in reversed(steps) if e.get("tag") == stage)
            reason = "post_stage_deadline" if last["kind"] == "illegal_post" else "no_device_dp_path"
            emit(stage, None, reason)
            return
        solved, _, certificate, trace = candidate
        assert bytes(u for u, _ in solved) == mapping
        point = m.endpoint(certificate)
        assert valid(trace, eng.p.horizon) and point["slack"] >= 0
        if point["status"] == "SAFE":
            assert point["peak"] <= 80
        emit(stage, point, None)
        if not thermal and point["status"] in ("SAFE", "HOT"):
            guide = candidate
