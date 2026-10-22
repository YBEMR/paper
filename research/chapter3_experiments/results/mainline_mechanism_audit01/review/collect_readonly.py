"""K169 targeted immutable report/archive extraction; no scientific imports."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
RESULTS=REPO/'research/chapter3_experiments/results'
PILOT_COMMIT='a8ecd41e41010f13b34962f057323bcd3624b9a2'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(name,v):
    with (HERE/name).open('x',encoding='utf-8') as s:json.dump(v,s,ensure_ascii=False,indent=2);s.write('\n')

def main():
    reports={}
    for code,name in [('C12','共享频域驻留与分源功率导致的设备选择上下文翻转'),
                      ('C17','前驱冲突与最低电热响应构造的安全能量下界审查'),
                      ('C18','主线搜索域审计与跨设备合法修复机制创新性闸门')]:
        original=f'research/hetero_thermal_pilot/{code}_{name}_20261022.md'
        data=subprocess.check_output(['git','show',PILOT_COMMIT+':'+original],cwd=REPO)
        destination=HERE/(code+'_source.md')
        with destination.open('xb') as s:s.write(data)
        blob=subprocess.check_output(['git','rev-parse',PILOT_COMMIT+':'+original],cwd=REPO).decode('ascii').strip()
        reports[code]={'commit':PILOT_COMMIT,'git_path':original,'blob':blob,'snapshot_sha256':sha(destination)}
    results={}
    for case,camp in [('base__R1','p0_execution01'),('base__R3','p0_resume01')]:
        path=RESULTS/camp/'calls'/case/'anchor_linked4/wrapper_raw_result.json'
        raw=read(path)
        phases=[]
        for phase in raw['phases']:
            condition=phase['condition']
            phases.append({'phase_index':phase['phase_index'],'name':phase['name'],
                'opened_by_scene':phase['opened_by_scene'],'condition_protocol':condition['protocol'],
                'shared_deployment':condition['shared_deployment'],
                'seed_options_by_scene':condition['seed_options_by_scene'],
                'warm_options_by_scene':condition.get('warm_options_by_scene'),
                'started_at_s':phase.get('started_at_s'),'completed_at_s':phase.get('completed_at_s')})
        results[case]={'raw_archive_path':path.relative_to(REPO).as_posix(),'sha256':sha(path),
            'shared_deployment':raw['shared_deployment'],'shared_stage_ids':raw['shared_stage_ids'],
            'control_policy':raw['control_policy'],'global_deployment_search_performed':raw['global_deployment_search_performed'],
            'phases':phases,'linked_record_contract':raw['linked_record_contract'],
            'safe_upper_bound_J':raw['safe_upper_bound_J'],'no_new_evaluation':True}
    sources={}
    for name in ['p0_batch/dispatch.py','run_neighborhood_diagnostic.py','run_four_method_comparison.py',
        'run_linked_pair.py','run_augmented_pair.py','linked_method.py','linked_neighborhood.py','neighborhood.py',
        'partial_bounds.py','milp.py','milp_coefficients.py','schedules.py','control_policy.py',
        'heft_method.py','sa_method.py','shared_search.py']:
        p=REPO/'research/chapter3_experiments'/name
        sources[p.relative_to(REPO).as_posix()]=sha(p)
    save('facts.json',{'protocol':'K169-independent-targeted-inheritance-facts-v1',
        'pilot_reports':reports,'pilot_worktree_not_updated':True,
        'pilot_worktree_available_head':'e595581bd5780f8b22561f1df728d73d824c275a',
        'immutable_reports_read_via_local_git_show':True,'P0_targeted_archives':results,
        'main_sources_sha256':sources,'scientific_calls':0,
        'scientific_scope':'Archived JSON and source text only; no imports or calls to builders, candidate evaluators, thermal kernels or solvers.'})
    print({'pilot_reports':len(reports),'targeted_P0_calls':len(results),'sources':len(sources),'scientific_calls':0})

if __name__=='__main__':main()
