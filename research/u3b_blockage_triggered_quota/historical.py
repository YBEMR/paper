"""Read immutable evidence only. This module is never imported by an online worker."""
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter, process_time

HERE = Path(__file__).resolve().parent
OLD = Path(os.environ["U3A_ARCHIVE"]).resolve()
def load(path):
    return json.loads(path.read_bytes())

def digest(data):
    return hashlib.sha256(data).hexdigest()

def audit():
    started, cpu = perf_counter(), process_time()
    result = []
    with (OLD/"tables/cases.csv").open(encoding="utf8") as stream:
        cases = list(csv.DictReader(stream))
    for case in cases:
        name = case["case"]
        root = OLD/"results"/name
        hist = load(root/"history.json")
        inp = hist["case"]
        assert digest((OLD/"registration/inputs"/inp["input"]).read_bytes()) == case["input_sha256"] == inp["input_sha256"]
        pooled = json.loads(gzip.decompress((root/"raw_pool.json.gz").read_bytes()))
        scores = {v["parent"]+v["extension"]:v["score"] for v in pooled[-1]["attempts"] if v["score"] is not None}
        ordered = sorted(scores, key=lambda k:(scores[k],k))
        assert len(ordered) == int(case["last_distinct"])
        known = [load(f) for f in sorted(root.glob("retained_*.json"))]
        detail = load(root/"audit.json") if (root/"audit.json").exists() else {}
        known.extend(detail.get("terminal",[]))
        attempts = []
        for pos, key in enumerate(ordered[:12],1):
            rec = next(r for r in known if r["rank"] == pos)
            assert rec["config_sha256"] == digest(bytes.fromhex(key))
            folder = root/"evidence"/inp["case"]/rec["plan"]
            cert = load(folder/"certificate.json")
            assert digest((folder/"plan.json").read_bytes().strip()) == cert["plan_sha256"] == rec["plan"]
            attempts.append(dict(rank=pos,plan=rec["plan"],status=cert["metrics"]["status"]))
            if attempts[-1]["status"]=="SAFE":
                break
        result.append(dict(case=name,input=inp,top12=[digest(bytes.fromhex(x)) for x in ordered[:12]],
            first_safe=next((r["rank"] for r in attempts if r["status"]=="SAFE"),None),
            archive_attempts=attempts,nt_best_history=hist.get("nt_call"),native_history=hist.get("first"),
            original_pool_sha256=digest((root/"raw_pool.json.gz").read_bytes())))
    dst = HERE/"tables"
    dst.mkdir(exist_ok=True)
    (dst/"historical.json").write_text(json.dumps(dict(cases=result,wall_s=perf_counter()-started,
        cpu_s=process_time()-cpu),indent=2),encoding="utf8")
if __name__=="__main__":
    audit()

