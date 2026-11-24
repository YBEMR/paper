"""Necessary residency and affine-composition checks; no performance pilot."""
from pathlib import Path
import json
import numpy as np
from model import Instance,Kernel,events
HERE=Path(__file__).resolve().parent
inst=Instance('balanced_forward_reference_start');inst.bind()
a,b=[inst.frozen['deployments'][d]['stages'] for d in ['D038','D040']]
assert all(a[str(i)]==b[str(i)] for i in range(3)) and a['3']!=b['3']
union=sorted({(app,*stage) for stages in [a,b] for app,ss in stages.items() for stage in ss if stage[0].startswith('DLA')})
assert len(union)==4 and sum(r[1]=='DLA0' for r in union)==sum(r[1]=='DLA1' for r in union)==2
# One existing scene is sufficient for a numerical composition unit check.
s=events.time_scene(inst.platform,inst.scenes[0],'D038','LHL');assert s.deadline_feasible
k=Kernel(inst,inst.scenes[0],'D038','LHL','idle_zero',s)
errors=[]
for T in [[30.,30.,30.,30.],[40.,65.,37.,36.]]:
    p,_,_=k.replay(T);e,end=k.affine(T)
    assert abs(e-p['energy_J'])<1e-7 and np.max(np.abs(end-p['final_C']))<1e-7
    errors.append(dict(energy_J=abs(e-p['energy_J']),final_C=float(np.max(np.abs(end-p['final_C'])))))
result=dict(status='PASS',DLA_union=union,per_device=[2,2],only_changed_app=3,
    assumed_gpu_engine_extra_cost='unverified and excluded',affine_errors=errors,
    scope='one fixed-scene correctness unit, not a comparative experiment')
(HERE/'checks.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(result)
