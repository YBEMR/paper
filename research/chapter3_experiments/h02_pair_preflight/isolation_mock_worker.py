"""R-only subprocess MOCK preflight. This is an application guard, not an OS sandbox.

Input is exactly planner_packet(pair, "R") JSON on stdin. Only this script's
standard-library imports occur before the audit hook. No main-core imports,
HEFT, lower bound, schedule construction or thermal evaluation are performed.
"""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

BASE_SHA = "20fb232a81d69782b8ebd1fc1972a6bc96fff09e"
PUBLIC = {"view", "problem_id", "source_commit_sha", "planner", "plan_sha256",
          "config_sha256", "physical_projection_sha256", "support_sha256",
          "scenario_sha256", "policy_id", "accuracy_sha256"}
FORBIDDEN_KEYS = {"truth_H", "truth_h", "truth_H_sha256", "pair", "audit",
                  "h_audit", "H_audit", "truth_receipt", "audit_receipt",
                  "post_audit", "real_H_alpha", "H_alpha", "frozen_candidate"}


class Rejected(ValueError):
    pass


class AccessDenied(PermissionError):
    pass


def require(ok, reason):
    if not ok:
        raise Rejected(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, "DUPLICATE_JSON_FIELD:" + key)
        out[key] = value
    return out


def check_no_truth(value):
    if isinstance(value, dict):
        require(not (set(value) & FORBIDDEN_KEYS), "TRUTH_OR_FEEDBACK_FIELD")
        for child in value.values():
            check_no_truth(child)
    elif isinstance(value, list):
        for child in value:
            check_no_truth(child)


def one(value):
    require(not isinstance(value, bool) and isinstance(value, (str, int)),
            "NONEXACT_R_ALPHA")
    require(Fraction(value) == 1, "R_REAL_H_ALPHA_LEAK")


def validate(packet):
    require(isinstance(packet, dict) and set(packet) == PUBLIC,
            "PLANNER_PUBLIC_FIELD_ALLOWLIST")
    check_no_truth(packet)
    require(packet["view"] == "R" and packet["source_commit_sha"] == BASE_SHA,
            "R_OR_SOURCE_IDENTITY")
    public = packet["planner"]
    require(isinstance(public, dict) and set(public) == {"config", "instance"},
            "PLANNER_VIEW_FIELDS")
    config, instance = public["config"], public["instance"]
    require(instance["id"] == packet["problem_id"] and instance["id"] in
            ("base__R1", "base__R2"), "PROBLEM_IDENTITY")
    require(config["defaults"]["response_variant"] == instance["response_variant"]
            == instance["settings"]["response_variant"] == "R", "R_LABEL")
    for stage in config["stage_catalog"]:
        for profile in stage["profiles"].values():
            one(profile["alpha"])
    support = []
    seen = set()
    for stage, modes in instance["stage_modes"].items():
        for mode in modes:
            one(mode["alpha"])
            key = (stage, mode["unit_id"], mode["opp_id"])
            require(key not in seen, "DUPLICATE_MODE_KEY")
            seen.add(key)
            support.append(dict(stage=stage, unit=key[1], opp=key[2],
                                mode_id=mode["mode_id"]))
    for value in instance["catalog_duration_weighted_mean_alpha"].values():
        one(value)
    require(digest(instance) == packet["plan_sha256"] and
            digest(config) == packet["config_sha256"], "PLANNER_HASH")
    support.sort(key=lambda row: (row["stage"], row["unit"], row["opp"]))
    require(digest(support) == packet["support_sha256"], "SUPPORT_HASH")
    require(digest(instance["scenarios"]) == packet["scenario_sha256"] and
            digest(config["accuracy_targets"]) == packet["accuracy_sha256"],
            "SCENARIO_OR_ACCURACY_HASH")
    require(packet["policy_id"] == "auto_low_immediate_v1", "POLICY_IDENTITY")
    config, instance = deepcopy(config), deepcopy(instance)
    del config["defaults"]["response_variant"]
    for stage in config["stage_catalog"]:
        for profile in stage["profiles"].values():
            del profile["alpha"]
    del instance["response_variant"]
    del instance["settings"]["response_variant"]
    del instance["catalog_duration_weighted_mean_alpha"]
    for modes in instance["stage_modes"].values():
        for mode in modes:
            for key in ("alpha", "duration_ms", "activity_energy_J"):
                del mode[key]
    require(digest({"config": config, "instance": instance}) ==
            packet["physical_projection_sha256"], "PHYSICAL_PROJECTION_HASH")
    return True


def install_guard(root):
    blocked = []

    def deny(event, target):
        blocked.append({"event": event, "target": str(target)})
        raise AccessDenied("R_WORKER_ACCESS_DENIED:" + event)

    def within(target):
        if isinstance(target, int):
            return target in (0, 1, 2)
        try:
            resolved = Path(os.fsdecode(target)).resolve()
            resolved.relative_to(root)
            return True
        except (TypeError, ValueError, OSError):
            return False

    def hook(event, args):
        if event == "open":
            if not within(args[0]):
                deny(event, args[0])
        elif event in ("os.listdir", "os.scandir"):
            target = args[0] if args and args[0] is not None else os.getcwd()
            if not within(target):
                deny(event, target)
        elif event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn",
                       "os.spawn", "os.startfile", "os.startfile/2", "os.fork",
                       "os.forkpty", "ctypes.dlopen", "socket.connect", "socket.bind"):
            deny(event, "PROCESS_OR_NATIVE_OR_NETWORK_OPERATION")
        elif event == "import":
            # Dependencies were loaded before this hook; no algorithm/code
            # imports are permitted after receiving the isolated R packet.
            deny(event, args[0])
        elif event in ("os.chdir", "os.fchdir", "os.symlink", "os.link"):
            deny(event, "WORKER_ROOT_OR_LINK_MUTATION")
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.rename"):
            targets = args[:2] if event == "os.rename" else args[:1]
            if not all(within(target) for target in targets):
                deny(event, targets)
    sys.addaudithook(hook)
    return blocked


