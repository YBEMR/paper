"""Pure H/base -> independent H/R planner projections, no search or cache."""
from pathlib import Path
import json,sys
from .common import BASE_SHA,POLICY,require,copy,exact,sha,byte_sha,mode_index
HERE=Path(__file__).resolve().parent
CORE=HERE.parent

def verify_sources():
    m=json.loads((HERE/'evidence/source_manifest.json').read_text(encoding='utf-8'))
    require(m['main_baseline']==BASE_SHA,'SOURCE_BASELINE_MISMATCH')
    for relative,digest in m['core'].items(): require(byte_sha((CORE/relative).read_bytes())==digest,'SOURCE_DRIFT:'+relative)
    return m

def fresh_H(problem_id,source_sha=BASE_SHA):
    require(problem_id in ('base__R1','base__R2') and source_sha==BASE_SHA,'UNDECLARED_PROBLEM_OR_SOURCE'); verify_sources()
    if str(CORE) not in sys.path: sys.path.insert(0,str(CORE))
    from inputs import build_instance
    from control_policy import with_auto_low_idle
    # Do not import P0/P1 dispatchers, old results, bounds, schedules or thermal.
    raw=json.loads((CORE/'config_v01.json').read_bytes())
    h=build_instance(raw,problem_id)
    return with_auto_low_idle(raw),with_auto_low_idle(h)

def physical_projection(config,instance):
    c,i=copy(config),copy(instance)
    del c['defaults']['response_variant']
    for stage in c['stage_catalog']:
        for profile in stage['profiles'].values(): del profile['alpha']
    del i['response_variant']; del i['settings']['response_variant']; del i['catalog_duration_weighted_mean_alpha']
    for rows in i['stage_modes'].values():
        for row in rows:
            for key in ('alpha','duration_ms','activity_energy_J'): del row[key]
    return {'config':c,'instance':i}

def all_diffs(a,b,path=()):
    require(type(a) is type(b),'INPUT_TYPE_DRIFT:'+str(path))
    if isinstance(a,dict):
        require(set(a)==set(b),'INPUT_FIELD_SET_DRIFT:'+str(path))
        return [v for k in a for v in all_diffs(a[k],b[k],path+(k,))]
    if isinstance(a,list):
        require(len(a)==len(b),'INPUT_LIST_SIZE_DRIFT:'+str(path))
        return [v for j in range(len(a)) for v in all_diffs(a[j],b[j],path+(j,))]
    return [] if a==b else [dict(path=list(path),H=a,R=b)]

def allowed(path):
    if path==('config','defaults','response_variant'): return True
    if len(path)==6 and path[:2]==('config','stage_catalog') and isinstance(path[2],int) and path[3]=='profiles' and path[5]=='alpha': return True
    if path in [('instance','response_variant'),('instance','settings','response_variant')]: return True
    if len(path)==3 and path[:2]==('instance','catalog_duration_weighted_mean_alpha'): return True
    return len(path)==5 and path[:2]==('instance','stage_modes') and isinstance(path[3],int) and path[4] in ('alpha','duration_ms','activity_energy_J')

