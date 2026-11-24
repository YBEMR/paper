"""Offline archive proof checks, never invoke scheduling or thermal simulation."""
from pathlib import Path
import json,gzip,hashlib,csv
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def read(name):
    with gzip.open(HERE/"raw"/name,"rt",encoding="utf-8") as f:return [json.loads(x) for x in f]
manifest=json.loads((HERE/"execution_manifest.json").read_bytes())
for name,h in manifest.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
inputs=json.loads((HERE/"inputs.json").read_bytes());cfg=json.loads((HERE/"config.json").read_bytes())
schedules=read("schedules.jsonl.gz");lookup={s["id"]:s for s in schedules}
assert len(schedules)==len(lookup)==1701
profiles={}
with (HERE/"stage_profiles.csv").open(encoding="utf-8",newline="") as f:
    for row in csv.DictReader(f):profiles.setdefault((row["path"],row["opp"],int(row["app"])),[]).append(row)
for s in schedules:
    jobs={q["id"]:q for q in s["requests"]}
    assert set(jobs)==set(s["completions_ns"])
    chains={}
    for r in s["rows"]:chains.setdefault(r["request"],[]).append(r)
    for rid,chain in chains.items():
        chain=sorted(chain,key=lambda r:r["stage_index"])
        expected=profiles[s["path"],s["opp"],jobs[rid]["app"]]
        assert len(chain)==len(expected)
        for stage,p in zip(chain,expected):
            assert stage["stage"]==p["name"] and stage["resource"]==p["resource"]
            assert stage["end_ns"]-stage["start_ns"]==int(p["duration_ns"])
            assert abs(stage["activity_w"]-float(p["activity_w"]))<1e-12
        assert chain[0]["start_ns"]>=jobs[rid]["release_ns"]
        assert all(a["end_ns"]<=b["start_ns"] for a,b in zip(chain,chain[1:]))
        assert chain[-1]["end_ns"]==s["completions_ns"][rid]
    for res in s["busy_ns"]:
        rr=sorted((r for r in s["rows"] if r["resource"]==res),key=lambda r:r["start_ns"])
        assert all(a["end_ns"]<=b["start_ns"] for a,b in zip(rr,rr[1:]))
        assert sum(max(0,min(r["end_ns"],40_000_000)-r["start_ns"]) for r in rr)==s["busy_ns"][res]
    assert s["deadline_ok"]==all(s["completions_ns"][rid]<=q["deadline_ns"] for rid,q in jobs.items())
    assert sum(s["duration_ns"])==40_000_000
raw=read("certificates.jsonl.gz");assert len(raw)==43740
keys=set();energy_error=0.;status={};expanded_requests=0
traces={}
for load in inputs["loads"]:
    with np.load(HERE/"raw"/(load+"_cycle_states.npz")) as z:
        for key,a in zip(z["keys"],z["states"]):traces[tuple(key)]=a.copy()
for r in raw:
    key=tuple(r[k] for k in ("schedule_id","mode","ambient_C","inlet","frames"));assert key not in keys;keys.add(key)
    s=lookup[r["schedule_id"]];assert s["deadline_ok"]==r["deadline_ok"]
    assert r["required"]==r["frames"]*len(s["requests"])
    # Exact expansion of all requests from certified no-backlog periodic trace.
    for f in range(r["frames"]):
        for q in s["requests"]:
            release=q["release_ns"]+f*40_000_000;end=s["completions_ns"][q["id"]]+f*40_000_000
            if r["deadline_ok"]:assert release<=end<=q["deadline_ns"]+f*40_000_000
            expanded_requests+=1
    status[r["status"]]=status.get(r["status"],0)+1
    if not r["deadline_ok"]:
        assert r["energy_J"] is None and r["thermal_status"]=="NOT_EVALUATED";continue
    a=traces[tuple(str(r[k]) for k in ("schedule_id","mode","ambient_C","inlet"))][r["frames"]-1]
    assert np.array_equal(a[:4],r["final_C"]) and np.array_equal(a[4:8],r["peak_lower_C"]) and np.array_equal(a[8:12],r["peak_upper_C"])
    assert np.all(np.array(r["peak_upper_C"])>=np.array(r["peak_lower_C"]))
    observed="VIOLATION" if max(r["peak_lower_C"])>80 else "SAFE" if max(r["peak_upper_C"])<=80 else "UNRESOLVED"
    assert observed==r["status"]
    total=r["common_J"]+r["transfer_J"]+sum(r["idle_J"])+sum(r["activity_J"])+sum(r["leakage_J"])
    energy_error=max(energy_error,abs(total-r["energy_J"]));assert abs(total-r["energy_J"])<1e-8
    expected=np.sum(np.array(s["activity_W"])*np.array(s["duration_ns"])[:,None],axis=0)*1e-9*r["frames"]
    assert np.max(np.abs(expected-r["activity_J"]))<1e-8
receipt=json.loads((HERE/"raw/receipt.json").read_bytes())
assert receipt["exit_code"]==0 and receipt["wall_seconds"]<cfg["batch_wall_budget_s"]
out=dict(status="PASS",source_hashes=len(manifest),scheduled=len(schedules),condition_rows=len(raw),
    thermal_trajectories=len(traces),expanded_request_checks=expanded_requests,states=status,
    max_energy_decomposition_error_J=energy_error,receipt=receipt,
    scope="read-only archive and full request expansion; numerical equivalence to original evaluator checked separately before freeze")
(HERE/"verification.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
print(json.dumps(out,indent=2))
