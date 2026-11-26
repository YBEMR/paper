"""Publish a case table only after every pre-registered physical cell has a receipt."""
import csv
import sys
from pathlib import Path
from audit_results import ROOT,OUT,checked_problem,verify_final,read


def checkpoint(case):
    rows=[r for r in read(ROOT/"execution_lock.json")["roster"] if r["case"]==case]
    if not rows or any(not (OUT/"cells"/r["id"]/"receipt.json").is_file() for r in rows):
        raise RuntimeError(f"{case} still has unopened or running cells")
    p=checked_problem(case)
    records=[]
    for job in rows:
        f=OUT/"cells"/job["id"]
        receipt=read(f/"receipt.json")
        row=dict(case=case,method=job["method"],mode=job["mode"],seed=job["seed"],budget_s=job["budget_s"],
                 charged_s=receipt["charged_s"],receipt=receipt["status"],actual_status="",SAFE_J="",initial_J="",
                 configuration_J="",post_gain_mJ="",plan="")
        if receipt["status"]=="COMPLETE":
            res=read(f/"result.json")
            row["actual_status"]=res["status"]
            if res["final"]:
                verify_final(f,res,p)
                row["plan"]=res["final"]["plan"]
                if (res["status"]=="SAFE" and res["elapsed_s"]<=job["budget_s"] and
                        res["post"]["elapsed_s"]<=.2*job["budget_s"]):
                    row["SAFE_J"]=res["final"]["J"]
                row["initial_J"]=res["initial"]["J"] if res["initial"] else ""
                row["configuration_J"]=res["configuration"]["J"]
                row["post_gain_mJ"]=1000*(res["configuration"]["J"]-res["selected"]["J"])
        records.append(row)
    out=ROOT/"checkpoints"
    out.mkdir(exist_ok=True)
    with (out/f"{case}.csv").open("w",encoding="utf8",newline="") as stream:
        cw=csv.DictWriter(stream,fieldnames=records[0],lineterminator="\n")
        cw.writeheader()
        cw.writerows(records)
    print(f"{case}: {len(records)} receipts; {sum(r['SAFE_J']!='' for r in records)} eligible SAFE endpoints")


if __name__=="__main__":
    checkpoint(sys.argv[1])
