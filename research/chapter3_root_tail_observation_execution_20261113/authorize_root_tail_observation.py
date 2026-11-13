"""Bind the user's current explicit start instruction to D279; does not run science."""
from pathlib import Path
import sys,datetime
ROOT=Path(__file__).resolve().parent.parent
PACKAGE=ROOT/'work/root_tail_observer_v1'
sys.path.insert(0,str(PACKAGE))
from guard import read,save,sha,verify_plan,verify_approval
p=verify_plan(PACKAGE/'plan.json',ROOT,PACKAGE)
expected='fa49d83b3252108de870e3930739ceb3a27cfc56b65d03ec4decf7cb5aa8f0bc'
assert sha(PACKAGE/'plan.json')==expected
assert not (ROOT/p['execution_directory']).exists(),'Single-use ledger already exists; never resume or retry'
a=read(PACKAGE/'approval.template.json')
a.update(approved=True,user_decision_reference={
    'kind':'direct_user_instruction_in_current_chat',
    'verbatim':'开始吧',
    'context':'Direct reply to D279 completion and readiness for exactly one independent saved C_noheur observation call',
    'subject_commit':'223097d2749249552087cca42336dda3ab2dd49a',
    'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope':'600 method / 550 response; frozen dynamic allocation; one MATLAB session and one MILP request maximum; no retuning, rebuild, LP probe, retry or follow-on experiment'})
verify_approval(a,expected)
save(ROOT/'work/root_tail_observation_approval_20261113.json',a)
print('New user approval recorded for frozen plan '+expected+'; no scientific execution by this script.')
