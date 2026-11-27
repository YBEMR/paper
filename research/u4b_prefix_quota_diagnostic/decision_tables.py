"""Link observed expansions and interventions to the first delivered SAFE, without new search."""
from collections import Counter
import csv
from shared import *
from archive_results import csvfile

def main():
    paths=[];historical=[]
    for k,o in cases().items():
        root=HERE/"results"/k;source=A/"results"/k
        base=read(source/"runs/Base.json")
        layers=next(e[2] for e in events(source,base) if e[:2]==["store","base"])
        phys=root/"physical";pmap={r["certificate"]["plan_sha256"]:r for r in map(json.loads,gzip.decompress((phys/"plans.jsonl.gz").read_bytes()).splitlines())}
        for arm in "RPDCH":
            r=read(root/f"runs/{arm}.json");d=r["delivered"]
            cfg=None if not d else u.encoded(row[:2] for row in pmap[d[0]["plan"]]["plan"]["rows"][1::3])
            ns=np.cumsum([60 if v=="L" else 100 for v in o["word"]]).tolist()
            pid={};intervention=None;choices=[];transitions=[];hit=[];skips=Counter()
            for e in events(root,r):
                if e[0]=="parent":pid[e[1]]=bytes.fromhex(e[2])
                if e[0]=="selection":
                    choices.append([e[1]+1,e[2],e[3],e[4]])
                    if arm=="R" and not e[2]:
                        j=e[1];old=layers["layers"][j]
                        assert e[3]==old["distinct"] and e[4][:4]==old["retained"]
                        if j+1==len(ns):assert e[4]==layers["terminal"]
                if e[0]=="enrich_start":intervention=e[1]+1
                if e[0]=="branch_skip":skips[e[1]+1]+=1
                if e[0]=="q4_action" and cfg is not None and intervention==e[2]+1:
                    _,pi,j,pair,q,offset,t=e
                    start=0 if j==0 else ns[j-1]
                    if t[-1] or pid[pi]!=cfg[:start]:continue
                    ext=cfg[start:ns[j]]
                    # Input CSV gives the exact within-window request kind sequence.
                    # All matching actions must reconstruct the delivered configuration.
                    if not transitions:
                        with (A/"registration/inputs"/o["input"]).open(encoding="utf8") as f:transitions=[row["kind"] for row in csv.DictReader(f)]
                    tps=np.array([int(v=="B") for v in transitions[start:ns[j]]])
                    from mechanism import Case
                    expected=Case.extension(tps,int(sum(tps==0)),int(sum(tps==1)),*pair,*q)
                    if ext==expected:hit.append(dict(pair=pair,quota=q,offset=offset,small=tuple(offset) in OFFSETS))
            paths.append(dict(case=k,arm=arm,first=d[0]["plan"] if d else None,first_phase=d[0]["phase"] if d else None,
                              empty_layer=intervention,branch_exclusions=dict(skips),enriched_seed_actions=hit,
                              selections=[z[:3]+[len(z[3])] for z in choices]))
        if k not in FOCUS:continue
        dd=HERE/"offline"/k
        a=read(dd/"audit.json");t=read(dd/"terminal_evidence.json");p=read(dd/"domain_prefixes.json")
        path=a["path"];ref=a["first_loss"];nu=[z["loss"] for z in path]
        rr=p["within_run"]["Base"];dup=[z for z in rr if z["same_prior_physics"]]
        hist=dict(case=k,windows=len(ns),last_observed=a["layers"][-1]["window"],distinct_terminal=a["terminal_distinct"],
              strict_physical_matches=sum(bool(v["matches"]) for v in t["complete"]),
              certified_original=len(rr),duplicate=len(dup),gross_duplicate_kernel_s=sum(v["kernel_s"] for v in dup),
              first_NT_loss=ref["loss"],window=ref["window"],rank_loss=nu.count("rank"),timing_loss=nu.count("timing"),
              conditional_balance=sum(w["balance"] for w in path),conditional_small=sum(w["perturb"] for w in path),
              conditional_composition=sum(w["composition"] for w in path),conditional_timing_pass=sum(not w["late"] for w in path),
              convergence_windows=sorted({v["earliest_all_beam_share"] for v in t["proofs"].values() if v["base_evidence"] and v["earliest_all_beam_share"]}))
        historical.append(hist)
    put(HERE/"tables/decisions.json",paths);csvfile("historical",historical)
if __name__=="__main__":
    u.stack()
    main()
