"""Independent finite structural-schedule oracle for option support tests.

Promoted from the frozen 2026-11-11 domain validation. The legality predicate
uses exact rational comparisons and never imports production schedule, MILP,
thermal, or solver code. Fixtures cover 10 named catalogues plus every subset
of four fixed catalogues (256 more). They are small structural tests, not
research instances or thermal safety certificates.
"""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations, product

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

def enumerate_all(case, options, check_time=None):
    groups=[(s['id'],t['id']) for s in case['scenarios'] for t in s['stage_instances']]
    choices=[[o for o in options if (o['scenario_id'],o['stage_instance_id'])==g] for g in groups]
    count=1
    for c in choices: count*=len(c)
    if count>512: raise AssertionError('Frozen per-case Cartesian cap exceeded')
    all_records=[]; valid=[]
    for chosen in product(*choices):
        if check_time is not None: check_time()
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
