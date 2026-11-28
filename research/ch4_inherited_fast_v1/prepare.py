"""Materialize immutable runtime files in a Linux-local scratch area for timed work."""
import json,os,shutil,subprocess,zipfile
from hashlib import sha1
from pathlib import Path
here=Path(__file__).resolve().parent
lab=here.parents[2];temp=Path(os.environ.get("FAST_SCRATCH","/tmp/ch4_inherited_v1"))
for f in sorted((lab/"Inherited_wheels312").glob("*.whl")):
    with zipfile.ZipFile(f) as z:z.extractall(temp/"site")
# A fresh checkout can materialize the identical small input tree from Git.
sources = json.loads((here/"sources.json").read_bytes())
for tree, roles in (("nt", ("search","registration")), ("four", ("physical",))):
    cached = lab/"U3a_inputs"/tree
    if cached.is_dir():
        shutil.copytree(cached,temp/tree,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.nbc","*.nbi"))
    for role in roles:
        for name, blob in sources[role]["files"].items():
            path = temp/tree/name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                data = subprocess.check_output(["git","-C",str(here),"cat-file","blob",blob])
                path.write_bytes(data)
            data = path.read_bytes()
            assert sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest() == blob
for name in ("ch3_integrated_quality_v1","ch3_integrated_quality_v2","ch3_integrated_quality_v3","m6a_global_frequency_mapping","u1_unified_diagnostic","u2_adaptive_groups"):
    target=temp/"driver"/name;target.mkdir(parents=True,exist_ok=True)
    for f in (here.parent/name).iterdir():
        if f.suffix in (".py",".cpp"):shutil.copyfile(f,target/f.name)
d=temp/"driver/m6a_global_frequency_mapping"
subprocess.run(["g++","-O3","-std=c++17","-ffp-contract=off","-fPIC","-shared","dp.cpp","-o","dp.so"],cwd=d,check=True)
print(temp,flush=True)
