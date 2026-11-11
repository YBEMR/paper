"""Synthetic row-template checks only; no scheduling or physical evaluation."""
from datetime import datetime, timezone
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO/'research/chapter3_experiments'))
import milp
import joint_state_support
import thermal
from thermal import I, Budget

start = time.monotonic(); started = datetime.now(timezone.utc).isoformat()
case = {'id':'pure-template-smoke','platform':{'node_order':['n'],'domains':{}}}
model = milp.Model(case, Budget(10)); model.preprocessing={'joint_state_pruning':{}}
sources = [model.var('theta',-5,55),model.var('q',0,2)]
target=model.var('next_theta',-5,55); energy=model.var('energy',0,1)


class Coeff:
    def get(self,state,duration):
        return {'temperature':[[I('.9'),I('.1'),I('.2')]],
                'energy':[I('.01'),I('.2'),I('.1')]}


model.coefficients=Coeff()
audit=lambda states:milp._audit_joint_state_gate_off(model,sources,[target],energy,states,F(1,1000))
a=audit([('H',),('M',)])
assert a['rows_checked']==8 and a['cache_snapshot']['misses']==1 and a['cache_snapshot']['hits']==1
assert a['cache_snapshot']['strict_rows_evaluated']==4
milp._clear_joint_state_gate_audit_cache(model)
b=audit([('H',)])
assert b['cache_snapshot']['misses']==2
# Same-valued context clone changes the actual kernel object while thermal.UP
# deliberately remains the old alias; certification must be re-executed.
old=thermal._kernel.UP
try:
    thermal._kernel.UP=old.copy()
    c=audit([('H',)])
    assert c['cache_snapshot']['misses']==3
    assert c['cache_snapshot']['identity_invalidations']==1
finally:
    thermal._kernel.UP=old
try:
    with patch.object(joint_state_support,'verify_gate_off_rows',
                      side_effect=ValueError('deliberate strict audit failure')):
        audit([('H',)])
except ValueError as error:
    assert str(error)=='deliberate strict audit failure'
else:
    raise AssertionError('patched verifier was bypassed')

result=dict(started_utc=started, ended_utc=datetime.now(timezone.utc).isoformat(),
    wall_s=time.monotonic()-start, passed=True, full_R1_builds=0,
    scheduling_model_builds=0, candidate_thermal_calls=0, solver_calls=0,
    checks=['strict miss then same-template hit','explicit clear recertifies',
            'kernel-only context rebinding with stale alias invalidates',
            'runtime verifier replacement propagates strict failure'],
    milp_sha256=hashlib.sha256(Path(milp.__file__).read_bytes()).hexdigest())
with (HERE/'pure_smoke_rev2.json').open('x') as stream:
    json.dump(result,stream,indent=2)
print(json.dumps(result,indent=2))
