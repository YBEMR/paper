"""Freeze the human-authorized six K172 calls; does not execute a method."""
import argparse
import ast
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import platform
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent.parent.parent))
from research.chapter3_experiments.linked_ablation_execution.registry import (
    REPO,SCIENCE,OUT,GLOBAL_CLAIM,PROTOCOL,BUDGETS,read,sha,canonical,write_new,validate_declaration)

PREP=SCIENCE/'results/linked_ablation_preparation01'


def matlab_path():
    tree=ast.parse((SCIENCE/'matlab_bridge.py').read_text('utf-8-sig'))
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(
        isinstance(t,ast.Name) and t.id=='DEFAULT_MATLAB' for t in n.targets))
    return str(Path(ast.literal_eval(assignment.value.args[0])).resolve())


def make_declaration(gates):
    proposal=read(PREP/'preparation02/proposal.json')
    source=dict(proposal['source_sha256'])
    for p in sorted(HERE.glob('*.py')):
        source[p.relative_to(REPO).as_posix()]=sha(p)
    dependency_paths=[PREP/'protocol.md',PREP/'preparation02/proposal.json',
        PREP/'precheck/run02/checks.json',PREP/'proposal_checks_run02/checks.json',
        PREP/'review/final_review02.json',PREP/'review/final_manifest02.json']+list(gates)
    dependencies={p.relative_to(REPO).as_posix():sha(p) for p in dependency_paths}
    cases=deepcopy(proposal['cases'])
    for case in cases:
        for recipe in case['recipes'].values():recipe['scientific_execution_authorized']=True
    slots=deepcopy(proposal['slots'])
    for slot in slots:slot['state']='AUTHORIZED_UNSTARTED'
    declaration={'protocol':PROTOCOL,'authorized':True,'scientific_execution_enabled':True,
        'authorization_origin':'direct human K173 message, six K172 calls only',
        'authorization':('用户批准P0/R1、R3各A/B/C共6次；每次300秒累计1800；每有效安全结果最多一次60秒post累计360；'
            '日历3600；先脚本身份与模拟检查后执行，不补跑不改算法/物理/参数/初解/设备支持/安全门；技术异常按原停；'
            '不扩R2/R4/R5，不启动K168或期限24次。'),
        'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'baseline_commit':'20fb232a81d69782b8ebd1fc1972a6bc96fff09e',
        'proposal_sha256':sha(PREP/'preparation02/proposal.json'),
        'output_directory':OUT.relative_to(REPO).as_posix(),
        'global_claim_path':GLOBAL_CLAIM.relative_to(REPO).as_posix(),
        'cases':cases,'slots':slots,'budgets':BUDGETS,
        'clock_start_policy':proposal['clock_start_policy'],
        'solver_options':proposal['solver_options'],
        'source_sha256':source,'scientific_source_sha256':proposal['source_sha256'],
        'protected_archive_sha256':proposal['archive_readonly_sha256'],
        'frozen_dependency_sha256':dependencies,
        'environment':{'python_executable':str(Path(sys.executable).resolve()),
            'python_version':sys.version,'platform':platform.platform(),
            'matlab_executable':matlab_path(),
            'matlab_executable_sha256':sha(matlab_path()),
            'license_checked_by':'Only the first billed original session startup; no free license run'},
        'no_retry':True,'new_bound_filter':False,'K168_authorized_here':False,
        'deadline_remainder_authorized_here':False,
        'acceptance':'Only current-call original-input full continuous SAFE formed before300, normal status/isolation, unique independent post',
        'post_rule':'no search, repair, new_U or U replacement; one <=60s only after normal method admission'}
    validate_declaration(declaration)
    return declaration


def main(paths):
    if GLOBAL_CLAIM.exists() or (OUT/'declaration.json').exists():
        raise FileExistsError('Already frozen or consumed; no replacement or restart')
    for p in paths:
        report=read(p)
        if report.get('passed') is not True:raise ValueError('A pure precheck did not pass: '+str(p))
    if not paths:raise ValueError('Explicit pure execution-chain gates required')
    declaration=make_declaration(paths)
    OUT.mkdir(parents=True,exist_ok=True)
    write_new(OUT/'declaration.json',declaration)
    write_new(OUT/'declaration_binding.json',{
        'protocol':PROTOCOL,'declaration_sha256':sha(OUT/'declaration.json'),
        'authorized_six_once':True,'research_calls_consumed_at_freeze':0,
        'research_seconds_reserved_at_freeze':0,'post_calls_consumed_at_freeze':0})
    for name,digest in declaration['source_sha256'].items():
        destination=OUT/'source_snapshot'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,destination)
        if sha(destination)!=digest:raise ValueError('Snapshot mismatch')
    write_new(OUT/'ledger.json',{'protocol':PROTOCOL,'state':'DECLARED','consumed':0,
        'reserved_method_budget_s':0,'post_consumed':0,'reserved_post_budget_s':0,
        'calls':[],'active':None})
    print('FROZEN: six calls, no research started, declaration '+sha(OUT/'declaration.json'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--gate',type=Path,action='append',required=True)
    main(parser.parse_args().gate)
