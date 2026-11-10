"""Freeze the nine authorized posterior configurations, without heat calls."""
import csv
from datetime import datetime,timezone
from fractions import Fraction as F
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[4]
sys.path[:0]=[str(REPO/'research/chapter3_experiments'),str(OUT)]
from periodic_core import clip_period,contraction
from schedules import validate_schedule

SOURCE='4339bdcc7dc6d37adf42963ed731f78d5f8ff63e';CSV_COMMIT='92cd9f1702d96d4606bdacc921ff5d1fe4769c67'
ROOT='research/chapter3_experiments/results/chapter3_closure_execution01/slots/'
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def original(relative):
    data=(REPO/relative).read_bytes();frozen=subprocess.check_output(['git','show',SOURCE+':'+relative],cwd=REPO)
    if data!=frozen:raise ValueError('SOURCE_COMMIT_BYTES_DIFFER:'+relative)
    return json.loads(data),{'path':relative,'source_commit':SOURCE,'sha256':hashlib.sha256(data).hexdigest()}

def main():
    target=OUT/'frozen';target.mkdir(exist_ok=False)
    milp,mi=original(ROOT+'t50_milp__method/worker/method/result.json');heft,hi=original(ROOT+'t50_heft__method/worker/method/result.json')
    raw,ri=original(ROOT+'t50_milp__method/worker/raw_result.json');config,ci=original(ROOT+'t50_milp__method/worker/method/input_config.json');instance,ii=original(ROOT+'t50_milp__method/worker/method/input_instance.json')
    assert instance['window_ms']=='400' and F(instance['settings']['deadline_beta'])==1
    assert sum(len(s['stage_instances']) for s in instance['scenarios'])==6
    assert all(s['entry']['temperature_degC']==['50']*4 and s['maximum_temperature_degC']==['80']*4 for s in instance['scenarios'])
    templates={'All-H initial':raw['initialisation']['witness']['candidate'],'Enhanced HEFT final':heft['safe_candidate'],'MILP final':milp['safe_candidate']}
    expected={'All-H initial':'c212a952205da85d4dc001846a2e699dd8953ad7f27e5cf361cca3e06904b126','Enhanced HEFT final':'58e9d4498725e4910ea9c852e30ca6212d8d4a9f2bdebf5add6295e9098b6531','MILP final':'bbbdf365f297c88e40cdc9f2f77b83c30500990884c8489c0b1ca9aa9370bac1'}
    legality={}
    for name,candidate in templates.items():
        assert digest(candidate)==expected[name],name
        checked=validate_schedule(instance,candidate);assert checked['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED';legality[name]=checked
        save(target/(name.replace(' ','_')+'_candidate.json'),candidate)
    save(target/'input_config.json',config);save(target/'input_instance.json',instance)
    csv_path='research/chapter3_experiments/results/periodic_thermal_discussion_20261109/periodic_thermal_results.csv'
    csv_bytes=subprocess.check_output(['git','show',CSV_COMMIT+':'+csv_path],cwd=REPO);(target/'original_periodic_thermal_results.csv').write_bytes(csv_bytes)
    old=list(csv.DictReader(io.StringIO(csv_bytes.decode())));slots=[]
    wanted=[(name,scene,'90') for name in templates for scene in ('AB','AC')]+[('All-H initial','AB',period) for period in ('75','80','85')]
    for ordinal,(name,short,period) in enumerate(wanted,1):
        sid=short+'_offset_0ms';s=legality[name]['scenes'][sid];makespan=max(F(row['end_ms']) for row in s['rows']);segments=clip_period(s['segments'],period,makespan)
        matching=[r for r in old if r['stage_executions']=='6' and F(r['deadline_beta'])==1 and r['template']==name and r['scene']==short and r['period_ms']==period]
        assert len(matching)==1 and F(matching[0]['makespan_ms'])==makespan
        slot={'id':f'{ordinal:02d}_{name.replace(" ","_")}_{short}_P{period}','template':name,'scene_id':sid,'scene_short':short,'period_ms':period,'makespan_ms':str(makespan),'candidate_sha256':expected[name],
            'segments':segments,'contraction':contraction(instance['platform'],segments,period),'reference_CSV_row':matching[0]}
        save(target/(slot['id']+'.json'),slot);slots.append({k:slot[k] for k in ('id','template','scene_id','period_ms','makespan_ms','candidate_sha256')})
    code_paths=[Path(__file__),OUT/'periodic_core.py',OUT/'run_C.py',OUT/'test_periodic.py',*[REPO/p for p in ('research/chapter3_experiments/thermal.py','research/chapter3_experiments/schedules.py','research/chapter3_experiments/control_policy.py','research/chapter3_experiments/start_domain.py','research/v1_evaluator/interval.py')]]
    code={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths}
    tests=json.loads((OUT/'artificial_checks.json').read_text());assert tests['passed'] and tests['real_workload_heat_calls']==0
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),'purpose':'C_FIXED_TEMPLATE_POSTERIOR_PERIODIC_REVIEW','source_commit':SOURCE,'CSV_source_commit':CSV_COMMIT,'current_HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        'slots':slots,'bounds':{'configurations':9,'seconds_per_configuration':180,'total_seconds':1800,'max_startup_rounds':128,'max_original_kernel_calls_per_configuration':259,'max_original_kernel_calls_total':2331,'panels_per_configuration':100000,'refinements_per_configuration':20000},
        'execution_gate':'Requires root agent start instruction after A delivery and plan review; no real heat calls made during preparation. CLI requires exact approved plan SHA256; no plan edits/retries/other configurations.',
        'original_window_semantics':'Original input400ms, schedules/deadlines/frequencies validated intact. Period diagnostic clips only idle tail atP after makespan<=P; original input remains400ms. Each scene repeats independently; no cross-scene concatenation.',
        'method':'Float only suggests4D fixed point. Original interval one-cycle residual plus exactR/(1-q) box; all period paths/means/energy bounded by original lower/upper-start propagation. Startup inherits endpoint boxes. Tail upper=steady peak upper+farthest infinity box distance after N checked rounds; model-range lower also bounded. Never report conservative all-round upper as actual peak.',
        'status_semantics':'Only low-start path point lower>80 after both paths certify model range proves actual overheat. SAFE_ALL_ROUNDS needs safe checked prefix and certified infinite tail within20..100 and<=80. Unresolved/cutoff retained without repair or retry. Unsafe periodic energy diagnostic only.',
        'sources':[mi,hi,ri,ci,ii],'template_sha256':expected,'input_sha256':digest(instance),'config_sha256':digest(config),'CSV_sha256':hashlib.sha256(csv_bytes).hexdigest(),'code_sha256':code,
        'frozen_files_sha256':{p.relative_to(OUT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()},'artificial_test_count':tests['tests_run'],'real_workload_heat_calls_so_far':0,'scheduling_search_calls':0,'independent_numerical_certificate':False}
    save(OUT/'plan.json',plan);identity=hashlib.sha256((OUT/'plan.json').read_bytes()).hexdigest();save(OUT/'plan_identity.json',{'sha256':identity,'utc':datetime.now(timezone.utc).isoformat()});print({'plan_sha256':identity,'configurations':len(slots),'codes':len(code),'real_heat_calls':0},flush=True)

if __name__=='__main__':main()
