"""Audit the saved K194 enumeration, no thermal integration or search call."""
from collections import Counter
from decimal import Decimal, localcontext
from fractions import Fraction as Q
from hashlib import sha256
from pathlib import Path
import argparse
import json
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRODUCTION=ROOT/'research/chapter3_experiments'
sys.path[:0]=[str(PRODUCTION/'small_exact_execution'),str(PRODUCTION/'small_exact_preparation'),str(PRODUCTION)]
import contract
from admission import admit,scene_view
from run_once import reference_data,canonical


def load(name): return json.loads((HERE/name).read_bytes())


def decimal(value):
    q=Q(value)
    with localcontext() as context:
        context.prec=55
        return str(Decimal(q.numerator)/Decimal(q.denominator))


def analyze():
    started=time.monotonic()
    terminal,supervisor,declaration=map(load,['terminal.json','supervisor_terminal.json','declaration.json'])
    if declaration['fixture_only']:
        raise ValueError('Cannot use fixture as scientific result')
    assert supervisor['worker_exited'] and supervisor['calendar_elapsed_s']<=2700
    assert supervisor['state']=='WORKER_EXITED' and supervisor['returncode']==0
    assert not supervisor['retry'] and not terminal['whole_MILP_started']
    identities={k:sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in declaration['source_sha256'].items()}
    assert all(identities.values())
    manifest=[json.loads(line) for line in (HERE/'scene_manifest.jsonl').read_bytes().splitlines()]
    assert sha256((HERE/'scene_manifest.jsonl').read_bytes()).hexdigest()==declaration['manifest_sha256']
    assert len(manifest)==1550 and len({r['id'] for r in manifest})==1550
    assert [r['ordinal'] for r in manifest]==list(range(1,1551))
    for row in manifest:
        assert sha256(canonical(row['candidate']).encode()).hexdigest()==row['id']
    for name,key in [('input_instance.json','input_sha256'),('input_config.json','config_sha256')]:
        assert sha256((HERE/name).read_bytes()).hexdigest()==declaration[key]
    instance=load('input_instance.json')
    records=load('coverage_records.json')
    reference=load('reference.json')
    claim=load('method.claim.json')
    assert claim['root_deadline']==claim['root_start']+2400
    declaration_hash=sha256((HERE/'declaration.json').read_bytes()).hexdigest()
    assert claim['declaration_sha256']==declaration_hash
    events=[json.loads(line) for line in (HERE/'ledger.jsonl').read_bytes().splitlines()]
    starts=[e for e in events if e['event']=='CALL_STARTED']
    finishes=[e for e in events if e['event']=='CALL_FINISHED']
    assert len(starts)==terminal['calls_started']
    assert [e['id'] for e in starts]==[r['id'] for r in manifest[:len(starts)]]
    assert len({e['id'] for e in finishes})==len(finishes)
    assert len({e['id'] for e in starts})==len(starts)
    assert {e['id'] for e in finishes}=={key for key,value in records.items() if value['state']!='NOT_STARTED'}
    started_by_id={event['id']:event for event in starts}
    by_id={r['id']:r for r in manifest}
    view_hashes={s['id']:sha256(canonical(scene_view(instance,s['id'])).encode()).hexdigest() for s in instance['scenarios']}
    times=[]
    peak_max={sid:Q(0) for sid in view_hashes}
    width_max=Q(0)
    group_totals=Counter()
    panels=refinements=0
    late_outer=0
    for event in finishes:
        raw_path=HERE/event['raw_file']
        admission_path=HERE/event['admission_file']
        assert sha256(raw_path.read_bytes()).hexdigest()==event['raw_sha256']
        assert sha256(admission_path.read_bytes()).hexdigest()==event['admission_sha256']
        saved=json.loads(raw_path.read_bytes())
        admission=json.loads(admission_path.read_bytes())
        request=saved['request']
        assert all(started_by_id[event['id']][key]==value and event[key]==value for key,value in request.items())
        row=by_id[event['id']]
        assert request['candidate_sha256']==row['id']
        assert request['full_input_sha256']==declaration['input_sha256']
        assert request['declaration_sha256']==declaration_hash
        assert request['scene_view_sha256']==view_hashes[row['scene_id']]
        assert request['root_deadline']==claim['root_deadline']
        assert claim['root_start']<=request['call_start']<claim['root_deadline']
        assert request['call_deadline']==min(request['call_start']+10,claim['root_deadline'])
        replay=admit(instance,row,saved['raw_receipt'],request['call_start'],request['call_deadline'],request['root_deadline'],declaration['accuracy'])
        assert replay==admission==records[row['id']]
        times.append(event['call_return_s'])
        group_totals[(row['scene_id'],row['shared_A_device'],admission['state'])]+=1
        raw=saved['raw_receipt']
        panels+=raw.get('panels',0);refinements+=raw.get('refinements',0)
        if admission['state']=='SAFE':
            width_max=max(width_max,Q(admission['energy_J'][1])-Q(admission['energy_J'][0]))
            if raw['state']!='SAFE':late_outer+=1
        for sid,scene in raw.get('scenes',{}).items():
            for peak in scene.get('peaks_degC',{}).values():
                peak_max[sid]=max(peak_max[sid],Q(peak[1]))
    assert set(records)==set(by_id)
    assert Counter(r['state'] for r in records.values())==Counter({k:v for k,v in terminal['counts'].items() if v})
    rebuilt=reference_data(manifest,records,instance)
    for key in ['state','lower_bound_J','upper_bound_J','gap_J','groups','chosen_scene_ids','complete_SAFE_candidate','complete_SAFE_energy_J']:
        assert rebuilt[key]==reference[key],key
    assert reference['formed_before_root_deadline']==(reference['formed_root_elapsed_s']<2400)
    accepted=(not declaration['fixture_only'] and len(starts)==1550 and terminal['reason'] is None
        and reference['formed_before_root_deadline'] and rebuilt['state']=='FINITE_DOMAIN_EPSILON_OPTIMAL'
        and all(row['state'] in {'SAFE','VIOLATION'} for row in records.values()))
    assert accepted==reference['formal_reference_accepted']==terminal['formal_reference_accepted']
    result={'state':'SAVED_ENUMERATION_AUDIT_PASS','analysis_only_no_new_physics':True,
        'elapsed_s':time.monotonic()-started,'manifest_entries':1550,
        'calls_started':len(starts),'finished_receipts':len(finishes),'receipt_admission_replays_matching':len(finishes),
        'counts':terminal['counts'],'source_hashes_checked':len(identities),'source_hashes_match':True,
        'root_elapsed_s':terminal['root_elapsed_s'],'calendar_elapsed_s':supervisor['calendar_elapsed_s'],
        'worker_exited':True,'timing':{'sum_scene_call_return_s':sum(times),
            'minimum_scene_call_s':min(times) if times else None,
            'maximum_scene_call_s':max(times) if times else None,
            'mean_scene_call_s':sum(times)/len(times) if times else None,
            'scope':'call start through return, including the started-ledger write; aggregation/IO/imports remain in root total'},
        'peak_upper_max_degC':{sid:decimal(v) for sid,v in peak_max.items()},
        'panels':panels,'refinements':refinements,'outer_not_SAFE_but_timely_inner_SAFE_count':late_outer,
        'largest_SAFE_energy_interval_width_J':str(width_max),
        'reference':{'state':reference['state'],'lower_bound_J':reference['lower_bound_J'],
            'upper_bound_J':reference['upper_bound_J'],'lower_decimal_J':decimal(reference['lower_bound_J']) if reference['lower_bound_J']!='+infinity' else None,
            'upper_decimal_J':decimal(reference['upper_bound_J']) if reference['upper_bound_J']!='+infinity' else None,
            'gap_J':reference['gap_J'],'gap_decimal_J':decimal(reference['gap_J']) if reference['gap_J'] is not None else None,
            'epsilon_J':'0.000001','formed_root_elapsed_s':reference['formed_root_elapsed_s'],
            'formal_reference_accepted':reference['formal_reference_accepted'],
            'unique_optimum_proven':False,'chosen_scene_ids':reference['chosen_scene_ids'],
            'shared_A_device':reference.get('shared_A_device')},
        'group_results':[{'scene_id':sid,'shared_A_device':unit,'state':state,'count':count}
            for (sid,unit,state),count in sorted(group_totals.items())],
        'new_thermal_integrations_in_analysis':0,'new_optimization_calls':0,'MATLAB_starts':0,
        'whole_MILP_started':False}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    result=analyze()
    if args.out:
        with args.out.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
    else: print(json.dumps(result,ensure_ascii=False,indent=2))
