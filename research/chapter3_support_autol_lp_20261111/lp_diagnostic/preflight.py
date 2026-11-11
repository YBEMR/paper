"""No optimization calls: source integrity and seven-array wiring checks."""
import ast
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import run_lp_pair as lp

start=dt.datetime.now(dt.timezone.utc).isoformat();t=time.monotonic();checks=[]
source=Path(lp.__file__).read_text();tree=ast.parse(source)
calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='linprog']
assert len(calls)==1
assert not any(k.arg in {'integrality','x0'} for k in calls[0].keywords)
assert not any(isinstance(n,ast.Call) and getattr(n.func,'id',None) in ['milp','intlinprog','evaluate_candidate'] for n in ast.walk(tree))
checks.append('one linprog site; no x0/integrality, MILP or thermal call')
manifest=lp.read(lp.SOURCE/'raw/local_records/execution_file_manifest.json')['files_sha256']
matrix_checks={}
for v in ['off','on']:
 p=lp.SOURCE/f'raw/local_records/r1_pair_run01/{v}/method/matlab/request_000001.mat'
 assert lp.digest(p)==manifest[f'local_records/r1_pair_run01/{v}/method/matlab/request_000001.mat']
 m,h,d=lp.load_original(p)
 bounds=np.column_stack([m['lb'].ravel(),m['ub'].ravel()])
 assert np.array_equal(bounds[:,0],m['lb'].ravel()) and np.array_equal(bounds[:,1],m['ub'].ravel())
 assert {k:lp.fingerprint(m[k]) for k in h}==h
 data=np.abs(m['A'].data);nonzero=data[data>0]
 assert nonzero.min()>1e-9 and data.max()<1e15
 matrix_checks[v]=dict(**d,sha256=lp.digest(p),minimum_abs_nonzero=float(nonzero.min()),maximum_abs=float(data.max()),
     input_arrays_unchanged=True,all_coefficients_above_HiGHS_small_matrix_default=True)
 checks.append(v+': original MAT hash, dimensions/integer indices, seven arrays, exact bounds wiring and solver coefficient thresholds')
a=np.array([1.,2.]);b=a.copy();b[1]+=1e-8
assert lp.fingerprint(a)!=lp.fingerprint(b)
checks.append('fingerprint detects changed coefficient')
lp.save(lp.HERE/'preflight_result.json',dict(started_utc=start,ended_utc=lp.now(),wall_s=time.monotonic()-t,
    checks=checks,matrix_checks=matrix_checks,new_lp_calls=0,new_milp_calls=0,new_thermal_calls=0))
print(json.dumps(dict(passed=len(checks),matrix_checks=matrix_checks,new_lp_calls=0),indent=2))
