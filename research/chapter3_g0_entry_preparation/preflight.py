"""Read-only source/input audit and pure protocol arithmetic; no production imports.

Outputs are a pending proposal, never an execution claim or scientific input.
No HEFT/MILP/SA, coefficient generation, thermal work or process launch exists.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = 'research/chapter3_method_entry_preparation/results/frozen_entry02/common_input.json'
COMMON_SHA = '07e458f3f811746f78931a340d258e230a8de4afb62ac0140459feff6a7bf80a'
BASELINE = 'd3fef20cc32e2246cd1a0014e8ab15f5e090f48c'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def locations(path,names):
    text=(ROOT/path).read_text(encoding='utf-8')
    tree=ast.parse(text)
    return [dict(path=path,name=n.name,line=n.lineno,end_line=n.end_lineno)
            for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]


def proposed_timing(root_start,total,now,scope_deadline):
    """Pure arithmetic oracle; not a MATLAB transport implementation/test."""
    if not root_start <= now < min(root_start+total,scope_deadline):
        raise ValueError('NO_EFFECTIVE_TIME')
    return {'session_lifetime_deadline':root_start+total,
        'ready_read_deadline':min(root_start+total,scope_deadline),
        'request_deadline':min(root_start+total,scope_deadline),
        'request_remaining':min(root_start+total,scope_deadline)-now}


def proposed_status(*,has_safe,local_entered,post,reason,settled=True,idle=True):
    """Protocol classification oracle, not the future real executor."""
    if reason in ('NUMERICAL_CONFLICT','INTERFACE_FAILURE','CLEANUP_FAILURE'):
        return {'acceptance':'STOP_FAULT','retain_prior_safe':has_safe,'continue':False}
    if reason=='TIME_CUTOFF' and (not settled or not idle):
        return {'acceptance':'STOP_UNSETTLED','retain_prior_safe':has_safe,'continue':False}
    if not has_safe:
        return {'acceptance':'NO_SAFE_UNRESOLVED','retain_prior_safe':False,'continue':False}
    if post in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
        return {'acceptance':'POST_SEMANTIC_CONFLICT','retain_prior_safe':True,'continue':False}
    if post=='UNRESOLVED':
        return {'acceptance':'POST_UNRESOLVED','retain_prior_safe':True,'continue':False}
    if not local_entered:
        return {'acceptance':'SAFE_ONLY_LOCAL_ENTRY_INCOMPLETE','retain_prior_safe':True,'continue':False}
    return {'acceptance':'ENTRY_PATH_CHECKED_NOT_PERFORMANCE','retain_prior_safe':True,'continue':False}


def prepare(output):
    if output.exists():
        raise ValueError('never overwrite a preparation receipt')
    output.mkdir(parents=True)
    checks=[]
    def check(ok,name):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:
            save(output/'preflight_failure.json',{'checks':checks,'new_scientific_calls':0})
            raise AssertionError(name)
    common=json.loads((ROOT/COMMON).read_text(encoding='utf-8'))
    config,instance=common['config'],common['instance']
    check(sha(ROOT/COMMON)==COMMON_SHA,'original common input bytes')
    check(canonical(instance)=='b292ced36fec69f4aa97c39edce6df7df58a27b9cec85135ad77a7e0cf4b8f48','original expanded instance identity')
    check(canonical(config)=='15ca987441165a0e994ddbe073874ef23c76ee6ec26d4eecfa41b436ca0c6c83','original config identity')
    scenes=instance['scenarios']; ids=[s['id'] for s in scenes]
    check(ids==['C1','C2'] and all(len(s['stage_instances'])==6 and len(s['requests'])==2 for s in scenes),
          'two original six-Stage two-request scenes')
    groups={s['id']:{v:sum(i['shared_stage_id']==v for i in s['stage_instances'])
        for v in sorted({i['shared_stage_id'] for i in s['stage_instances']})} for s in scenes}
    occurrences={v:{s['id'] for s in scenes if v in groups[s['id']]} for v in set().union(*(set(g) for g in groups.values()))}
    check(len(occurrences)==8 and sum(len(v)>1 for v in occurrences.values())==4,'eight identities and four cross-scene identities')
    check(all(len(g)==6 and set(g.values())=={1} for g in groups.values()),'single-copy groups; not S7 replicas')
    check(F(instance['window_ms'])==230 and F(config['defaults']['window_ms'])==400,
          'effective 230ms instance distinguished from unused 400ms config default')
    check(F(instance['start_grid_ms'])==5 and instance['response_variant']=='H','original five-ms starts and H response')
    check(all(all(F(t)==50 for t in s['entry']['temperature_degC'])
              and all(F(t)==80 for t in s['maximum_temperature_degC']) for s in scenes),'original 50/80C entries and limits')
    check(len(instance['platform']['node_order'])==4 and instance['platform']==config['platform']
          and instance['execution_rules']['idle_policy']=='auto_low_immediate_v1','four-node platform and auto-L unchanged')
    check(sum(F(s['weight']) for s in scenes)==1,'original weights complete')
    baseline=json.loads((ROOT/'research/chapter3_g0/tests/fixtures/protected_baseline.json').read_text(encoding='utf-8'))
    manual_manifest=json.loads((ROOT/'research/chapter3_g0/results/manual06/source_manifest.json').read_text(encoding='utf-8'))
    protected={**baseline['protected_source_sha256'],**baseline['frozen_input_and_contract_sha256'],
               **manual_manifest['source_sha256']}
    check(all(sha(ROOT/p)==h for p,h in protected.items()),'208 legacy and validated G0 sources/frozen artifacts unchanged')
    check(all(sum(sorted(g.values())[:2])<=2 and len(g)>2 for g in groups.values()),'B1 fits and leaves complementary seeds')
    # These are arithmetic checks of a proposed split, not actual timing.
    first=proposed_timing(1000,300,1060,1100)
    second=proposed_timing(1000,300,1180,1240)
    check(first['session_lifetime_deadline']==second['session_lifetime_deadline']==1300
          and first['request_remaining']==40 and second['request_remaining']==60,
          'root lifetime outlives first slot; requests use active scope')
    try:
        proposed_timing(1000,300,1100,1100)
        expired=False
    except ValueError:
        expired=True
    check(expired,'exact effective deadline permits no new request')
    status_tests=[
      ({'has_safe':True,'local_entered':False,'post':'SAFE','reason':'TIME_CUTOFF'},'SAFE_ONLY_LOCAL_ENTRY_INCOMPLETE'),
      ({'has_safe':True,'local_entered':True,'post':'SAFE','reason':'TIME_CUTOFF','settled':False},'STOP_UNSETTLED'),
      ({'has_safe':True,'local_entered':True,'post':'SAFE','reason':'TIME_CUTOFF'},'ENTRY_PATH_CHECKED_NOT_PERFORMANCE'),
      ({'has_safe':True,'local_entered':True,'post':'SAFE','reason':'NUMERICAL_CONFLICT'},'STOP_FAULT'),
      ({'has_safe':False,'local_entered':False,'post':None,'reason':'TIME_CUTOFF'},'NO_SAFE_UNRESOLVED'),
      ({'has_safe':True,'local_entered':True,'post':'THERMAL_VIOLATION','reason':'NORMAL'},'POST_SEMANTIC_CONFLICT'),
      ({'has_safe':True,'local_entered':True,'post':'INVALID_SCHEDULE','reason':'NORMAL'},'POST_SEMANTIC_CONFLICT'),
      ({'has_safe':True,'local_entered':True,'post':'UNRESOLVED','reason':'NORMAL'},'POST_UNRESOLVED')]
    status_receipts=[]
    for i,(args,expected) in enumerate(status_tests,1):
        result=proposed_status(**args)
        check(result['acceptance']==expected,f'proposed classification oracle {i}')
        status_receipts.append({'input':args,'result':result})
    facts=[]
    for path,names in [
      ('research/chapter3_g0/method.py',{'run_g0'}),
      ('research/chapter3_g0/receipts.py',{'production_dependencies','Archive','bind_manual_model_view','ReceiptBridge'}),
      ('research/chapter3_g0/local_model.py',{'build_local_model','prepare_view_initial_point','apply_view_feedback'}),
      ('research/chapter3_experiments/matlab_bridge.py',{'MatlabSession','__init__','solve'}),
      ('research/chapter3_experiments/partial_method.py',{'_solve_scene'}),
      ('research/chapter3_experiments/augmented_method.py',{'AugmentedMethodContext','AugmentedSession','assess_vector'}),
      ('research/chapter3_experiments/heft_method.py',{'run_heft'})]:
        facts.extend(locations(path,names))
    proposal={
      'schema':'g0-small-real-entry-proposal-v1','baseline_commit':BASELINE,
      'status':'INPUT_AND_BUDGET_PROPOSAL_ONLY_REAL_WIRING_NOT_READY',
      'execution_authorized':False,'real_entry_present':False,'runtime_source_freeze':'PENDING_REAL_ADAPTER_AND_SIMULATION',
      'input_file':COMMON,'input_sha256':COMMON_SHA,'instance_sha256':canonical(instance),'config_sha256':canonical(config),
      'actual_window_ms':instance['window_ms'],'ignored_config_default_window_ms':config['defaults']['window_ms'],
      'group_sizes':groups,'shared_across_scenes':sorted(k for k,v in occurrences.items() if len(v)>1),
      'methods':['G0_ONLY'],'research_method_calls_max':1,'method_seconds_max':300,
      'post_calls_max':1,'post_seconds_max':60,'method_process_wall_seconds':480,'batch_wall_seconds':720,
      'retry_count':0,'whole_heft_sa_comparison_calls':0,'initialization':'same-call original run_heft kernel including finite energy pass',
      'stages':{'stage1_deadline_root_seconds':150,'stage2_deadline_root_seconds':300,
                'block_execution_capacities':[2,4],'local_blocks_max':4,'native_requests_per_block_max':50,
                'same_root_budget':True,'shared_devices_frozen_after_S0':True},
      'builder_flags':{'include_physics':True,'fix_late_options':True,'aggregate_opp_locks':True,
         'relax_auxiliary_integrality':True,'strengthen_energy_lower_bounds':True,
         'prefilter_deadlines':True,'cumulative_precedence':False,'preeliminate_closed_anchors':True},
      'numeric_transport':{'stage1':'original matrix','stage2':'existing C selected exact-row complement/original-prefix admission',
                           'cut_max_iterations':10,'tolerances':'unchanged original native options'},
      'resource_gate_from_original_entry':deepcopy(json.loads((ROOT/'research/chapter3_method_entry_executor/results/post_status_precheck01/plan.json').read_text(encoding='utf-8'))['resource_prelaunch']),
      'no_free_inputs':['reference timetables','historical SAFE','independent HEFT results','cross-method thermal caches'],
      'post_condition':'only normally terminated matching full SAFE; zero or one fresh bounded post, no repair',
      'pending_work':['separate REAL provenance and gates','real G0 option/coefficient/model path',
                      'HEFT/x0/view/PARTIAL full aggregation','root-life/scoped-startup-and-request session',
                      'scope-aware native recorder/augmented adapter status','fresh executor/post and final hash freeze'],
      'frozen_input_or_formal_parameters_modified':False,'formal_beta_and_statistics_frozen':False,
      'next_action_requires':'bounded real wiring implementation and pure mock acceptance before one separately authorized call'}
    save(output/'plan.json',proposal)
    save(output/'source_audit.json',{'kind':'STATIC_SOURCE_READING_NOT_RUNTIME_VERIFICATION','facts':facts,
        'protected_source_sha256':protected,'preparation_source_sha256':sha(Path(__file__)),
        'native_lifetime_example':first,'next_slot_example':second,'proposed_status_examples':status_receipts,
        'real_wiring_verified':False,'production_imports':0,'scientific_calls':0})
    save(output/'checks.json',{'schema':'g0-entry-proposal-checks-v1','kind':'READONLY_AND_PROTOCOL_ORACLE_ONLY',
        'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),
        'plan_sha256':sha(output/'plan.json'),'scientific_calls':0,'real_execution_ready':False})
    return {'passed':len(checks),'total':len(checks),'real_execution_ready':False,'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(Path(args.out).resolve()),ensure_ascii=False))
