"""Exactly ten bounded original-kernel calls for additional figure points."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

OUT=Path(__file__).resolve().parent;REPO=OUT.parents[5]
sys.path[:0]=[str(OUT),str(REPO/'research/chapter3_experiments')]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def verify(plan,identity):
    if sha(OUT/'plan.json')!=identity or read(OUT/'plan_identity.json')['sha256']!=identity:raise ValueError('FIGURE_PLAN_CHANGED')
    for name,value in plan['source_sha256'].items():
        if sha(REPO/name)!=value:raise ValueError('FIGURE_SOURCE_CHANGED:'+name)
    for name,value in plan['code_sha256'].items():
        if sha(OUT/name)!=value:raise ValueError('FIGURE_CODE_CHANGED:'+name)
    for name,value in plan['frozen_sha256'].items():
        if sha(OUT/'frozen'/name)!=value:raise ValueError('FIGURE_FROZEN_DATA_CHANGED:'+name)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--approved-plan-sha256',required=True);args=parser.parse_args();plan=read(OUT/'plan.json');verify(plan,args.approved_plan_sha256)
    result_dir=OUT/'point_run01';result_dir.mkdir(exist_ok=False);config=read(OUT/'frozen/input_config.json');instance=read(OUT/'frozen/input_instance.json');began=time.monotonic();started=datetime.now(timezone.utc).isoformat();results=[];fatal=None
    save(result_dir/'started.json',{'utc':started,'argv':sys.argv,'cwd':str(REPO),'plan_sha256':args.approved_plan_sha256})
    for case in plan['cases']:
        verify(plan,args.approved_plan_sha256)
        if time.monotonic()-began+case['seconds']>plan['limits']['total_seconds']:fatal='INSUFFICIENT_NEXT_CALL_BUDGET';break
        start=time.monotonic();utc=datetime.now(timezone.utc).isoformat();raw=None;error=None
        try:
            import thermal
            from fractions import Fraction as F
            budget=thermal.Budget(seconds=case['seconds'],panels=plan['limits']['panels_each'],refinements=plan['limits']['refinements_each']);budget.start=start
            power=read(OUT/'frozen'/case['power_file'])
            raw=thermal.evaluate_piecewise(instance['platform'],case['entry_degC'],case['limits_degC'],power['fine_segments'],case['window_ms'],config['accuracy_targets'],budget,scene_id='AB_offset_0ms')
            save(result_dir/(case['id']+'_receipt.json'),raw)
            if not raw['complete'] or F(raw['covered_until_s'])!=F(case['window_ms'])/1000:raise ValueError('PLOT_TRAJECTORY_INCOMPLETE')
            if len(raw['trace'])+1>case['maximum_trace_points_including_initial']:raise ValueError('PLOT_POINT_CAP_EXCEEDED')
            lower,upper=map(F,instance['platform']['power_model_temperature_range_degC'])
            if any(F(raw['minimum_degC'][node][0])<lower or F(raw['peaks_degC'][node][1])>upper for node in instance['platform']['node_order']):raise ValueError('PLOT_TRAJECTORY_OUTSIDE_DECLARED_MODEL')
        except BaseException as failure:error={'type':type(failure).__name__,'reason':str(failure),'traceback':traceback.format_exc()}
        result={'case':case,'started_utc':utc,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-start,'error':error,'raw_receipt_state':raw.get('state') if raw else None,'complete':bool(raw and raw.get('complete')),'raw_trace_vector_points':len(raw.get('trace',[]))+1 if raw else 0,'original_kernel_calls':1,'new_search_calls':0}
        save(result_dir/(case['id']+'_return.json'),result);results.append(result);print({k:result[k] for k in ('wall_s','raw_receipt_state','complete','error')},case['id'],flush=True)
        if error:fatal=error['reason'];break
    verify(plan,args.approved_plan_sha256)
    summary={'started_utc':started,'ended_utc':datetime.now(timezone.utc).isoformat(),'wall_s':time.monotonic()-began,'planned_original_kernel_calls':10,'actual_original_kernel_calls':len(results),'complete_all_calls':len(results)==10 and not fatal,'fatal':fatal,'results':results,'new_scheduling_search_calls':0,'independent_safety_certificate':False}
    save(result_dir/'summary.json',summary)
    if not summary['complete_all_calls']:raise SystemExit(1)

if __name__=='__main__':main()
