"""Freeze the prepared AB/AC technical task in an independent directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import psutil

PROGRESS = "775944b47458306147612cde2d48bfb3cb69852b"
RUNTIME = "native_source/.runtime/"
CONTROLLERS = (
    "cancellation.py", "equivalent_transport.py", "exact_equalities.py",
    "native_entry_prepared.py", "native_equivalent_entry.py", "process_observer.py",
    "protected_runtime.py", "shared_mapping_adapter.py", "single_mapping.py",
    "stage_helpers.py", "stop_control.py", "test_adapter_runner.py",
    "test_equivalent_transport.py",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def optimize_profile(out, files, delivery):
    """Change only the predeclared search budget and feasible-point limit."""
    gate = read(delivery)
    if not gate["delivery_gate_pass"] or not gate["cleanup_verified"]:
        raise ValueError("Completed dual-scene delivery gate required")
    changes = {
        "single_mapping.py": [(b"ROOT_SECONDS = 300", b"ROOT_SECONDS = 600", 1),
                              (b"SCENE_SLICE_SECONDS = 120", b"SCENE_SLICE_SECONDS = 330", 1)],
        "native_equivalent_entry.py": [
            (b"origin+300", b"origin+600", 1),
            (b"'root_seconds':300", b"'root_seconds':600", 2),
            (b"26de537b474db9bb493c6e1c'))",
             b"26de537b474db9bb493c6e1c'),native_caps=(120.0,300.0))", 1),
        ],
        "native_source/research/chapter3_experiments/solve_model.m": [
            (b"            'MaxFeasiblePoints',1, ...\n", b"", 1),
        ],
    }
    recorded = {}
    for name, edits in changes.items():
        path = out / name
        before = files[name]
        body = path.read_bytes()
        for original, replacement, count in edits:
            if body.count(original) != count:
                raise ValueError(f"Unexpected frozen profile literal in {name}: {original!r}")
            body = body.replace(original, replacement)
        path.write_bytes(body)
        files[name] = sha(path)
        recorded[name] = {"before_sha256": before, "after_sha256": files[name]}
    return {"prior_delivery_audit_sha256": sha(delivery), "changes": recorded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("parent", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--after-delivery", type=Path,
                        help="Passing audit for the one subsequent optimization validation")
    args = parser.parse_args()
    source, parent, out = (p.resolve() for p in (args.source, args.parent, args.out))
    predecessor = read(parent / "FROZEN.json")
    immutable = {}
    excluded = []
    for name, digest in predecessor["files"].items():
        if name.startswith(RUNTIME):
            excluded.append(name)
            continue
        if name.startswith(("baseline/", "inputs/", "native_source/")):
            path = (source / name).resolve()
            if not path.is_relative_to(source) or sha(path) != digest:
                raise ValueError(f"Scientific, input or native source drift: {name}")
            immutable[name] = digest
    if sha(source / "exact_equalities.py") != sha(parent / "exact_equalities.py"):
        raise ValueError("Exact transformation changed")
    executable = Path(predecessor["matlab_executable"])
    if sha(executable) != predecessor["matlab_executable_sha256"]:
        raise ValueError("MATLAB executable changed")
    out.mkdir(parents=True, exist_ok=False)
    files = {**immutable, **{
        name: sha(source / name) for name in (
            *CONTROLLERS, "BASELINE_MANIFEST.json", "OFFLINE_EQUIVALENCE.json", "TASK_START.json")
    }}
    for name, digest in files.items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        if sha(target) != digest:
            raise ValueError(f"Snapshot copy drift: {name}")
    # The prepared task omitted this transitive import. Restore the exact
    # predecessor source rather than reconstructing its stage definitions.
    helper = "build_stage_source.py"
    if sha(parent / helper) != predecessor["files"][helper]:
        raise ValueError("Frozen stage marker helper changed")
    shutil.copyfile(parent / helper, out / helper)
    files[helper] = sha(out / helper)
    optimization = optimize_profile(out, files, args.after_delivery) if args.after_delivery else None
    subprocess.run([sys.executable, "-B", "-c",
                    "import sys; sys.path[:0]=['native_source/research/chapter3_experiments',"
                    "'baseline/research/chapter3_experiments','baseline']; "
                    "import native_equivalent_entry, protected_runtime, single_mapping, "
                    "native_entry_prepared, equivalent_transport, matlab_bridge"],
                   cwd=out, check=True)
    for name in ("logs", "runs", "fixtures"):
        (out / name).mkdir()
    test = subprocess.run([sys.executable, "-B", "test_adapter_runner.py"], cwd=out, check=True)
    assert test.returncode == 0
    result = read(out / "ADAPTER_TEST_RESULT.json")
    if not result["success"] or result["tests"] != 18 or result["native_api_attempts"]:
        raise ValueError("Adapter test gate failed")
    # Bridge creates and uses this isolated profile. Probe only directory access.
    prefs = out / RUNTIME / "matlab_prefs"
    prefs.mkdir(parents=True, exist_ok=False)
    marker = prefs / ".writable_probe"
    marker.write_bytes(b"probe")
    if marker.read_bytes() != b"probe":
        raise IOError("MATLAB preference directory failed round trip")
    marker.unlink()
    visible = [p.info["name"] for p in psutil.process_iter(["name"])
               if "matlab" in (p.info["name"] or "").lower()]
    free = psutil.virtual_memory().available
    save(out / "ENVIRONMENT_PREFLIGHT.json", {
        "prefdir_relative": prefs.relative_to(out).as_posix(),
        "isolated_writable_empty_at_preflight": not any(prefs.iterdir()),
        "historical_runtime_files_excluded": len(excluded),
        "preference_content_is_frozen_scientific_source": False,
        "entry_import_preflight_passed": True,
        "available_bytes": free, "visible_matlab_count": len(visible),
        "matlab_executable_sha256": sha(executable),
    })
    if visible or free < 2**31:
        raise RuntimeError("Resource gate requires no other visible MATLAB and 2 GiB available")
    save(out / "PLAN.json", {
        "progress_commit": PROGRESS, "source_subject": predecessor["subject_commit"],
        "technical_validation": not optimization, "root_seconds": 600 if optimization else 300,
        "native_caps_s": {"AB_offset_0ms": 120 if optimization else 30,
                          "AC_offset_0ms": 300 if optimization else 120},
        "mapping": {"A.pre": "CPU1", "A.main": "NPU0", "A.post": "CPU1"},
        "fresh_initialisation_both_scenes": True, "max_launches": 1,
        "max_requests": 2, "max_rounds": 1, "retries": 0,
        "native_options": ("MaxFeasiblePoints=Inf, original tolerances and other options"
                           if optimization else "original probe, MaxFeasiblePoints=1; original tolerances"),
        "optimization_validation": optimization,
        "budget_reason": ("Observed root LP about 27 s AB and 116 s AC. Native caps allow "
                          "about 90 s and 180 s beyond those observations, with shared "
                          "method allowance for startup, transport and continuous SAFE."
                          if optimization else "User-specified delivery diagnostic"),
        "formal_comparison": False,
        "admission": "each scene native vector, original rows and full original continuous SAFE",
        "optimality": "preserve raw output; never infer optimality from conflicted status",
        "runtime_preference_policy": "fresh isolated writable directory; environment only",
        "prior_frozen_immutable_files_verified": len(immutable),
    })
    for name in ("PLAN.json", "ENVIRONMENT_PREFLIGHT.json", "ADAPTER_TEST_RESULT.json"):
        files[name] = sha(out / name)
    save(out / "FROZEN.json", {
        "subject_commit": predecessor["subject_commit"], "progress_commit": PROGRESS,
        "files": files, "matlab_executable": str(executable),
        "matlab_executable_sha256": predecessor["matlab_executable_sha256"],
    })
    print(json.dumps({"frozen": len(files), "prior_immutable_matched": len(immutable),
                      "runtime_excluded": len(excluded), "adapter_tests": result["tests"],
                      "plan_sha256": sha(out / "PLAN.json")}))


if __name__ == "__main__":
    main()
