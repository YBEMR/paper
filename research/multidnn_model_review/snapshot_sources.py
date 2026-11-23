"""Bind reused local sources to the immutable Kim-line commit, not to branch names."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = json.loads((HERE / "protocol.json").read_bytes())["base_commit"]
DIRECTORIES = (
    "kim_synthetic_platform_v1", "kim_scene_dvfs_admission", "kim_safety_repair_audit",
    "kim_multidnn_expansion", "kim_multidnn_search_trial", "ch3_cooperative_cuts",
    "ch3_energy_repair", "ch3_joint_repair", "ch3_algorithm_selection",
    "ch3_final_experiments/p2",
)
EXTRA = (
    "main.pdf",
    "research/kim_case_b_freeze/input.json",
    "research/kim_synthetic_platform_v1/platform.json",
    "research/kim_synthetic_platform_v1/experiments.json",
    "research/kim_multidnn_expansion/catalog.json",
    "research/kim_multidnn_expansion/expanded_input.json",
    "research/kim_multidnn_expansion/sources.md",
    "research/ch3_algorithm_selection/config.json",
    "research/ch3_algorithm_selection/hardware.md",
    "research/ch3_energy_repair/config.json",
    "research/kim_safety_repair_audit/design.json",
    "research/kim_multidnn_expansion/raw/expanded/forward_flat_25C/deployment_C.json",
)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    names = set(EXTRA)
    for directory in DIRECTORIES:
        names.update(n for n in git("ls-tree", "-r", "--name-only", BASE,
                                    "research/" + directory).decode().splitlines()
                     if n.endswith(".py") and str(Path(n).parent).replace("\\", "/") == "research/" + directory)
    hashes = {}
    for name in sorted(names):
        expected = git("show", f"{BASE}:{name}")
        local = ROOT / name
        if not local.is_file():
            raise FileNotFoundError(f"Expand sparse checkout before snapshot: {name}")
        actual = local.read_bytes()
        # Git may check out Windows line endings, but they are not source changes.
        normalized = actual.replace(b"\r\n", b"\n") if name.endswith((".py", ".md", ".json")) else actual
        expected_normalized = expected.replace(b"\r\n", b"\n") if name.endswith((".py", ".md", ".json")) else expected
        if normalized != expected_normalized:
            raise ValueError(f"Local source differs from pinned commit: {name}")
        hashes[name] = sha256(actual).hexdigest()
    result = dict(base_commit=BASE, verification="Compared with git show at immutable base",
                  byte_hash_policy="local file bytes; regenerate only after Git line-ending normalization",
                  sha256=hashes)
    (HERE / "frozen_sources.json").write_bytes((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(f"Bound {len(hashes)} reused files to {BASE}")


if __name__ == "__main__":
    main()
