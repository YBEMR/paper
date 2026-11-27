"""Stage only the checked M1-j deliverables and list their SHA-256 values."""
import hashlib
import subprocess
from pathlib import Path

from paths_j import DATA, REPO, ROOT, inputs

TABLES = """repetitions.csv medians.csv paired_cases.csv paired_repeats.csv interactions.csv interactions_repeats.csv
group_coverage.csv group_contrasts.csv group_interactions.csv calls.csv.gz improvements.csv stages.csv historical_fixed.csv
batch_receipt.json event_volumes.csv sample_replay.csv repeat_stability.csv verification.json""".split()
CASE_FILES = ("runs.tar.xz","physical.tar.xz","event_index.csv.gz","event_volume.json","receipt.json")


def main():
    names=[ROOT/n for n in ("README.md","paired_results.md","path_examples.md")]
    names.extend(DATA/n for n in TABLES)
    for i in range(6):
        names.extend(DATA/"environment"/f"{k}{i}.json" for k in ("lane","host"))
    names.extend(DATA/"paths"/n for n in ("lineage.csv.gz","windows.csv","verification.json"))
    for c in inputs():
        names.extend(DATA/"evidence"/c["case"]/n for n in CASE_FILES)
        names.append(DATA/"paths"/(c["case"]+"_pools.csv.gz"))
    assert len(names)==len(set(names)) and all(p.is_file() and p.stat().st_size for p in names)
    lines=[]
    for path in sorted(names):
        with path.open("rb") as f:
            lines.append(hashlib.file_digest(f,"sha256").hexdigest()+"  "+path.relative_to(ROOT).as_posix())
    manifest=ROOT/"SHA256SUMS"
    manifest.write_text("\n".join(lines)+"\n",encoding="utf8")
    names.append(manifest)
    paths=[n.relative_to(REPO).as_posix() for n in names]
    subprocess.run(["git","add","--",*paths],cwd=REPO,check=True)
    staged=subprocess.check_output(["git","diff","--cached","--name-only","-z"],cwd=REPO).decode().split("\0")
    assert set(staged)-{""}==set(paths)


if __name__=="__main__":
    main()
