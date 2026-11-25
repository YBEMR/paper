"""Run the two authorized S80 arms once, using the original worker and a separate evidence store."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

PAIR = Path(__file__).resolve().parent
G1 = PAIR.parent
REPO = G1.parents[1]
OUT = PAIR / "results"
PREFIX = G1.relative_to(REPO).as_posix()
FREEZE = "0bf054836fdad819388a01cd365b84b808a7611e"
BASELINES = "e3e6ef91"
PREVIOUS = "5c32412cea367a6750d1f0ef9cda8de1d653c973"
SEED = "bcdaa7177b3263f707a29f57619a538884ab6e77c4922bc691ceece2dc4ef3c2"
LIMIT = 3600


def utc():
    return datetime.now(timezone.utc).isoformat()


def git(*args):
    return subprocess.check_output(["git", "-C",str(REPO), *args])


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    tmp.replace(path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source(commit, name):
    return git("show", f"{commit}:{PREFIX}/{name}")


def verify():
    assert git("remote", "get-url", "origin").decode().strip() == "https://github.com/YBEMR/paper.git"
    assert git("branch", "--show-current").decode().strip() == "codex/global-config-g1"
    for file in git("ls-tree", "--name-only", FREEZE + ":" + PREFIX).decode().splitlines():
        if file.endswith(".py") or file in ("PROTOCOL.md", "input_lock.json"):
            assert (G1 / file).read_bytes() == source(FREEZE, file), file
    inputs = json.loads(source(FREEZE, "input_lock.json"))
    for row in inputs["upstream"]:
        assert sha((REPO / row["path"]).read_bytes()) == row["sha256"], row["path"]
    for name, digest in inputs["new_instances"].items():
        assert sha((G1 / "instances" / name).read_bytes()) == digest, name
    sys.path.insert(0, str(G1))
    import g1io
    import importlib.metadata as metadata
    import ortools
    assert platform.python_version() == inputs["python"]
    assert all(metadata.version(k) == v for k, v in inputs["packages"].items())
    assert Path(ortools.__file__).resolve().is_relative_to(g1io.runtime.resolve())
    for name, digest in inputs["solver_runtime_files"]:
        assert sha((g1io.runtime / name).read_bytes()) == digest, name
    gates = json.loads(source(BASELINES, "results/preflight/gates.json"))
    assert all(gates["barriers"]["S80"][m]["passed"] for m in ("C0","C1"))
    for name in ("slices.jsonl", "timeline.jsonl", "model.json", "candidates.jsonl"):
        p = "results/cp/S80/C0/" + name
        assert (G1 / p).read_bytes() == source(PREVIOUS, p), p
    assert not (G1 / "results/cp/S80/C1").exists()
    assert all((PAIR / f).read_bytes() == source("HEAD", "s80_pair/" + f)
               for f in ("run_pair.py","PROTOCOL.md"))
    return inputs


def prepare_seed():
    data = source(BASELINES, "results/seeds/S80.json")
    assert json.loads(data)["plan"] == SEED
    keys = {SEED}
    for f in ("references.jsonl", "construction.jsonl"):
        for line in source(BASELINES, "results/" + f).splitlines():
            row = json.loads(line)
            if row["case"] == "S80" and "plan" in row:
                keys.add(row["plan"])
    for name in ("seeds","certificates","plans"):
        (OUT / name).mkdir()
    (OUT / "seeds/S80.json").write_bytes(data)
    for key in sorted(keys):
        for path in (f"plans/{key}.json.gz", f"certificates/{key}.json", f"certificates/{key}.npz"):
            blob = source(BASELINES, "results/" + path)
            if path.endswith(".gz"):
                assert sha(gzip.decompress(blob)) == key
            (OUT / path).write_bytes(blob)
    return sorted(keys)


def run_worker(method, start, deadline):
    sys.path.insert(0, str(G1))
    import g1io
    g1io.OUT = OUT
    from run import worker
    import g1_experiment
    assert g1_experiment.OUT == OUT and Path(g1_experiment.__file__).parent == G1
    worker("cp", "S80", method, start, deadline)


def main():
    inputs = verify()
    OUT.mkdir(exist_ok=False)
    seed_cache = prepare_seed()
    head = git("rev-parse","HEAD").decode().strip()
    save(OUT / "execution.json", dict(freeze=head, source=FREEZE, original_checkpoint=PREVIOUS,
         baseline_source=git("rev-parse",BASELINES).decode().strip(), utc=utc(), seed_plan=SEED,
         preexisting_S80_plans=seed_cache, seed=101, threads=1, budget_per_method_s=LIMIT,
         methods=["C0","C1"], packages=inputs["packages"], supervisor_pid=os.getpid()))
    batch_start = time.perf_counter()
    status = "STOP"
    try:
        for method in ("C0", "C1"):
            rec = dict(job="cp", case="S80", method=method, budget_s=LIMIT, utc=utc())
            save(OUT / f"start_{method}.json", rec)
            with (OUT / f"worker_{method}.txt").open("xb") as log:
                start = time.perf_counter()
                deadline = start + LIMIT
                args = [sys.executable,"-B","-u",str(Path(__file__).resolve()),"worker",
                        method,str(start),str(deadline)]
                try:
                    completed = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=max(.01,deadline-time.perf_counter()))
                    rec.update(status="OK" if completed.returncode == 0 else "ERROR",
                               exit_code=completed.returncode)
                except subprocess.TimeoutExpired:
                    rec.update(status="TIME_LIMIT")
                rec.update(elapsed_s=time.perf_counter()-start, end_utc=utc())
            with (OUT/"jobs.jsonl").open("a",encoding="utf8") as f:
                f.write(json.dumps(rec) + "\n")
            expected = OUT / "cp" / "S80" / method
            if rec["status"] == "ERROR" or not (expected/"model.json").is_file():
                raise RuntimeError(f"{method} failed, see worker log")
        status = "COMPLETED"
    except BaseException:
        save(OUT/"stop.json", dict(utc=utc(), error=traceback.format_exc()))
        raise
    finally:
        save(OUT/"end.json",dict(outcome=status, utc=utc(), elapsed_s=time.perf_counter()-batch_start))


if __name__ == "__main__":
    if len(sys.argv)>1:
        assert sys.argv[1]=="worker" and sys.argv[2] in ("C0","C1")
        run_worker(sys.argv[2],float(sys.argv[3]),float(sys.argv[4]))
    else:
        main()
