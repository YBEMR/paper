"""Read/verify historical evidence and freeze topology-only probes. No evaluation/search calls."""
from collections import Counter
from itertools import zip_longest
import csv
import gzip
import hashlib
import random
import tarfile
from common import ROOT,HERE,HISTORY,read,save,sha,encoded,make_domain,loads

def main():
    inputs=HERE/"inputs";inputs.mkdir(exist_ok=True)
    domain=make_domain(ROOT);assert domain.size==4319803
    cases=[];history=[];pools={}
    manifest=read(HISTORY/"archives/manifest.json")
    for load in ["original","A","B"]:
        for temp in [25,30]:
            case=f"{load}_{temp}C";arc=HISTORY/"archives"/(case+".tar")
            assert sha(arc)==manifest[arc.name]["sha256"]
            rows=[]
            with tarfile.open(arc) as tar:
                for seed in loads.CFG["seeds"]:
                    prefix=f"kim_anytime_{seed}/"
                    receipt=read_member(tar,prefix+"receipt.json")
                    for name,digest in receipt["files"].items():
                        assert hashlib.sha256(tar.extractfile(prefix+name).read()).hexdigest()==digest
                    result=read_member(tar,prefix+"result.json.gz")
                    proof=read_member(tar,prefix+"selection.json.gz")
                    assert result["result"]["status"]==proof["physical"]["thermal_status"]=="SAFE"
                    assert result["result"]["energy_j"]==proof["physical"]["energy_j"]
                    assert proof["stages"]==domain.stages(proof["dep"])
                    requests=[[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]] for r in proof["completions"]]
                    assert requests==read(HISTORY/"streams"/(load+".json"))
                    assert loads.verify(requests,loads.CFG["loads"][load])==result["request_sha"]
                    assert all(r["deadline_ns"]-r["completion_ns"]==r["slack_ns"]>=0 for r in proof["completions"])
                    rows.append(dict(case_id=case,load=load,ambient_c=temp,seed=seed,dep=proof["dep"],indices=proof["indices"],
                        energy_j=proof["physical"]["energy_j"],source=arc.relative_to(ROOT).as_posix(),
                        member=prefix+"selection.json.gz",archive_sha=sha(arc),proof_sha=receipt["files"]["selection.json.gz"],
                        request_sha=result["request_sha"],wall_s=receipt["wall_s"],search_end_s=result["search_end_s"]))
                best=min(rows,key=lambda r:(r["energy_j"],r["seed"]))
                (inputs/(case+"_kim.json.gz")).write_bytes(tar.extractfile(best["member"]).read())
            cases.append(best);history.extend(rows)
            center=best["dep"]
            if center not in pools:
                rng=random.Random(20261123)
                near=domain.neighbors(center,40,rng,allow_exchange=True)
                target=domain._decode(domain.raw(center))
                # The frozen neighbor generator can return fewer than k. Fill the
                # declared quota uniformly from other legal single-app cuts, no scores.
                remaining=set()
                for app,(old,bit) in enumerate(target):
                    for idx,shape in enumerate(domain.cuts[app]):
                        child=list(target);child[app]=(idx,bit if shape else 0)
                        if sum(len(domain.cuts[i][s]) for i,(s,b) in enumerate(child))<=4:
                            d=domain.ident(domain._encode(tuple(child)))
                            if d!=center and d not in {d for d,a in near}:remaining.add(d)
                near.extend((d,"cut_fill") for d in rng.sample(sorted(remaining),40-len(near)))
                assert len(near)==40 and len({d for d,a in near})==40
                local=[dict(dep=d,group=a) for d,a in near if a!="exchange"]
                swaps=[dict(dep=d,group=a) for d,a in near if a=="exchange"]
                selected={center,*[d for d,a in near]};far=[]
                attempts=0
                while len(far)<8:
                    attempts+=1;assert attempts<=10000
                    d=domain.order[rng.randrange(domain.size)];layout=domain._decode(domain.raw(d))
                    if d not in selected and sum(a[0]!=b[0] for a,b in zip(layout,target))>=3:
                        selected.add(d);far.append(dict(dep=d,group="distant"))
                sequence=[v for row in zip_longest(local,swaps,far) for v in row if v is not None]
                assert len(sequence)==48
                for row in sequence:
                    row["stages"]=domain.stages(row["dep"])
                    for app,chain in row["stages"].items():domain.rules.check_chain(app,chain)
                pools[center]=sequence
    save(inputs/"cases.json",cases);save(inputs/"historical_kim.json",history);save(inputs/"candidates.json",pools)
    save(inputs/"domain_manifest.json",domain.manifest())
    save(HERE/"config.json",dict(base="72afaa405b7e9303c2f8fc95096c4a2e70ed4285",domain=4319803,
        case_ids=[c["case_id"] for c in cases],phases=["fixed_frequency","deployment_probe"],cap_s=120,admit_s=116,
        cores=[0,2,4,6,8,10],probe_seed=20261123,neighbors=40,distant=8,probe_total=48,
        e_tolerance_j=1e-7,kernel_cache=4096,no_retry=True,proxy_selection=False,
        baseline="lowest SAFE energy across historical three Kim-Anytime seeds; tie by seed",
        ordering="existing neighbor generator plus uniform legal single-cut fill to 40; interleave local, exchange, distant; no adaptive proposals",
        stop="one 120s phase per case; finish frozen list or deadline; preserve incomplete candidate and remaining list",
        claim="fixed-deployment and individually completed candidate certificates only; no 4319803-domain optimum"))
    save(HERE/"preparation_checks.json",dict(status="PASS",historical_kim_runs=18,selected=6,requests_per_certificate=500,
         sealed_archive_hashes=True,all_frozen_candidate_chains_valid=True,source_domain=domain.size,
         group_counts={d:dict(Counter(r["group"] for r in v)) for d,v in pools.items()},
         evaluation_calls=0,optimizer_calls=0))
    print([(r["case_id"],r["seed"],r["dep"],r["energy_j"]) for r in cases])
    print({d:dict(Counter(r["group"] for r in v)) for d,v in pools.items()})

def read_member(tar,name):
    raw=tar.extractfile(name).read()
    import json
    return json.loads(gzip.decompress(raw) if name.endswith(".gz") else raw)
if __name__=="__main__":main()
