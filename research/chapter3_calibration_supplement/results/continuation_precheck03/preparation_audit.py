"""Read-only verification of the pending remaining-25 freeze; writes only its receipt."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from research.chapter3_calibration_supplement import protocol as p, continuation as c
from research.chapter3_calibration_supplement.persistence import write_once


def main():
    frozen = p.PACKAGE / "results/frozen_remaining25_01"
    plan, inv, record = p.check_frozen(frozen, full_archive_check=True)
    checks = p.read_json(Path(__file__).parent / "checks.json")
    old, batch, calls, binding, history = c.prior_evidence()
    repaired = p.read_json(p.PACKAGE / "results/persistence_precheck02/source_manifest.json")
    current = p.sources()
    changed = sorted(k for k in repaired if current.get(k) != repaired[k])
    added = sorted(set(current) - set(repaired))
    expected_changed = ["protocol.py", "run_checks.py", "runtime.py", "test_runtime.py"]
    prefix = "research/chapter3_calibration_supplement/"
    assert changed == [prefix + name for name in expected_changed]
    assert added == [prefix + name for name in ("continuation.py", "test_continuation.py")]
    unchanged = {k: v for k, v in repaired.items() if k not in changed}
    approval = p.read_json(frozen / "approval_template.json")
    absent = [frozen / "execution_claim.json", p.result_path(plan["consumption_claim_path"]),
              p.PACKAGE / "results/remaining25_execution01"]
    assert all(not path.exists() for path in absent)
    assert approval["approved"] is False and plan["execution_authorized"] is False
    assert checks["state"] == "PASS" and checks["source_files"] == current
    assert checks["supplement_conditions_executed"] == checks["real_worker_processes"] == 0
    assert checks["formal_algorithm_calls"] == checks["thermal_integrations"] == 0
    assert plan["calls"] == calls == old["calls"][3:]
    assert len(calls) == 25
    by_axis = {axis: sum(call["axis"] == axis for call in calls) for axis in ("S4", "S7")}
    assert by_axis == {"S4": 13, "S7": 12}
    report = {
        "state": "PASS_PENDING_USER_APPROVAL", "plan_sha256": record["plan_sha256"],
        "source_manifest_sha256": record["source_manifest_sha256"],
        "source_count": len(current), "changed_from_repair": changed, "added": added,
        "unchanged_repair_sources": unchanged, "prior_result_sha256": binding["prior_batch_sha256"],
        "prior_completed_conditions": batch["completed_conditions"],
        "retained_conditions": c.RETAINED, "remaining_conditions": [x["condition_id"] for x in calls],
        "remaining_by_axis": by_axis, "remaining_root_count": len({x["root_id"] for x in calls}),
        "family_timetables": 75, "scenario_schedules": 600, "limits": plan["limits"],
        "precheck_tests": checks["tests_run"], "precheck_subtests": len(checks["subtest_records"]),
        "precheck_elapsed_s": checks["elapsed_s"], "manual_reference_calls": checks["manual_reference_calls"],
        "protected_file_count": len(p.protected()), "prior_supplement_file_count": len(history),
        "protected_unchanged": checks["protected_unchanged"],
        "historical_supplement_unchanged": checks["historical_supplement_unchanged"],
        "absent_real_execution_paths": [x.relative_to(REPO).as_posix() for x in absent],
        "execution_authorized": False, "supplement_conditions_executed": 0,
        "formal_algorithm_calls": 0, "thermal_integrations": 0,
        "internal_review": "Second agent read-only review found no blocking issue; not external execution approval.",
        "failed_prechecks_retained": ["continuation_precheck01: C9/C09 identity fixture mismatch",
                                      "continuation_precheck02: manual test omitted required progress argument"]}
    write_once(Path(__file__).parent / "preparation_audit.json", report)
    print(json.dumps({k: report[k] for k in ("state", "source_count", "precheck_tests", "precheck_subtests",
                     "remaining_by_axis", "remaining_root_count", "plan_sha256")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
