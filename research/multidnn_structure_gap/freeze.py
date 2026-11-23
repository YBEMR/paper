"""Freeze input/model/source bytes before the single formal batch."""
from pathlib import Path
from hashlib import sha256
import json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(p):return sha256(p.read_bytes()).hexdigest()
sources=json.loads((HERE/"frozen_old_sources.json").read_bytes())
for relative in [
 "research/multidnn_algorithm_comparison/common.py",
 "research/ch3_cooperative_cuts/physical.py","research/ch3_cooperative_cuts/catalog_ext.py",
 "research/ch3_final_experiments/p2/search.py","research/ch3_algorithm_selection/kim_anytime.py",
 "research/multidnn_diagnostics/instance.py","research/multidnn_model_review/verify_inputs.py",
 "research/multidnn_model_review/input_manifest.json","research/multidnn_model_review/frozen_sources.json"]:
    sources[relative]=sha(ROOT/relative)
files=[p for p in HERE.rglob("*") if p.is_file() and p.name!="execution_manifest.json" and "__pycache__" not in p.parts]
for p in files:sources[p.relative_to(ROOT).as_posix()]=sha(p)
for name,expected in sources.items():assert sha(ROOT/name)==expected,name
(HERE/"execution_manifest.json").write_bytes((json.dumps(dict(sorted(sources.items())),indent=2)+"\n").encode())
print(len(sources),"frozen source/input files")
