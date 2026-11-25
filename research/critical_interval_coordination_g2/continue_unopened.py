"""Seal two interrupted endpoints as unresolved; launch only the unopened frozen jobs."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from batch import ROOT,BUDGET,METHODS,read,dump,launch,physical_cores,git,utc

def main():
    runs=ROOT/"runs"
    freeze=read(runs/"freeze.json")
    assert git("remote","get-url","origin")=="https://github.com/YBEMR/paper.git"
    assert git("branch","--show-current")=="codex/critical-interval-g2"
    for name,digest in freeze["sources"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    cores=physical_cores()
    assert cores==freeze["cores"]
    all_tasks=[]
    for case,cap in BUDGET.items():
        charged=read(runs/f"init_{case}"/"receipt.json")["elapsed_s"]
        for ix,seed in enumerate((101,102,103)):
            all_tasks.append([("main",case,m,seed,cap-charged,cores[(i+ix)%len(cores)],charged) for i,m in enumerate(METHODS)])
    for case in ("S80","D3"):
        all_tasks.append([("strong",case,m,101,600,cores[i%len(cores)],0) for i,m in enumerate(("AB","Proposed"))])
    def folder(t):return runs/f"{t[0]}_{t[1]}_{t[2]}_{t[3]}"
    waves=[];partials=[]
    for wave in all_tasks:
        remaining=[]
        for t in wave:
            d=folder(t)
            if not d.exists():remaining.append(t);continue
            if (d/"receipt.json").exists():
                assert read(d/"receipt.json")["status"]=="OK";continue
            assert d.name in ("main_D1_Compact_102","main_D1_Proposed_102")
            assert not (d/"result.json").exists()
            q=read(d/"progress.json");assert q["phase"]=="timing"
            partials.append(d.name)
        if remaining:waves.append(remaining)
    assert sum(map(len,waves))==16 and len(partials)==2
    with (runs/"continuation.json").open("x",encoding="utf8") as f:
        import json
        json.dump(dict(utc=utc(),local_freeze=git("rev-parse","HEAD"),original=freeze["head"],interrupted=partials,
                       remaining=[[folder(t).name for t in w] for w in waves]),f,indent=2)
    for n in partials:
        d=runs/n;s=read(d/"start.json");progress=read(d/"progress.json")
        lines=[json.loads(line) for line in (d/"rounds.jsonl").read_bytes().splitlines()]
        cfg=[l for l in lines if l["phase"]=="configuration"];post=[l for l in lines if l["phase"]=="timing"]
        assert post and cfg[-1]["after"]["plan"]==post[0]["before"]["plan"]
        dump(d/"receipt.json",dict(**s,status="INTERRUPTED",reconciled_utc=utc(),exit_code=None,
             elapsed_s=None,last_observed_charged_s=progress["elapsed_s"],reserved_s=s["limit_s"]))
        dump(d/"result.json",dict(case=s["case"],method=s["method"],seed=s["seed"],status="INTERRUPTED",
             initial=lines[0]["before"],configuration=cfg[-1]["after"],last_observed=progress["best"],
             configuration_rounds=len(cfg),post_rounds=len(post),final=None))
    try:
        for wave in waves:
            with ThreadPoolExecutor(max_workers=len(cores)) as pool:
                futures=[pool.submit(launch,runs,*t) for t in wave]
                for f in futures:f.result()
    except BaseException:
        import traceback
        dump(runs/"continuation_stop.json",dict(utc=utc(),error=traceback.format_exc()));raise
    dump(runs/"end.json",dict(utc=utc(),outcome="CLOSED_WITH_INTERRUPTION",incomplete=partials))
if __name__=="__main__":main()
