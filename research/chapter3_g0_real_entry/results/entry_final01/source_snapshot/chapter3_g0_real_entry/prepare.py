"""Freeze an unapproved single-run plan using file reads only."""
import argparse
import sys
from .launch_contract import ROOT,HERE,INPUT,INPUT_SHA,SCOPE,read,save,sha,verify_plan,digest


def freeze(output):
    from pathlib import Path
    output=Path(output)
    if output.exists():raise ValueError('NEW_PLAN_DIRECTORY_REQUIRED')
    b=read(ROOT/'research/chapter3_g0/tests/fixtures/protected_baseline.json')
    sources=dict(b['protected_source_sha256'])
    for folder in (HERE,ROOT/'research/chapter3_g0',ROOT/'research/chapter3_method_entry_executor'):
        for p in folder.glob('*.py'):sources[str(p.relative_to(ROOT)).replace('\\','/')]=sha(p)
    # MATLAB worker and shared numerical helpers are part of actual execution.
    for p in (ROOT/'research/chapter3_experiments').glob('*.m'):
        sources[str(p.relative_to(ROOT)).replace('\\','/')]=sha(p)
    plan={'schema':'g0-real-single-entry-v1','basis_commit':'b76c01990ce219995751a83e74e69108eb205569',
          'input':INPUT,'input_sha256':INPUT_SHA,'scope':dict(SCOPE),
          'algorithm':{'fixed_D0':True,'block_capacities':[2,4],'stage1_deadline_root_s':150},
          'python_executable':sys.executable.replace('\\','/'),
          'matlab_executable':'F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe',
          'source_sha256':sources,'execution_authorized':False,
          'purpose':'one C01 G0 connection check, not algorithm ranking'}
    plan['executable_sha256']={p:sha(p) for p in (plan['python_executable'],plan['matlab_executable'])}
    verify_plan(plan)
    output.mkdir(parents=True)
    save(output/'plan.json',plan)
    save(output/'approval_TEMPLATE_NOT_AUTHORIZED.json',{
        'status':'PENDING_USER_APPROVAL','plan_sha256':sha(output/'plan.json'),
        'input_sha256':INPUT_SHA,'source_manifest_sha256':digest(sources),'scope':dict(SCOPE),
        'user_authorization_reference':None,
        'notice':'工程准备授权不构成科研批准；不得由执行器自行填成APPROVED。'})
    return plan


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True)
    freeze(p.parse_args().out)
