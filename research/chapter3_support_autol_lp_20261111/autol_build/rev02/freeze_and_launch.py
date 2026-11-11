"""One-time source/input archive and sequential bounded static builds."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,platform,shutil,subprocess,sys,time
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,d):
 with p.open('x',encoding='utf-8') as f:json.dump(d,f,ensure_ascii=False,indent=2,default=str);f.write('\n')
def freeze():
 HERE.mkdir(parents=True,exist_ok=True)
 frozen=HERE/'frozen';frozen.mkdir(exist_ok=False)
 sources=sorted(p for p in (REPO/'research/chapter3_experiments').iterdir() if p.suffix in ['.py','.m','.json'])+[REPO/'research/v1_evaluator/interval.py']
 hashes={}
 for p in sources:
  n=str(p.relative_to(REPO));q=frozen/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);hashes[n]=sha(q)
 src=REPO/'research/chapter3_experiments/results/whole_long_budget01/method'
 origin={}
 for name in ['input_config.json','input_instance.json']:
  p=src/name;shutil.copyfile(p,HERE/name);origin[str(p.relative_to(REPO))]=sha(p)
 sys.path.insert(0,str(frozen/'research/chapter3_experiments'))
 from inputs import build_instance
 from control_policy import resolve_idle_policy
 c=read(HERE/'input_config.json');i=read(HERE/'input_instance.json');assert build_instance(c,'base__R1')==i
 old=REPO/'research/chapter3_support_propagation_20261110/baseline'
 differences={}
 for n in ['input_instance.json','input_config.json']:
  a=read(old/n);b=read(HERE/n);diff=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)];assert diff==['execution_rules'];differences[n]=diff
 assert resolve_idle_policy(i)=='auto_low_immediate_v1'
 plan=dict(created_utc=datetime.now(timezone.utc).isoformat(),scope='Full original R1 auto-L, static model construction/export only, no candidate initialization or solver',frozen_source_sha256=hashes,frozen_input_sha256={n:sha(HERE/n) for n in ['input_config.json','input_instance.json']},origin_sha256=origin,provenance=dict(source_archive='whole_long_budget01',generated_from_current_frozen_inputs_matches_original=True,scene_stage_counts={s['id']:len(s['stage_instances']) for s in i['scenarios']},mode_count=sum(len(v) for v in i['stage_modes'].values()),differences_from_hold_last=differences,physical_values_preserved=True),baseline_flags=dict(fix_late_options=True,aggregate_opp_locks=True,relax_auxiliary_integrality=True,strengthen_energy_lower_bounds=True,prefilter_deadlines=True,cumulative_precedence=False,preeliminate_closed_anchors=False),variants=['off','on'],only_method_switch='propagate_support',seconds_each=300,batch_watchdog_seconds=800,process_watchdog_seconds=380,runner_sha256=sha(HERE/'run_static.py'),launcher_sha256=sha(Path(__file__)),expected_no_new_solver_calls=0,expected_no_initialization_or_candidate_thermal_evaluations=0)
 save(HERE/'plan.json',plan);save(HERE/'plan_identity.json',dict(plan_sha256=sha(HERE/'plan.json'),created_utc=datetime.now(timezone.utc).isoformat()))
 print(json.dumps({'plan_sha256':sha(HERE/'plan.json'),'sources':len(hashes),'provenance':plan['provenance']},ensure_ascii=False,indent=2))
def launch():
 plan=read(HERE/'plan.json');identity=sha(HERE/'plan.json');save(HERE/'launch_claim.json',dict(started_utc=datetime.now(timezone.utc).isoformat(),plan_sha256=identity,one_off_no_retries=True))
 deadline=time.monotonic()+plan['batch_watchdog_seconds'];results=[]
 for v in plan['variants']:
  cmd=[sys.executable,'-B',str(HERE/'run_static.py'),'--variant',v,'--plan-sha256',identity];start=datetime.now(timezone.utc).isoformat();t=time.monotonic()
  with (HERE/f'{v}.stdout.log').open('x') as out,(HERE/f'{v}.stderr.log').open('x') as err:
   try:p=subprocess.run(cmd,cwd=REPO,stdout=out,stderr=err,timeout=min(plan['process_watchdog_seconds'],max(.001,deadline-time.monotonic())));code=p.returncode;error=None
   except subprocess.TimeoutExpired as e:code=None;error=str(e)
  record=dict(variant=v,argv=cmd,cwd=str(REPO),started_utc=start,ended_utc=datetime.now(timezone.utc).isoformat(),wall_s=time.monotonic()-t,returncode=code,watchdog_error=error)
  save(HERE/f'{v}_command.json',record);results.append(record)
  if code!=0:break
 save(HERE/'launch_completion.json',dict(ended_utc=datetime.now(timezone.utc).isoformat(),plan_sha256=identity,results=results,unrun=[v for v in plan['variants'] if v not in [r['variant'] for r in results]]))
 print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':
 if sys.argv[1]=='freeze':freeze()
 elif sys.argv[1]=='launch':launch()
 else:raise ValueError('freeze or launch required')
