"""Rebuild the four exact winning cuts using the unchanged synthetic graph validator."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT/"research/ch3_cooperative_cuts"), str(ROOT/"research/ch3_final_experiments/p2")]
from catalog_ext import make_domain


def main():
    domain = make_domain(ROOT)
    import catalog
    stages = domain.stages("X4139374")
    rows = []
    for idx, end in enumerate([42,22,24,12]):
        app = str(idx)
        chain = stages[app]
        ops, heads, kinds = catalog.graph(app)
        handoff, = catalog.check_chain(app,chain)
        if chain[0] != ["DLA0" if idx==0 else "DLA1",0,end] or chain[1] != ["GPU",end+1,len(ops)-1]:
            raise ValueError("Unexpected winning deployment")
        entry = catalog.PLATFORM["architecture_reference"]["graphs"][app]
        rows.append(dict(app=idx, network=catalog.BASE["applications"][idx]["network"],
                         prefix=chain[0],suffix=chain[1],graph=entry["source"],graph_blob=entry["blob"],
                         prefix_operations=dict(Counter(kinds[:end+1])),following_op=kinds[end+1],
                         live_tensors={j:ops[j].shape for j in handoff["live_layers"]},handoff_bytes=handoff["bytes"],
                         prefix_mac=sum(o.mac for o in ops[:end+1]),abstract_check="passed",
                         matched_FP16_weights="unverified",target_build="unverified",
                         device_placement="unverified",output_equivalence="unverified"))
    target=HERE/"tables"
    target.mkdir(exist_ok=True)
    with (target/"cut_audit.csv").open("w",encoding="utf8",newline="") as f:
        out=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n");out.writeheader()
        out.writerows([{k:json.dumps(v,separators=(",",":")) if isinstance(v,(dict,list)) else v
                        for k,v in row.items()} for row in rows])


if __name__=="__main__":
    main()
