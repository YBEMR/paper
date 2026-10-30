"""File-only preparation of an UNAPPROVED plan; never launches workers."""
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent/'frozen'

def main():
    import sys
    sys.path.insert(0,str(ROOT))
    from research.chapter3_g0_real_entry.prepare import freeze
    from research.chapter3_g0_real_entry.launch_contract import save,sha,digest,verify_plan,load_authorized,HERE
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if head!='e4184dcb6fae272b11b6ebd1278dd975c6405554':
        raise ValueError('PREPARATION_SOURCE_COMMIT_DRIFT')
    changed=subprocess.check_output(['git','diff','--name-only','HEAD','--',
        'research/chapter3_g0','research/chapter3_g0_real_entry','research/chapter3_experiments',
        'research/chapter3_method_entry_executor'],cwd=ROOT,text=True)
    if changed.strip():raise ValueError('RUNTIME_WORKTREE_DRIFT')
    plan=freeze(OUT)
    plan.update(execution_source_commit=head,
        predecessor_consumed_plan_sha256='5f93b9149cdfd07f38ca972c79d89787c8b46273c0e106c528b3f0078a4f5bf9',
        lineage_note='basis_commit is the original entry-contract lineage; execution_source_commit and source_sha256 bind this version',
        purpose='one C01 G0 public-startup connection check; no ranking or automatic retry')
    verify_plan(plan);save(OUT/'plan.json',plan)
    template=OUT/'approval_TEMPLATE_NOT_AUTHORIZED.json'
    approval=json.loads(template.read_text(encoding='utf-8'))
    approval['plan_sha256']=sha(OUT/'plan.json');save(template,approval)
    denied=False
    try:load_authorized(OUT/'plan.json',template,sha(template))
    except PermissionError as e:denied=str(e)=='NO_MATCHING_USER_RESEARCH_APPROVAL'
    if not denied:raise AssertionError('PENDING_TEMPLATE_MUST_NOT_AUTHORIZE_REAL')
    claim=HERE/'claims'/(sha(OUT/'plan.json')+'.json')
    if claim.exists():raise ValueError('NEW_PLAN_ALREADY_CONSUMED')
    manual=ROOT/'research/chapter3_g0_real_entry/results/public_startup_final01'
    manifest=json.loads((manual/'source_manifest.json').read_text(encoding='utf-8'))
    drift=[p for p,h in manifest['source_sha256'].items() if sha(ROOT/p)!=h]
    if drift:raise ValueError('TESTED_SOURCE_DRIFT:'+str(drift))
    old=ROOT/'research/chapter3_g0_real_entry/results/real_entry_plan01/plan.json'
    if sha(old)!=plan['predecessor_consumed_plan_sha256']:raise ValueError('OLD_PLAN_DRIFT')
    record=dict(kind='FILE_ONLY_PREPARATION_NOT_REAL_EXECUTION',
        plan_sha256=sha(OUT/'plan.json'),execution_source_commit=head,
        input_sha256=plan['input_sha256'],source_manifest_sha256=digest(plan['source_sha256']),
        frozen_runtime_files=len(plan['source_sha256']),tested_active_files=len(manifest['source_sha256']),
        source_drift=drift,pending_approval_rejected=denied,new_claim_exists=False,
        execution_authorized=False,can_launch_now=False,old_claim_reusable=False,
        real_scientific_calls=0,matlab_processes=0,thermal_integrations=0,
        method_budget_s=300,post_budget_s=60,method_process_cap_s=480,batch_cap_s=720,
        host_gate='MUST_RECHECK_AFTER_NEW_USER_APPROVAL_BEFORE_CONSUMING_CLAIM')
    save(OUT/'preparation_checks.json',record)
    print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
