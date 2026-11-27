"""Run stage 1, seal its gate, then optionally run stage 2. All arms share the hardware core."""
import argparse
import os
import platform
import time
from core import (
    CAP,CUTS,K,LIMIT,OUT,WORK,bind,cases,distribution,e,evaluate,improves,lower,
    np,ranking,read,save,seed,sha,verify_seed,
)

def search(c,stage,arm,start_cfg,start_cert):
    thermal = arm == "thermal"
    begin = time.perf_counter()
    candidates = distribution(c,start_cfg) if stage == 1 else lower(c,start_cfg)
    scored = [(evaluate(c,cfg,thermal),cfg) for _,_,cfg in candidates]
    ordered = sorted(((r,cfg) for r,cfg in scored if r["timing"]),key=lambda rec:ranking(rec,thermal))
    ranked_at = time.perf_counter()-begin
    calls = []
    winner,cert = start_cfg,start_cert
    for _,cfg in ordered[:K]:
        if time.perf_counter()-begin >= LIMIT:
            break
        native,_ = c.certify(cfg)
        at = time.perf_counter()-begin
        calls.append(dict(cfg=sha(cfg),plan=native["plan_sha256"],metrics=native["metrics"],
                          cert_s=native["cert_s"],at=at))
        if at <= LIMIT and improves(native,cert):
            winner,cert = cfg,native
    end = time.perf_counter()-begin
    assert len(scored) <= CAP and len(calls) <= K and len(scored) == len(candidates)
    return dict(arm=arm,stage=stage,start=sha(start_cfg),start_plan=start_cert["plan_sha256"],
                start_metrics=start_cert["metrics"],ranked_at=ranked_at,elapsed=end,
                candidates=[dict(cfg=sha(cfg),family=f,action=a,**r)
                            for (f,a,cfg),(r,_) in zip(candidates,scored)],
                calls=calls,winner=sha(winner),winner_plan=cert["plan_sha256"])


def gate():
    evidence = []
    for item in cases():
        label = item["case"]
        records = read(OUT/label/"s1.json.gz")["runs"]
        # Candidate identities and certifications are deterministic. Primary repetition 1.
        rows = [r for r in records if r["repeat"] == 1]
        for r in rows:
            base = r["start_metrics"]
            for t in r["calls"]:
                m = t["metrics"]
                delta_peak = max(base["peak_hi"])-max(m["peak_hi"])
                delta_slack = m["min_deadline_slack_ms"]-base["min_deadline_slack_ms"]
                if t["at"] <= LIMIT and m["status"] == "SAFE" and (delta_peak >= .05 or delta_slack >= 1):
                    evidence.append(dict(case=label,arm=r["arm"],cfg=t["cfg"],peak_drop_C=delta_peak,
                                         slack_gain_ms=delta_slack))
    n = len({r["case"] for r in evidence})
    save(OUT/"gate.json",dict(open=n>=2,cases=n,witnesses=evidence))


def run(item, stage):
    c = bind(item)
    label = item["case"]
    cfg,arch,ix = seed(label)
    orig,receipt = verify_seed(c,cfg,arch,ix)
    assert receipt["archived_array"] == receipt["replay_array"]
    assert max(receipt["max_abs_by_field"].values()) == 0
    folder = OUT/label
    if stage == 1:
        save(folder/"seed.json",dict(input_sha=item["input_sha256"],**receipt))
        arms = ["ordinary","thermal"]
        previous = []
    else:
        if not read(OUT/"gate.json")["open"]:
            return
        arms = ["original","ordinary","thermal"]
        previous = read(folder/"s1.json.gz")["runs"]
    starts = {sha(cfg):cfg}
    if stage == 2:
        starts.update({sha(b):b for _,_,b in distribution(c,cfg)})
    runs = []
    for rep in range(1,4):
        turn = (item["index"]+rep-1) % len(arms)
        for pos,arm in enumerate(arms[turn:]+arms[:turn]):
            start_cfg = cfg
            cert = orig
            if stage == 2 and arm != "original":
                one, = [r for r in previous if r["repeat"] == rep and r["arm"] == arm]
                start_cfg = starts[one["winner"]]
                cert = read(WORK/"native/evidence"/label/one["winner_plan"]/"certificate.json")
            r = search(c,stage,arm,start_cfg,cert)
            r.update(repeat=rep,position=pos+1)
            runs.append(r)
    import numba, scipy
    environment = dict(cpu=sorted(os.sched_getaffinity(0)),python=platform.python_version(),
                       numpy=np.__version__,numba=numba.__version__,scipy=scipy.__version__,
                       platform=platform.platform(),
                       threads={k:os.environ.get(k) for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS",
                                                              "NUMBA_NUM_THREADS","MKL_NUM_THREADS")})
    save(folder/f"s{stage}.json.gz",dict(case=label,environment=environment,runs=runs))
    print(label,"stage",stage,"max wall",round(max(r["elapsed"] for r in runs),3),flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("stage",choices=["1","2","gate"])
    p.add_argument("indices",nargs="*",type=int)
    a = p.parse_args()
    if a.stage == "gate":
        gate()
    else:
        for item in cases():
            if not a.indices or item["index"] in a.indices:
                run(item,int(a.stage))
