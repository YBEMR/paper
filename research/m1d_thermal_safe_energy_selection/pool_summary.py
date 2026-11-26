"""Summaries of partially labeled fixed pools. Unsent candidates stay unknown."""
from collections import Counter
import gzip
import json
from study import CASES,OUT,load,write_rows

def main():
    rows=[]
    for p in sorted((OUT/"terminal").glob("*/*/orders.json")):
        with gzip.open(p.parent/"pool.json.gz","rt") as f:pool=json.load(f)
        tracks=load(p)
        labels={}
        for o in tracks:
            for v in o["records"]:
                prev=labels.setdefault(v["id"],v)
                assert (prev["E"],prev["status"])==(v["E"],v["status"])
        rows.append(dict(case=p.parent.parent.name,pool=p.parent.name,size=len(pool),
                     expected_safe=sum(s["peak"]<=80. for s in pool),actually_tested=len(labels),
                     untested=len(pool)-len(labels),tested_safe=sum(v["status"]=="SAFE" for v in labels.values()),
                     tested_false_safe=sum(v["prediction"]<=80 and v["status"]!="SAFE" for v in labels.values()),
                     tested_false_hot=sum(v["prediction"]>80 and v["status"]=="SAFE" for v in labels.values())))
    write_rows(OUT/"pool_calibration.csv",rows)

if __name__=="__main__":main()
