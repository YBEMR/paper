"""Synthetic certificate checks only: no schedule/thermal/search implementation."""
import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from h02_pair_b0.classification import classify_invalid_schedule


def fixture():
    modes = {}
    for shared in ("A.one", "A.two"):
        modes[shared] = [dict(mode_id=f"{shared}@{unit}:{opp}", shared_stage_id=shared,
                              unit_id=unit, opp_id=opp, domain_id="CPU", duration_ms="10",
                              activity_power_W="1")
                         for unit in ("CPU1", "CPU2") for opp in ("L", "H")]
    instance = dict(schema_version="chapter3-input-v0.1", response_variant="H",
                    settings=dict(response_variant="H"), window_ms="100", start_grid_ms="5",
                    platform=dict(units=[dict(id=unit, domain_id="CPU") for unit in ("CPU1", "CPU2")],
                                  domains=dict(CPU=dict(unit_ids=["CPU1", "CPU2"], opps={"L": {}, "H": {}}))),
                    stage_modes=modes, scenarios=[dict(id="AB", requests=[dict(id="A1", release_ms="5",
                    deadline_ms="50", stage_instance_ids=["one", "two"])],
                    stage_instances=[dict(id=sid, request_id="A1", shared_stage_id=shared)
                                     for sid, shared in (("one", "A.one"), ("two", "A.two"))],
                    dependencies=[["one", "two"]])])
    candidate = dict(scenes={"AB": [dict(stage_id="one", unit="CPU1", opp="L", start_ms="5"),
                                    dict(stage_id="two", unit="CPU2", opp="L", start_ms="15")]})
    return instance, candidate


def invalid(reason, **details):
    return dict(state="INVALID_SCHEDULE", reason=reason, details=details,
                thermal_status="NOT_EVALUATED", energy_status="NOT_EVALUATED")


