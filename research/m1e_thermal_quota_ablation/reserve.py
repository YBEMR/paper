"""Reserve new input labels without building pools, certifying, or inspecting outcomes."""
import hashlib
import json
from itertools import combinations
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"
BASE="c33f5bf00fb90059586dc27490d2d9e2a0f41ef5"
RUNNER="c84f278edc624f70a636cfe3ff9ab446e7657125"
SEED="M1-e/c33f5bf0/next-holdout/v1/"

def freeze():
    with (DATA/"decision.json").open() as src:
        if not json.load(src)["freeze_H"]:
            return
    declared={p.stem.split("_",1)[1] for p in (DATA/"validation_inputs").glob("*.csv")}
    assert len(declared)==8
    cases=[]
    for size in (800,640,480,320):
        n=size//80
        options=[]
        for h in combinations(range(n),n//2):
            w="".join("H" if j in h else "L" for j in range(n))
            if w not in declared and 1<sum(x!=y for x,y in zip(w,w[1:]))<n-1:
                options.append(w)
        for first in "LH":
            eligible=[w for w in options if w.startswith(first)]
            if eligible:
                def key(word):
                    return hashlib.sha256((SEED+word).encode()).hexdigest()
                word=min(eligible,key=key)
                cases.append(dict(size=size,order=word,sha256=key(word),eligible=len(eligible)))
    assert len(cases)==6 and not declared.intersection(c["order"] for c in cases)
    algorithm={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in ("sampler.py","experiment.py","PROTOCOL.md")}
    obj=dict(base=BASE,runner=RUNNER,algorithm=algorithm,seed=SEED,orders=cases,methods=["HT","NT","C2","BT"],
             budget="HT W4 K4 elapsed per case, fixed and anytime; BT fixed only",status="reserved_unexecuted",
             L320="No unused balanced nontrivial nonalternating ordering")
    (ROOT/"holdout_freeze.json").write_text(json.dumps(obj,indent=2)+"\n")
if __name__=="__main__":
    freeze()
