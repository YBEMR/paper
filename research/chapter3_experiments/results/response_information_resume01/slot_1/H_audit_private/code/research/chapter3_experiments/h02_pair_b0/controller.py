"""Versioned four-slot controller. B0 gate prevents every real launch.
Launches one private Python worker per plan, and at most one worker per H audit.
"""
import json,os,subprocess,sys,time,uuid
from pathlib import Path
from h02_pair_preflight.common import BASE_SHA,POLICY,require,sha,encoded,byte_sha,copy
from h02_pair_preflight.paired_response_input_view import paired_response_input_view,planner_packet
from h02_pair_preflight.contracts import static_monotonicity_contract
from h02_pair_preflight.receipts import technical_issues
from .io_contract import HERE,load_json,atomic_json,policy_files,require_research_authorization
from .budget import RootClock,watchdog_decision,RootBudgetExpired
from .bundle import build_bundle,verify_runtime_freeze
from .exports import verify_final_export

class CallLedger:
    def __init__(self,root,*,kind='REAL'):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.kind=kind; self.stopped=False
        self.stop_path=self.root/'STOP.json'
    def stop(self,reason):
        self.stopped=True
        if not self.stop_path.exists(): atomic_json(self.stop_path,{'reason':reason,'kind':self.kind})
    def claim(self,name,details):
        require(not self.stopped and not self.stop_path.exists(),'STOP_LATCHED')
        require(isinstance(name,str) and name.replace('_','').replace('-','').isalnum(),'UNSAFE_CLAIM_NAME')
        value={'name':name,'kind':self.kind,'nonce':uuid.uuid4().hex,**details}
        # Atomic exclusive create; launch failure, timeout and crash cannot reclaim it.
        with (self.root/(name+'.claim.json')).open('xb') as f: f.write(encoded(value)); f.flush(); os.fsync(f.fileno())
        return value

def claim_authorization_once(gate,destination):
    """Fixed authority store survives changes of output dir or code checkout.
    Gate identity/path is frozen; same authorization ID can never start twice.
    """
    destination=Path(destination).resolve()
    require(destination==Path(gate['allowed_run_directory']).resolve(),'UNAPPROVED_RUN_DIRECTORY')
    identifier=gate['authorization_id']
    require(identifier and identifier.replace('-','').replace('_','').isalnum(),'INVALID_AUTHORIZATION_ID')
    store=Path(gate['authority_store']); require(store.is_absolute(),'AUTHORITY_STORE_NOT_ABSOLUTE'); store.mkdir(parents=True,exist_ok=True)
    claim={'authorization_id':identifier,'run_directory':str(destination),'gate_sha256':sha(gate),'once_consumed_before_launch':True}
    with (store/(identifier+'.claim.json')).open('xb') as f: f.write(encoded(claim)); f.flush(); os.fsync(f.fileno())
    return claim

def frozen_candidate(packet,result,truth,static_contract,runtime_sha):
    checked=verify_final_export(packet,result); best=checked['best']
    require(best is not None,'NO_PLAN_CANDIDATE')
    identity=checked['identity']; raw=encoded(best['candidate'])
    return dict(token_id=uuid.uuid4().hex,source_commit_sha=BASE_SHA,problem_id=packet['problem_id'],view=packet['view'],plan_sha256=packet['plan_sha256'],truth_H_sha256=sha(truth['instance']),truth_H_config_sha256=sha(truth['config']),physical_projection_sha256=packet['physical_projection_sha256'],accuracy_sha256=packet['accuracy_sha256'],policy_id=POLICY,p1_p2_static_passed=static_contract['passed'],static_contract_sha256=sha(static_contract),planning_top_state='SAFE',planning_receipt_sha256=sha(best['evaluation']),plan_formed_at_elapsed_s=best['evaluation']['completed_at_elapsed_s'],candidate_raw_sha256=byte_sha(raw),candidate_semantic_sha256=identity['candidate_semantic_sha256'],candidate_json=raw.decode('utf-8'),runtime_freeze_sha256=runtime_sha)

