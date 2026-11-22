"""Load the common Numba screen specialization once, without any workload or candidate kernel."""
import json
from pathlib import Path
import sys
from time import perf_counter
start=perf_counter()
src=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(src/"research/kim_scene_dvfs_admission"))
import joint_thermal as jt
import numpy as np
a=np.zeros((1,4)); q=np.zeros((1,4,4))
jt._screen(a,np.eye(4),a,a,a,a,q,np.full(4,80.))
print(json.dumps(dict(scope="generic screen specialization, zero candidate kernels",elapsed_s=perf_counter()-start)))
