"""E4b offline arithmetic from frozen records; no search or thermal imports.

This program checks recorded aggregates against manually derived selected
prefixes. It never enumerates starts, runs HEFT, creates a complete candidate,
or evaluates the pre-existing handwritten fixture.
"""
import argparse,ast,hashlib,json
from fractions import Fraction as F
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[1]

def read(p):return json.loads(p.read_bytes())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def fsha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def packed(v):return (json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()

def main(destination):
    out=Path(destination).resolve()
    if out.exists():raise FileExistsError('new offline evidence directory required')
    run=HERE/'results/e4_req_01';packet=read(run/'slot_2/plan/job.json')['packet'];i=packet['instance']
    saved=read(run/'slot_2/plan/accepted_result.json')['result'];attempts=saved['search']['construction_attempts']
    single=read(run/'slot_1/plan/accepted_result.json')['result']
    manifest=read(HERE/'evidence/e4_requests_precheck01/frozen_real_manifest.json')
    auth=read(HERE/'authorizations/e4_req_01.json')
    ledger=Path(auth['authority_store'])/digest({'authorization_id':auth['authorization_id']})
    ledger_before={p.name:fsha(p) for p in ledger.glob('*.json')}
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    check('source input identity',digest(i)==manifest['inputs'][i['id']]['input_sha256'])
    check('unresolved without complete candidate',saved['state']=='UNRESOLVED' and saved['safe_candidate'] is None)
    check('zero evaluated double-copy candidates',saved['archive']['candidates']==0 and saved['archive']['evaluations']==[])
    check('four original construction attempts',len(attempts)==4 and [a['opp_rank'] for a in attempts]==[None,0,1,2])
    check('same frozen shared priority',all(a['shared_priority']==attempts[0]['shared_priority'] for a in attempts))
    check('single and double-copy priorities unchanged',single['search']['construction_attempts'][0]['shared_priority']==attempts[0]['shared_priority'])
    check('single and double-copy rank values unchanged',single['search']['construction_attempts'][0]['rank_u_ms']==attempts[0]['rank_u_ms'])
    check('all failures before thermal',all(a['thermal_status']=='NOT_EVALUATED' and a['reason']=='NO_LEGAL_EFT_INSERTION' for a in attempts))
    modes=i['stage_modes']
    def d(stage,unit,opp):
        rows=[m for m in modes[stage] if m['unit_id']==unit and m['opp_id']==opp]
        check('unique mode '+stage+'/'+unit+'/'+opp,len(rows)==1)
        return F(rows[0]['duration_ms'])
    deadlines={r['application']:F(r['deadline_ms']) for s in i['scenarios'] for r in s['requests']}
    check('zero releases',all(F(r['release_ms'])==0 for s in i['scenarios'] for r in s['requests']))
    check('two copies and no relaxed deadlines',i['settings']['requests_per_application']==2 and deadlines==dict(A=F('123.5'),B=F('157.3'),C=F(143)))
    capacities=[]
    for stage,app in [('A.main','A'),('B.main','B'),('C.main','C')]:
        fastest=min(F(m['duration_ms']) for m in modes[stage] if m['unit_id'].startswith('CPU'))
        workload=2*fastest;check('CPU copy-capacity excludes '+stage,workload>deadlines[app])
        capacities.append(dict(stage=stage,unit_class='CPU',minimum_duration_ms=str(fastest),copies=2,
            minimum_work_ms=str(workload),latest_main_completion_ms=str(deadlines[app]),excluded=True))
    unit_classes={u['id']:u['device_class'] for u in i['platform']['units']}
    check('B support only CPU and NPU',{unit_classes[m['unit_id']] for m in modes['B.main']}=={'CPU','NPU'})
    check('C support only CPU and GPU',{unit_classes[m['unit_id']] for m in modes['C.main']}=={'CPU','GPU'})
    gpu_work=2*d('A.main','GPU0','H')+2*d('C.main','GPU0','H')
    check('shared GPU A+C cannot meet latest deadline',gpu_work>max(deadlines['A'],deadlines['C']))
    forced=dict(B_main='NPU0',C_main='GPU0',A_main='NPU0',kind='necessary placement conditions only; global safety/feasibility unresolved',
        A_C_minimum_GPU_work_ms=str(gpu_work),latest_GPU_deadline_ms=str(max(deadlines['A'],deadlines['C'])))
    # Fixed selected prefixes deduced on paper from source EFT rules and the
    # archived chosen units. These are not a replay of rejected unit trials.
    prefixes={
        'H':{'B.pre':[(0,15),(15,30)],'B.main':[(15,50),(50,85)],
             'C.pre':[(0,12),(15,27)],'C.main':[(15,60),(60,105)],'A.pre':[(0,10),(10,20)]},
        'M':{'B.pre':[(0,F('35/2')),(20,F('75/2'))],'B.main':[(20,62),(65,107)],
             'C.pre':[(0,F('72/5')),(15,F('147/5'))],'C.main':[(15,72),(75,132)],
             'A.pre':[(0,F('34/3')),(15,F('79/3'))]}}
    units={'B.pre':'CPU1','B.main':'NPU0','C.pre':'CPU1','C.main':'GPU0','A.pre':'CPU2'}
    checked_prefixes={}
    for attempt_index,opp in [(0,'H'),(1,'H'),(2,'M')]:
        a=attempts[attempt_index];decisions={x['shared_stage_id']:x for x in a['decisions']}
        for stage,pairs in prefixes[opp].items():
            check(f'prefix selected unit {attempt_index}/{stage}',decisions[stage]['unit']==units[stage])
            for j,(start,end) in enumerate(pairs):
                check(f'prefix mode duration {attempt_index}/{stage}/{j}',F(end)-F(start)==d(stage,units[stage],opp))
                check(f'prefix start grid {attempt_index}/{stage}/{j}',F(start)/F(i['start_grid_ms'])%1==0)
            weight=F(1) if stage=='A.pre' else F('1/2')
            check(f'recorded weighted finish sum {attempt_index}/{stage}',sum((F(end) for _,end in pairs),F(0))*weight==F(decisions[stage]['weighted_inserted_finish_sum_ms']))
        checked_prefixes[str(attempt_index+1)]={stage:[[str(F(x)),str(F(y))] for x,y in rows] for stage,rows in prefixes[opp].items()}
    check('H NPU prefix blocks two A copies',F(85)+2*d('A.main','NPU0','H')>deadlines['A'])
    check('H before-NPU gap too short',F(15)-F(10)<d('A.main','NPU0','H'))
    check('H after-GPU gap too short',F(105)+d('A.main','GPU0','H')>deadlines['A'])
    check('H before-GPU gap too short',F(15)-F(10)<d('A.main','GPU0','H'))
    npu_M_gaps=[F(20)-F('34/3'),F(65)-F(62),deadlines['A']-F(107)]
    gpu_M_gaps=[F(15)-F('34/3'),F(75)-F(72),max(F(0),deadlines['A']-F(132))]
    check('all relaxed M NPU gaps shorter than A.main',max(npu_M_gaps)<d('A.main','NPU0','M'))
    check('all relaxed M GPU gaps shorter than A.main',max(gpu_M_gaps)<d('A.main','GPU0','M'))
    check('L C.main CPU single copy already late',d('C.main','CPU1','L')>deadlines['C'])
    check('L C.main shared GPU two-copy workload late',2*d('C.main','GPU0','L')>deadlines['C'])
    fixture_path=REPO/'research/chapter3_experiments/e4_requests/test_input_contract.py'
    tree=ast.parse(fixture_path.read_bytes());fixture=None
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HANDWRITTEN' for t in node.targets):fixture=ast.literal_eval(node.value)
    check('fixture read as literal only',isinstance(fixture,dict))
    # Read an already frozen fixture's NPU order only. Do not instantiate or
    # validate its 24 execution rows, and do not propagate its temperature.
    partial=[dict(stage='A.main',copy=j+1,start_ms=str(F(t)),end_ms=str(F(t)+d('A.main','NPU0','H'))) for j,t in enumerate(fixture['A.main'][1])]
    partial += [dict(stage='B.main',copy=j+1,start_ms=str(F(t)),end_ms=str(F(t)+d('B.main','NPU0','H'))) for j,t in enumerate(fixture['B.main'][1])]
    partial.sort(key=lambda x:F(x['start_ms']))
    check('old static fixture has A-before-B local NPU order',[x['stage'] for x in partial]==['A.main','A.main','B.main','B.main'])
    check('no authority records changed',{p.name:fsha(p) for p in ledger.glob('*.json')}==ledger_before)
    sources=[run/'slot_2/plan/job.json',run/'slot_2/plan/accepted_result.json',run/'slot_1/plan/accepted_result.json',
        REPO/'research/chapter3_experiments/heft_method.py',REPO/'research/chapter3_experiments/e1_objective/search.py',
        fixture_path,HERE/'evidence/e4_requests_precheck01/mock_tests.txt',HERE/'evidence/e4_requests_precheck01/precheck_result.json']
    evidence=dict(schema='E4B_OFFLINE_CONSTRUCTION_ARITHMETIC_V1',experiment_source_sha=manifest['source_sha'],
        input_sha256=digest(i),analysis_script_sha256=fsha(Path(__file__)),evidence_sha256={p.relative_to(REPO).as_posix():fsha(p) for p in sources},
        check_count=len(checks),checks=checks,logged_shared_priority=attempts[0]['shared_priority'],
        failed_shared_stages=[x['failed_shared_stage'] for x in attempts],CPU_capacity_exclusions=capacities,necessary_main_placements=forced,
        reconstructed_selected_prefixes_ms=checked_prefixes,prefix_scope='Source-based deduction consistent with logged aggregates; not all rejected unit/OPP/start trials were recorded or recovered.',
        M_continuous_gap_upper_bounds_ms=dict(NPU=list(map(str,npu_M_gaps)),GPU=list(map(str,gpu_M_gaps))),
        fixed_all_L_C_main_subdomain_infeasible=True,original_complete_thermal_problem_feasibility='UNRESOLVED',
        existing_frozen_fixture_local_NPU_example=partial,fixture_thermal_evaluated=False,complete_candidate_generated=False,
        formal_research_calls=0,HEFT_constructor_calls=0,schedule_validator_calls=0,thermal_kernel_calls=0,MILP_calls=0,new_real_SAFE=0,
        authority_records_before_after_identical=True,interpretation='Diagnoses this constructor prefix; neither a whole-domain infeasibility proof nor a new safe or energy result.')
    out.mkdir(parents=True);(out/'offline_arithmetic.json').write_bytes(packed(evidence))
    print(json.dumps(dict(passed=all(x['passed'] for x in checks),checks=len(checks),formal_research_calls=0,new_real_SAFE=0)))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);main(p.parse_args().out)
