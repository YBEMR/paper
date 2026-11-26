"""Copy pinned P1 assets and reference fixtures without executing archive entry points."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
ARCHIVES = {
    "ch4_original_experiments.zip": "4d352ecda69b3ef72f8f8cdf262703d7b50c480946cfe08d572bc5d8e5218f1e",
    "ch4_thermal_evidence.zip": "ae306fa4ac78ecf48eaa2d6660ee1e492a62cbfca93ef5db0506b028886bea17",
}


def main():
    files = [ROOT.parent / name for name in ARCHIVES]
    for path in files:
        assert sha256(path.read_bytes()).hexdigest() == ARCHIVES[path.name]
    with ZipFile(files[0]) as original, ZipFile(files[1]) as replay:
        p, q = "ch4_preflight_v1/", "ch4_long_scene_replay_20261126/"
        for line in replay.read(q + "SHA256SUMS").decode().splitlines():
            digest, name = line.split(None, 1)
            assert sha256(replay.read(q + name)).hexdigest() == digest
        for n in original.namelist():
            rel = n.removeprefix(p)
            if rel == "preflight.py" or rel.startswith("p1/"):
                data = original.read(n)
                assert data == replay.read(q + rel)
                dst = ROOT / "frozen" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
        for case in ("L640", "L800", "L320", "L480"):
            data = replay.read(q + "replayed/inputs/" + case + ".csv")
            if case in ("L640", "L800"):
                assert data == original.read(p + "run/inputs/" + case + ".csv")
            dst = ROOT / "inputs" / (case + ".csv")
            dst.parent.mkdir(exist_ok=True)
            dst.write_bytes(data)
        manifest = json.loads(replay.read(q + "replayed/manifest.json"))
        (ROOT / "inputs/source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
