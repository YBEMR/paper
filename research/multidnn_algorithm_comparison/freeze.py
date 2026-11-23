"""Freeze exact runnable sources/inputs; never invoked by a search process."""
import json
from common import ROOT,HERE,sha,encoded
sources=json.loads((ROOT/"research/multidnn_model_review/frozen_sources.json").read_bytes())["sha256"]
sources.update({("research/multidnn_model_review/"+name):value for name,value in
    json.loads((ROOT/"research/multidnn_model_review/input_manifest.json").read_bytes()).items()})
names=[
 "research/multidnn_model_review/input_manifest.json","research/multidnn_model_review/frozen_sources.json",
 "research/multidnn_model_review/verify_inputs.py","research/multidnn_diagnostics/instance.py",
 "research/ch3_energy_repair/optimizer.py","research/ch3_energy_repair/config.json",
 "research/ch3_cooperative_cuts/physical.py","research/ch3_cooperative_cuts/catalog_ext.py",
 "research/ch3_algorithm_selection/kim_anytime.py","research/ch3_final_experiments/p2/search.py"]
names += ["research/multidnn_algorithm_comparison/"+n for n in
          ("common.py","run.py","protocol.json","PROTOCOL.md","regression.py","regression.json","freeze.py","formal_experiment_config.csv")]
for name in names:
    sources[name]=sha(ROOT/name)
for name,expected in sources.items():
    assert sha(ROOT/name)==expected,name
(HERE/"execution_manifest.json").write_bytes(encoded(dict(sorted(sources.items())))+b"\n")
print(len(sources),"frozen files")
