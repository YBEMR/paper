"""Verify one lane and restore all 12 final schedules, certificates and traces offline."""
import gzip
import json
import sys
import tarfile
from pathlib import Path

from lane import CASES, ORDERS, SETTINGS

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"ch3_analytic_quota"))
import analyze as audit


def run(folder, code, source, run_id):
    rows=[]
    host_cores=set()
    request_shas=set()
    for rep in (1,2,3):
        audit.ROOT=folder/f"r{rep}"
        results=audit.ROOT/"paired_results"/code
        expected_order=ORDERS[(CASES.index(code)+rep-1)%4]
        with tarfile.open(audit.ROOT/"final_endpoints.tar.gz","w:gz") as bundle:
            for setting,(arm,budget) in enumerate(SETTINGS):
                cell=results/f"{arm}-{budget}"
                rc=audit.read(cell/"receipt.json")
                assert rc["commit"]==source and str(rc["run"])==run_id
                assert rc["repeat"]==rep and rc["position"]==expected_order.index(setting)+1
                assert audit.lines(cell/"start.jsonl")[0]["core"]==[rc["core"]]
                ids={e["request_sha"] for e in audit.lines(cell/"search.jsonl") if e.get("request_sha")}
                assert len(ids)==1
                request_shas.update(ids)
                host_cores.add((rc["host"],rc["core"]))
                record=audit.cell(code,arm,budget,bundle)
                row=record["row"]
                row.update(setting="ABCD"[setting],repeat=rep,order=rc["position"],request_sha=next(iter(ids)))
                assert not row["plan"] or row["low_J"]<=row["final_J"]<=row["high_J"]
                rows.append(dict(row=row,updates=record["updates"],config=record["config"]))
    assert len(host_cores)==len(request_shas)==1 and len(rows)==12
    assert sum(r["row"]["charged_s"] for r in rows)<=3960
    with gzip.open(folder/"reduced.json.gz","wt",encoding="utf8") as out:
        json.dump(rows,out,separators=(",",":"))


if __name__=="__main__":
    run(Path(sys.argv[1]),sys.argv[2],sys.argv[3],sys.argv[4])
