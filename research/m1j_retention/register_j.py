import json
from pathlib import Path
from paths_j import ROOT,I,REG,REPO,BASE,METHODS,inputs,sha,write_csv,write_json

def main():
    cases=inputs()
    write_json(REG/"cases.json",cases)
    rotation=[]
    for c in cases:
        for rep in range(3):
            k=(c["index"]+rep)%4
            for n,m in enumerate(METHODS[k:]+METHODS[:k]):
                rotation.append(dict(case=c["case"],repeat=rep+1,position=n+1,lane=c["index"]%6,method=m))
    write_csv(REG/"rotation.csv",rotation)
    old=json.loads((I/"registration/source_hashes.json").read_bytes())
    # All frozen computational modules and physical tables from the inherited manifest.
    hashes={p:h for p,h in old.items() if p.endswith(".py") or "/frozen/" in p or "/inputs/" in p}
    for p,h in hashes.items():assert sha((REPO/p).read_bytes())==h,p
    files=[ROOT/p for p in ("retention.py","batch_j.py","paths_j.py","register_j.py","PROTOCOL.md","registration/rotation.csv","registration/cases.json")]
    files+=[I/"registration/inputs"/r["input"] for r in cases]
    for p in files:hashes[str(p.relative_to(REPO))]=sha(p.read_bytes())
    write_json(REG/"hashes.json",hashes)
if __name__=="__main__":main()
