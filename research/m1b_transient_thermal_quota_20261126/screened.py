from base import ROOT,Case,load,save
from search_b import run
from attribution import empty,advance,sets


if __name__=="__main__":
    for label in ("L800","L640","L480","L320"):
        for gen in ("N","H"):
            for rank in ("C","T"):
                run(label,gen,rank,4,4,screened=True)
    c=Case("L800",ROOT/"data/audit")
    history=load(ROOT/"data/diagnostic/cold_w10.json")["reference_actions"]
    parent=empty(c)
    for j,a in enumerate(history[:9]):
        parent=advance(c,parent,j,a)
    out=[]
    for row in load(ROOT/"data/audit/archived_prefix_recall.json"):
        g,n,x,y=row["action"]
        o,ng,hg,_,_=sets(c,parent,9,(g,n),True)
        out.append(dict(action=row["action"],O=(x,y) in o,N=(x,y) in ng,H=(x,y) in hg))
    save(ROOT/"data/audit/screened_prefix_recall.json",out)
