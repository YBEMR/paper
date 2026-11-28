"""Materialize frozen Python sources on Linux disk and compile the unmodified DP."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
R=Path(os.environ["TRANSFER_ROOT"])
S=Path(os.environ["FAST_SCRATCH"])
start=time.perf_counter()
R.mkdir(parents=True,exist_ok=True)
for name in ("ch3_direct_thermal_final","ch3_center_only","ch3_analytic_quota","ch3_mapping_first_nested","ch3_integrated_quality_v3","ch3_integrated_quality_v2","ch3_integrated_quality_v1","m6a_global_frequency_mapping","u1_unified_diagnostic","u2_adaptive_groups"):
    src=HERE.parent/name
    dest=R/"driver"/name
    dest.mkdir(parents=True,exist_ok=True)
    for path in src.iterdir():
        if path.suffix in (".py",".cpp"):
            shutil.copyfile(path,dest/path.name)
dp=R/"driver/m6a_global_frequency_mapping"
subprocess.run(["g++","-O3","-std=c++17","-ffp-contract=off","-fPIC","-shared","dp.cpp","-o","dp.so"],cwd=dp,check=True)
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
(R/"setup.json").write_text(json.dumps(dict(elapsed_s=time.perf_counter()-start,mode="local frozen objects plus prior pinned physical/runtime dependencies",sources={str(p.relative_to(R/"driver")):h(p) for p in (R/"driver").rglob("*") if p.is_file()})))
