"""One-shot bounded posterior review of exactly the frozen nine configurations."""
from datetime import datetime,timezone
from fractions import Fraction as F
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[4]
sys.path[:0]=[str(OUT),str(REPO/'research/chapter3_experiments')]
from periodic_core import review_configuration

def read(path):return json.loads(path.read_text())
def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(plan,approved):
    if sha(OUT/'plan.json')!=approved or read(OUT/'plan_identity.json')['sha256']!=approved:raise ValueError('PLAN_SHA_DRIFT')
    for name,value in plan['code_sha256'].items():
        if sha(REPO/name)!=value:raise ValueError('SOURCE_DRIFT:'+name)
    for name,value in plan['frozen_files_sha256'].items():
        if sha(OUT/name)!=value:raise ValueError('FROZEN_INPUT_DRIFT:'+name)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--approved-plan-sha256',required=True);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if not args.execute:raise ValueError('EXPLICIT_EXECUTION_FLAG_REQUIRED')
    plan=read(OUT/'plan.json');verify(plan,args.approved_plan_sha256);output=args.output.resolve();output.relative_to(OUT);output.mkdir(parents=True,exist_ok=False)
    config=read(OUT/'frozen/input_config.json');instance=read(OUT/'frozen/input_instance.json');start=time.monotonic();started=datetime.now(timezone.utc).isoformat();results=[];fatal=None
    save(output/'started.json',{'utc':started,'argv':sys.argv,'cwd':str(REPO),'plan_sha256':args.approved_plan_sha256,'scope':'Exactly frozen nine fixed schedules/scenes/periods, no search'})
    for slot in plan['slots']:
        verify(plan,args.approved_plan_sha256)
        if time.monotonic()-start+plan['bounds']['seconds_per_configuration']>plan['bounds']['total_seconds']:
            fatal='INSUFFICIENT_FULL_NEXT_SLOT_BUDGET';break
        folder=output/slot['id'];folder.mkdir();entered=time.monotonic();utc=datetime.now(timezone.utc).isoformat();spec=read(OUT/'frozen'/(slot['id']+'.json'));calls=[];returned=None;error=None
        try:
            import thermal
            budget=thermal.Budget(seconds=plan['bounds']['seconds_per_configuration'],panels=plan['bounds']['panels_per_configuration'],refinements=plan['bounds']['refinements_per_configuration']);budget.start=entered
            selected=next(s for s in instance['scenarios'] if s['id']==slot['scene_id'])
            with (folder/'calls.jsonl').open('x') as journal:
                def evaluate(entry,label):
                    budget.check()
                    if len(calls)>=plan['bounds']['max_original_kernel_calls_per_configuration']:raise ValueError('FROZEN_CALL_COUNT_EXHAUSTED')
                    number=len(calls)+1;candidate={'ordinal':number,'label':label,'entry_degC':list(map(str,entry)),'started_elapsed_s':budget.elapsed};calls.append(candidate);journal.write(json.dumps({'event':'START',**candidate})+'\n');journal.flush()
                    receipt=thermal.evaluate_piecewise(instance['platform'],entry,selected['maximum_temperature_degC'],spec['segments'],slot['period_ms'],config['accuracy_targets'],budget,scene_id=slot['scene_id'])
                    save(folder/f'receipt_{number:03d}.json',receipt);candidate.update(state=receipt['state'],reason=receipt['reason'],complete=receipt['complete'],returned_elapsed_s=budget.elapsed,receipt_file=f'receipt_{number:03d}.json')
                    journal.write(json.dumps({'event':'RETURN',**candidate})+'\n');journal.flush();return receipt
                evaluate.segments=spec['segments']
                returned=review_configuration(config,instance,read(OUT/'frozen'/(slot['template'].replace(' ','_')+'_candidate.json')),slot['scene_id'],slot['period_ms'],evaluate,max_rounds=plan['bounds']['max_startup_rounds'])
        except BaseException as failure:
            error={'type':type(failure).__name__,'reason':str(failure),'traceback':traceback.format_exc()}
        record={'slot':slot,'started_utc':utc,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-entered,'classification':returned['classification'] if returned else 'UNRESOLVED','result':returned,'error':error,'actual_original_kernel_calls':len(calls),'calls':calls,'new_scheduling_search_calls':0}
        save(folder/'result.json',record);results.append(record);print({'id':slot['id'],'state':record['classification'],'calls':len(calls),'seconds':record['wall_s'],'error':error and error['reason']},flush=True)
    verify(plan,args.approved_plan_sha256)
    summary={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-start,'plan_sha256':args.approved_plan_sha256,'planned_configurations':9,'processed_configurations':len(results),'fatal':fatal,'completed_all_nine':len(results)==9 and fatal is None,'results':results,'actual_original_kernel_calls':sum(r['actual_original_kernel_calls'] for r in results),'new_scheduling_search_calls':0,'independent_certificate':False}
    save(output/'summary.json',summary)
    differences=[]
    for row in results:
        spec=read(OUT/'frozen'/(row['slot']['id']+'.json'));old=spec['reference_CSV_row'];r=row['result'];entry={'slot':row['slot'],'old_CSV':old,'new_classification':row['classification'],'same_classification':row['classification']==old['classification'],'new_result_available':r is not None}
        if r:
            rounding=F(1,1000000)
            entry['steady_peak_enclosure_overlaps_old_reported_interval_with_1e_6_rounding']=max(F(r['periodic_peak_degC'][0]),F(old['periodic_peak_lower_degC'])-rounding)<=min(F(r['periodic_peak_degC'][1]),F(old['periodic_peak_upper_degC'])+rounding)
            entry['steady_peak_upper_difference_degC']=str(F(r['periodic_peak_degC'][1])-F(old['periodic_peak_upper_degC']))
            entry['first_energy_upper_difference_J']=str(F(r['first_round']['energy_J'][1])-F(old['first_energy_J']))
            entry['periodic_energy_upper_difference_J']=str(F(r['periodic_bounds']['energy_J'][1])-F(old['periodic_energy_J_diagnostic_if_unsafe']))
            entry['all_rounds_upper_comparison_role']='Both may be conservative bounds; different safe bounds need not be equal and are not actual trajectory maxima.'
            entry['new_first_unsafe_round_if_certified']=r['first_unsafe_round'];entry['old_first_unsafe_round']=old['first_unsafe_round']
            entry['new_witness']=r['violation_witness']
        differences.append(entry)
    save(output/'comparison_to_original_CSV.json',differences)

if __name__=='__main__':main()
