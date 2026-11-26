from base import Case,ROOT,load,save
from diagnose import OUT,probe

if __name__=="__main__":
    c=Case("L800",OUT)
    source=load(OUT/"cold_w10.json")
    witness=min((w for w in source["witnesses"] if w["status"]=="SAFE"),key=lambda w:w["E_J"])
    rows=[]
    for j in (7,8):
        path=OUT/f"recovered_w{j+1}.json"
        rows.append(load(path) if path.exists() else probe(c,"recovered","D2",2,j,witness))
    save(OUT/"recovered_summary.json",rows)
