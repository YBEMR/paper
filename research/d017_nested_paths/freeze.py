"""Freeze read-only dependencies and new executable/configuration inputs."""
from common import *
files=set()
for name in ["kim_synthetic_platform_v1","kim_thermal_v1","kim_multidnn_expansion"]:
    p=ROOT/"research"/name
    files.update(p.glob("*.py"))
files.update([ROOT/"research/kim_synthetic_platform_v1/platform.json",
    ROOT/"research/kim_synthetic_platform_v1/experiments.json",
    ROOT/"research/kim_case_b_freeze/input.json",
    ROOT/"research/kim_multidnn_expansion/expanded_input.json",
    ROOT/"research/multidnn_model_review/protocol.json",
    ROOT/"research/multidnn_model_review/inputs/cases/balanced_forward_preheated.json"])
files.update(HERE.glob("*.py"))
files.update(HERE/n for n in ["config.json","inputs.json","path_audit.json","stage_profiles.csv","checks.json","PROTOCOL.md"])
save(HERE/"execution_manifest.json",{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)})
print(len(files))
