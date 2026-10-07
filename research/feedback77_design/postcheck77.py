"""Read-only checks of saved 77 results; never invokes scheduling or thermal search."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "research/matlab_config_value_src/feedback77_reports/frozen_20260928_172132_129"


def readjson(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def readcsv(p):
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


rows = readcsv(RUN / "summary.csv")
post = readcsv(RUN / "postchecks.csv")
assert len(rows) == len(post) == 20
assert all(r["final_status_within_budget"] == "1" for r in rows)
assert all(r["final_solver_bound_within_budget"] == "1" for r in rows)
assert all(float(r["elapsed_s"]) < 60 for r in rows)
assert sum(r["safe"] == "1" for r in rows) == 18
assert sum(r["independent_optimal"] == "1" for r in rows) == 10
assert all(r["independent_infeasible"] == "0" for r in rows)
assert all(r["rounds"] == "1" and r["cuts"] == "0" for r in rows)
assert sum(r["checked"] == "1" for r in post) == 18
assert all(r["passed"] == "1" for r in post if r["checked"] == "1")
historical = readcsv(ROOT / "research/matlab_config_value_src/milp68_reports/frozen_20260927_113720_286/summary.csv")
old = {r["case_id"]: r for r in historical if r["method"] == "milp"}
if not old:  # Keep actual stored spelling, never infer numerical answers.
    old = {r["case_id"]: r for r in historical if "milp" in r["method"].lower()}
assert len(old) == 10

cases = []
for i in range(10):
    pair = rows[2*i:2*i+2]
    assert [r["method"] for r in pair] == ["no_good", "thermal_row"]
    assert pair[0]["case_id"] == pair[1]["case_id"]
    cid = pair[0]["case_id"]
    assert pair[0]["energy_mJ"] == pair[1]["energy_mJ"]
    assert pair[0]["status"] == pair[1]["status"]
    assert float(pair[0]["energy_mJ"]) == float(old[cid]["energy_mJ"])
    unique = []
    for j, r in enumerate(pair, 1):
        data = readjson(RUN / f"diagnostics_{i+1:02d}_{j:02d}.json")
        assert data["raw_method_status"] == r["status"]
        assert not data["cuts"] and not data["message"]
        assert len(data["rounds"]) == 1
        assert not data["rounds"][0]["output"].get("test_only_replay", False)
        assert all(e["thermal_status"] == "safe" for e in data["events"])
        candidates = {tuple(e["selected"]) for e in data["events"]}
        unique.append(len(candidates))
        assert len(candidates) == (1 if r["safe"] == "1" else 0)
        assert all(e["origin"] != "injected_duplicate" for e in data["events"])
        if r["safe"] == "1":
            lo, hi = data["first_safe_interval_s"]
            assert 0 <= lo <= hi <= float(r["elapsed_s"]) < 60
    equal_schedule = None
    if pair[0]["safe"] == "1":
        equal_schedule = (RUN / f"schedule_{i+1:02d}_01.csv").read_bytes() == (RUN / f"schedule_{i+1:02d}_02.csv").read_bytes()
    cases.append(dict(case_id=cid, energy_mJ=pair[0]["energy_mJ"],
                      same_schedule=equal_schedule, distinct_candidates=unique))

before = readjson(ROOT / "research/feedback77_design/protected_before.json")
protected_changes = [x["path"] for x in before if not (ROOT/x["path"]).is_file() or digest(ROOT/x["path"]) != x["sha256"].lower()]
assert not protected_changes, protected_changes
hashes = readjson(RUN / "source_hashes.json")
current_changes = []
for i, x in enumerate(hashes, 1):
    src = Path(x["path"])
    snapshot = RUN / "source" / f"{i:03d}_{src.name}"
    assert digest(snapshot) == x["sha256"].lower()
    if digest(src) != x["sha256"].lower():
        current_changes.append(src.name)
assert sorted(current_changes) == ["f77_budget_audit.m", "f77_tests.m", "run_feedback77.m"]
by_method = {}
for method in ["no_good", "thermal_row"]:
    rs = [r for r in rows if r["method"] == method]
    main = rs[:8]
    by_method[method] = dict(
        main_safe=sum(r["safe"] == "1" for r in main),
        main_independent_optimal=sum(r["independent_optimal"] == "1" for r in main),
        total_wall_s=sum(float(r["elapsed_s"]) for r in rs),
        main_wall_s=sum(float(r["elapsed_s"]) for r in main),
        all_calls_under_budget=True)
result = dict(
    research_calls=20, safe_witnesses=18, independent_optimal=10,
    independently_proved_infeasible=0, thermal_rows=0, no_goods=0,
    source_snapshot_hashes_verified=len(hashes),
    protected_files=len(before), protected_changes=protected_changes,
    postrun_error_guard_only_source_changes=current_changes,
    calls=cases, methods=by_method,
    interpretation="No replay, one solver round, zero feedback. No feedback speedup attribution.")
(RUN / "postcheck_readonly.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
