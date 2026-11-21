"""Archive completed cases of the fixed study, retaining the original slot files."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile

from run_study import CONFIG, HERE, directory, files_for, jobs


GITHUB_LIMIT = 100 * 1024 ** 2


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return digest(stream)


def unit_members(job, input_hashes):
    folder = directory(job)
    receipt_path = folder / "receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    expected_inputs = {name: input_hashes[name] for name in files_for(job[2])}
    if receipt["job"] != list(job) or receipt["inputs"] != expected_inputs:
        raise ValueError(f"Receipt job or input SHA differs: {folder}")

    outputs = receipt["files"]
    paths = sorted(folder.iterdir())
    if ({p.name for p in paths} != set(outputs) | {"receipt.json"} or "receipt.json" in outputs or
            any(not p.is_file() or p.is_symlink() for p in paths)):
        raise ValueError(f"Unreceipted, missing or non-regular output: {folder}")
    if not {"reservation.json", "console.txt"} <= outputs.keys():
        raise ValueError(f"Incomplete supervision evidence: {folder}")
    reservation = json.loads((folder / "reservation.json").read_bytes())
    if (reservation["inputs"] != expected_inputs or reservation["job"] != list(job) or
            reservation["core"] != receipt["core"] or reservation["cap_s"] != CONFIG["slot_wall_cap_s"]):
        raise ValueError(f"Reservation identity differs: {folder}")

    state = receipt["state"]
    if state not in {"finished", "fault", "hard_timeout"}:
        raise ValueError(f"Unknown slot state {state}: {folder}")
    if state == "finished":
        if receipt["exitcode"] != 0 or not {"events.jsonl.gz", "result.json.gz"} <= outputs.keys():
            raise ValueError(f"Finished slot lacks events or result: {folder}")
        with gzip.open(folder / "result.json.gz", "rt", encoding="utf-8") as stream:
            result = json.load(stream)
        if (result["job"] != list(job) or
                (result["selected_genome"] is not None) != ("selection.json.gz" in outputs)):
            raise ValueError(f"Selected evidence or result identity differs: {folder}")

    members = {}
    for path in paths:
        actual = file_hash(path)
        if path.name != "receipt.json" and actual != outputs[path.name]:
            raise ValueError(f"Output SHA differs from original receipt: {path}")
        members[f"{folder.name}/{path.name}"] = (path, path.stat().st_size, actual)
    return state, members


def tar_size(members):
    # USTAR, plain regular files, two zero blocks followed by 10 KiB record padding.
    block = tarfile.BLOCKSIZE
    payload = sum(block + ((size + block - 1) // block) * block for _, size, _ in members.values())
    return ((payload + 2 * block + tarfile.RECORDSIZE - 1) // tarfile.RECORDSIZE) * tarfile.RECORDSIZE


def verify_tar(path, members, size):
    seen = set()
    if path.stat().st_size != size:
        raise ValueError(f"Unexpected tar size: {path}")
    with tarfile.open(path, "r|") as archive:
        for item in archive:
            if item.name not in members or item.name in seen or not item.isfile():
                raise ValueError(f"Unexpected, repeated or non-file member: {item.name}")
            _, expected_size, expected_sha = members[item.name]
            stream = archive.extractfile(item)
            # Streaming tar extraction is not seekable. Hash fixed-size chunks in order.
            hasher = hashlib.sha256()
            with stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    hasher.update(chunk)
            if item.size != expected_size or hasher.hexdigest() != expected_sha:
                raise ValueError(f"Tar member differs from original: {item.name}")
            seen.add(item.name)
    if seen != members.keys():
        raise ValueError(f"Missing tar members: {sorted(members.keys() - seen)}")


def case_archive(outdir, case, units, input_hashes):
    counts, members = Counter(), {}
    for job in units:
        state, files = unit_members(job, input_hashes)
        if members.keys() & files.keys():
            raise ValueError(f"Duplicate planned unit: {job}")
        counts[state] += 1
        members.update(files)
    size = tar_size(members)
    if size >= GITHUB_LIMIT:
        raise ValueError(f"{case}: {size:,} bytes reaches the 100 MiB per-file limit; split this case before publication.")
    dest = outdir / f"{case}.tar"
    if dest.exists():
        verify_tar(dest, members, size)
    else:
        temp = tempfile.NamedTemporaryFile(dir=outdir, prefix=case + ".", suffix=".partial", delete=False)
        tmp = Path(temp.name)
        temp.close()
        try:
            with tarfile.open(tmp, "w", format=tarfile.USTAR_FORMAT) as archive:
                for name, (source, length, _) in sorted(members.items()):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = length, 0o644, 0
                    with source.open("rb") as stream:
                        archive.addfile(info, stream)
            verify_tar(tmp, members, size)
            # Create the final name exclusively. A simultaneous identical creator is harmless.
            try:
                if os.name == "nt":
                    # Same-directory rename is atomic and refuses an existing destination.
                    os.rename(tmp, dest)
                else:
                    os.link(tmp, dest)
            except FileExistsError:
                verify_tar(dest, members, size)
        finally:
            tmp.unlink(missing_ok=True)
    return dict(case=case, path=f"archives/{dest.name}", sha256=file_hash(dest), bytes=size,
                runs=len(units), members=len(members), states=dict(sorted(counts.items())))


def build(partial=False):
    planned = jobs()
    groups = defaultdict(list)
    for job in planned:
        groups[job[0]].append(job)
    if len(set(planned)) != 420 or len(planned) != 420 or len(groups) != 12 or any(
            len(group) != 35 for group in groups.values()):
        raise ValueError("The frozen 12 × 35 matrix differs.")
    pending = [case for case, group in groups.items()
               if not all((directory(job) / "receipt.json").is_file() for job in group)]
    if pending and not partial:
        raise ValueError(f"Waiting for cases {', '.join(pending)}. Use --partial to archive only completed cases.")

    outdir = HERE / "archives"
    outdir.mkdir(exist_ok=True)
    inputs = {name for _, _, method, _ in planned for name in files_for(method)}
    hashes = {name: file_hash(HERE / name) for name in inputs}
    archives = [case_archive(outdir, case, group, hashes)
                for case, group in groups.items() if case not in pending]
    report = dict(subject=CONFIG["subject"], study_config_sha256=hashes["study_config.json"],
                  format="uncompressed USTAR; original gzip bytes preserved", planned_runs=len(planned),
                  archived_runs=sum(row["runs"] for row in archives), pending_cases=pending, archives=archives)
    dest = HERE / "archive_manifest.json"
    with tempfile.NamedTemporaryFile(dir=HERE, prefix="archive_manifest.", suffix=".partial", mode="w",
                                     encoding="utf-8", newline="\n", delete=False) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        tmp = Path(stream.name)
    try:
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partial", action="store_true",
                        help="archive all cases that have all 35 receipts; list the rest as pending")
    args = parser.parse_args()
    report = build(args.partial)
    print(f"{report['archived_runs']}/{report['planned_runs']} runs in {len(report['archives'])} verified archives")
