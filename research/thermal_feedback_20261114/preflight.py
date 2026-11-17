import hashlib,json
from pathlib import Path
import numpy as np
from model import P,ALL_SEQUENCES,simulate,constants
ROOT=Path(__file__).resolve().parent;checks=[]
def check(name,condition):checks.append({'name':name,'passed':bool(condition)});assert condition,name
for name,sha in json.loads((ROOT/'design_freeze.json').read_text())['files'].items():check('freeze/'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha)
check('catalogue_unique',len(np.unique(ALL_SEQUENCES,axis=0))==4096)
for s in P['scenarios']:
    C,K,F=constants(s,.02);check('passive_stability/'+s['id'],np.linalg.eigvalsh(K).min()>0)
nom=P['scenarios'][0]
a=simulate(nom,[[0,0,0]],stop_at=.1,prefix=False)
check('low_frequency_work_integral',abs(a['unfinished_work'][0]-(3*sum(P['work'])-.05))<1e-9)
check('fixed_work_count',a['completed'][0]==0)
b=simulate(nom,[[3,3,3]],stop_at=.1,prefix=False)
check('switch_stall_then_high_frequency_work',abs(b['unfinished_work'][0]-(3*sum(P['work'])-.08))<1e-9)
check('switch_once',b['frequency_changes'][0].tolist()==[1,0])
check('components',np.max(abs(b['components'].sum(axis=1)-b['energy']))<1e-10)
check('no_spurious_initial_trip',not a['hw_entries'].any() and not b['hw_entries'].any())
result={'status':'PASS_PRE_SCAN','checks':checks,'note':'Only two 0.1-unit dry trajectories; no parameter tuning or full-catalogue pilot.'}
(ROOT/'preflight_result.json').write_text(json.dumps(result,indent=2)+'\n');print({'status':result['status'],'checks':len(checks)})
