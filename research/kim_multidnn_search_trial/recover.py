"""Reconcile the interrupted trial from existing bytes. No solver or worker is started."""
import gzip
import io
import json
import tarfile
from collections import Counter
from statistics import median

from summarize import HERE, OUT, RAW, collect, read, seal, sha, write


def complete_events(path):
    complete = []
    for line in path.read_bytes().splitlines(keepends=True):
        if line.endswith(b"\n"):
            complete.append(json.loads(line))
    assert all(a["t"] <= b["t"] for a, b in zip(complete, complete[1:]))
    return complete


def check_bundles():
    manifest = {item["path"]: item for item in read(OUT/"raw_sha256.json")}
    recovered = {}
    for kind in ("logs", "arrays"):
        index = read(OUT/(kind+"_index.json"))
        parts = [(OUT/part["name"]).read_bytes() for part in index["parts"]]
        for part, receipt in zip(parts, index["parts"]):
            assert len(part) == receipt["bytes"] and sha(part) == receipt["sha256"]
        data = b"".join(parts)
        assert sha(data) == index["whole_sha256"]
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(data)), mode="r:") as source:
            for member in source:
                assert member.isfile() and member.name not in recovered
                item = source.extractfile(member).read()
                recovered[member.name] = (len(item), sha(item))
        for name, primary in index["identical_files"].items():
            assert name not in recovered
            recovered[name] = recovered[primary]
    assert recovered == {name:(x["size"], x["sha256"]) for name,x in manifest.items()}
    for name,(size, digest) in recovered.items():
        live = (HERE/name).read_bytes()
        assert len(live) == size and sha(live) == digest
    return dict(files=len(recovered), arrays=sum(p.endswith(".npz") for p in recovered),
                raw_bytes=sum(size for size,_ in recovered.values()))


def main():
    freeze = (HERE/"freeze.json").read_bytes()
    for name,digest in json.loads(freeze)["files"].items():
        assert sha((HERE.parents[1]/name).read_bytes()) == digest, name
    subject = (RAW/"launch.lock").read_text().strip()
    jobs = read(HERE/"design.json")["jobs"]
    ledger = [json.loads(line) for line in (RAW/"ledger.jsonl").read_bytes().splitlines()]
    reserved = [event for event in ledger if event["event"] == "reserve"]
    closed = [event for event in ledger if event["event"] == "close"]
    assert [x["id"] for x in reserved] == [j["id"] for j in jobs[:len(reserved)]]
    assert [x["id"] for x in closed] == [x["id"] for x in reserved[:-1]]
    assert not (RAW/"stop.json").exists()
    for job, entry in zip(jobs, reserved):
        assert job["cap"] == entry["cap_s"]
        folder = RAW/job["id"]
        pin = read(folder/"job.json")
        assert all(pin[k] == job[k] for k in job)
        assert pin["preregistration"] == subject and pin["freeze_sha256"] == sha(freeze)
    for record in closed:
        result = read(RAW/record["id"]/"result.json")
        assert result["status"] == record["status"] and result["process_wall_s"] == record["actual_s"]
    interrupted = reserved[-1]
    partial = RAW/interrupted["id"]
    assert not (partial/"result.json").exists()
    ev = complete_events(partial/"events.jsonl")
    assert not any(x["kind"] == "certificate" for x in ev)
    states = [x for x in ev if x["kind"] == "deployment" and x["t"] <= interrupted["cap_s"]]
    by_phase = Counter(x["phase"] for x in states)
    safe = [x for x in ev if x["kind"] == "full_replay" and x["t"] <= interrupted["cap_s"] and
            x["choice"]["physical"]["feasible"]]
    for row in safe:
        physical = row["choice"]["physical"]
        assert physical["fully_replayed"] and physical["deadline_ok"]
        assert physical["required"] == physical["completed"] == 500
        assert physical["thermal_status"] == "SAFE" and max(physical["peak_upper_c"]) <= 80
    rows,pairs,budget = collect()
    assert len(rows) + len(read(OUT/"e0.json")) == len(closed)
    holdouts = []
    for case in ("H1","H2"):
        for method in ("M0","M1","M2"):
            rr = [x for x in rows if x["case"] == case and x["method"] == method]
            certs = [x["certificate_s"] for x in rr if x["certificate_s"] is not None]
            holdouts.append(dict(case=case,method=method,closed=len(rr),certified=len(certs),
                coverage=[x["completed"] for x in rr],
                first_safe_s=[x["first_safe_s"] for x in rr],
                certificate_s=certs,best_safe_j=[x["best_safe_j"] for x in rr],
                legal_hits=[x["legal_hits"] for x in rr],
                observed_certificate_median_s=median(certs) if certs else None))
    seal()
    integrity = check_bundles()
    audit = dict(subject=subject,freeze_sha256=sha(freeze),
        frozen_files_checked=len(json.loads(freeze)["files"]),budget=budget,archive=integrity,
        interrupted=dict(id=interrupted["id"],last_complete_event=ev[-1],
            completed_by_phase=dict(by_phase),first_safe_s=safe[0]["t"] if safe else None,
            best_safe_j=min((x["choice"]["physical"]["energy_j"] for x in safe),default=None),
            supervisor_result=False,classification="INTERRUPTED_UNSETTLED"),
        unstarted=[j["id"] for j in jobs[len(reserved):]],holdouts=holdouts,
        paired_deployment_arrays_identical=sum(x["byte_equal_energy_arrays"] for x in pairs),
        note="Recovery observation only. Original ledger, logs and arrays were preserved byte for byte.")
    write(OUT/"recovery_audit.json",audit)
    print(json.dumps(audit,ensure_ascii=True))


if __name__ == "__main__":
    main()
