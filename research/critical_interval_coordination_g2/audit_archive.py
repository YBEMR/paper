"""Check every published archive against its declared SHA and its original job receipts."""
import hashlib
import io
import json
import subprocess
import tarfile

from archive import ROOT, group, verify

GROUPS = ("preflight", "initialization", "main_S32", "main_S80", "main_D1", "main_D2",
          "strong_S80", "strong_D3")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_inputs(freeze):
    g1 = ROOT.parent / "global_config_coordination_g1"
    repo = ROOT.parents[1]
    tree = freeze["original_G1_tree"]
    lock = g1 / "input_lock.json"
    assert digest(lock) == freeze["G1_input_lock_sha256"]
    inputs = json.loads(lock.read_bytes())
    for row in inputs["upstream"]:
        assert digest(repo / row["path"]) == row["sha256"], row["path"]
    for name, expected in inputs["new_instances"].items():
        assert digest(g1 / "instances" / name) == expected
    for file in sorted(g1.glob("*.py")):
        args = ["git", "-C", str(repo)]
        name = file.relative_to(repo).as_posix()
        expected = subprocess.check_output([*args, "rev-parse", tree + ":" + name]).strip()
        actual = subprocess.check_output([*args, "hash-object", str(file)]).strip()
        assert expected == actual, name


def main():
    freeze = json.loads((ROOT / "formal_lock.json").read_bytes())
    check_inputs(freeze)
    for name, expected in freeze["files"].items():
        assert digest(ROOT / name) == expected, name
    data = {}
    for name in GROUPS:
        parent = ROOT / "archive"
        path = parent / (name + ".tar.xz")
        if path.exists():
            archive_hash = digest(path)
            size = path.stat().st_size
            payload = path.read_bytes()
        else:
            path = parent / (name + ".index.json")
            parts = json.loads(path.read_bytes())
            archive_hash = parts["sha256"]
            size = sum((parent / item["name"]).stat().st_size for item in parts["parts"])
            assert size == parts["size"]
            payload = b"".join((parent / item["name"]).read_bytes() for item in parts["parts"])
        verify(path)
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as tar:
            entries = json.load(tar.extractfile("index.json"))
        originals = {p.relative_to(ROOT).as_posix(): p for p in group(name) if p.is_file()}
        assert entries.keys() == originals.keys(), name
        for item, original in originals.items():
            assert digest(original) == entries[item]["sha256"], item
        data[name] = {
            "entry": path.relative_to(ROOT).as_posix(), "sha256": archive_hash,
            "bytes": size, "paths_in_original_group": len(entries),
        }
    for name in ("witness_gate.json", "model_gate.json", "finite_gate.json", "runs/freeze.json",
                 "runs/continuation.json", "runs/end.json", "budget_receipts.csv", "construction.csv",
                 "paired.csv", "summary.csv", "mechanism.csv", "matched_rounds.csv", "budget_audit.json"):
        data[name] = {"sha256": digest(ROOT / name)}
    target = ROOT / "archive_manifest.json"
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf8", newline="\n")
    print(f"Verified {len(GROUPS)} groups covering {sum(x.get('paths_in_original_group', 0) for x in data.values())} original files.")


if __name__ == "__main__":
    main()
