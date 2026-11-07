"""One frozen R2023b replay of the AC request with only x0 omitted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
import psutil
from scipy import sparse
from scipy.io import loadmat, savemat

SUBJECT = "301407b6a7c39b952550ae984e635edd89f0f6e1"
MAT_SHA = "bde54760351d94569dbc7524dd7fc1e30eb1efe5fa97d9e9a59938fe7ec44af7"
WORKER_SHA = "fd5bd23eba9eac80ca59c3ac9e9191ae43bfc0ce92bcec7d3697362e69a103e2"
EXE_SHA = "52a6d2755a9f9c7cd90ad97af7f6487c4d2c967729873255d782661bfec64f52"
ARRAYS = ("c", "A", "b", "Aeq", "beq", "lb", "ub", "intcon")
TIME_FIELDS = ("remaining_s", "solver_max_time_s_declared", "solver_max_time_s")
OMIT = ("x0", "x0_validation")
REQUEST = "request_000001"
HARD_SECONDS = 390
READY_SECONDS = 60
MEMORY_BYTES = 2**31


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def same(a, b):
    if sparse.issparse(a):
        return (sparse.issparse(b) and a.shape == b.shape and a.format == b.format
                and all(same(getattr(a, key), getattr(b, key))
                        for key in ("data", "indices", "indptr")))
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def freeze(reference, out, matlab):
    native = reference / "runs/native_once/condition/matlab"
    source = reference / "native_source/research/chapter3_experiments/solve_model.m"
    mat = native / "request_000002.mat"
    response = native / "request_000002.response.json"
    request = native / "request_000002.request.json"
    if (sha(mat), sha(source), sha(matlab)) != (MAT_SHA, WORKER_SHA, EXE_SHA):
        raise ValueError("Reference MAT, worker, or executable identity changed")
    original = {k: v for k, v in loadmat(mat).items() if not k.startswith("__")}
    if set(original) != set(ARRAYS + TIME_FIELDS + OMIT):
        raise ValueError("Unexpected historical MAT fields")
    ref = read(response)
    req = read(request)
    guard = ref["stop_decisions"][0]["guard_seconds"]
    if (ref["exitflag"] != 1 or ref["options"]["MaxTime"] != 300
            or ref["options"]["MaxFeasiblePoints"] is not None or guard <= HARD_SECONDS
            or not ref["initial_point"]["provided"] or ref["output"]["absolutegap"] <= 0):
        raise ValueError("Reference is not the AC early-stop request")
    if (min(original["remaining_s"].item(), req["remaining_s"]) <= 300
            or any(original[k].item() != 300 or req[k] != 300 for k in TIME_FIELDS[1:])):
        raise ValueError("Historical timing fields do not permit the original 300 s cap")
    out.mkdir(parents=True, exist_ok=False)
    worker = out / "worker"
    worker.mkdir()
    (out / "prefs").mkdir()
    shutil.copyfile(source, out / "solve_model.m")
    shutil.copyfile(response, out / "reference_response.json")
    shutil.copyfile(request, out / "frozen_request.json")
    delivered = worker / (REQUEST + ".mat")
    savemat(delivered, {k: original[k] for k in ARRAYS + TIME_FIELDS})
    check = {k: v for k, v in loadmat(delivered).items() if not k.startswith("__")}
    if set(check) != set(ARRAYS + TIME_FIELDS) or not all(same(original[k], check[k]) for k in check):
        raise ValueError("Replay serialization changed an original array")
    plan = {
        "subject_commit": SUBJECT, "scene": "AC_offset_0ms",
        "treatment": "omit x0 and its unused validation metadata",
        "reference_mat_sha256": MAT_SHA, "replay_mat_sha256": sha(delivered),
        "worker_sha256": WORKER_SHA, "matlab_executable_sha256": EXE_SHA,
        "version": read(native / "ready.json")["version"],
        "reference_response_sha256": sha(response), "request_sha256": sha(request),
        "runner_sha256": sha(Path(__file__)), "unchanged_bitwise_fields": sorted(check),
        "guard_seconds": guard, "max_time_s": 300, "external_wall_seconds": HARD_SECONDS,
        "startup_seconds": READY_SECONDS, "max_native_calls": 1, "retries": 0,
        "setup_difference": "fresh worker and preferences, first request instead of AC after AB",
        "scope": "technical native discrimination; no model build or thermal evaluation",
    }
    write(out / "plan.json", plan)
    print(json.dumps(plan, ensure_ascii=False), flush=True)


def run(out, matlab):
    plan = read(out / "plan.json")
    worker = out / "worker"
    for path, key in ((out / "solve_model.m", "worker_sha256"),
                      (worker / (REQUEST + ".mat"), "replay_mat_sha256"),
                      (out / "reference_response.json", "reference_response_sha256"),
                      (out / "frozen_request.json", "request_sha256"),
                      (Path(__file__), "runner_sha256"), (matlab, "matlab_executable_sha256")):
        if sha(path) != plan[key]:
            raise ValueError(f"Frozen artifact changed: {path.name}")
    if (psutil.virtual_memory().available < MEMORY_BYTES or
            any("matlab" in (p.info["name"] or "").lower()
                for p in psutil.process_iter(["name"]))):
        raise RuntimeError("Resource preflight requires 2 GiB available and no visible MATLAB")
    if any((out / "prefs").iterdir()):
        raise ValueError("Fresh isolated preferences required")
    write(out / "claim.json", {"plan_sha256": sha(out / "plan.json"), "max_native_calls": 1})
    env = dict(os.environ, MATLAB_PREFDIR=str(out / "prefs"), AC_REPLAY_SRC=str(out),
               AC_REPLAY_WORK=str(worker), AC_REPLAY_GUARD=str(plan["guard_seconds"]))
    command = "addpath(getenv('AC_REPLAY_SRC')); solve_model(getenv('AC_REPLAY_WORK'),str2double(getenv('AC_REPLAY_GUARD')))"
    started = time.monotonic()
    owned = {}
    status = "NO_NATIVE_RESPONSE"
    published = False
    response_path = worker / (REQUEST + ".response.json")
    with (out / "matlab.log").open("xb") as log:
        process = subprocess.Popen([str(matlab), "-wait", "-batch", command], cwd=worker,
                                   env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        root = psutil.Process(process.pid)
        try:
            while process.poll() is None:
                for child in root.children(recursive=True):
                    owned[child.pid] = child
                elapsed = time.monotonic() - started
                if response_path.exists():
                    status = "NATIVE_RESPONSE"
                    break
                if elapsed >= HARD_SECONDS or (not published and elapsed >= READY_SECONDS):
                    status = "WALL_DEADLINE" if published else "STARTUP_DEADLINE"
                    break
                if psutil.virtual_memory().available < MEMORY_BYTES:
                    status = "LOW_MEMORY"
                    break
                if not published and (worker / "ready.json").exists():
                    ready = read(worker / "ready.json")
                    if ready["status"] != "READY" or ready["version"] != plan["version"]:
                        status = "VERSION_OR_LICENSE_GATE_FAILED"
                        break
                    temporary = worker / "request.tmp"
                    shutil.copyfile(out / "frozen_request.json", temporary)
                    temporary.rename(worker / (REQUEST + ".request.json"))
                    published = True
                time.sleep(0.25)
        finally:
            (worker / "stop").touch()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                for child in reversed(list(owned.values()) + [root]):
                    try:
                        if child.is_running():
                            child.kill()
                    except psutil.NoSuchProcess:
                        pass
                process.wait(timeout=10)
            _, alive = psutil.wait_procs(list(owned.values()), timeout=5)
    result = {"status": status, "request_published": published,
              "wrapper_elapsed_s": time.monotonic() - started,
              "returncode": process.returncode, "surviving_owned_process_count": len(alive)}
    if response_path.exists():
        raw, ref = read(response_path), read(out / "reference_response.json")
        stops = raw.get("stop_decisions", [])
        result.update(
            comparable=bool(raw.get("status") == "SOLVED"
                            and raw.get("intlinprog_entered")
                            and raw.get("options") == ref["options"]
                            and raw.get("stop_decisions_log_complete") is True
                            and stops and not any(c["actual_stop"] for c in stops)
                            and raw.get("initial_point", {}).get("provided") is False
                            and not alive),
            identical_options=raw.get("options") == ref["options"],
            response_sha256=sha(response_path), exitflag=raw.get("exitflag"),
            fval=raw.get("fval"), x_length=len(raw.get("x") or []),
            native_output=raw.get("output"), native_call_s=raw.get("phase_seconds", {}).get("intlinprog_call"),
            native_initial_point_provided=raw.get("initial_point", {}).get("provided"),
            callbacks=[{"state": c["state"], "values": c["values"]} for c in raw.get("callbacks", [])],
        )
    write(out / "result.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "run"))
    parser.add_argument("out", type=Path)
    parser.add_argument("matlab", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.reference.resolve(strict=True), args.out.resolve(), args.matlab.resolve(strict=True))
    else:
        run(args.out.resolve(strict=True), args.matlab.resolve(strict=True))
