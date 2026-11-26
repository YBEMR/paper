"""Separate actual W4 path divergence, seat changes, and final physical reconvergence."""
from itertools import combinations
import json
from summarize import DATA,METHODS,rows,write

def main():
    points={(r["case"],r["method"],r["regime"]):r for r in rows(DATA/"checkpoints.csv")}
    changes=[];soft=[]
    for casefolder in sorted((DATA/"pools").glob("V*")):
        case=casefolder.name
        seats=[r for r in rows(casefolder/"seats.csv.gz") if r["scope"]=="actual_pool" and r["policy"] in r["observed_paths"].split("/")]
        active={}
        for m in METHODS[:4]:
            windows={}
            for r in seats:
                if r["policy"]==m:
                    windows.setdefault(int(r["window"]),[]).append(r)
            active[m]={j:[r["id"] for r in sorted(v,key=lambda r:int(r["slot"]))] for j,v in windows.items()}
            if m=="ZQ-Beam":
                for j,rs in windows.items():
                    unsafe=[int(r["slot"]) for r in rs if json.loads(r["risk"])[0]]
                    soft.append(dict(case=case,window=j,retained=len(rs),soft_over80_count=len(unsafe),
                                     slots="/".join(map(str,sorted(unsafe)))))
        for a,b in combinations(METHODS[:4],2):
            left,right=active[a],active[b]
            assert set(left)==set(right)
            first_order=next((j for j in sorted(left) if left[j]!=right[j]),None)
            first_set=next((j for j in sorted(left) if set(left[j])!=set(right[j])),None)
            def same(k):
                x,y=points[case,a,k],points[case,b,k]
                return x["plan"]==y["plan"] if x["plan"] and y["plan"] else None
            changes.append(dict(case=case,left=a,right=b,first_order_divergence=first_order,first_set_divergence=first_set,
                                same_W4_SAFE_plan=same("W4/K4"),same_60s_SAFE_plan=same("60s")))
    write(DATA/"actual_path_divergence.csv",changes);write(DATA/"ZQ_soft_retention.csv",soft)

if __name__=="__main__":
    main()
