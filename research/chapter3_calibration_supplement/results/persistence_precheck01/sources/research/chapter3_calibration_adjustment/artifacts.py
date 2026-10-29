"""One inspectable hand-authored example; never accepts a calibration root."""

import json

from research.chapter3_workload_calibration.evaluation import evaluate_condition
from research.chapter3_workload_calibration.generator import transform
from .fixtures import manual_evidence
from .transforms import derive_branch_multi, derive_staggered, validate_adjustment
from .window_policy import make_window_receipt
from .idle_certificate import SOURCE_PATH, SOURCE_SHA256, POLICY, make_idle_certificate


def manual_example():
    base = manual_evidence(large_nodes=8, small_nodes=4, offsets=("0", "15"))
    config = {"betas": ["1", "1.3", "1.6", "2"]}
    children = {"branch_multi": derive_branch_multi(base["workload"]),
                "staggered": derive_staggered(base),
                "synchronous": transform(base["workload"], "S7", value=2,
                                           settings={"s7_release_rule": "synchronous_same_application"})}
    for name in ("branch_multi", "staggered"):
        validate_adjustment(base, children[name])
    evidence = {name: evaluate_condition(bundle, config, parent=base, progress=lambda *args: None)
                for name, bundle in children.items()}
    members = {"single": base, "synchronous": evidence["synchronous"], "staggered": evidence["staggered"]}
    idle = make_idle_certificate(json.loads(SOURCE_PATH.read_text(encoding="utf-8")),
                                 source_sha256=SOURCE_SHA256, policy=POLICY, lower_C="20", upper_C="80")
    return {"scope": "HAND_AUTHORED_FIXTURE_NOT_CALIBRATION", "baseline": base,
            "derived": evidence,
            "windows": {"S7": make_window_receipt("manual-S7", "S7", members, beta="1.3", baseline=base),
                        "S4": make_window_receipt("manual-S4", "S4", {"multi": evidence["branch_multi"]},
                                                   beta="1.3", baseline=base)},
            "idle_certificate": idle, "beta_selected": None,
            "supplement_conditions_executed": 0, "thermal_integrations": 0}
