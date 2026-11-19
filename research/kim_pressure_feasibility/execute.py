"""Read-only preflight by default. Explicitly approved execution is single use."""
import argparse
import hashlib
from importlib.metadata import distribution, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter, time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RAW = HERE / "raw_execution"
CAP = 120


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, record):
    temp = path.with_suffix(path.suffix + ".pending")
    with temp.open("w", encoding="utf8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def append(path, event):
    with path.open("a", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(event, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def verify_freeze(freeze_bytes=None):
    if freeze_bytes is None:
        freeze_bytes = (HERE / "execution_freeze.json").read_bytes()
    freeze = json.loads(freeze_bytes)
    for name, expected in freeze["sha256"].items():
        data = (ROOT / name).read_bytes()
        # Historic Windows archives and Git can use different text checkout endings.
        candidates = [data]
        if not name.endswith(".npz"):
            lf = data.replace(b"\r\n", b"\n")
            candidates.extend((lf, lf.replace(b"\n", b"\r\n")))
        require(any(sha(candidate) == expected for candidate in candidates), "SHA256 mismatch: " + name)
    require(platform.python_version() == freeze["python"] and
            all(version(k) == v for k,v in freeze["packages"].items()), "runtime dependency mismatch")
    runtime = freeze["runtime_sha256"]
    require(sha(Path(sys.executable).read_bytes()) == runtime["python_exe"], "Python executable mismatch")
    for package, hashes in runtime["distributions"].items():
        dist = distribution(package)
        for path, expected in hashes.items():
            require(sha(Path(dist.locate_file(path)).read_bytes()) == expected, "package metadata: " + path)
    manifest = read(HERE / "manifest.json")
    jobs = manifest["execution_order"]
    require(jobs == [dict(case_id=c, deployment=d) for d in ["A","C","D001","D015"]
                     for c in manifest["case_order"]] and len(set(manifest["case_order"])) == 3,
            "execution order mismatch")
    require(len(jobs) * CAP == 1440 and manifest["proposed_budget"]["retries"] == 0, "budget mismatch")
    return manifest


def committed_freeze(subject, freeze_bytes=None):
    git = ["git", "-C", str(ROOT)]
    head = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
    require(len(subject) == 40 and head == subject, "expected approved checkout SHA")
    rel = (HERE / "execution_freeze.json").relative_to(ROOT).as_posix()
    committed = subprocess.check_output(git + ["show", subject + ":" + rel])
    if freeze_bytes is None:
        freeze_bytes = (HERE / "execution_freeze.json").read_bytes()
    require(committed == freeze_bytes,
            "execution freeze differs from approved commit")
    return sha(freeze_bytes)


def worker(index):
    start = float(os.environ["PRESSURE_UNIT_START"])
    output = RAW / ("%02d" % index)
    reservation = read(output / "reservation.json")
    freeze_bytes = (HERE / "execution_freeze.json").read_bytes()
    digest = committed_freeze(reservation["subject"], freeze_bytes)
    require(digest == reservation["freeze_sha256"], "worker reservation freeze SHA256 mismatch")
    manifest = verify_freeze(freeze_bytes)
    job = manifest["execution_order"][index]
    require(reservation["job"] == job and reservation["index"] == index, "worker reservation mismatch")
    require(not (RAW / "stop.json").exists(), "batch already stopped")
    with (output / "worker.lock").open("x", encoding="ascii") as lock:
        lock.write(reservation["subject"])
    import unit
    result = unit.run_unit(manifest, job, output)
    result["subject"] = reservation["subject"]
    result["runtime"] = dict(host=platform.platform(), cpu=platform.processor(), python=sys.version)
    write(output / "result.json", result)
    # Receipt follows the atomic, flushed result and the closed NPZ/request files.
    write(output / "finished.json", dict(certificate_persisted_s=perf_counter()-start))


def gate(index, settled, jobs):
    if index >= 6:
        require(len(settled) == index and all(
            (row["case_id"], row["deployment"]) == (job["case_id"], job["deployment"])
            and row["deployment"] in ("A","C") and row["certificate"] == "NO_SAFE"
            and row["control_max_abs_energy_error_j"] is not None
            and row["control_max_abs_energy_error_j"] <= 1e-7 for row,job in zip(settled[:6], jobs[:6], strict=True)),
            "six A/C references must pass before expanded deployments")


def dispatch(index, job, subject, digest):
    output = RAW / ("%02d" % index)
    output.mkdir()
    reserve = dict(event="reserve", index=index, job=job, subject=subject,
                   freeze_sha256=digest, cap_s=CAP, cumulative_reserved_s=(index+1)*CAP, unix=time())
    write(output / "reservation.json", reserve)
    append(RAW / "ledger.jsonl", reserve)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               NUMBA_CACHE_DIR=str(output / "jit"), OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", NUMBA_NUM_THREADS="1")
    with (output / "console.log").open("wb") as console:
        start = perf_counter()
        env["PRESSURE_UNIT_START"] = str(start)
        child = subprocess.Popen([sys.executable, "-B", str(HERE / "execute.py"), "--worker", str(index)],
                                 env=env, stdout=console, stderr=subprocess.STDOUT)
        try:
            child.wait(timeout=max(0., CAP - (perf_counter()-start) - .05))
        except BaseException as exc:
            child.kill()
            child.wait()
            append(RAW / "ledger.jsonl", dict(event="close", index=index,
                                              status="DEADLINE" if isinstance(exc, subprocess.TimeoutExpired) else "ABORTED",
                                              wall_s=perf_counter()-start))
            raise
    elapsed = perf_counter() - start
    finished = read(output / "finished.json") if (output / "finished.json").is_file() else {}
    passed = child.returncode == 0 and 0 < finished.get("certificate_persisted_s", float("inf")) <= CAP
    status = "COMPLETE" if passed else "FAULT"
    append(RAW / "ledger.jsonl", dict(event="close", index=index, status=status, wall_s=elapsed,
                                      exit_code=child.returncode, **finished))
    require(passed, "unit failed or missed deadline")
    result = read(output / "result.json")
    require(all(result[k] == v for k,v in job.items()) and result["subject"] == subject, "wrong result identity")
    return dict(result, process_wall_s=elapsed, **finished)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute-approved", metavar="COMMIT")
    group.add_argument("--worker", type=int, choices=range(12), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker is not None:
        worker(args.worker)
        return
    manifest = verify_freeze()
    if args.execute_approved is None:
        print("Static freeze OK. No scientific calls.")
        return
    subject = args.execute_approved
    digest = committed_freeze(subject)
    RAW.mkdir(exist_ok=False)
    settled = []
    index = None
    try:
        for index,job in enumerate(manifest["execution_order"]):
            gate(index, settled, manifest["execution_order"])
            settled.append(dispatch(index, job, subject, digest))
        write(RAW / "summary.json", settled)
        outcomes = {}
        for case_id in manifest["case_order"]:
            added = [r for r in settled if r["case_id"] == case_id and r["deployment"] in ("D001","D015")]
            witnesses = [r["deployment"] for r in added if r["safe_witness"]]
            outcome = ("RESTORED" if witnesses else "NO_SAFE_IN_FOUR" if
                       all(r["certificate"] == "NO_SAFE" for r in added) else "UNRESOLVED")
            outcomes[case_id] = dict(outcome=outcome, witness_deployments=witnesses)
        write(RAW / "interpretation.json", dict(scope=settled[0]["scope"], cases=outcomes))
        write(RAW / "stop.json", dict(reason="COMPLETE", reserved_s=1440, completed=len(settled)))
    except BaseException as exc:
        write(RAW / "stop.json", dict(reason="STOP", index=index, completed=len(settled), error=repr(exc)))
        raise
    finally:
        artifacts = {p.relative_to(RAW).as_posix():sha(p.read_bytes()) for p in RAW.rglob("*")
                     if p.is_file() and "jit" not in p.relative_to(RAW).parts}
        write(RAW / "sha256.json", artifacts)


if __name__ == "__main__":
    main()
