"""Freeze the authorized remaining H02 calls; no scientific computation."""
import argparse
from datetime import datetime, timezone
import hashlib,json,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent;CORE=HERE.parent;REPO=CORE.parent.parent
PRE=CORE/'results/response_information_resume_precheck01'
OUT=CORE/'results/response_information_resume01'
OLD=CORE/'results/response_information_execution01'
sys.path.insert(0,str(CORE))
from h02_pair_b0.io_contract import load_json,require_research_authorization
from h02_pair_b0.bundle import runtime_sources,verify_runtime_freeze
from h02_pair_b0.exports import verify_final_export
from h02_pair_preflight.common import candidate_identity
from h02_resume.launcher import (PROTOCOL,AUTHORIZATION_ID,SCIENTIFIC_POLICY_SHA,
                                BUDGETS,SLOTS,CLAIM_REL)

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as f:f.write((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

def freeze(gates):
    gates=[Path(p).resolve() for p in gates]
    target=PRE/'execution_declaration.json'
    if target.exists() or OUT.exists() or (REPO/CLAIM_REL).exists():raise FileExistsError('No replacement or retry')
    for path in gates:
        check=load_json(path)
        passed=check.get('passed') is True or (check.get('status')=='PASS'
            and check.get('failures')==0 and check.get('errors')==0)
        if not passed:raise ValueError('Precheck not passed: '+str(path))
    prior_decl=load_json(CORE/'results/response_information_execution_precheck01/execution_declaration.json')
    repaired='research/chapter3_experiments/h02_pair_preflight/receipts.py'
    differences=[rel for rel,wanted in prior_decl['expected_sha'].items() if digest(REPO/rel)!=wanted]
    if differences!=[repaired]:raise ValueError('Only intended receipt repair may differ: '+str(differences))
    source_change=load_json(PRE/'receipt_run01/source_change.json')
    # The functional gate and exact original-source diff are both archived.
    original=load_json(CORE/'h02_pair_b0/evidence/runtime_freeze.json')
    oldsuper=load_json(CORE/'results/response_information_execution01_supervision/terminal.json')
    if oldsuper['controller_ledger']['plan_calls_consumed']!=1 or oldsuper['controller_ledger']['audit_calls_consumed']!=0:
        raise ValueError('Original prefix consumption changed')
    if oldsuper['calendar_elapsed_s']+1100>1200:raise ValueError('Calendar cap exceeded')
    prior_files=[OLD/'slot_1/planner_public/method/result.json',
        OLD/'slot_1/planner_public/accepted_checkpoint.json',OLD/'slot_1/planner_public/job.json',
        OLD/'slot_1/controller_private/truth_H.json',OLD/'slot_1/controller_private/static_contract.json',
        OLD/'ledger/slot_1.claim.json',OLD/'authorization_claim.json',OLD/'terminal.json',
        CORE/'results/response_information_execution01_supervision/terminal.json',
        CORE/'results/response_information_execution_claim01.json',
        CORE/'results/response_information_execution_precheck01/execution_declaration.json']
    raw=load_json(prior_files[0]);packet=load_json(prior_files[2])['packet']
    verified=verify_final_export(packet,raw)
    if verified['best'] is None or verified['technical_details']:raise ValueError('Recovered export invalid')
    identity=candidate_identity(packet['planner']['instance'],raw['safe_candidate'])
    b0=CORE/'h02_pair_b0';saved=PRE/'prior_execution_identity';saved.mkdir(exist_ok=False)
    for name in ('policy.json','execution_gate.json','evidence/runtime_freeze.json'):
        with (saved/name.replace('/','_')).open('xb') as f:f.write((b0/name).read_bytes())
    policy=load_json(b0/'policy.json');gate=load_json(b0/'execution_gate.json')
    gate.update(stage='K178_DIRECT_USER_CONTINUATION',authorization_id=AUTHORIZATION_ID,
        approval_reference='Direct user 2026-10-23: fix the audit and continue the experiment without another approval',
        authorization_note='Prior slot1 plan consumed120; only its unique H audit plus plans2/3/4 and their unique H audits remain. No first-slot replan.',
        allowed_run_directory=str(OUT),authority_store=str(CORE/'results/response_information_resume_authority01'))
    require_research_authorization(gate,policy)
    (b0/'execution_gate.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    runtime=dict(original,source_files_sha256={rel:digest(p) for rel,p in runtime_sources().items()},
        policy_files_sha256={name:digest(b0/name) for name in ('policy.json','execution_gate.json')},
        K178_receipt_enclosure_repair_only=True)
    (b0/'evidence/runtime_freeze.json').write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    verify_runtime_freeze()
    files=dict(runtime_sources())
    for p in HERE.glob('*'):
        if p.is_file() and p.suffix in ('.py','.md'):files[p.relative_to(REPO).as_posix()]=p
    for p in [b0/'policy.json',b0/'execution_gate.json',b0/'evidence/runtime_freeze.json',
              CORE/'config_v01.json',CORE/'h02_pair_preflight/evidence/source_manifest.json']+prior_files:
        files[p.relative_to(REPO).as_posix()]=p
    prior={p.relative_to(REPO).as_posix():digest(p) for p in prior_files}
    declaration=dict(protocol=PROTOCOL,main_baseline_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        authorization_id=AUTHORIZATION_ID,authorization_origin=gate['approval_reference'],
        frozen_utc=datetime.now(timezone.utc).isoformat(),output_directory=str(OUT),global_claim=str(REPO/CLAIM_REL),
        calendar_limit_s=1100,prior_calendar_actual_s=oldsuper['calendar_elapsed_s'],
        budgets=BUDGETS,slots=SLOTS,policy_path=str(b0/'policy.json'),gate_path=str(b0/'execution_gate.json'),
        scientific_policy_sha256=SCIENTIFIC_POLICY_SHA,prior_plan_calls_consumed=1,prior_method_budget_consumed_s=120,
        cumulative_plan_calls_max=4,cumulative_audit_calls_max=4,cumulative_scientific_budget_s=720,
        recovered_candidate_semantic_sha256=identity['candidate_semantic_sha256'],
        recovered_candidate_raw_sha256=identity['candidate_raw_sha256'],
        prior_sha256=prior,expected_sha={rel:digest(p) for rel,p in files.items()},
        prechecks_sha256={p.relative_to(REPO).as_posix():digest(p) for p in gates},
        no_retry=True,no_first_planner_rerun=True,K175_paused=True,K168_authorized=False,deadline_24_authorized=False)
    for rel,p in files.items():
        snapshot=PRE/'source_snapshot'/rel;snapshot.parent.mkdir(parents=True,exist_ok=True)
        with snapshot.open('xb') as f:f.write(p.read_bytes())
    write_new(target,declaration)
    print(json.dumps({'declaration':str(target),'sha256':digest(target),'files':len(files),'new_scientific_calls':0}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--gate',action='append',type=Path,required=True)
    freeze(p.parse_args().gate)