class ClassificationTests(unittest.TestCase):
    def check_class(self, instance, candidate, receipt, expected, explanation=None):
        result = classify_invalid_schedule(instance, candidate, receipt)
        self.assertEqual(result["audit_status"], expected, result)
        self.assertEqual(result["certificate_checked"], expected == "TRUE_H_INVALID")
        if explanation:
            self.assertIn(explanation, result["details"]["classification_explanation"])
        return result

    def test_before_release(self):
        i, c = fixture(); c["scenes"]["AB"][0]["start_ms"] = "0"
        self.check_class(i, c, invalid("BEFORE_RELEASE", stage="one"), "TRUE_H_INVALID")

    def test_window_exceeded(self):
        i, c = fixture(); c["scenes"]["AB"][1]["start_ms"] = "95"
        self.check_class(i, c, invalid("WINDOW_EXCEEDED", stage="two"), "TRUE_H_INVALID")

    def test_exact_deadline(self):
        i, c = fixture(); c["scenes"]["AB"][1]["start_ms"] = "45"
        self.check_class(i, c, invalid("REQUEST_DEADLINE_EXCEEDED", stage="two", request="A1",
                                      finish_ms="55", deadline_ms="50"), "TRUE_H_INVALID")

    def test_forged_deadline(self):
        i, c = fixture()
        self.check_class(i, c, invalid("REQUEST_DEADLINE_EXCEEDED", stage="two", request="A1",
                                      finish_ms="55", deadline_ms="50"), "INPUT_OR_INTERFACE_ERROR",
                         "FALSE_DEADLINE_WITNESS")

    def test_dependency(self):
        i, c = fixture(); c["scenes"]["AB"][1]["start_ms"] = "10"
        self.check_class(i, c, invalid("DEPENDENCY_VIOLATION", predecessor="one", successor="two"), "TRUE_H_INVALID")

    def test_wrong_dependency_edge(self):
        i, c = fixture()
        self.check_class(i, c, invalid("DEPENDENCY_VIOLATION", predecessor="two", successor="one"),
                         "INPUT_OR_INTERFACE_ERROR", "UNKNOWN_WITNESS_DEPENDENCY")

    def test_unit_overlap(self):
        i, c = fixture(); c["scenes"]["AB"][1].update(unit="CPU1", start_ms="10")
        self.check_class(i, c, invalid("EXECUTION_UNIT_OVERLAP", stages=["one", "two"]), "TRUE_H_INVALID")

    def test_half_open_touch_not_overlap(self):
        i, c = fixture(); c["scenes"]["AB"][1]["unit"] = "CPU1"
        self.check_class(i, c, invalid("EXECUTION_UNIT_OVERLAP", stages=["one", "two"]),
                         "INPUT_OR_INTERFACE_ERROR", "FALSE_OVERLAP_WITNESS")

    def test_frequency_conflict(self):
        i, c = fixture(); c["scenes"]["AB"][1].update(opp="H", start_ms="10")
        self.check_class(i, c, invalid("FREQUENCY_DOMAIN_CONFLICT", stages=["one", "two"]), "TRUE_H_INVALID")

    def test_equal_frequency_not_conflict(self):
        i, c = fixture(); c["scenes"]["AB"][1]["start_ms"] = "10"
        self.check_class(i, c, invalid("FREQUENCY_DOMAIN_CONFLICT", stages=["one", "two"]),
                         "INPUT_OR_INTERFACE_ERROR", "FALSE_FREQUENCY_DOMAIN_WITNESS")

    def test_malformed_is_interface(self):
        i, c = fixture()
        self.check_class(i, c, invalid("MALFORMED_INPUT_OR_CANDIDATE", error_type="KeyError", message="x"), "INPUT_OR_INTERFACE_ERROR")

    def test_unsupported_idle_is_interface(self):
        i, c = fixture()
        self.check_class(i, c, invalid("UNSUPPORTED_IDLE_POLICY", message="wrong idle policy"), "INPUT_OR_INTERFACE_ERROR")

    def test_unknown_reason_is_interface(self):
        i, c = fixture()
        self.check_class(i, c, invalid("NEW_CORE_REASON", stage="one"), "INPUT_OR_INTERFACE_ERROR")

    def test_domain_only_uncertified(self):
        i, c = fixture()
        for reason in ("SIMULTANEOUS_OPP_CONFLICT", "BUSY_DOMAIN_OPP_CHANGE"):
            with self.subTest(reason=reason):
                self.check_class(i, c, invalid(reason, domain="CPU"), "INPUT_OR_INTERFACE_ERROR")

    def test_policy_or_schema_errors_not_violation(self):
        i, c = fixture()
        for reason in ("START_OUTSIDE_GRID", "SHARED_DEPLOYMENT_MISMATCH", "INVALID_MODE_COST",
                       "ILLEGAL_OR_AMBIGUOUS_MODE", "BASELINE_ACCOUNTING_MISMATCH"):
            with self.subTest(reason=reason):
                self.check_class(i, c, invalid(reason, stage="one"), "INPUT_OR_INTERFACE_ERROR")

    def test_envelope_not_unevaluated(self):
        i, c = fixture(); receipt = invalid("BEFORE_RELEASE", stage="one")
        receipt["thermal_status"] = "SAFE"
        self.check_class(i, c, receipt, "INPUT_OR_INTERFACE_ERROR", "INVALID_LEGALITY_ENVELOPE")

    def test_candidate_identity_strict(self):
        i, c = fixture(); c["scenes"]["AB"][0]["end_ms"] = "15"
        self.check_class(i, c, invalid("BEFORE_RELEASE", stage="one"), "INPUT_OR_INTERFACE_ERROR", "CANDIDATE_ROW_FIELDS")

    def test_wrong_truth_response(self):
        i, c = fixture(); i["response_variant"] = "R"
        self.check_class(i, c, invalid("BEFORE_RELEASE", stage="one"), "INPUT_OR_INTERFACE_ERROR", "TRUTH_RESPONSE_NOT_H")

    def test_nonphysical_mode_is_interface(self):
        i, c = fixture(); i["stage_modes"]["A.one"][0]["activity_power_W"] = "-1"
        self.check_class(i, c, invalid("BEFORE_RELEASE", stage="one"), "INPUT_OR_INTERFACE_ERROR", "INVALID_TRUTH_MODE_COST")

    def test_details_missing_or_wrong_stage(self):
        i, c = fixture()
        self.check_class(i, c, invalid("BEFORE_RELEASE", stage="missing"), "INPUT_OR_INTERFACE_ERROR")
        receipt = invalid("BEFORE_RELEASE", stage="one"); receipt["details"] = []
        self.check_class(i, c, receipt, "INPUT_OR_INTERFACE_ERROR")

    def test_inputs_unchanged(self):
        i, c = fixture(); receipt = invalid("WINDOW_EXCEEDED", stage="one")
        before = copy.deepcopy((i, c, receipt))
        result = self.check_class(i, c, receipt, "INPUT_OR_INTERFACE_ERROR")
        self.assertEqual((i, c, receipt), before)
        self.assertNotIn("SAFE", result["audit_status"])

    def test_no_true_core_imports(self):
        from h02_pair_b0 import classification
        import ast
        from pathlib import Path
        tree = ast.parse(Path(classification.__file__).read_text(encoding="utf-8"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name and any(word in name for word in ("schedules", "thermal", "heft")) for name in imports))


if __name__ == "__main__":
    unittest.main()
