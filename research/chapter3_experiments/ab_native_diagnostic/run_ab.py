"""Bounded technical diagnosis for the fixed 2026-11-06 AB request."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MODEL = "affa9501fc75d8ee6ccc314b3b3043dce88a704f0c63d50691df9ebda7d27001"
X0 = "47d009fd41f8d0281ee347709c8d9a346a4f20ffab3af7c73025986fa5b61333"
ORIGINAL_MAT = "dd8ce3fe40d8d641d755e211eea0649642fcc689d4a0b4a6547c7b65686867d1"
NATIVE_MAT = "2f2a7cbdd57585b8c25877420c954910733c81f2b0c40d945015bc7920edbc72"
CONFIG = "132323b4b18dd514b9baa929543d235ff91bb07026a60e7b629e1adb6aaaa5e2"
INSTANCE = "01eacb2a653d56419c32f38740021a787ea01ac9e7ade407bef2edd81ec6ef89"
MANIFEST = "7b5c2e5c5870c0513d4a913d3756d37b68fbb3180c7735594b87f5d269d92358"
MAPPING = {"A.pre": "CPU1", "A.main": "NPU0", "A.post": "CPU1"}
SCENE = "AB_offset_0ms"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normal(value):
    # Same identity encoding as the frozen handoff adapter.
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return {"float_hex": value.hex()}
    if isinstance(value, dict):
        return {k: normal(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normal(v) for v in value]
    if hasattr(value, "tocoo"):
        coo = value.tocoo()
        return {"sparse_shape": list(coo.shape), "row": normal(coo.row),
                "col": normal(coo.col), "data": normal(coo.data)}
    return {"dtype": str(value.dtype), "shape": list(value.shape),
            "data_sha256": sha(value.tobytes(order="C"))}


def identity(value):
    return sha(json.dumps(normal(value), sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def read_inputs(source):
    values = []
    for name, expected in (("input_config.json", CONFIG), ("input_instance.json", INSTANCE)):
        raw = (source / name).read_bytes()
        original = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if sha(raw) != expected and sha(original) != expected:
            raise ValueError(f"Frozen input hash mismatch: {name}")
        values.append(json.loads(raw))
    return values


def build(source, budget_seconds):
    origin = time.monotonic()
    raw = (source / "BASELINE_MANIFEST.json").read_bytes().replace(b"\r\n", b"\n")
    if sha(raw) != MANIFEST:
        raise ValueError("Frozen baseline manifest mismatch")
    manifest = json.loads(raw)
    differences = [r["path"] for r in manifest["files"]
                   if not (REPO / r["path"]).is_file()
                   or sha((REPO / r["path"]).read_bytes()) != r["sha256"]]
    # The later formal entry/driver changes are outside this direct build path.
    allowed = {"formal_milp.py", "bpre_formal_entry.py", "test_bpre_formal_entry.py",
               "test_formal_continuation.py", "test_formal_driver.py", "test_formal_milp.py"}
    if any(Path(p).parent != HERE.parent.relative_to(REPO) or Path(p).name not in allowed
           for p in differences):
        raise ValueError(f"Unexpected baseline source drift: {differences}")
    sys.path.insert(0, str(HERE.parent))
    from milp import build_model
    from scene_method import DEFAULT_BUILDER_OPTIONS
    from thermal import _accuracy
    from timing import MethodBudget
    budget = MethodBudget(budget_seconds, clock=lambda: time.monotonic())
    config, instance = read_inputs(source)
    model = build_model(instance, config, budget=budget, fixed_scene_id=SCENE,
                        fixed_shared_deployment=MAPPING, **DEFAULT_BUILDER_OPTIONS)
    payload = model.as_solver_dict()
    digest = identity(payload)
    if digest != MODEL or (len(payload["c"]), payload["A"].shape[0] + payload["Aeq"].shape[0]) != (8738, 40078):
        raise ValueError(f"AB model does not match historical payload: {digest}")
    return model, payload, _accuracy(config["accuracy_targets"]), instance, budget, differences, origin


def prepare(args):
    import numpy as np
    from scipy.io import loadmat, savemat
    started = time.monotonic()
    args.out.mkdir(parents=True, exist_ok=False)
    target = args.out / "request.mat"
    if args.original_mat:
        read_inputs(args.source)
        data = args.original_mat.read_bytes()
        if sha(data) != ORIGINAL_MAT:
            raise ValueError("Historical request MAT SHA-256 mismatch")
        saved = loadmat(args.original_mat)
        x0 = saved["x0"].reshape(-1)
        names = ("A", "Aeq", "b", "beq", "c", "lb", "ub", "intcon")
        if args.native_mat:
            if sha(args.native_mat.read_bytes()) != NATIVE_MAT:
                raise ValueError("Historical native MAT SHA-256 mismatch")
            native = loadmat(args.native_mat, variable_names=["x","fval","exitflag","initialPoint"])
            if (native["initialPoint"].reshape(-1).tobytes() != x0.tobytes()
                    or native["x"].size or native["fval"].size or native["exitflag"].item() != 0):
                raise ValueError("Historical native result disagrees with probe audit")
        differences = None
        origin_label = "historical_request_bytes"
    else:
        model, raw, accuracy, _, budget, differences, _ = build(args.source, 60)
        # The generated export can be checked against the historical payload hash.
        from initial_point import prepare_initial_witness
        prepared = prepare_initial_witness(model, accuracy, budget, None, 3)
        if prepared["state"] != "SAFE_POINT_READY":
            raise ValueError(f"Fresh initial point not ready: {prepared['reason']}")
        x0 = prepared["x0"]
        origin_label = "rebuilt_matching_model_and_x0"
    if identity(x0) != X0:
        raise ValueError(f"AB initial vector differs from historical vector: {identity(x0)}")
    sys.path.insert(0, str(HERE.parent))
    from matlab_bridge import _prepare, _check_initial_point
    if args.original_mat:
        target.write_bytes(data)
        payload = {name: saved[name] if name in ("A", "Aeq") else saved[name].reshape(-1)
                   for name in (*names, "x0")}
        _, payload["x0_validation"] = _check_initial_point(payload, x0)
    else:
        payload = _prepare(raw, x0)
        savemat(target, payload, oned_as="column")
    stored = loadmat(target)
    for name in ("A", "Aeq"):
        if stored[name].shape != payload[name].shape or (stored[name] != payload[name]).nnz:
            raise ValueError(f"Stored matrix differs: {name}")
    for name in ("b", "beq", "c", "lb", "ub", "intcon", "x0"):
        if not np.array_equal(stored[name].reshape(-1), payload[name]):
            raise ValueError(f"Stored vector differs: {name}")
    coeffs = np.abs(payload["A"].data)
    coeffs = coeffs[coeffs > 0]
    receipt = {"provenance": origin_label, "model_payload_sha256": MODEL,
               "x0_sha256": X0, "request_mat_sha256": sha(target.read_bytes()),
               "historical_request_mat_sha256": ORIGINAL_MAT,
               "historical_native_mat_sha256": NATIVE_MAT if args.native_mat else None,
               "input_config_sha256": CONFIG, "input_instance_sha256": INSTANCE,
               "variables": len(payload["c"]), "inequalities": payload["A"].shape[0],
               "equalities": payload["Aeq"].shape[0], "integer_count": len(payload["intcon"]),
               "A_nnz": payload["A"].nnz, "A_min_abs_nonzero": float(coeffs.min()),
               "A_max_abs": float(coeffs.max()), "x0_check": payload["x0_validation"],
               "baseline_file_differences": differences,
               "elapsed_s": time.monotonic() - started}
    write_json(args.out / "identity.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def prepared_request(folder):
    meta = json.loads((folder / "identity.json").read_bytes())
    mat = (folder / "request.mat").resolve(strict=True)
    if (meta["model_payload_sha256"], meta["x0_sha256"], meta["request_mat_sha256"]) != (
            MODEL, X0, sha(mat.read_bytes())):
        raise ValueError("Prepared request failed identity check")
    return meta, mat


def make_repair(args):
    from scipy.io import loadmat, savemat
    sys.path.insert(0, str(HERE.parent / "numeric_case_diagnostic"))
    from exact_equalities import KEYS, transform
    _, mat = prepared_request(args.prepared)
    loaded = loadmat(mat, variable_names=KEYS)
    original = {k: loaded[k] if k in ("A", "Aeq") else loaded[k].reshape(-1) for k in KEYS}
    derived, cert = transform(original)
    if not cert["exact_pairs_moved"]:
        raise ValueError("No exact equality pairs on this input")
    args.out.mkdir(parents=True, exist_ok=False)
    target = args.out / "repair.mat"
    savemat(target, derived, oned_as="column")
    cert.update(source_mat_sha256=sha(mat.read_bytes()), repair_mat_sha256=sha(target.read_bytes()))
    write_json(args.out / "certificate.json", cert)
    print(json.dumps({k: cert[k] for k in ("exact_pairs_moved", "derived_inequalities",
                                         "derived_equalities", "repair_mat_sha256", "checks")}))


def post(args):
    from scipy.io import loadmat
    model, payload, accuracy, instance, budget, _, _ = build(args.source, 60)
    from matlab_bridge import _prepare
    from milp import decode
    from scene_adapter import evaluate_partial_scene
    r = loadmat(args.result, variable_names=["x", "flag"])
    if not r["x"].size or r["flag"].item() not in (1, 2, 3):
        raise ValueError("No final integer candidate eligible for thermal replay")
    x = r["x"].reshape(-1)
    admission = _prepare(payload, x)["x0_validation"]
    candidate = decode(model, x)
    receipt = evaluate_partial_scene(instance, SCENE, MAPPING, candidate, accuracy, budget)
    write_json(args.out, {"source_result_mat_sha256": sha(args.result.read_bytes()),
                          "original_model_payload_sha256": MODEL, "original_row_admission": admission,
                          "candidate": candidate, "scope": "AB only; original continuous model; no repair",
                          "formal_experiment": False, "receipt": receipt})
    print(json.dumps({"post_state": receipt["state"],
                      "safe_upper_bound_J": receipt["safe_upper_bound_J"],
                      "elapsed_s": budget.elapsed}))


def run(args):
    import psutil
    meta, mat = prepared_request(args.prepared)
    if psutil.virtual_memory().available < 2**31 or any(
            "matlab" in (p.info["name"] or "").lower() for p in psutil.process_iter(["name"])):
        raise RuntimeError("Resource gate requires 2 GiB available and no other MATLAB process")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    hard_s = {"lp": 120, "milp": 155, "repair": 145}[args.phase]
    env = dict(os.environ, AB_DIAG_SCRIPT=str(HERE), AB_DIAG_MAT=str(mat),
               AB_DIAG_OUT=str(out), AB_DIAG_PHASE=args.phase)
    if args.phase == "repair":
        repair = args.repair_dir / "repair.mat"
        certificate = json.loads((args.repair_dir / "certificate.json").read_bytes())
        if (certificate["source_mat_sha256"], certificate["repair_mat_sha256"]) != (
                meta["request_mat_sha256"], sha(repair.read_bytes())):
            raise ValueError("Repair matrix does not match equivalence certificate")
        env["AB_DIAG_REPAIR_MAT"] = str(repair.resolve(strict=True))
    start = time.monotonic()
    processes = {}
    reason = "MATLAB_EXITED"
    with (out / "matlab.log").open("wb") as log:
        process = subprocess.Popen(
            [str(args.matlab.resolve(strict=True)), "-wait", "-batch",
             "addpath(getenv('AB_DIAG_SCRIPT')); diagnose_ab"],
            cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        root = psutil.Process(process.pid)
        try:
            while process.poll() is None:
                for p in root.children(recursive=True):
                    processes[p.pid] = p
                if time.monotonic() - start >= hard_s:
                    reason = "EXTERNAL_DEADLINE"
                    break
                if psutil.virtual_memory().available < 2**31:
                    reason = "LOW_AVAILABLE_MEMORY"
                    break
                time.sleep(0.25)
        finally:
            if process.poll() is None:
                processes[root.pid] = root
            for p in reversed(list(processes.values())):
                try:
                    if p.is_running():
                        p.kill()
                except psutil.NoSuchProcess:
                    pass
            process.wait(timeout=10)
            _, alive = psutil.wait_procs(list(processes.values()), timeout=5)
    status = {"reason": reason, "returncode": process.returncode,
              "elapsed_s": time.monotonic() - start, "hard_seconds": hard_s,
              "surviving_owned_processes": [p.pid for p in alive],
              "phase": args.phase, "request_mat_sha256": meta["request_mat_sha256"],
              "result_files": sorted(p.name for p in out.glob("*.json"))}
    write_json(out / "supervisor.json", status)
    print(json.dumps(status))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--original-mat", type=Path)
    p.add_argument("--native-mat", type=Path)
    r = sub.add_parser("run")
    r.add_argument("--prepared", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--matlab", required=True, type=Path)
    r.add_argument("--phase", choices=("lp", "milp", "repair"), required=True)
    r.add_argument("--repair-dir", type=Path)
    q = sub.add_parser("prepare-repair")
    q.add_argument("--prepared", required=True, type=Path)
    q.add_argument("--out", required=True, type=Path)
    p = sub.add_parser("post")
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--result", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "prepare-repair":
        make_repair(args)
    elif args.command == "post":
        post(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
