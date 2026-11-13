"""Freeze only the explicitly approved K176 two-method pair; no method call."""
import argparse
import ast
from copy import deepcopy
from pathlib import Path
import platform
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from linked_release_execution import registry as r
PREP=r.SCIENCE/'results/linked_release_integration01'

def make_declaration(gates):
    p=r.read(r.PROPOSAL);cases=[{'common':p['common'],'recipes':deepcopy(p['recipes'])}]
    for recipe in cases[0]['recipes'].values():recipe['scientific_execution_authorized']=True
    source=dict(p['source_sha256'])
    for f in sorted(HERE.glob('*.py')):source[f.relative_to(r.REPO).as_posix()]=r.sha(f)
    paths=[r.PROPOSAL,PREP/'summary.md',PREP/'checks_run03/checks.json',PREP/'review/final_review.json',PREP/'review/proposal_review.json']+[Path(x).resolve() for x in gates]
    deps={f.relative_to(r.REPO).as_posix():r.sha(f) for f in paths}
    tree=ast.parse((r.SCIENCE/'matlab_bridge.py').read_text('utf-8-sig'))
    n=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEFAULT_MATLAB' for t in n.targets))
    matlab=str(Path(ast.literal_eval(n.value.args[0])).resolve())
    archived=r.read(r.SCIENCE/'results/linked_ablation_execution01/declaration.json')['protected_archive_sha256']
    slots=[{'ordinal':i+1,'slot_id':c+'__'+v,'case_id':c,'variant':v,'method_seconds':300,'post_seconds_max':60} for i,(c,v) in enumerate(r.ORDER)]
    d={'protocol':r.PROTOCOL,'authorized':True,'scientific_execution_enabled':True,
       'authorization_origin':'direct human K176 message, two K175 R3 calls only',
       'authorization':'用户批准仅P0/R3原C→K175新版各1次300；总方法600，正常完整SAFE各至多一次60post总120，日历1200；不补跑不改规则参数/初解/安全门，不扩题或恢复K168/期限24。',
       'frozen_at_utc':r.now(),'baseline_commit':'58b089e9161e23b17653a15dfe7bb26301e42222',
       'proposal_sha256':r.sha(r.PROPOSAL),'output_directory':r.OUT.relative_to(r.REPO).as_posix(),
       'global_claim_path':r.GLOBAL_CLAIM.relative_to(r.REPO).as_posix(),
       'cases':cases,'slots':slots,'budgets':r.BUDGETS,'clock_start_policy':p['clock_start_policy'],
       'solver_options':p['solver_options'],'source_sha256':source,'scientific_source_sha256':p['source_sha256'],
       'frozen_dependency_sha256':deps,'protected_archive_sha256':archived,
       'environment':{'python_executable':str(Path(sys.executable).resolve()),'python_version':sys.version,
          'platform':platform.platform(),'matlab_executable':matlab,'matlab_executable_sha256':r.sha(matlab),
          'license_checked_by':'first billed original session only; no free license probe'},
       'no_retry':True,'new_bound_filter':False,'K168_authorized_here':False,'deadline_remainder_authorized_here':False,
       'acceptance':'Current-call full SAFE formed within 300s, normal return, identity/isolation and unique independent post; no late new U',
       'post_rule':'same frozen model/full original candidate, <=60s once; no search/repair/replacement U'}
    return r.validate_declaration(d)

def main(gates):
    if r.GLOBAL_CLAIM.exists() or (r.OUT/'declaration.json').exists():raise FileExistsError('No replace or resume')
    if not gates or any(r.read(g).get('passed') is not True for g in gates):raise ValueError('Passing pure gates required')
    d=make_declaration(gates)
    r.OUT.mkdir(exist_ok=True,parents=True);r.write_new(r.OUT/'declaration.json',d)
    r.write_new(r.OUT/'declaration_binding.json',{'protocol':r.PROTOCOL,'declaration_sha256':r.sha(r.OUT/'declaration.json'),'authorized_two_once':True,'research_calls_consumed_at_freeze':0})
    for name,h in d['source_sha256'].items():
        target=r.OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r.REPO/name,target)
        if r.sha(target)!=h:raise ValueError('Snapshot drift')
    r.write_new(r.OUT/'ledger.json',{'protocol':r.PROTOCOL,'state':'DECLARED','consumed':0,'reserved_method_budget_s':0,'post_consumed':0,'reserved_post_budget_s':0,'calls':[],'active':None})
    print('FROZEN TWO ONLY '+r.sha(r.OUT/'declaration.json'))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--gate',action='append',type=Path,required=True)
    main(parser.parse_args().gate)
