"""Bind all replay targets to frozen archived pre-states, without running a solver."""
from pathlib import Path
import gzip, hashlib, json, subprocess
ROOT = Path(__file__).resolve().parent
B = ROOT.parent / "domain_joint_optimization_e2b"
REPO = ROOT.parents[1]
BASE = "34d36f56a78166360503e41a1a057171e29fd4eb"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False, default=str)+"\n", encoding="utf8", newline="\n")
    tmp.replace(path)

def stream(path):
    with gzip.open(path, "rb") as f:
        for line in f:
            yield json.loads(line)

def freeze():
    snap = read(B/"snapshot.json")["files"]
    manifest = read(B/"manifest.json")
    hashes = {}
    def use(path):
        value = digest(path.read_bytes())
        assert value == snap[path.relative_to(B).as_posix()], path
        hashes[path.relative_to(REPO).as_posix()] = value
        return path
    for name in ("manifest.json","base.py","neighborhood.py","numerics.py","arm.py","supervise.py"):
        use(B/name)
    for rel, expected in manifest["files"].items():
        assert digest((REPO/rel).read_bytes()) == expected, rel
    data = []
    for case in ("D1","D2","D3"):
        for seed in (101,102,103):
            folder = B/"runs"/f"{case}_Proposed_{seed}"
            iterations = list(stream(use(folder/"iterations.jsonl.gz")))
            plans = dict(stream(use(folder/"plans.jsonl.gz")))
            history = {x["after"]:x for x in stream(use(folder/"history.jsonl.gz"))}
            stale = 0
            failures = []
            for event in iterations:
                if event.get("operator",{}).get("fallback"):
                    failures.append((event,stale))
                stale = 0 if event.get("adopted") else stale+1
            assert len(failures)>=3
            for pos,role in ((0,"first"),(len(failures)//2,"middle"),(len(failures)-1,"last")):
                event,stale = failures[pos]
                src = event["source"]
                body = json.dumps(plans[src],ensure_ascii=False,separators=(",",":")).encode()
                assert digest(body)==src and history[src]["metrics"]["status"]=="SAFE"
                path = ROOT/"prestates"/(src+".json.gz")
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(gzip.compress(body,mtime=0))
                target,option = event["operator"]["conditional"][-1]["targets"][0]
                data.append(dict(id=f"{case}_{seed}_{role}",case=case,seed=seed,role=role,rank_zero=pos,
                                 fallback_count=len(failures),iteration=event["iteration"],stale=stale,
                                 window=event["window"],source=src,primary=target,proposal=option,
                                 prior_metrics=history[src]["metrics"],historical_mode=event["mode"],
                                 historical_region=event["region"],historical_anchor=event["anchor"],
                                 history_log=(folder/"iterations.jsonl.gz").relative_to(REPO).as_posix()))
    structure=[]
    for case in ("D2","D3"):
        folder=B/"preflight"/("pilot_"+case+"_Proposed")
        event=next(stream(use(folder/"iterations.jsonl.gz")))
        plan = dict(stream(use(folder/"plans.jsonl.gz")))[event["source"]]
        body=json.dumps(plan,ensure_ascii=False,separators=(",",":")).encode()
        assert digest(body)==event["source"]
        (ROOT/"prestates"/(event["source"]+".json.gz")).write_bytes(gzip.compress(body,mtime=0))
        z=event["operator"]["conditional"][-1]
        structure.append(dict(case=case,source=event["source"],targets=z["targets"],projection=z["count"],
                              historical_support=z["final"]["support"],minimum_expected=14 if case=="D3" else None))
    assert len(data)==len({x["id"] for x in data})==27
    write(ROOT/"samples.json",dict(base=BASE,cases=data,structural=structure,sources=hashes,
          inherited_manifest_sha256=digest((B/"manifest.json").read_bytes())))
if __name__=="__main__":
    freeze()