def supervise(job,bundle_info,bundle,output,policy,*,mode='real',clock=time.monotonic,popen=subprocess.Popen,sleep=time.sleep):
    output=Path(output); require(output.exists(),'MISSING_FRESH_WORKER_DIRECTORY')
    jobpath=output/'job.json'; atomic_json(jobpath,job)
    env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ}
    command=[sys.executable,'-I','-B',bundle_info['worker'],'--job',str(jobpath.resolve()),'--job-sha',sha(job),'--bundle',str(Path(bundle).resolve()),'--output',str(output.resolve()),'--mode',mode]
    with (output/'stdout.log').open('wb') as stdout,(output/'stderr.log').open('wb') as stderr:
        RootClock(job['limit_s'],origin=job['root_origin'],clock=clock).check()
        process=popen(command,cwd=output,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        transitions=[]; last=None; killed=False
        while process.poll() is None:
            phase=watchdog_decision(clock(),job['root_origin'],job['limit_s'],policy['watchdog_grace_s'])
            if phase!=last: transitions.append({'phase':phase,'elapsed_s':clock()-job['root_origin']}); last=phase
            if phase=='TERMINATE': process.kill(); process.wait(timeout=5); killed=True; break
            sleep(policy['watchdog_poll_s'])
        outcome={'returncode':process.returncode,'watchdog_killed':killed,'watchdog_transitions':transitions,'process_wall_s_from_root':clock()-job['root_origin'],'method_or_audit_limit_s':job['limit_s'],'archive_grace_s':policy['watchdog_grace_s'],'no_new_evidence_after_deadline':True}
    atomic_json(output/'process_receipt.json',outcome)
    return outcome

def prepare_public_slot(root,slot,callroot):
    """Must be invoked AFTER constructing this slot's 120s root."""
    root.check(); pair=paired_response_input_view(slot['problem_id']); root.check()
    contract=static_monotonicity_contract(pair['truth_H']['config'],pair['truth_H']['instance'],pair['planner_R']['instance']); root.check()
    packet=planner_packet(pair,slot['view']); root.check()
    private=callroot/'controller_private'; private.mkdir()
    atomic_json(private/'truth_H.json',pair['truth_H'])
    atomic_json(private/'static_contract.json',contract)
    return packet,pair['truth_H'],contract,private

def run_four_slots(destination):
    policy,gate=policy_files(); require_research_authorization(gate,policy)
    # No input, process, source-bundle work or claim occurs before this gate.
    verify_runtime_freeze()
    destination=Path(destination).resolve(); require(not destination.exists(),'RUN_DIRECTORY_REUSED')
    authorization_claim=claim_authorization_once(gate,destination)
    destination.mkdir(parents=True); atomic_json(destination/'authorization_claim.json',authorization_claim)
    ledger=CallLedger(destination/'ledger'); outputs=[]
    for slot in policy['slots']:
        root=RootClock(120)  # before per-slot source verification, read/expansion/masking/transport/import
        name='slot_'+str(slot['ordinal']); callroot=destination/name; callroot.mkdir()
        plan_claim=ledger.claim(name,{'slot':slot,'budget_s':120,'root_origin':root.origin})
        token=None; phase='PLAN'; audit_claim=None
        try:
            packet,truth,contract,private=prepare_public_slot(root,slot,callroot)
            planner=callroot/'planner_public'; planner.mkdir(); bundle=planner/'code'
            bundle_info=build_bundle(bundle); root.check()
            job={'kind':'planner','root_origin':root.origin,'limit_s':120,'packet':packet,'ordinal':slot['ordinal'],'launch_claim_sha256':sha(plan_claim)}
            process=supervise(job,bundle_info,bundle,planner,policy)
            if process['watchdog_killed'] or process['returncode']!=0:
                # Preserve checkpoints and raw output, but no guessed final SAFE/export/audit.
                outputs.append({'slot':slot,'plan_status':'PLAN_UNRESOLVED','reason':'PLANNER_PROCESS_FAILURE_OR_HARD_CUTOFF','checkpoint_preserved_for_diagnosis_only':True})
                ledger.stop('PLANNER_PROCESS_FAILURE_OR_HARD_CUTOFF'); break
            returned=load_json(planner/'worker_return.json'); require(returned['job_sha256']==sha(job),'PLANNER_RETURN_IDENTITY')
            payload=returned['payload']; raw=payload['raw_method_result']; checked=verify_final_export(packet,raw)
            atomic_json(private/'raw_planner_return.json',returned)
            if checked['technical_details']:
                best=checked['best']
                outputs.append({'slot':slot,'plan_status':'PLAN_SAFE_WITH_TECHNICAL_STOP' if best is not None else 'PLAN_UNRESOLVED','technical_failure':True,'technical_details':checked['technical_details'],'known_safe_candidate_sha256':best['candidate_sha256'] if best else None,'known_safe_upper_bound_J':best['evaluation']['safe_upper_bound_J'] if best else None,'post_audit_not_started':True})
                ledger.stop('PLANNER_TECHNICAL_FAILURE'); break
            if checked['best'] is None:
                outputs.append({'slot':slot,'plan_status':'PLAN_NO_SAFE' if raw.get('reason')=='DECLARED_SEARCH_COMPLETED' else 'PLAN_UNRESOLVED'}); continue
            token=frozen_candidate(packet,raw,truth,contract,bundle_info['bundle_sha256']); atomic_json(private/'frozen_candidate.json',token)
            # Independent one-use post root starts before reading sealed truth/token.
            phase='AUDIT'; post=RootClock(60)
            claim=ledger.claim('audit_'+str(slot['ordinal']),{'token_sha256':sha(token),'budget_s':60,'root_origin':post.origin})
            audit_claim=claim
            truth_for_audit=load_json(private/'truth_H.json'); token_for_audit=load_json(private/'frozen_candidate.json'); post.check()
            auditdir=callroot/'H_audit_private'; auditdir.mkdir(); auditbundle=auditdir/'code'
            auditinfo=build_bundle(auditbundle); post.check()
            auditjob={'kind':'audit','ordinal':slot['ordinal'],'launch_claim_sha256':sha(claim),'root_origin':post.origin,'limit_s':60,'truth':truth_for_audit,'token':token_for_audit,'audit_claim_sha256':sha(claim)}
            auditprocess=supervise(auditjob,auditinfo,auditbundle,auditdir,policy)
            if auditprocess['watchdog_killed'] or auditprocess['returncode']!=0:
                outputs.append({'slot':slot,'plan_status':'PLAN_SAFE','post':{'audit_status':'TRUE_H_UNRESOLVED','audit_consumed':True,'reason':'AUDIT_PROCESS_FAILURE_OR_HARD_CUTOFF'},'frozen_candidate_sha256':sha(token)})
                ledger.stop('AUDIT_PROCESS_FAILURE_OR_HARD_CUTOFF'); break
            audited=load_json(auditdir/'worker_return.json'); require(audited['job_sha256']==sha(auditjob),'AUDIT_RETURN_IDENTITY')
            output=audited['payload']; outputs.append({'slot':slot,'plan_status':'PLAN_SAFE','post':output})
            if output.get('stop_required'): ledger.stop(output.get('anomaly') or output.get('reason') or 'AUDIT_TECHNICAL_FAILURE'); break
        except RootBudgetExpired:
            # No new worker is launched after its root expires. Existing claims stay consumed.
            if token is not None:
                outputs.append({'slot':slot,'plan_status':'PLAN_SAFE','post':{'audit_status':'TRUE_H_UNRESOLVED','audit_consumed':audit_claim is not None,'reason':'AUDIT_ROOT_EXHAUSTED_BEFORE_WORKER'},'frozen_candidate_sha256':sha(token)})
            else: outputs.append({'slot':slot,'plan_status':'PLAN_UNRESOLVED','reason':'PLAN_ROOT_EXHAUSTED_BEFORE_WORKER'})
            ledger.stop('ROOT_EXHAUSTED'); break
        except Exception as error:
            outputs.append({'slot':slot,'plan_status':'PLAN_SAFE' if token is not None else 'PLAN_UNRESOLVED','stage':phase,'technical_failure':True,'reason':type(error).__name__+':'+str(error),'audit_consumed':audit_claim is not None})
            ledger.stop(type(error).__name__+':'+str(error)); break
    atomic_json(destination/'terminal.json',{'slots':outputs,'stopped':ledger.stopped,'no_automatic_retry':True})
    return outputs

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--describe',action='store_true'); parser.add_argument('--execute',type=Path)
    args=parser.parse_args()
    if args.describe: print(json.dumps(policy_files()[0],ensure_ascii=False,indent=2))
    elif args.execute:
        try: run_four_slots(args.execute)
        except Exception as error: print(type(error).__name__+':'+str(error),file=sys.stderr); raise SystemExit(3)
    else: parser.error('Use --describe; research --execute remains gated off in B0')
