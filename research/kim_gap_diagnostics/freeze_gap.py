"""Freeze old dependencies, original source archives, declared input and execution adapter bytes."""
from common import ROOT,HERE,HISTORY,read,save,sha
sources=read(ROOT/"research/ch3_joint_repair/inputs.json")
sources.update(read(ROOT/"research/ch3_energy_repair/frozen_inputs.json"))
pinned=read(ROOT/"research/kim_pressure_feasibility/execution_freeze.json")
sources.update({p:h for p,h in pinned["sha256"].items() if "/raw" not in p and p.endswith((".json",".py"))})
for name in ["loads.py","config.json","kim_anytime.py","tables/runs.csv","archives/manifest.json"]:
    p=HISTORY/name;sources[p.relative_to(ROOT).as_posix()]=sha(p)
for p in list((HISTORY/"streams").glob("*.json"))+list((HISTORY/"archives").glob("*.tar")):
    sources[p.relative_to(ROOT).as_posix()]=sha(p)
for relative in ["research/ch3_cooperative_cuts/physical.py","research/ch3_cooperative_cuts/catalog_ext.py",
                 "research/kim_multidnn_search_trial/solver.py"]:
    sources[relative]=sha(ROOT/relative)
assert not (HERE/"raw").exists(),"Do not refreeze after experimentation"
for p in HERE.rglob("*"):
    if p.is_file() and p.name!="execution_manifest.json" and "__pycache__" not in p.parts:
        sources[p.relative_to(ROOT).as_posix()]=sha(p)
for name,value in sources.items():assert sha(ROOT/name)==value,name
save(HERE/"execution_manifest.json",dict(sorted(sources.items())))
print(len(sources),"source/input/archive files frozen")
