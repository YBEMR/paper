"""Final archive consistency checks, no scientific trajectories generated."""
import ast,csv,hashlib,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent;O=R/'results';checks=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)})
    if not ok:raise AssertionError(name)
for q in R.glob('*.py'):ast.parse(q.read_text(encoding='utf-8'));check('syntax/'+q.name,True)
for name,sha in json.loads((R/'design_freeze.json').read_text())['files'].items():check('freeze/'+name,hashlib.sha256((R/name).read_bytes()).hexdigest()==sha)
for name,sha in json.loads((O/'run_environment.json').read_text())['files_sha256'].items():check('simulation_identity/'+name,hashlib.sha256((R/name).read_bytes()).hexdigest()==sha)
for row in json.loads((R/'source_manifest.json').read_text()):
    q=R.parent/'throttle_sources'/row['name']
    if q.exists():check('source/'+row['name'],hashlib.sha256(q.read_bytes()).hexdigest()==row['sha256'])
raw=np.load(O/'all_candidate_arrays.npz');case={};count=0
with (O/'all_candidates.csv').open(newline='',encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        count+=1;k=row['scenario']+('_hardware__' if row['hardware_enabled']=='True' else '_no_cap__');i=int(row['sequence_index']);case[k]=case.get(k,0)+1
        if abs(float(row['energy'])-raw[k+'energy'][i])>1e-10 or (row['feasible']=='True')!=raw[k+'feasible'][i]:raise AssertionError('CSV/NPZ mismatch')
check('all_candidates_match_npz',count==61440 and len(case)==15 and all(x==4096 for x in case.values()))
v=json.loads((O/'numerical_validation.json').read_text());check('numerical_validation_status',v['status']=='PASS_NUMERIC_AND_SELECTED_FEASIBILITY_CONVERGENCE' and not v['selected_feasibility_changes'])
st=json.loads((O/'structural_audit.json').read_text());check('strong_simple_equal_every_case',all(abs(r['lookahead_gain_vs_one_switch_pct'])<1e-10 for r in st['rows']) and len(st['rows'])==13)
par=json.loads((R/'parameter_identifiability.json').read_text());check('unknown_stays_null',all(r['value'] is None for r in par if r['status']=='UNKNOWN'))
html=(R/'report.html').read_text(encoding='utf-8');check('selfcontained_images',html.count('src="data:image/png;base64,')==2)
# Create exact row-preserving shards; transport-only transformation after analysis.
dest=O/'candidates';dest.mkdir(exist_ok=True);data=(O/'all_candidates.csv').read_bytes();lines=data.splitlines(keepends=True);header=lines[0];groups=[]
for line in lines[1:]:
    fields=line.split(b',',2);key=fields[0].decode()+('__hardware' if fields[1]==b'True' else '__no_cap')
    if not groups or groups[-1][0]!=key:groups.append((key,[]))
    groups[-1][1].append(line)
items=[];back=[header]
for key,part in groups:
    blob=header+b''.join(part);name=key+'.csv';(dest/name).write_bytes(blob);back.extend(part);items.append({'name':name,'rows':len(part),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
check('shard_exact_reconstruction',b''.join(back)==data and len(groups)==15)
(dest/'index.json').write_text(json.dumps({'total_rows':count,'full_csv_sha256':hashlib.sha256(data).hexdigest(),'files':items},indent=2)+'\n')
check('visual_artifacts_present',all((R/'figures'/f).exists() for f in ['comparison.svg','comparison.png','mechanism.svg','mechanism.png']))
out={'status':'PASS','check_count':len(checks),'checks':checks,'scope':'Archive, frozen identity and output consistency; not hardware calibration or external review.'}
(R/'archive_validation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':out['status'],'check_count':len(checks),'candidate_rows':count,'case_shards':len(items)}))
