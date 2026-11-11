"""Freeze then run the one bounded validation batch; never a full R1 model."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
now=lambda:datetime.now(timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def save(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def freeze():
    expected={'research/chapter3_experiments/milp.py':'98c1ad5735d06e07ad8cb89e8f90e99542c1a1142ef2e7b42439fa47d5eec182',
              'research/chapter3_experiments/joint_state_support.py':'d4f7ee5916d5bb935f11852a5969d04379e11adde1e015b8e248cdb6f03c979c'}
    for name,value in expected.items():assert sha(REPO/name)==value,name
    for script in ['test_joint_state_support.py','test_option_support_structural.py']:
        old=subprocess.check_output(['git','show','fe6216afcd0e8d94742adbc0ff62d70651dd60ba:research/chapter3_experiments/'+script],cwd='/workspace/paper_publish_autol_lp_20261111')
        assert hashlib.sha256(old).hexdigest()==sha(REPO/'research/chapter3_experiments'/script),script
    legacy=HERE/'legacy_joint';cache=HERE/'cache_checks'
    commands=[['python3','-B','research/chapter3_experiments/test_joint_state_support.py','freeze','--output',str(legacy.relative_to(REPO))],
        ['python3','-B','research/chapter3_experiments/test_joint_audit_cache.py','freeze','--output',str(cache.relative_to(REPO)),'--legacy',str(legacy.relative_to(REPO)),'--reuse-baseline',str((HERE.parent/'cache_checks').relative_to(REPO))]]
    for ordinal,command in enumerate(commands):
        with (HERE/f'freeze_{ordinal}.stdout.log').open('xb') as out,(HERE/f'freeze_{ordinal}.stderr.log').open('xb') as err:
            subprocess.run(command,cwd=REPO,stdout=out,stderr=err,check=True)
    expected.update({str((REPO/'research/chapter3_experiments'/name).relative_to(REPO)):sha(REPO/'research/chapter3_experiments'/name)
        for name in ['test_joint_audit_cache.py','test_joint_state_support.py','test_option_support_structural.py']})
    save('plan.json',dict(frozen_utc=now(),baseline_commit='fe6216afcd0e8d94742adbc0ff62d70651dd60ba',
        source_sha256=expected,launcher_sha256=sha(Path(__file__)),
        test_plans_sha256={str(p.relative_to(REPO)):sha(p) for p in [legacy/'plan.json',cache/'plan.json']},
        freeze_commands=commands,total_budget_s=240,maximum_thermal_calls=64,expected_thermal_calls=24,previous_thermal_calls=36,expected_cumulative_thermal_calls=60,
        original_joint_tests=7,old_structural_tests=8,new_cache_tests=6,full_R1_models=0,solver_calls=0,
        retries=False,correctness_revision=2,notes='Necessary context-identity correctness repair; prior revision retained and cumulative budget charged. Synthetic audit-only mutations do not change research inputs.'))


def run():
    plan=json.loads((HERE/'plan.json').read_text())
    assert sha(Path(__file__))==plan['launcher_sha256']
    for name,value in {**plan['source_sha256'],**plan['test_plans_sha256']}.items():assert sha(REPO/name)==value,name
    ledger=json.loads((HERE.parent/'cumulative_budget_ledger.json').read_text())
    remaining=ledger['remaining_test_wall_s']
    assert ledger['rev1']['thermal_calls']==36 and remaining>0
    start=time.monotonic();deadline=start+remaining;started=now()
    save('batch_claim.json',dict(started_utc=started,pid=os.getpid(),plan_sha256=sha(HERE/'plan.json')))
    commands=[['python3','-B','research/chapter3_experiments/test_joint_state_support.py','run','--output',str((HERE/'legacy_joint').relative_to(REPO))],
        ['python3','-B','research/chapter3_experiments/test_option_support_structural.py','--output',str((HERE/'old_structural').relative_to(REPO))],
        ['python3','-B','research/chapter3_experiments/test_joint_audit_cache.py','run','--output',str((HERE/'cache_checks').relative_to(REPO))]]
    receipts=[]
    for ordinal,command in enumerate(commands):
        at=now();begin=time.monotonic();env=os.environ.copy();env['PRUNING_OPT_VALIDATION_DEADLINE']=str(deadline)
        with (HERE/f'command_{ordinal}.stdout.log').open('xb') as out,(HERE/f'command_{ordinal}.stderr.log').open('xb') as err:
            process=subprocess.Popen(command,cwd=REPO,stdout=out,stderr=err,env=env)
            try:rc=process.wait(timeout=max(0,deadline-time.monotonic()));expired=False
            except subprocess.TimeoutExpired:process.kill();rc=process.wait();expired=True
        receipts.append(dict(argv=command,started_utc=at,ended_utc=now(),wall_s=time.monotonic()-begin,returncode=rc,watchdog_expired=expired))
        if rc or expired:break
    success=len(receipts)==len(commands) and all(r['returncode']==0 and not r['watchdog_expired'] for r in receipts)
    save('command_receipts.json',dict(started_utc=started,ended_utc=now(),wall_s=time.monotonic()-start,records=receipts,passed=success))
    print(json.dumps(receipts,indent=2));raise SystemExit(0 if success else 1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    {'freeze':freeze,'run':run}[args.action]()
