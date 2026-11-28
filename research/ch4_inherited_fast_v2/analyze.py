"""Audit completed receipts and summarize paired elapsed time without re-running a candidate."""
import csv
import gzip
import hashlib
import json
import os
import platform
import resource
import statistics as st
import sys
import tarfile
import time
import zlib
from collections import Counter
from pathlib import Path

from sequence import CASES, FIRST, HERE, recover

PHASES = ("replay","events","identity","checkpoint","integrate","certificate","write")
COMPARE = ("ordinal","stage","detail","plan","status","cert_sha","event_sha","trace_sha","all_kernel_fields_sha",
           "energy_bounds","peak_lo","peak_hi","minimum_lo","minimum_hi","panels","entries")
ARMS = ("full","incremental")


def archived_prefixes(case, sequence):
    """Offline oracle using only the physical-input columns of archived traces."""
    sys.path.insert(0,str(Path(os.environ["FAST_SCRATCH"])/"site"))
    import numpy as np
    folder=FIRST/"results"/case/"physical"
    ix=json.loads((folder/"index.json").read_bytes())
    plans={p:ix["plans"][p] for _,_,p,_ in sequence}
    wanted={b for m in plans.values() for b in m["blocks"]}
    blocks={}
    for name in {ix["blocks"][b] for b in wanted}:
        with tarfile.open(folder/name,"r|") as tar:
            for member in tar:
                role,key=member.name.split("/")
                if role=="blocks" and key in wanted:
                    data=zlib.decompress(tar.extractfile(member).read())
                    assert hashlib.sha256(data).hexdigest()==key
                    blocks[key]=data
    physical={}
    for plan,meta in plans.items():
        data=b"".join(blocks[b] for b in meta["blocks"])
        assert hashlib.sha256(data).hexdigest()==meta["trace_sha"]
        matrix=np.frombuffer(data,np.float64).reshape(meta["shape"])
        physical[plan]=np.ascontiguousarray(matrix[:,:14]).view("V112").reshape(-1)
    def common(a,b):
        n=min(len(a),len(b))
        mismatch=np.flatnonzero(a[:n]!=b[:n])
        return int(mismatch[0]) if len(mismatch) else n
    return [[common(physical[p],physical[q]) for _,_,q,_ in sequence[:i]] for i,(_,_,p,_) in enumerate(sequence)]


