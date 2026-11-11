"""Independent exhaustive finite structural-schedule oracle; no thermal/model imports."""
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
from itertools import combinations, product
import json
from pathlib import Path
import platform
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
START = time.monotonic()
DEADLINE = START + 60

def now(): return datetime.now(timezone.utc).isoformat()
def digest(data): return hashlib.sha256(data).hexdigest()
def save(name, value):
    with (HERE/name).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')
def check_time():
    if time.monotonic() > DEADLINE: raise TimeoutError('Frozen 60s suite wall budget exhausted')

def instance(groups, edges=()):
    scenes={}
    for sid,stage,shared in groups:
        scenes.setdefault(sid,{'id':sid,'stage_instances':[],'dependencies':[]})['stage_instances'].append({'id':stage,'shared_stage_id':shared})
    for sid,a,b in edges: scenes[sid]['dependencies'].append([a,b])
    return {'id':'finite-structural-unit-catalogue','scenarios':list(scenes.values()),
            'fixture_constraints':{'window_ms':'40','cpu_shared_frequency_units':['CPU1','CPU2']}}

def opt(oid,sid,stage,unit,start,end,opp='H'):
    return dict(option_id=oid,scenario_id=sid,stage_instance_id=stage,unit_id=unit,
                start_ms=str(start),end_ms=str(end),opp_id=opp)

def legal_reason(case, chosen):
    """Independent full structural predicate; deliberately does not call support helpers."""
    selected={(r['scenario_id'],r['stage_instance_id']):r for r in chosen}
    deployment={}
    for sc in case['scenarios']:
        sid=sc['id']
        for st in sc['stage_instances']:
            row=selected[(sid,st['id'])]
            lo,hi=Fraction(row['start_ms']),Fraction(row['end_ms'])
            if lo<0 or hi<=lo or hi>Fraction(case['fixture_constraints']['window_ms']): return 'window_or_duration'
            shared=st['shared_stage_id']
            if shared in deployment and deployment[shared]!=row['unit_id']: return 'shared_mapping'
            deployment[shared]=row['unit_id']
        for a,b in sc['dependencies']:
            if Fraction(selected[sid,a]['end_ms'])>Fraction(selected[sid,b]['start_ms']): return 'dependency'
        rows=[selected[sid,st['id']] for st in sc['stage_instances']]
        for a,b in combinations(rows,2):
            overlap=max(Fraction(a['start_ms']),Fraction(b['start_ms']))<min(Fraction(a['end_ms']),Fraction(b['end_ms']))
            if not overlap: continue
            if a['unit_id']==b['unit_id']: return 'resource_overlap'
            if a['unit_id'] in ['CPU1','CPU2'] and b['unit_id'] in ['CPU1','CPU2'] and a['opp_id']!=b['opp_id']:
                return 'shared_cpu_frequency'
    return None

def enumerate_all(case, options):
    groups=[(s['id'],t['id']) for s in case['scenarios'] for t in s['stage_instances']]
    choices=[[o for o in options if (o['scenario_id'],o['stage_instance_id'])==g] for g in groups]
    count=1
    for c in choices: count*=len(c)
    if count>512: raise AssertionError('Frozen per-case Cartesian cap exceeded')
    all_records=[]; valid=[]
    for chosen in product(*choices):
        check_time()
        identity=tuple(o['option_id'] for o in chosen)
        reason=legal_reason(case,chosen)
        all_records.append({'option_ids':identity,'legal':reason is None,'rejection_reason':reason})
        if reason is None: valid.append(identity)
    return all_records,sorted(valid)

