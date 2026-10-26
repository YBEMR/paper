"""Read-only analysis of a completed E1 batch; no physical evaluator imports."""
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RUN=HERE/'results/e1_obj_01'

def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):Path(path).write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def interval(value):
    a,b=map(F,value);assert a<=b;return a,b

def weighted_components(receipt,instance):
    parts={k:[F(0),F(0)] for k in ('baseline','activity','external_common','temperature_correction')}
    for scene in instance['scenarios']:
        for key in parts:
            a,b=interval(receipt['scenes'][scene['id']]['energy_components_J'][key]);w=F(scene['weight'])
            parts[key][0]+=w*a;parts[key][1]+=w*b
    return {k:list(map(str,v)) for k,v in parts.items()}

def stage_rows(receipt):
    return {(sid,r['stage_id']):r for sid,v in receipt['legality']['scenes'].items() for r in v['rows']}

def main():
    batch=read(RUN/'batch_summary.json');assert len(batch['outputs'])==8
    slots=[]
    for ordinal in range(1,5):
        folder=RUN/f'slot_{ordinal}';job=read(folder/'plan/job.json');packet=job['packet'];i=packet['instance']
        plan=read(folder/'plan/accepted_result.json')['result'];post=read(folder/'post/accepted_result.json')['result']
        pp=read(folder/'plan/process.json');ap=read(folder/'post/process.json')
        assert plan['state']=='SAFE' and post['state']=='POST_SAFE'
        assert not plan['stop_required'] and not post['stop_required']
        assert pp['reaped'] and ap['reaped'] and not pp['killed'] and not ap['killed']
        assert pp['method_elapsed_s']<300 and ap['method_elapsed_s']<60
        key=hashlib.sha256(json.dumps(plan['safe_candidate'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        assert key==plan['selected_candidate_sha256']==post['candidate_sha256']
        receipt=post['evaluation'];lo,hi=interval(receipt['weighted_energy_J'])
        a,b=interval(plan['evaluation']['weighted_energy_J']);assert max(a,lo)<=min(b,hi)
        peak=max(F(v[1]) for scene in receipt['scenes'].values() for v in scene['peaks_degC'].values())
        archive=plan['archive'];states=Counter(r['evaluation']['state'] for r in archive['evaluations'])
        slots.append(dict(ordinal=ordinal,problem_id=i['id'],objective=packet['objective'],
            candidate_sha256=key,planning_score_J=plan['planning_score_J'],plan_true_energy_J=plan['evaluation']['weighted_energy_J'],
            post_true_energy_J=receipt['weighted_energy_J'],post_U_J=str(hi),post_U_approx_J=float(hi),
            weighted_components_J=weighted_components(receipt,i),peak_temperature_upper_degC=str(peak),
            plan_method_s=plan['timing']['method_elapsed_s'],plan_process_s=pp['method_elapsed_s'],
            post_method_s=post['timing']['method_elapsed_s'],post_process_s=ap['method_elapsed_s'],
            startup_s=pp['startup_elapsed_s'],first_safe_s=archive['first_safe_at_s'],selected_at_s=plan['selected_at_s'],
            candidate_attempts=archive['candidates'],unique_evaluations=len(archive['evaluations']),cache_hits=archive['cache_hits'],
            candidate_states=dict(states),score_improvements=len(archive['events']),state='POST_SAFE',
            no_global_optimality_proof=True))
    pairs=[]
    for problem in ('base__R1','base__R3'):
        full=next(x for x in slots if x['problem_id']==problem and x['objective']=='FULL')
        omit=next(x for x in slots if x['problem_id']==problem and x['objective']=='OMIT_TEMP')
        f0,f1=interval(full['post_true_energy_J']);o0,o1=interval(omit['post_true_energy_J'])
        delta=[o0-f1,o1-f0];ratios=[d/o*100 for d in delta for o in (o0,o1)]
        fs=stage_rows(read(RUN/f"slot_{full['ordinal']}/post/accepted_result.json")['result']['evaluation'])
        os=stage_rows(read(RUN/f"slot_{omit['ordinal']}/post/accepted_result.json")['result']['evaluation'])
        changes=[]
        for key in sorted(fs):
            differing=[k for k in ('unit','opp','start_ms','end_ms') if fs[key][k]!=os[key][k]]
            if differing:changes.append(dict(scene_id=key[0],stage_id=key[1],differing_fields=differing,
                FULL={k:fs[key][k] for k in ('unit','opp','start_ms','end_ms')},
                OMIT_TEMP={k:os[key][k] for k in ('unit','opp','start_ms','end_ms')}))
        part_deltas={}
        for k in full['weighted_components_J']:
            a,b=interval(full['weighted_components_J'][k]);c,d=interval(omit['weighted_components_J'][k])
            part_deltas[k]=[str(c-b),str(d-a)]
        pairs.append(dict(problem_id=problem,conclusion='FULL_STRICTLY_LOWER' if f1<o0 else
             ('OMIT_STRICTLY_LOWER' if o1<f0 else 'NUMERICALLY_UNRESOLVED'),
             delta_OMIT_minus_FULL_J=list(map(str,delta)),delta_midpoint_microJ=float(sum(delta)/2*1000000),
             relative_percent=[str(min(ratios)),str(max(ratios))],relative_percent_approx=float(sum(delta)/2/((o0+o1)/2)*100),
             same_device_mapping=all(fs[k]['unit']==os[k]['unit'] for k in fs),
             same_OPPs=all(fs[k]['opp']==os[k]['opp'] for k in fs),
             differing_stage_count=len(changes),stage_changes=changes,component_delta_OMIT_minus_FULL_J=part_deltas))
    summary=dict(material_passport=dict(type='code_experiment_result',mode='run',status='COMPLETED_AND_READ_ONLY_AUDITED',
                scope='abstract fixed 4-node H/50/80/auto-L; two inputs; objective ablation'),
        authorization_id=batch['authorization_id'],source_sha=read(RUN/'slot_1/plan/bundle/runtime_manifest.json')['source_sha'],
        planned_plan_calls=4,consumed_plan_calls=4,consumed_post_calls=4,retries=0,
        safe_pairs=2,all_slots_natural_completed=True,batch_wall_s=batch['wall_s'],
        sum_plan_process_s=sum(x['plan_process_s'] for x in slots),sum_post_process_s=sum(x['post_process_s'] for x in slots),
        slots=slots,pairs=pairs,interpretation='strictly distinguishable but tiny model-predicted savings; no significance or global optimum claim')
    save(RUN/'analysis.json',summary)
    fields=['ordinal','problem_id','objective','state','post_U_approx_J','plan_method_s','plan_process_s',
            'post_method_s','post_process_s','startup_s','first_safe_s','selected_at_s','candidate_attempts','unique_evaluations','cache_hits','score_improvements']
    with (RUN/'results.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fields,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(slots)
    all_stages=[]
    for x in slots:
        receipt=read(RUN/f"slot_{x['ordinal']}/post/accepted_result.json")['result']['evaluation']
        for (sid,stage),row in stage_rows(receipt).items():
            all_stages.append(dict(ordinal=x['ordinal'],problem_id=x['problem_id'],objective=x['objective'],scene_id=sid,
                                   stage_id=stage,**{k:row[k] for k in ('unit','opp','start_ms','duration_ms','end_ms')}))
    with (RUN/'schedules.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,list(all_stages[0]),lineterminator='\n');writer.writeheader();writer.writerows(all_stages)
    print(json.dumps({k:summary[k] for k in ('consumed_plan_calls','consumed_post_calls','batch_wall_s','sum_plan_process_s','sum_post_process_s')}))
    for pair in pairs:print(json.dumps({k:pair[k] for k in ('problem_id','conclusion','delta_midpoint_microJ','relative_percent_approx','same_device_mapping','same_OPPs','differing_stage_count')}))

if __name__=='__main__':main()
