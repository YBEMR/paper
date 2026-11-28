"""Stage sealed input bytes and verify archive hashes before starting the compute clock."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
DRIVER = ROOT.parents[1]
OLD = ROOT.parent / "ch3_direct_thermal_dp"
LANES = ROOT.parent / "ch3_center_confirmation/lanes"
OUT = ROOT / "out"
BASE = "65b6cbc2c77baef9ef2092c7e05f3e26ae99f7b0"


def checks(path):
    return {Path(name): digest for digest, name in
            (line.split(maxsplit=1) for line in path.read_text().splitlines())}


def verify(path, digest):
    with path.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == digest, path


def pending():
    with (OLD / "tables/mappings.csv").open() as stream:
        slots = {(r["case"], int(r["construction_s"]), int(r["rank"]))
                 for r in csv.DictReader(stream) if r["complete"] == "False"}
    manifest = json.loads((OLD / "out/nominees.json").read_bytes())
    rows = [r for r in manifest if (r["case"], r["budget"], r["rank"]) in slots]
    assert len(manifest) == 96 and len(rows) == len(slots) == 56
    assert len({(r["case"],r["budget"]) for r in rows}) == 14
    return rows


def main():
    start = time.monotonic()
    assert subprocess.check_output(["git","rev-parse","HEAD^"],cwd=DRIVER,text=True).strip() == "66a0abe5aa1cc84067ab384b5a8ddadab23da5f6"
    # Confirm the inherited data and evaluator trees are identical to the frozen baseline.
    parent = subprocess.check_output(["git","cat-file","-p","HEAD^"],cwd=DRIVER,text=True)
    assert "parent "+BASE+"\n" in parent
    old_checks = checks(OLD / "SHA256SUMS")
    for rel, digest in old_checks.items():
        verify(OLD / rel, digest)
    paths = set()
    rows = pending()
    cases = sorted({r["case"] for r in rows})
    manifests = {}
    for case in cases:
        lane = LANES / case
        manifests[case] = checks(lane / "SHA256SUMS")
        base = lane / "r1/paired_results" / case
        physical = base / "physical"
        index_path = physical / "index.json"
        verify(index_path, manifests[case][index_path.relative_to(lane)])
        index = json.loads(index_path.read_bytes())
        paths.add(index_path)
        for r in (r for r in rows if r["case"] == case):
            folder = base / f"center-{r['budget']}"
            paths.update(folder / f for f in ("certificates.jsonl","refine.jsonl","search.jsonl"))
            keys = {r["seed"]} | {h["point"]["plan"] for h in r["history"].values() if h["point"]}
            for key in keys:
                plan = index["plans"][key]
                paths.add(physical / plan["archive"])
                paths.update(physical / index["blocks"][block] for block in plan["blocks"])
    subprocess.run(["git","sparse-checkout","add","--stdin"],cwd=DRIVER,check=True,
                   input="".join("/"+p.relative_to(DRIVER).as_posix()+"\n" for p in sorted(paths)),text=True)
    fetched = time.monotonic()
    audited = {}
    for p in sorted(paths):
        case = p.relative_to(LANES).parts[0]
        rel = p.relative_to(LANES / case)
        digest = manifests[case][rel]
        verify(p, digest)
        audited[p.relative_to(DRIVER).as_posix()] = digest
    OUT.mkdir()
    for folder in ("slots","evidence"):
        shutil.copytree(OLD / "out" / folder, OUT / folder)
    shutil.copyfile(OLD / "out/nominees.json", OUT / "nominees.json")
    checkpoint = DRIVER.parent/"checkpoint"
    inputs = ROOT/"out/checkpoint"
    inputs.mkdir()
    for p in ("acquisition.json","out/budget.json"):
        shutil.copyfile(checkpoint/p,inputs/Path(p).name)
    fresh = checkpoint/"out/evidence/C10/computed"
    assert len(list(fresh.glob("*/ordinary/evidence/*/*/trace.npz"))) == 1
    shutil.copytree(fresh,inputs/"C10")
    data = dict(previous_preparation_wall_s=json.loads((inputs/"acquisition.json").read_bytes())["total_preparation_wall_s"],base=BASE, initial_checkout_and_environment_s=time.time()-float(os.environ["ACQUIRE_START"])-(time.monotonic()-start),
                acquisition_and_prior_validation_s=fetched-start,archive_validation_and_staging_s=time.monotonic()-fetched,
                total_preparation_wall_s=time.time()-float(os.environ["ACQUIRE_START"]),
                frozen_files_checked=len(old_checks),selected_files=len(paths),
                selected_bytes=sum(p.stat().st_size for p in paths),sha256=audited)
    (ROOT/"acquisition.json").write_text(json.dumps(data,indent=2)+"\n")
    print("Verified selected files, bytes, preparation wall seconds:",len(paths),data["selected_bytes"],data["total_preparation_wall_s"],flush=True)


if __name__ == "__main__":
    main()