def fixtures():
    equality=(instance([('a','p','P'),('a','q','Q')],[('a','p','q')]),[
        opt('p0','a','p','CPU1',0,'3/2'),opt('plate','a','p','CPU1',5,'13/2'),
        opt('qearly','a','q','NPU0',0,1),opt('qeq','a','q','NPU0','3/2','5/2'),opt('qlate','a','q','NPU0',5,6)])
    interaction=(instance([('a','s','S'),('a','t','T'),('b','s','S'),('b','v','V')],[('a','s','t'),('b','s','v')]),[
        opt('a1','a','s','CPU1',0,2),opt('a2','a','s','CPU2',0,7),opt('at','a','t','NPU0',2,3),
        opt('b1','b','s','CPU1',10,12),opt('b2','b','s','CPU2',0,7),opt('bv7','b','v','GPU0',7,8),opt('bv12','b','v','GPU0',12,13)])
    shared=(instance([('a','s','S'),('b','s','S')]),[
        opt('aH','a','s','CPU1',0,'3/2','H'),opt('aM','a','s','CPU1',5,'13/2','M'),opt('a2','a','s','CPU2',0,2),
        opt('bM','b','s','CPU1',0,2,'M'),opt('bH','b','s','CPU1',15,17,'H')])
    parallel=(instance([('a','p','P'),('a','q','Q')]),[
        opt('pH','a','p','CPU1',0,2,'H'),opt('pM','a','p','CPU1',0,2,'M'),opt('pGPU','a','p','GPU0',0,2),
        opt('qH','a','q','CPU2',0,2,'H'),opt('qM','a','q','CPU2',0,2,'M'),opt('qTouch','a','q','CPU1',2,3,'H')])
    cases=[('equality_fraction',*equality),('interaction_multiround',*interaction),('shared_device_distinct_mode_start',*shared),('parallel_resources_cpu_domain',*parallel),
        ('empty_domain',instance([('a','p','P'),('a','q','Q'),('b','q','Q')],[('a','p','q')]),[opt('p','a','p','CPU1',0,1),opt('bq','b','q','CPU1',0,1)]),
        ('no_common_device',instance([('a','s','S'),('b','s','S')]),[opt('a','a','s','CPU1',0,1),opt('b','b','s','CPU2',0,1)]),
        ('nonempty_but_resource_infeasible',instance([('a','p','P'),('a','q','Q')]),[opt('p','a','p','CPU1',0,2),opt('q','a','q','CPU1',0,2)]),
        ('scenarios_independent_frequency',instance([('a','s','S'),('b','s','S')]),[opt('a','a','s','CPU1',0,2,'H'),opt('b','b','s','CPU1',0,2,'M')]),
        ('same_scene_shared_device_distinct_start',instance([('a','s1','S'),('a','s2','S')]),[opt('a1','a','s1','CPU1',0,1),opt('a2','a','s1','CPU2',0,1),opt('b','a','s2','CPU1',5,7,'M')]),
        ('five_ms_start_fractional_end',instance([('a','p','P'),('a','q','Q')],[('a','p','q')]),[
            opt('pfrac','a','p','CPU1',0,'9/2','M'),opt('peq','a','p','CPU1',0,5,'H'),
            opt('q5','a','q','NPU0',5,'13/2'),opt('q0','a','q','NPU0',0,'3/2')])]
    # Exhaust every subset, including empty occurrence domains, of four fixed catalogs.
    for name,(case,options) in [('eq',equality),('interaction',interaction),('shared',shared),('parallel',parallel)]:
        for bits in range(1<<len(options)):
            subset=[o for i,o in enumerate(options) if bits&(1<<i)]
            cases.append((f'{name}_subset_{bits:03d}',deepcopy(case),deepcopy(subset)))
    return cases

def main():
    began=now()
    spec=importlib.util.spec_from_file_location('archived_option_support',HERE/'archive/option_support.py')
    support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
    cases=fixtures()
    save('declared_fixture_inputs.json',[{'name':n,'instance':c,'options':o} for n,c,o in cases])
    records=[]; totals={'cases':len(cases),'cartesian_before':0,'cartesian_after':0,'legal_before':0,'legal_after':0,'deletions_checked':0}
    for name,case,options in cases:
        before_inputs=deepcopy((case,options))
        before_all,before=enumerate_all(case,options)
        retained,proof=support.propagate_option_support(case,options)
        after_all,after=enumerate_all(case,retained)
        replay=support.verify_option_support_report(case,options,retained,proof)
        record=dict(name=name,before_candidates=before_all,after_candidates=after_all,
            legal_before=before,legal_after=after,retained_option_ids=[o['option_id'] for o in retained],proof=proof,replay=replay,
            input_unchanged=(case,options)==before_inputs,sets_equal=before==after)
        records.append(record)
        for k,v in [('cartesian_before',len(before_all)),('cartesian_after',len(after_all)),('legal_before',len(before)),('legal_after',len(after)),('deletions_checked',replay['checked_deletions'])]: totals[k]+=v
        if not record['sets_equal'] or not record['input_unchanged']:
            save('failure_records.json',records);raise AssertionError('Complete legal schedule set or input mutation mismatch: '+name)
    # Assertions ensure named boundary cases actually exercise the intended behavior.
    byname={r['name']:r for r in records}
    assert byname['interaction_multiround']['proof']['round_count_including_fixed_point_check']>=4
    assert len(byname['equality_fraction']['legal_before'])==2
    assert byname['nonempty_but_resource_infeasible']['proof']['retained_option_count']==2
    assert not byname['nonempty_but_resource_infeasible']['legal_before']
    assert byname['scenarios_independent_frequency']['legal_before']==[('a','b')]
    assert ('aH','bM') in byname['shared_device_distinct_mode_start']['legal_before']
    assert ('aM','bH') in byname['shared_device_distinct_mode_start']['legal_before']
    assert byname['empty_domain']['proof']['logical_feasibility']=='INFEASIBLE_BY_EMPTY_OPTION_DOMAIN'
    assert byname['no_common_device']['proof']['retained_option_count']==0
    assert len(byname['five_ms_start_fractional_end']['legal_before'])==2
    save('complete_schedule_sets_and_proofs.json',records)
    save('completion.json',dict(started_utc=began,ended_utc=now(),wall_s=time.monotonic()-START,passed=True,totals=totals,
        command=[sys.executable,*sys.argv],environment={'python':sys.version,'platform':platform.platform()},
        source_sha256={n:digest((HERE/'archive'/n).read_bytes()) for n in ['option_support.py','test_option_support.py']},
        thermal_calls=0,model_builds=0,solver_calls=0,scope='Complete finite structural schedule sets; not thermal integration or a universal empirical proof'))
    print(json.dumps(totals,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except BaseException:
        save('failure.json',dict(utc=now(),elapsed_s=time.monotonic()-START,traceback=traceback.format_exc()))
        raise