def csv_file(path, rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def verify_sources(scratch):
    manifest=json.loads((FIRST/"sources.json").read_bytes())
    counts={}
    for role, prefix in (("search","nt"),("registration","nt"),("physical","four"),("driver","driver")):
        count=0
        for name, expected in manifest[role]["files"].items():
            if role=="driver":
                name=name.removeprefix("research/")
                if Path(name).suffix not in (".py",".cpp"):
                    continue
            p=scratch/prefix/name
            assert p.is_file(),p
            data=p.read_bytes()
            blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            assert blob == expected,p
            count+=1
        counts[role]=count
    return counts


def main():
    root=Path(os.environ["FIXED_RUN"])
    budget=json.loads((root/"budget.json").read_bytes())
    assert budget["state"]=="complete"
    out=HERE/"results"
    out.mkdir(exist_ok=True)
    assert (out/"summary.json").exists() is False, "Refusing to replace a complete decision archive"
    material=[]
    paired=[]
    by_case=[]
    status=Counter()
    total=Counter()
    stages={a:Counter() for a in ARMS}
    sizes={a:[] for a in ARMS}
    resident={a:[] for a in ARMS}
    sources=verify_sources(Path(os.environ["FAST_SCRATCH"]))
    for case in CASES:
        sequence,_,truth=recover(case)
        oracle=archived_prefixes(case,sequence)
        improvements=[]
        elapsed=Counter()
        for rep in range(1,4):
            trials={m:json.loads((root/"receipts"/f"{case}-{rep}-{m}.json").read_bytes()) for m in ARMS}
            full, inc=(trials[m]["rows"] for m in ARMS)
            assert len(sequence)==len(full)==len(inc)
            for j,(a,b) in enumerate(zip(full,inc)):
                assert all(a[field]==b[field] for field in COMPARE)
                assert a["plan"]==sequence[j][2] and a["cert_sha"]==truth[a["plan"]]["certificate"]
                if rep==1:
                    status[case,a["stage"],a["status"]]+=1
                if b["source_ordinal"] is not None:
                    assert 0<=b["source_ordinal"]<j
                    assert oracle[j][b["source_ordinal"]]==b["reused"]
                assert max(oracle[j],default=0)==b["reused"]
                for item in (a,b):
                    assert abs(sum(item[p] for p in PHASES)-item["elapsed"])<1e-7
            row=dict(case=case,rep=rep)
            row["order"]="full/incremental" if (CASES.index(case)+rep)%2 else "incremental/full"
            for m in ARMS:
                trial=trials[m]
                material.append(trial)
                rs=trial["rows"]
                overhead=trial["setup"]+trial["release"]
                duration=sum(x["elapsed"] for x in rs)+overhead
                row[m+"_s"]=duration
                elapsed[m]+=duration
                total[m]+=duration
                for p in PHASES:
                    stages[m][p]+=sum(x[p] for x in rs)
                stages[m]["checkpoint"]+=overhead
                sizes[m].append(trial["cache_bytes"])
                resident[m].append(trial["maxrss_KiB"])
            row["saved_s"]=row["full_s"]-row["incremental_s"]
            row["saved_pct"]=100*row["saved_s"]/row["full_s"]
            improvements.append(row["saved_s"])
            paired.append(row)
        first=inc
        by_case.append(dict(case=case,candidates=len(sequence),full_s=elapsed["full"],incremental_s=elapsed["incremental"],
                     net_pct=100*(1-elapsed["incremental"]/elapsed["full"]),median_paired_saved_s=st.median(improvements),
                     improved_pairs=sum(x>0 for x in improvements),total_events=sum(x["entries"] for x in first),
                     reused_events=sum(x["reused"] for x in first),
                     hit_candidates=sum(x["reused"]>0 for x in first),max_cache_bytes=max(x["cache_bytes"] for x in first)))
    assert len(material)==24 and len(paired)==12
    receipts=json.dumps(material,separators=(",",":"),sort_keys=True,allow_nan=False).encode()
    (out/"candidate_receipts.json.gz").write_bytes(gzip.compress(receipts,6,mtime=0))
    assert gzip.decompress((out/"candidate_receipts.json.gz").read_bytes())==receipts
    csv_file(out/"pairs.csv",paired)
    csv_file(out/"flows.csv",by_case)
    csv_file(out/"components.csv",[dict(method=m,**stages[m]) for m in ARMS])
    gain=100*(1-total["incremental"]/total["full"])
    improved=sum(c["median_paired_saved_s"]>0 for c in by_case)
    for arm in ARMS:
        assert abs(sum(stages[arm].values())-total[arm])<1e-6
    budget["analysis_cpu_s"]=time.process_time()
    budget["total_with_analysis_s"]=budget["charged"]+budget["analysis_cpu_s"]
    assert budget["total_with_analysis_s"]<budget["limit"]
    resource_info=dict(os=platform.platform(),python=platform.python_version(),
                       cpu=material[0]["cpu"],assigned_cpu=[material[0]["cpu"]])
    summary=dict(candidates=sum(x["candidates"] for x in by_case),certifications=sum(len(x["rows"]) for x in material),
                 total=dict(total),net_gain_pct=gain,positive_flows=improved,
                 eligible=gain>=10 and improved>=3,all_fields_agree=True,
                 cache_peak_bytes={m:max(v) for m,v in sizes.items()},
                 max_peak_RSS_KiB={m:max(v) for m,v in resident.items()},
                 median_peak_RSS_KiB={m:st.median(v) for m,v in resident.items()},
                 counts={"/".join(k):v for k,v in status.items()},source_blobs=sources,
                 environment=resource_info,budget=budget)
    write_json(out/"summary.json",summary)
    print(json.dumps(summary))


if __name__=="__main__":
    main()
