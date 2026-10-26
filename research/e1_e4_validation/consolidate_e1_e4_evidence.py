"""Consolidate saved E1-E4 evidence using stdlib only; no scientific calls.
Run from any directory. Only two evidence/consolidation_e1_e4 JSONs are written.
"""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OUT=HERE/'evidence/consolidation_e1_e4'
SPECS=(
 ('E1','e1_obj_01','e1_process_precheck01'),
 ('E2','e2_res_01','e2_resource_precheck01'),
 ('E3','e3_deploy_01','e3_deployment_precheck01'),
 ('E4a','e4_dead_01','e4_deadline_precheck01'),
 ('E4b','e4_req_01','e4_requests_precheck01'),
 ('E4b-DF','e4_df_01','e4_deadline_fallback_precheck02'))
def read(p):return json.loads(p.read_bytes())
def packed(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(x):return hashlib.sha256(packed(x)).hexdigest()
def save(p,x):p.write_bytes((json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def effect(before,after):
 a,b=map(F,before);c,d=map(F,after);delta=(a-d,b-c)
 percentages=[x/y*100 for x in delta for y in (a,b)]
 return dict(delta_J=list(map(str,delta)),percent=list(map(str,(min(percentages),max(percentages)))),percent_approx=float((min(percentages)+max(percentages))/2))
def main():
 OUT.mkdir(exist_ok=True,parents=True)
 checks=[];files={};batches=[];platforms=set();all_states=Counter()
 def check(value,label):
  checks.append(label)
  if not value:raise AssertionError(label)
 def source(p):
  rel=p.relative_to(REPO).as_posix();files[rel]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
  return read(p)
 for label,run_name,pre_name in SPECS:
  run=HERE/'results'/run_name;auth=source(HERE/'authorizations'/(run_name+'.json'))
  manifest=source(HERE/'evidence'/pre_name/'frozen_real_manifest.json')
  batch=source(run/'batch_summary.json');analysis=source(run/('readonly_analysis.json' if label=='E4b-DF' else 'analysis.json'))
  check(sha(manifest)==auth['scope_sha256'],label+':manifest authorization')
  check(analysis['source_sha']==manifest['source_sha']==auth['source_sha'],label+':source SHA')
  authority=HERE/'authority'/sha({'authorization_id':auth['authorization_id']})
  ab=source(authority/'batch.json');check(ab['authorization_sha256']==sha(auth),label+':one-use identity')
  claims=[source(p) for p in sorted(authority.glob('*_claim.json'))]
  counts=Counter(x['phase'] for x in claims);check(counts['PLAN']==analysis['consumed_plan_calls'] and counts['POST']==analysis['consumed_post_calls'],label+':actual claims')
  check(batch['retries']==analysis['retries']==0,label+':no retry')
  # The historical E1 freeze predates the explicit supervision object. Its
  # immutable E1 protocol declares the original 1800-second batch cap.
  supervision=manifest.get('supervision',{'batch_wall_s':1800} if label=='E1' else {})
  check(batch['wall_s']<=supervision['batch_wall_s'],label+':batch wall')
  slots=[]
  for n,(pid,objective) in enumerate(manifest['slots'],1):
   job=source(run/f'slot_{n}/plan/job.json');record=source(run/f'slot_{n}/plan/accepted_result.json');plan=record['result'];i=job['packet']['instance']
   check(i['id']==pid and job['packet']['objective']==objective,label+':slot '+str(n))
   check(sha(i)==manifest['inputs'][pid]['input_sha256'],label+':frozen instance '+str(n))
   check(plan.get('stop_required') is False and record['process']['method_elapsed_s']<300,label+':plan timely/no fault '+str(n))
   platforms.add(sha(i['platform']))
   evaluations=plan['archive']['evaluations'];all_states.update(e['evaluation']['state'] for e in evaluations)
   matching=next(x for x in analysis['slots'] if x['ordinal']==n)
   check(matching['unique_evaluations']==len(evaluations),label+':evaluation count '+str(n))
   postpath=run/f'slot_{n}/post/accepted_result.json';final=None
   if postpath.exists():
    post_record=source(postpath);post=post_record['result'];receipt=source(run/f'slot_{n}/post/post_receipt.json')['receipt']
    check(post['state']=='POST_SAFE' and post.get('stop_required') is False,label+':post safe '+str(n))
    check(post_record['process']['method_elapsed_s']<60,label+':post timely '+str(n))
    check(post['candidate_sha256']==sha(plan['safe_candidate'])==plan['selected_candidate_sha256'],label+':selected identity '+str(n))
    check(post['evaluation']==receipt and receipt['evidence_identity']['input_sha256']==sha(i),label+':raw post '+str(n))
    check(receipt['weighted_energy_J']==matching['post_true_energy_J'],label+':reported real energy '+str(n));final=receipt
   else:check(plan['state']=='UNRESOLVED' and not evaluations,label+':missing means no candidate '+str(n))
   denom=sum((F(s['weight'])*len(s['requests']) for s in i['scenarios']),F(0))
   peak=max((F(v[1]) for s in final['scenes'].values() for v in s['peaks_degC'].values()),default=None) if final else None
   slacks=[F(req['deadline_ms'])-F(final['legality']['scenes'][scene['id']]['request_completion_ms'][req['id']]) for scene in i['scenarios'] for req in scene['requests']] if final else []
   if final:check(min(slacks)>=0,label+':per request deadline '+str(n))
   slots.append(dict(ordinal=n,problem_id=pid,objective=objective,method_policy=job.get('method_policy','ORIGINAL_ADAPTED_HEFT'),
    final_state='POST_SAFE' if final else plan['state'],energy_J=final['weighted_energy_J'] if final else None,
    energy_U_J_approx=float(F(final['weighted_energy_J'][1])) if final else None,weighted_request_count=str(denom),
    per_request_energy_J=[str(F(v)/denom) for v in final['weighted_energy_J']] if final else None,
    peak_upper_degC_approx=float(peak) if peak is not None else None,min_deadline_slack_ms=str(min(slacks)) if slacks else None,
    first_safe_s=plan['archive'].get('first_safe_at_s'),plan_process_s=record['process']['method_elapsed_s'],
    post_process_s=post_record['process']['method_elapsed_s'] if final else None,
    candidate_evaluations=len(evaluations),candidate_states=dict(Counter(e['evaluation']['state'] for e in evaluations)),
    candidate_sha256=plan.get('selected_candidate_sha256'),scientific_packet_sha256=sha(job['packet'])))
  batches.append(dict(experiment=label,run=run_name,source_sha=manifest['source_sha'],manifest_sha256=sha(manifest),
   authorization_id=auth['authorization_id'],manifest_path=('evidence/'+pre_name+'/frozen_real_manifest.json'),
   analysis_path=('results/'+run_name+'/'+('readonly_analysis.json' if label=='E4b-DF' else 'analysis.json')),
   planned_plan_calls=auth['budgets']['plan_calls'],actual_plan_calls=counts['PLAN'],actual_post_calls=counts['POST'],
   batch_wall_s=batch['wall_s'],candidate_evaluations=sum(s['candidate_evaluations'] for s in slots),slots=slots))
 check(len(platforms)==1,'same physical platform across all 17 plans')
 check(all_states=={'SAFE':589},'589 saved planning thermal receipts all SAFE')
 effects={
  'E1_R1_OMIT_minus_FULL':effect(batches[0]['slots'][1]['energy_J'],batches[0]['slots'][0]['energy_J']),
  'E1_R3_OMIT_minus_FULL':effect(batches[0]['slots'][2]['energy_J'],batches[0]['slots'][3]['energy_J']),
  'E2_CPU_vs_expanded':[effect(batches[1]['slots'][0]['energy_J'],s['energy_J']) for s in batches[1]['slots'][1:]],
  'E3_saved_intervals_identical':batches[2]['slots'][0]['energy_J']==batches[2]['slots'][1]['energy_J'],
  'E4a_beta1_vs_beta1_6':effect(batches[3]['slots'][0]['energy_J'],batches[3]['slots'][2]['energy_J']),
  'E4b_same_method_scale_curve_available':False,
  'E4b_DF_energy_comparison_available':False}
 totals=dict(plans=sum(b['actual_plan_calls'] for b in batches),posts=sum(b['actual_post_calls'] for b in batches),
  final_post_safe_slots=sum(s['final_state']=='POST_SAFE' for b in batches for s in b['slots']),
  unresolved_slots=sum(s['final_state']=='UNRESOLVED' for b in batches for s in b['slots']),
  saved_planning_candidate_evaluations=sum(all_states.values()),saved_post_evaluations=sum(b['actual_post_calls'] for b in batches),
  sum_separate_batch_wall_s=sum(b['batch_wall_s'] for b in batches))
 check((totals['plans'],totals['posts'],totals['final_post_safe_slots'],totals['unresolved_slots'])==(17,15,15,2),'complete scope totals')
 out=dict(schema='E1_E4_WRITING_EVIDENCE_INDEX_V1',baseline_commit='8088f66ca9a499f3d63ea21add4f71847f6029e1',
  interpretation='saved abstract-simulation evidence; no rerun, no global optimality or algorithm ranking',
  totals=totals,batches=batches,effects=effects,source_files=files,new_research_calls=0,new_thermal_evaluations=0,new_real_SAFE=0)
 save(OUT/'evidence_index.json',out)
 save(OUT/'checks.json',dict(passed=True,checks=len(checks),labels=checks,all_source_hashes_rechecked=all(hashlib.sha256((REPO/p).read_bytes()).hexdigest()==v['sha256'] for p,v in files.items()),new_research_calls=0,new_real_SAFE=0))
 print(json.dumps(dict(checks=len(checks),**totals),ensure_ascii=False))
if __name__=='__main__':main()
