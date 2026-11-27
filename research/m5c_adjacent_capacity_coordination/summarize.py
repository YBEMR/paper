"""Publish flat four-way comparisons and reconcile both offline receipts."""
import csv
import json
import sys
import time
from pathlib import Path


def main(archive, supplement):
    start=time.perf_counter()
    load=lambda p:json.loads(p.read_bytes())
    cases=load(archive/"counterfactuals.json")
    with (supplement/"counterfactual_summary.csv").open("w",newline="") as f:
        writer=None
        for x in cases:
            row={k:x[k] for k in ("case","method","turn","front_window","chosen")}
            for key in ("parent","front_only","rear_only","joint"):
                v=x[key]
                row.update({key+"_status":v["status"],key+"_J":v.get("J"),key+"_identity":v.get("plan",v.get("cfg"))})
            for key in ("old_boundary","new_boundary","after_two"):
                for dev,z in zip(("gpu","npu"),x[key]):
                    row[key+"_"+dev+"_ms"]=z["remaining"]/10
            row["rear_alone_improves"]=x["rear_strict"]
            row["joint_beats_rear"]=x["joint_beats_rear"]
            if writer is None:
                writer=csv.DictWriter(f,fieldnames=list(row),lineterminator="\n")
                writer.writeheader()
            writer.writerow(row)
    receipt=load(archive/"receipt.json")
    history=load(supplement/"historical_receipt.json")
    post=receipt["offline_s"]+history["wall_s"]+(time.perf_counter()-start)+2
    total=receipt["formal_s"]+receipt["gate_s"]+post
    assert post<120 and total<1200
    result=dict(gate_upper_core_s=receipt["gate_s"],formal_upper_core_s=receipt["formal_s"],
        frozen_audit_upper_core_s=receipt["offline_s"],historical_index_upper_core_s=history["wall_s"],
        post_total_upper_core_s=post,total_upper_core_s=total,final_table_startup_write_allowance_s=2,
        searched_cells=receipt["cells"],historical_negative_pairs=history["rows"],offline_groups=len(cases))
    (supplement/"final_receipt.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":main(*map(Path,sys.argv[1:3]))
