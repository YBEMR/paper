"""Pure metadata/AST checks for the disarmed K172 recipe; no science imports."""
import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.abc
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
BLOCKED=[]


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'scipy','numpy','matlab','milp','thermal','schedules',
                'inputs','linked_method','neighborhood_method','timing','matlab_bridge',
                'subprocess','socket'}:
            BLOCKED.append(fullname)
            raise RuntimeError('Preparation refuses scientific/process imports')
        return None


def audit(event,args):
    if event in ('subprocess.Popen','os.system','os.posix_spawn','socket.connect'):
        BLOCKED.append(event)
        raise RuntimeError('Preparation refuses process/network execution')


def main(output):
    if output.exists():raise FileExistsError('Never overwrite checks')
    before=hashlib.sha256((HERE/'prepare.py').read_bytes()).hexdigest()
    sys.meta_path.insert(0,NoScience());sys.addaudithook(audit)
    spec=importlib.util.spec_from_file_location('K172_disarmed_prepare',HERE/'prepare.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    proposal=module.build_proposal()
    checks={}
    checks['explicit_pending_zero_consumption_no_claim']=all([
        proposal['authorized'] is False,proposal['scientific_execution_enabled'] is False,
        proposal['preparation_only'] is True,proposal['research_calls_consumed']==0,
        proposal['research_seconds_reserved']==0,proposal['native_requests_consumed']==0,
        proposal['real_launcher_implemented'] is False,proposal['claim'] is None])
    checks['six_fixed_once_only_slots']=([(x['case_id'],x['variant']) for x in proposal['slots']]==[
        ('base__R1','A'),('base__R1','B'),('base__R1','C'),
        ('base__R3','C'),('base__R3','B'),('base__R3','A')]
        and all(x['run_once'] and x['state']=='PENDING_USER_CONFIRMATION' for x in proposal['slots']))
    checks['full_and_reduced_budgets_separate_post']=all(
        b['method_seconds_total_max']+b['post_seconds_total_max']==b['method_plus_post_seconds_max']
        for b in (proposal['budget_proposal']['recommended_full_development'],
                  proposal['budget_proposal']['reduced_B_C_only']))
    checks['both_cases_all_existing_entry_keywords']=all(module.entry_accepts(c['recipes'][v])
        for c in proposal['cases'] for v in ('A','B','C'))
    pairs=[]
    for c in proposal['cases']:
        a,b,cc=(c['recipes'][v] for v in ('A','B','C'))
        bk,ck=deepcopy(b['kwargs']),deepcopy(cc['kwargs'])
        off,on=bk.pop('preeliminate_closed_anchors'),ck.pop('preeliminate_closed_anchors')
        pairs.append(bk==ck and off is False and on is True)
    checks['B_C_only_one_parameter_difference']=all(pairs)
    checks['A_uses_full_root_not_old60']=all(c['recipes']['A']['kwargs']['scene_slice_s']==150
        and c['recipes']['A']['kwargs']['seconds']==300
        and 'preeliminate_closed_anchors' not in c['recipes']['A']['kwargs']
        and 'linked_opened_by_scene' not in c['recipes']['A']['kwargs']
        and c['recipes']['A']['second_phase'] is False for c in proposal['cases'])
    checks['same_initialization_and_builder_options_per_case']=all(
        all(c['recipes'][v]['kwargs'][key]==c['recipes']['A']['kwargs'][key] for v in ('B','C'))
        for c in proposal['cases'] for key in ('shared_deployment','builder_options','opened_by_scene'))
    checks['stage_openings_2_then4']=all(
        all(len(x)==2 for x in c['common']['first_opened_by_scene'].values()) and
        all(len(x)==4 for x in c['common']['second_opened_by_scene'].values()) for c in proposal['cases'])
    forbidden_initial={'seed_candidate','warm_candidate','seed_receipt','warm_receipt','safe_upper_bound_J','cache'}
    checks['no_old_candidate_or_U_supplied_as_argument']=all(
        not forbidden_initial.intersection(c['recipes'][v]['kwargs'])
        and c['recipes'][v]['new_bound_filter'] is False
        for c in proposal['cases'] for v in ('A','B','C'))
    try:module.recipe('D',proposal['cases'][0]['common'])
    except ValueError:checks['unknown_version_rejected']=True
    else:checks['unknown_version_rejected']=False
    checks['source_reading_preparation_has_no_run_entry']=not any(
        isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in ('run','execute','launch')
        for n in ast.parse((HERE/'prepare.py').read_text('utf-8')).body)
    checks['original_sources_hash_and_input_ID_verified_by_generator']=len(proposal['source_sha256'])==254
    checks['no_scientific_module_or_process_attempts']=not BLOCKED
    after=hashlib.sha256((HERE/'prepare.py').read_bytes()).hexdigest()
    checks['preparation_source_unchanged']=before==after
    result={'protocol':'K172-disarmed-proposal-metadata-AST-checks-v1','passed':all(checks.values()),
        'checks':checks,'count':len(checks),'preparation_source_sha256':after,
        'source_sha256':proposal['source_sha256'],'archive_sha256':proposal['archive_readonly_sha256'],
        'guard':{'blocked_attempts':BLOCKED,'all_zero':not BLOCKED,
            'matrix_builds':0,'optimization_calls':0,'thermal_calls':0,
            'formal_evaluations':0,'research_calls':0},
        'scope':'Read-only hashes/recipes/AST only; not an end-to-end execution or an authorization'}
    output.mkdir(parents=True)
    (output/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'passed':result['passed'],'checks':len(checks),'blocked':BLOCKED}))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    main(p.parse_args().out)
