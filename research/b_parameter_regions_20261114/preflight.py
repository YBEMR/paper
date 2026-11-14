import json,hashlib,math
from pathlib import Path
import numpy as np
from model import catalogue,schedule,evaluate,P
root=Path(__file__).resolve().parent
cfg=json.loads((root/'design.json').read_text())
for file,sha in json.loads((root/'design_freeze.json').read_text())['files'].items():
    assert hashlib.sha256((root/file).read_bytes()).hexdigest()==sha
actions=catalogue()
for scenario in cfg['scenarios']:
    for a in actions:schedule(a,scenario)
nom=next(s for s in cfg['scenarios'] if s['id']==cfg['nominal_id'])
chosen=[a for a in actions if a['id'] in ['B-211-100-on','B-22-11-on','B-1111-0000-on','B-1111-0000-off']]
r=evaluate(nom,[40.,60.],actions=chosen)
old=json.loads((root/'previous_selected_references.json').read_text(encoding='utf-8'))['records']
maxdiff=0.
for ai,a in enumerate(chosen):
    if not a['dpm']:continue
    for ti,temp in enumerate([40.,60.]):
        ref=next(x for x in old if x['id']==a['base_id'] and x['variant']=='full' and x['state']==('cool' if temp==40 else 'warm'))
        for h,key in enumerate(['energy_J','extended_energy_J']):
            maxdiff=max(maxdiff,abs(r['energy'][h,ai,ti]-ref[key]))
assert maxdiff<1e-7,maxdiff
print(json.dumps({'status':'PASS','scheduled_cases':len(cfg['scenarios'])*len(actions),'previous_energy_max_abs_diff_J':maxdiff,'component_balance_J':r['accounting_error_J']}))
(root/'preflight_result.json').write_text(json.dumps({'status':'PASS','previous_energy_max_abs_diff_J':maxdiff},indent=2)+'\n')