def run(packet, root, forbidden):
    validate(packet)
    require(root.is_dir(), "ISOLATED_ROOT_MUST_ALREADY_EXIST")
    os.chdir(root)
    blocked = install_guard(root)
    tests = []

    def accepted(name, action):
        try:
            action()
            tests.append({"name": name, "passed": True, "result": "ALLOWED"})
        except Exception as error:
            tests.append({"name": name, "passed": False, "error": type(error).__name__,
                          "reason": str(error)})

    def rejected(name, action, error_type=AccessDenied):
        try:
            action()
            tests.append({"name": name, "passed": False, "result": "UNEXPECTED_ALLOW"})
        except error_type as error:
            tests.append({"name": name, "passed": True, "result": "REJECTED",
                          "reason": str(error)})
        except Exception as error:
            tests.append({"name": name, "passed": False, "error": type(error).__name__,
                          "reason": str(error)})

    public_path, cache_path = root / "worker_public_packet.json", root / "worker_cache.json"
    def own_public():
        with public_path.open("x", encoding="utf-8") as out:
            json.dump(packet, out, ensure_ascii=False, allow_nan=False)
        with public_path.open(encoding="utf-8") as source:
            require(json.load(source) == packet, "OWN_PUBLIC_FILE_MISMATCH")
    def own_cache():
        cache = {"kind": "MOCK_ONLY", "planner_input_sha256": packet["plan_sha256"],
                 "cached_candidates": [], "real_scores": []}
        with cache_path.open("x", encoding="utf-8") as out:
            json.dump(cache, out)
        with cache_path.open(encoding="utf-8") as source:
            require(json.load(source) == cache, "OWN_CACHE_MISMATCH")
    def read(path):
        with open(path, "rb") as source:
            source.read(1)
    accepted("read_own_public_R_packet", own_public)
    accepted("independent_empty_mock_cache", own_cache)
    accepted("list_own_R_directory", lambda: list(os.scandir(root)))
    for number, path in enumerate(forbidden):
        rejected("external_or_truth_read_" + str(number), lambda path=path: read(path))
        rejected("external_or_truth_traversal_" + str(number),
                 lambda path=path: os.listdir(str(Path(path).parent)))
    rejected("real_HEFT_import", lambda: __import__("heft_method"))
    rejected("real_thermal_import", lambda: __import__("thermal"))
    rejected("real_lower_bound_import", lambda: __import__("partial_bounds"))
    rejected("subprocess_execution", lambda: subprocess.run([sys.executable, "-c", "pass"],
                                                            check=True))
    rejected("os_system_execution", lambda: os.system("echo MUST_NOT_EXECUTE"))
    for field in ("truth_H", "audit_receipt", "truth_H_sha256"):
        altered = deepcopy(packet)
        altered[field] = {"kind": "MOCK_TRUTH_OR_FEEDBACK"}
        rejected("reject_reverse_feedback_" + field, lambda altered=altered: validate(altered),
                 Rejected)
    altered = deepcopy(packet)
    altered["planner"]["instance"]["audit_receipt"] = {"state": "MOCK_SAFE"}
    rejected("reject_nested_reverse_feedback", lambda: validate(altered), Rejected)
    altered = deepcopy(packet)
    altered["planner"]["config"]["stage_catalog"][0]["profiles"][
        next(iter(altered["planner"]["config"]["stage_catalog"][0]["profiles"]))]["alpha"] = "1/2"
    rejected("reject_real_H_alpha_leak", lambda: validate(altered), Rejected)
    return {"evidence_kind": "MOCK_ONLY", "passed": all(row["passed"] for row in tests),
            "planner_input_sha256": packet["plan_sha256"], "view": "R", "tests": tests,
            "blocked_events": blocked, "real_heft_calls": 0, "real_h_thermal_audits": 0,
            "research_calls": 0, "new_safe": 0, "formal_budget_authorized": False,
            "scope": "Python application audit guard; not an OS security sandbox; no Stage B authorization"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--forbidden-path", action="append", default=[])
    args = parser.parse_args()
    try:
        packet = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=no_duplicates,
                           parse_constant=lambda value: (_ for _ in ()).throw(Rejected("NONFINITE_JSON")))
        root = Path(args.root).resolve()
        # These are path strings only. Neither existence nor content is read.
        forbidden = list(args.forbidden_path) or [str(root.parent / "sealed_H" / "truth.json")]
        report = run(packet, root, forbidden)
    except Exception as error:
        report = {"evidence_kind": "MOCK_ONLY", "passed": False,
                  "state": "INPUT_OR_INTERFACE_ERROR", "reason": str(error),
                  "error_type": type(error).__name__, "research_calls": 0, "new_safe": 0,
                  "real_heft_calls": 0, "real_h_thermal_audits": 0,
                  "formal_budget_authorized": False}
    sys.stdout.buffer.write(json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
