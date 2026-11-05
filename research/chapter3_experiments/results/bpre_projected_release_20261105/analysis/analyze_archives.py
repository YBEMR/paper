"""Read archived JSON only; no solver/evaluator imports or experiment calls.
Numeric source tokens are retained as strings; exact arithmetic uses Fraction.
Run from the archive workspace: python -B paper_bpre_publication_20261105/analysis/analyze_archives.py
"""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext
from datetime import datetime, timezone
import csv, hashlib, json, time

START = datetime.now(timezone.utc).isoformat()
T0 = time.perf_counter()
ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
LATEST = Path('bpre_projected_retry_20261105T071312Z')
OLD = Path('task_a_rebuild_20261104T114840Z/paper/research/chapter3_experiments/results/bpre_formal_execution_20261104_01')
LIVE = Path('bpre_live_heft_milp_20261105T011253Z')
sources = {}
checks = []

def read(rel):
    rel = Path(rel)
    data = (ROOT / rel).read_bytes()
    sources[rel.as_posix()] = {'record_id': rel.as_posix(), 'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
    return json.loads(data.decode('utf-8-sig'), parse_float=str)

def dec(value, precision=85):
    v = F(value)
    with localcontext() as c:
        c.prec = precision
        return str(Decimal(v.numerator) / Decimal(v.denominator))

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def csvwrite(name, rows):
    with (OUT / name).open('w', encoding='utf-8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def check(label, value):
    checks.append({'check':label, 'passed':bool(value)})
    if not value: raise AssertionError(label)

def canonical_candidate(candidate):
    return {s: sorted(rows,key=lambda r:r['stage_id']) for s,rows in candidate['scenes'].items()}

paths = {'projected_600':LATEST/'execution/worker/method/result.json',
         'live_heft_milp_600':LIVE/'execution/worker/method/result.json'}
for key in ['heft','sa101','sa102','sa103','sa104','sa105','whole_milp']:
    paths[key] = OLD/f'slots/{key}__method/worker/method/result.json'
results = {key:read(p) for key,p in paths.items()}
instances = {key:read(p.parent/'input_instance.json') for key,p in paths.items()}
configs = {key:read(p.parent/'input_config.json') for key,p in paths.items()}
latest = results['projected_600']; inp=instances['projected_600']; config=configs['projected_600']
delivery=read(LATEST/'delivery_result.json')
cert=read(LATEST/'execution/worker/method/matlab/request_000001.projection_certificate.json')
eqcert=read(LATEST/'execution/worker/method/matlab/request_000001.projection_equality_certificate.json')
receipts=[read(LATEST/f'execution/worker/method/matlab/request_000001.projection_receipt_{i:06d}.json') for i in range(1,4)]
for key in results:
    check(key+': identical archived input instance', instances[key]==inp)
    check(key+': identical archived configuration', configs[key]==config)

U=F(latest['safe_upper_bound_J'])
summary=[]; stages=[]; scene_rows=[]; components=[]; peaks=[]; stage_deltas=[]; component_deltas=[]; temperature_deltas=[]; safe_evidence={}; validation_by_method={}
scene_lookup={s['id']:s for s in inp['scenarios']}
for key,result in results.items():
    e=result['evaluation'];leg=e['legality']; cand=result['safe_candidate']
    check(key+': archived complete SAFE', result['state']=='SAFE' and e['state']=='SAFE' and e['rankable_energy'] and not e['violations'])
    weighted=[]
    safe_evidence[key]={'source_record_id':paths[key].as_posix(), 'safe_upper_bound_J':result['safe_upper_bound_J'], 'safe_candidate':cand,
      'evaluation':{k:e[k] for k in ['state','reason','problem_id','scenes','violations','weighted_energy_J','safe_upper_bound_J','rankable_energy','numerical_protocol','control_policy','evidence_identity','legality'] if k in e},
      'timing':{k:result.get('timing',{}).get(k) for k in ['limit_s','method_elapsed_s','deadline_overshoot_s','phases_exclusive_s']}}
    for sid,s in e['scenes'].items():
        check(key+': '+sid+' complete 400ms SAFE',s['state']=='SAFE' and s['complete'] and s['rankable_energy'] and F(s['covered_until_s'])==F(2,5))
        weight=F(scene_lookup[sid]['weight']);weighted.append((weight,F(s['energy_J'][0]),F(s['energy_J'][1])))
        rows=leg['scenes'][sid]['rows'];byid={r['stage_id']:r for r in rows}
        check(key+': '+sid+' candidate/legality alignment',sorted([(r['stage_id'],r['unit'],r['opp'],r['start_ms']) for r in rows])==sorted([(r['stage_id'],r['unit'],r['opp'],r['start_ms']) for r in cand['scenes'][sid]]))
        npu=sorted([r for r in rows if r['domain_id']=='NPU'],key=lambda r:F(r['start_ms']))
        scene_rows.append({'method':key,'scene':sid,'weight':str(weight),'state':s['state'],'energy_lower_J':s['energy_J'][0],'energy_upper_J':s['energy_J'][1], 'peak_upper_degC':max(s['peaks_degC'].values(),key=lambda x:F(x[1]))[1], 'npu_order':'>'.join(r['shared_stage_id'] for r in npu),'request_completion_ms':json.dumps(leg['scenes'][sid]['request_completion_ms'],ensure_ascii=False,sort_keys=True)})
        for r in rows:
            mode=next(v for v in inp['stage_modes'][r['shared_stage_id']] if v['unit_id']==r['unit'] and v['opp_id']==r['opp'])
            check(key+': '+r['stage_id']+' duration/catalog/release/deadline',F(r['end_ms'])-F(r['start_ms'])==F(r['duration_ms'])==F(mode['duration_ms']) and F(r['start_ms'])>=F(r['release_ms']) and F(r['end_ms'])<=F(r['deadline_ms']))
            predecessors=[p for p,t in scene_lookup[sid]['dependencies'] if t==r['stage_id']]
            check(key+': '+r['stage_id']+' precedence',all(F(byid[p]['end_ms'])<=F(r['start_ms']) for p in predecessors))
            check(key+': '+r['stage_id']+' 5ms start grid',F(r['start_ms'])/F(inp['start_grid_ms'])==int(F(r['start_ms'])/F(inp['start_grid_ms'])))
            stages.append({'method':key,'scene':sid,**r,'frequency_GHz':mode['frequency_GHz'],'frequency_decimal_GHz':dec(mode['frequency_GHz']),'voltage_V':mode['voltage_V'],'activity_energy_J_exact':mode['activity_energy_J'],'predecessors':';'.join(predecessors),'predecessor_slack_ms':';'.join(str(F(r['start_ms'])-F(byid[p]['end_ms'])) for p in predecessors),'npu_position':next((i+1 for i,v in enumerate(npu) if v['stage_id']==r['stage_id']),'')})
        for a in rows:
            for b in rows:
                if a['stage_id']>=b['stage_id']:continue
                overlap=max(F(a['start_ms']),F(b['start_ms']))<min(F(a['end_ms']),F(b['end_ms']))
                check(key+': '+sid+' resources '+a['shared_stage_id']+'/'+b['shared_stage_id'],not overlap or (a['unit']!=b['unit'] and (a['domain_id']!=b['domain_id'] or a['opp']==b['opp'])))
        for c,iv in s['energy_components_J'].items():
            components.append({'method':key,'scene':sid,'component':c,'lower_J':iv[0],'upper_J':iv[1]})
        lo=sum(F(v[0]) for v in s['energy_components_J'].values());hi=sum(F(v[1]) for v in s['energy_components_J'].values())
        check(key+': '+sid+' energy/component enclosure overlap',lo<=F(s['energy_J'][1]) and F(s['energy_J'][0])<=hi)
        for node,iv in s['peaks_degC'].items():
            witness=s['peak_witnesses'][node]
            peaks.append({'method':key,'scene':sid,'node':node,'peak_lower_degC':iv[0],'peak_upper_degC':iv[1],'witness_time_s':witness['time_s'],'maximum_allowed_degC':scene_lookup[sid]['maximum_temperature_degC'][inp['platform']['node_order'].index(node)]})
    wlo=sum(w*lo for w,lo,hi in weighted);whi=sum(w*hi for w,lo,hi in weighted)
    check(key+': weighted energy enclosure overlap',wlo<=F(e['weighted_energy_J'][1]) and F(e['weighted_energy_J'][0])<=whi)
    check(key+': reported U matches SAFE upper endpoint',result['safe_upper_bound_J']==e['safe_upper_bound_J']==e['weighted_energy_J'][1])
    v=F(result['safe_upper_bound_J'])
    summary.append({'method':key,'seed':result.get('seed',''),'energy_lower_J':e['weighted_energy_J'][0],'energy_upper_J':result['safe_upper_bound_J'],'new_minus_method_J':dec(U-v),'reduction_from_method_percent':dec(100*(v-U)/v),'method_limit_s':result.get('timing',{}).get('limit_s',''),'method_elapsed_s':result.get('timing',{}).get('method_elapsed_s',''),'complete_SAFE':True,'independently_proven_optimal':result.get('independently_proven_optimal',False)})

newst={(r['scene'],r['stage_id']):r for r in stages if r['method']=='projected_600'}
for r in stages:
    if r['method']=='projected_600':continue
    n=newst[(r['scene'],r['stage_id'])]
    for field in ['unit','opp','frequency_GHz','start_ms','end_ms','duration_ms','activity_power_W','predecessors','predecessor_slack_ms','npu_position']:
        stage_deltas.append({'reference_method':r['method'],'scene':r['scene'],'stage_id':r['stage_id'],'field':field,'reference_value':r[field],'projected_value':n[field],'changed':r[field]!=n[field]})
newcomp={(r['scene'],r['component']):r for r in components if r['method']=='projected_600'}
for r in components:
    if r['method']=='projected_600':continue
    n=newcomp[r['scene'],r['component']]
    component_deltas.append({'reference_method':r['method'],'scene':r['scene'],'component':r['component'],'new_minus_reference_lower_J':dec(F(n['lower_J'])-F(r['upper_J'])),'new_minus_reference_upper_J':dec(F(n['upper_J'])-F(r['lower_J']))})
newpk={(r['scene'],r['node']):r for r in peaks if r['method']=='projected_600'}
for r in peaks:
    if r['method']=='projected_600':continue
    n=newpk[r['scene'],r['node']]
    temperature_deltas.append({'reference_method':r['method'],'scene':r['scene'],'node':r['node'],'new_minus_reference_lower_degC':dec(F(n['peak_lower_degC'])-F(r['peak_upper_degC'])),'new_minus_reference_upper_degC':dec(F(n['peak_upper_degC'])-F(r['peak_lower_degC']))})

weighted_components=[];weighted_differences=[]
for key in results:
    for component in ['baseline','activity','external_common','temperature_correction']:
        vals=[r for r in components if r['method']==key and r['component']==component]
        lo=sum(F(r['lower_J'])*F(scene_lookup[r['scene']]['weight']) for r in vals)
        hi=sum(F(r['upper_J'])*F(scene_lookup[r['scene']]['weight']) for r in vals)
        weighted_components.append({'method':key,'component':component,'weighted_lower_J':dec(lo),'weighted_upper_J':dec(hi)})
for r in weighted_components:
    if r['method']=='projected_600':continue
    n=next(v for v in weighted_components if v['method']=='projected_600' and v['component']==r['component'])
    weighted_differences.append({'reference_method':r['method'],'component':r['component'],'new_minus_reference_lower_J':dec(F(n['weighted_lower_J'])-F(r['weighted_upper_J'])),'new_minus_reference_upper_J':dec(F(n['weighted_upper_J'])-F(r['weighted_lower_J']))})

commits=[]
for idx,(receipt,committed) in enumerate(zip(receipts,latest['diagnostic']['evaluations']),1):
    ce=committed['evaluation']; archive_e=receipt['evaluation']
    check('projection receipt '+str(idx)+' matches committed evaluator output',ce==archive_e and canonical_candidate(receipt['candidate'])==canonical_candidate(committed['candidate']))
    check('projection receipt '+str(idx)+' committed before root deadline',F(committed['admission_committed_at_s'])<=600 and ce['state']=='SAFE' and all(s['complete'] for s in ce['scenes'].values()))
    commits.append({'receipt_number':idx,'state':receipt['state'],'source':receipt['source'],'numeric':receipt['numeric'],'publication_event_number':receipt['publication']['event_number'],'publication_sha256':receipt['publication']['sha256'],'received_at_elapsed_s':receipt['publication']['received_at_elapsed_s'],'evaluation_completed_at_s':ce.get('completed_at_elapsed_s'),'admission_committed_at_s':committed['admission_committed_at_s'],'safe_upper_bound_J':ce['safe_upper_bound_J'],'candidate_sha256_in_commit':committed['candidate_sha256'],'candidate_sha256_in_evaluation':ce['evidence_identity']['candidate_sha256'],'certificate_sha256':receipt['certificate_sha256'],'original_vector_length':receipt['original_vector_length'],'native_vector_length':receipt['native_vector_length'],'archive_is_not_acceptance_commit':receipt['archive_is_not_acceptance_commit']})
check('final incumbent matches third committed SAFE candidate',canonical_candidate(latest['safe_candidate'])==canonical_candidate(latest['diagnostic']['evaluations'][2]['candidate']) and latest['safe_upper_bound_J']==commits[2]['safe_upper_bound_J'])
check('HEFT/live/new initializer candidate identity',canonical_candidate(results['heft']['safe_candidate'])==canonical_candidate(results['live_heft_milp_600']['safe_candidate'])==canonical_candidate(latest['initialisation']['witness']['candidate']))

sa=sorted(F(results[f'sa{i}']['safe_upper_bound_J']) for i in range(101,106))
sa_stats={'seeds':[101,102,103,104,105],'n':5,'min_upper_J':dec(sa[0]),'median_upper_J':dec(sa[2]),'max_upper_J':dec(sa[-1]),'mean_upper_J':dec(sum(sa)/5),'range_J':dec(sa[-1]-sa[0]),'new_reduction_vs_median_percent':dec(100*(sa[2]-U)/sa[2]),'inference':'descriptive only; one instance; no population inference or significance test'}
write('archived_safe_evidence.json',safe_evidence)
write('scientific_input.json',{k:inp[k] for k in ['id','condition_id','sample_id','settings','duration_scale','platform','execution_rules','units','window_ms','start_grid_ms','response_variant','stage_modes','scenarios']})
write('summary.json',{'methods':summary,'sa_all_seeds':sa_stats,'verification_status':'ANALYZED; archive consistency checked, no scientific reevaluation','solver_calls':0,'thermal_evaluator_calls':0,'scope':'one fixed synthetic instance, archived complete SAFE endpoints only'})
write('projection_acceptance.json',{'root_budget_s':600,'committed_evaluations':commits,'native_final_response_used_for_new_evaluation':False,'independently_proven_optimal':False,'note':'Independent receipt files are archive evidence, not acceptance commits. Commit times come from result.json diagnostic.evaluations. Candidate hashes differ, possibly due to historical serialization conventions; both hash algorithms were not reconstructed here. Candidates were compared structurally by stage IDs.'})
for name,rows in [('methods.csv',summary),('stages.csv',stages),('scenes.csv',scene_rows),('energy_components.csv',components),('weighted_energy_components.csv',weighted_components),('weighted_component_differences.csv',weighted_differences),('peaks.csv',peaks),('stage_differences.csv',stage_deltas),('component_differences.csv',component_deltas),('temperature_differences.csv',temperature_deltas)]:csvwrite(name,rows)
write('consistency_checks.json',{'checks':checks,'all_passed':all(x['passed'] for x in checks),'count':len(checks),'limitations':'Checks compare archived fields and use exact rational arithmetic. They do not rerun schedule construction, solver, or thermal evaluator; the archived SAFE certificate remains the source of the thermal claim.'})
write('source_manifest.json',{'hash_algorithm':'SHA-256','source_records':list(sources.values()),'public_repository_destination':'research/chapter3_experiments/results/bpre_projected_release_20261105/analysis','prior_public_record':'research/chapter3_experiments/results/bpre_release_20261105','prior_public_commit':'bfcf3db10364da1b01391333dc132a8a3faa8eee','source_numeric_token_policy':'JSON float tokens read as strings to preserve source decimals; source energy/temperature strings kept verbatim; derived decimal differences use 85-digit Decimal conversion of exact Fraction arithmetic.'})
write('analysis_run.json',{'command':'python -B paper_bpre_publication_20261105/analysis/analyze_archives.py','start_utc':START,'end_utc':datetime.now(timezone.utc).isoformat(),'elapsed_s':time.perf_counter()-T0,'scientific_solver_calls':0,'scientific_evaluator_calls':0,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source_count':len(sources),'check_count':len(checks),'source_files_modified':False})
print(json.dumps({'all_checks_passed':True,'checks':len(checks),'sources':len(sources),'sa':sa_stats},ensure_ascii=False))
