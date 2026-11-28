"""Materialize immutable runtime files in a Linux-local scratch area for timed work."""
import os,sys,shutil,subprocess,zipfile
from pathlib import Path
here=Path(__file__).resolve().parent
lab=here.parents[2];temp=Path(os.environ.get("FAST_SCRATCH","/tmp/ch4_inherited_v1"))
for f in sorted((lab/"Inherited_wheels").glob("*.whl")):
    with zipfile.ZipFile(f) as z:z.extractall(temp/"site")
for tree in ("nt","four"):
    shutil.copytree(lab/"U3a_inputs"/tree,temp/tree,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.nbc","*.nbi"))
for name in ("ch3_integrated_quality_v1","ch3_integrated_quality_v2","ch3_integrated_quality_v3","m6a_global_frequency_mapping","u1_unified_diagnostic","u2_adaptive_groups"):
    target=temp/"driver"/name;target.mkdir(parents=True,exist_ok=True)
    for f in (here.parent/name).iterdir():
        if f.suffix in (".py",".cpp"):shutil.copyfile(f,target/f.name)
d=temp/"driver/m6a_global_frequency_mapping"
subprocess.run(["g++","-O3","-std=c++17","-ffp-contract=off","-fPIC","-shared","dp.cpp","-o","dp.so"],cwd=d,check=True)
print(temp,flush=True)
