"""Exact comparison edge cases only; zero thermal or scheduling calls."""
import json
from pathlib import Path
from analyze import comparison
base={'eligible':True,'final_energy':{'lower':'4','upper':'5'},'initial_energy':None,
  'final_candidate_sha256':'r','initial_candidate_sha256':'i'}
def changed(lo,hi):return dict(base,final_energy={'lower':lo,'upper':hi},final_candidate_sha256='x')
cases=[('strict_lower',changed('2','3'),'STRICT_LOWER'),('strict_higher',changed('6','7'),'STRICT_HIGHER'),
  ('touching_intervals',changed('3','4'),'OVERLAP_NO_CERTIFIED_ORDER'),('same_interval',base,'EXACT_SAME_INTERVAL'),
  ('failed_feasibility',dict(base,eligible=False),'FEASIBILITY_ONLY')]
checks=[]
for name,value,expected in cases:
    result=comparison(value,base);assert result['kind']==expected
    if expected=='FEASIBILITY_ONLY':assert 'saving_percent_interval' not in result
    checks.append({'name':name,'passed':True,'result':result})
out={'status':'PASS','check_count':len(checks),'checks':checks,'scientific_calls':0}
Path(__file__).with_name('interval_analysis_checks.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','checks':len(checks),'scientific_calls':0}))
