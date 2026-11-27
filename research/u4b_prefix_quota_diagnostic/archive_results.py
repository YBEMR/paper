"""Pack original online journals and continuous evidence with the frozen lossless writer."""
import csv
import struct
import platform
import subprocess
from collections import Counter
from shared import *
import batch_control
pack_spec=importlib.util.spec_from_file_location("u4a_packing",A/"pack_results.py")
pack=importlib.util.module_from_spec(pack_spec);pack_spec.loader.exec_module(pack)
pack.DEST=HERE/"results"

def csvfile(name,rows):
    path=HERE/"tables"/(name+".csv");path.parent.mkdir(exist_ok=True)
    with path.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

def main():
    import psutil
    psutil.Process().cpu_affinity([8]);rows=[];summ=[]
    idx=read(Path(os.environ["U3B_SRC"])/"registration/frozen_sources.json")
    for f in idx["files"]:assert sha((Path(os.environ["U3A_INPUTS"])/f["tree"]/f["path"]).read_bytes())==f["sha256"]
    pins={}
    for role,repo,pin in (("u3b",Path(os.environ["U3B_SRC"]).parents[1],"785cbcf78f17a48cd23567251418f8ef4a59e55c"),
                          ("u4a",A.parents[1],"0231bc8b1e54977cb617f53a03e64df84fbf7cca")):
        assert subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"]).decode().strip()==pin
        assert not subprocess.check_output(["git","-C",str(repo),"diff","HEAD","--","research"])
        pins[role]=pin
    put(HERE/"sources.json",dict(pins=dict(idx["pins"],**pins),files_verified=len(idx["files"]),
                                 inputs={k:o["input_sha256"] for k,o in cases().items()},
                                 python=sys.version,host=platform.platform()))
    for k,o in cases().items():
        root=pack.DEST/k;phy=pack.Physics(k)
        for m in "RPDCH":pack.pack_unit(RAW/(k+"-"+m),phy,o)
        phy.close()
        by={m:read(root/f"runs/{m}.json") for m in "RPDCH"}
        by["Base"]=read(A/f"results/{k}/runs/Base.json")
        for m,run in by.items():
            d=run["delivered"];final=d[-1] if d else {}
            certs=run["certificates"];counts=run["counts"]
            evroot=A/"results"/k if m=="Base" else root
            open_s=0.;checks=0;pending=None;probes=0.;attempt=0;skip_count=0
            for a in events(evroot,run):
                if a[0]=="open_start":pending=a[3]
                elif a[0]=="open_done":open_s+=a[5];pending=None;checks+=1
                elif a[0]=="reuse_test":probes+=a[3]
                elif a[0]=="enrich_start":attempt+=1
                elif a[0]=="terminal_skip":skip_count+=1
            if pending is not None:open_s+=max(0,run["wall_s"]-pending)
            rows.append(dict(case=k,arm=m,SAFE=int(bool(d)),first_s=d[0]["t"] if d else None,final_s=final.get("t"),
                plan=final.get("plan"),energy_J=final.get("J"),lo=final["bounds"][0] if d else None,hi=final["bounds"][1] if d else None,
                peak_hi_C=struct.unpack("<d",bytes.fromhex(final["peak"]))[0] if d else None,
                min_slack_ms=final.get("slack"),wall_s=run["wall_s"],stop=run["receipt"]["status"],
                fallbacks=int(run.get("fallback",False)),cert_started=run["started_certificates"],cert_done=len(certs),
                terminal_done=sum(c["phase"]=="terminal" for c in certs),strict_terminal_skips=skip_count,
                checked_parents=checks,open_started=counts.get("open_start",0),open_s=open_s,strict_branch_skips=counts.get("branch_skip",0),
                quota_expansions=attempt,lookup_s=probes,kernel_s=sum(c["kernel_s"] for c in certs),
                **{s+"_s":run["phases"].get(s,0.) for s in ("model","construct","terminal","fallback","group")}))
        print("packed",k,len(phy.plans),flush=True)
    csvfile("routes",rows)
    for m in ("Base",*"RPDCH"):
        rr=[r for r in rows if r["arm"]==m];good=[r for r in rr if r["SAFE"]]
        summ.append(dict(arm=m,SAFE=len(good),cases=" ".join(r["case"] for r in good),cert=sum(r["cert_done"] for r in rr),
                         terminal=sum(r["terminal_done"] for r in rr),fallback=sum(r["fallbacks"] for r in rr),
                         skip=sum(r["strict_terminal_skips"] for r in rr),branch=sum(r["strict_branch_skips"] for r in rr),
                         open=sum(r["checked_parents"] for r in rr),open_s=sum(r["open_s"] for r in rr),expansions=sum(r["quota_expansions"] for r in rr),
                         cutoff=sum(r["stop"]=="wall" for r in rr),min_slack_ms=min((r["min_slack_ms"] for r in good),default=None)))
    csvfile("summary",summ)
    pairs=[]
    for m,n in (("Base","R"),("R","P"),("P","D"),("D","C"),("C","H"),("Base","C")):
        for k in cases():
            a,b=[next(r for r in rows if r["arm"]==v and r["case"]==k) for v in (m,n)]
            both=bool(a["SAFE"] and b["SAFE"])
            pairs.append(dict(case=k,left=m,right=n,left_safe=a["SAFE"],right_safe=b["SAFE"],common=both,
                              energy_delta_J=b["energy_J"]-a["energy_J"] if both else None,
                              first_delta_s=b["first_s"]-a["first_s"] if both else None,final_delta_s=b["final_s"]-a["final_s"] if both else None,
                              distinct_improvement=bool(both and b["hi"]<a["lo"]),same_plan=bool(both and a["plan"]==b["plan"])))
    csvfile("paired",pairs)

if __name__=="__main__":main()