def pair_audit(config_H,H,config_R,R):
    hm,ho=mode_index(H); rm,ro=mode_index(R)
    require(set(hm)==set(rm),'MODE_SUPPORT_DRIFT'); require(ho==ro,'MODE_ORDER_DRIFT')
    require(config_H['defaults']['response_variant']=='H' and H['response_variant']==H['settings']['response_variant']=='H','H_RESPONSE_IDENTITY')
    require(config_R['defaults']['response_variant']=='R' and R['response_variant']==R['settings']['response_variant']=='R','R_RESPONSE_IDENTITY')
    for stage in config_R['stage_catalog']:
        for profile in stage['profiles'].values(): require(exact(profile['alpha'])==1,'R_CONFIG_H_ALPHA_LEAK')
    require(all(exact(v)==1 for v in R['catalog_duration_weighted_mean_alpha'].values()),'R_MEAN_ALPHA_LEAK')
    rows=[]
    for key,h in hm.items():
        r=rm[key]; reference=H['platform']['domains'][h['domain_id']]; fref=exact(reference['opps'][reference['reference_opp']]['frequency_GHz']); f=exact(h['frequency_GHz']); q=exact(h['activity_power_W'])
        expected=exact(h['d_ref_ms'])*fref/f
        require(exact(r['alpha'])==1 and exact(r['duration_ms'])==expected,'R_MODE_RESPONSE_FORMULA')
        require(r['activity_power_W']==h['activity_power_W'],'MODE_ACTIVITY_POWER_DRIFT')
        require(exact(r['activity_energy_J'])==q*expected/1000,'R_ACTIVITY_ENERGY_FORMULA')
        rows.append(dict(key=list(key),mode_id=h['mode_id'],H_alpha=h['alpha'],R_alpha=r['alpha'],H_duration_ms=h['duration_ms'],R_duration_ms=r['duration_ms'],activity_power_W=h['activity_power_W'],d_R_minus_d_H_ms=str(expected-exact(h['duration_ms']))))
    differences=all_diffs({'config':config_H,'instance':H},{'config':config_R,'instance':R})
    require(all(allowed(tuple(v['path'])) for v in differences),'NON_WHITELIST_INPUT_DIFFERENCE')
    hp,rp=physical_projection(config_H,H),physical_projection(config_R,R); require(hp==rp,'PHYSICAL_PROJECTION_DRIFT')
    require(H['id']==R['id'] and H['id'] in ('base__R1','base__R2'),'PROBLEM_ID_DRIFT')
    support=[dict(stage=k[0],unit=k[1],opp=k[2],mode_id=hm[k]['mode_id']) for k in sorted(hm)]
    return dict(passed=True,problem_id=H['id'],diffs=differences,mode_diff=rows,profile_alpha_cleared=True,
      truth_H_sha256=sha(H),plan_H_sha256=sha(H),plan_R_sha256=sha(R),H_config_sha256=sha(config_H),R_config_sha256=sha(config_R),
      physical_projection_sha256=sha(hp),support_sha256=sha(support),scenario_sha256=sha(H['scenarios']),accuracy_sha256=sha(config_H['accuracy_targets']),policy_id=POLICY,
      start_domain_note='Declared grid/start_domain preserved; duration-dependent derived option lists may differ')

def paired_response_input_view(problem_id,source_sha=BASE_SHA):
    c,h=fresh_H(problem_id,source_sha); rc,r=copy(c),copy(h)
    rc['defaults']['response_variant']='R'
    for stage in rc['stage_catalog']:
        for profile in stage['profiles'].values(): profile['alpha']='1'
    r['response_variant']=r['settings']['response_variant']='R'
    r['catalog_duration_weighted_mean_alpha']={d:'1' for d in r['catalog_duration_weighted_mean_alpha']}
    for rows in r['stage_modes'].values():
        for mode in rows:
            dom=r['platform']['domains'][mode['domain_id']]; ref=dom['opps'][dom['reference_opp']]
            mode['alpha']='1'; mode['duration_ms']=str(exact(mode['d_ref_ms'])*exact(ref['frequency_GHz'])/exact(mode['frequency_GHz']))
            mode['activity_energy_J']=str(exact(mode['activity_power_W'])*exact(mode['duration_ms'])/1000)
    report=pair_audit(c,h,rc,r)
    return dict(truth_H={'config':copy(c),'instance':copy(h)},planner_H={'config':copy(c),'instance':copy(h)},planner_R={'config':rc,'instance':r},audit=report,source_commit_sha=source_sha)

def planner_packet(pair,view):
    require(view in ('H','R'),'INVALID_RESPONSE_VIEW')
    report=pair_audit(pair['planner_H']['config'],pair['planner_H']['instance'],pair['planner_R']['config'],pair['planner_R']['instance'])
    require(pair['truth_H']==pair['planner_H'],'TRUTH_OR_PLANNER_H_MUTATION')
    public=copy(pair['planner_'+view])
    return dict(view=view,problem_id=public['instance']['id'],source_commit_sha=pair['source_commit_sha'],
      planner=public,plan_sha256=sha(public['instance']),config_sha256=sha(public['config']),
      physical_projection_sha256=report['physical_projection_sha256'],support_sha256=report['support_sha256'],scenario_sha256=report['scenario_sha256'],
      policy_id=POLICY,accuracy_sha256=report['accuracy_sha256'])
