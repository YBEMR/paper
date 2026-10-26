"""E1 frozen process handoff. Default REAL gate is closed; mocks are distinct."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys
import time
from .execution_io import (CORE,DEFAULT_GATE,BUDGETS,SLOTS,read_json,save,sha,require,
                            validate_gate,build_bundle,selected_token)
from .ledger import Ledger
from .process_control import supervise
from h02_pair_b0.budget import RootBudgetExpired


def _fresh_packet(problem,objective):
    from inputs import load_config,build_instance
    from control_policy import with_auto_low_idle
    config=with_auto_low_idle(load_config(CORE/'config_v01.json'))
    return dict(config=config,instance=build_instance(config,problem),objective=objective)


def _root_check(origin,limit,slot_deadline,batch_deadline):
    if time.monotonic()>=min(origin+limit,slot_deadline,batch_deadline): raise RootBudgetExpired('parent_root_expired')


def recover_plan(packet,job,output,process,*,ignore_return=False):
    """Authenticate completed bytes only. No candidate repair or new selection."""
    from .exports import verify_export
    technical=process.get('classification') in ('NONZERO_EXIT_FAULT','SPAWN_FAULT','SUPERVISOR_FAULT','PROCESS_CLEANUP_FAULT')
    returned=None; checkpoint=None
    if not ignore_return and (output/'worker_return.json').exists():
        returned=read_json(output/'worker_return.json')
        require(returned['job_sha256']==sha(job) and returned['kind']==job['mode'],'RETURN_IDENTITY')
        if not returned.get('pre_backend_root_exhausted'):
            require(returned['manifest_sha256']==job['scope_sha256'] and returned['packet_sha256']==sha(packet),
                    'RETURN_CONTEXT')
    if (output/'checkpoint.json').exists():
        checkpoint=read_json(output/'checkpoint.json')
        require(checkpoint['job_sha256']==sha(job) and checkpoint['kind']==job['mode'] and
                checkpoint['manifest_sha256']==job['scope_sha256'] and checkpoint['packet_sha256']==sha(packet),
                'CHECKPOINT_CONTEXT')
    if returned and 'result' in returned:
        result=deepcopy(returned['result'])
        require(result.get('input_sha256') in (None,sha(packet['instance'])),'RETURN_INPUT')
    else:
        result=dict(method='e1-adapted-heft',seed=None,state='UNRESOLVED',objective=packet['objective'],
                    input_sha256=sha(packet['instance']),config_sha256=sha(packet['config']),
                    accuracy_sha256=sha(packet['config']['accuracy_targets']),safe_candidate=None,evaluation=None,
                    safe_upper_bound_J=None,planning_score_J=None,stop_required=False,
                    independently_proven_optimal=False,coverage_complete=False,
                    reason='TECHNICAL_FAILURE' if technical else 'METHOD_BUDGET_EXHAUSTED',
                    timing=dict(limit_s=300,method_elapsed_s=process['method_elapsed_s']))
        if checkpoint:
            archive=deepcopy(checkpoint['snapshot']);result['archive']=archive
            best=archive.get('best')
            if best is not None:
                result.update(state='SAFE',safe_candidate=best['candidate'],evaluation=best['evaluation'],
                              safe_upper_bound_J=best['evaluation']['safe_upper_bound_J'],
                              planning_score_J=best['score']['planning_score_J'],
                              selected_candidate_sha256=best['candidate_sha256'],selected_at_s=best['selection_formed_at_s'],
                              selected_source=best['source'])
    result['stop_required']=technical or result.get('stop_required') is True
    effective=min(300,job['slot_deadline']-job['root_origin'],job['batch_deadline']-job['root_origin'])
    for row in result.get('archive',{}).get('evaluations',[]):
        if row.get('eligible_for_selection'):
            require(0<=row['selection_formed_at_s']<effective and
                    0<=row['evaluation']['completed_at_elapsed_s']<effective,'EVIDENCE_AFTER_EARLIEST_CUTOFF')
    from h02_pair_preflight.common import timely
    provenance_end=process['method_elapsed_s']
    if checkpoint:
        require(checkpoint['archived_at_s']<=provenance_end,'CHECKPOINT_FUTURE_ARCHIVE_TIME')
        provenance_end=min(provenance_end,checkpoint['archived_at_s'])
    if returned:
        require(returned['returned_at_s']<=process['method_elapsed_s'],'RETURN_FUTURE_ARCHIVE_TIME')
    for row in result.get('archive',{}).get('evaluations',[]):
        if row.get('eligible_for_selection'):
            require(row['selection_formed_at_s']<=provenance_end,'SELECTION_FUTURE_TIMESTAMP')
    # Raw late witnesses stay in the archive; only pre-cutoff witnesses count.
    result['effective_violations']=[v for v in result.get('archive',{}).get('violations',[])
         if timely(v.get('formed_at_elapsed_s'),effective) and v['formed_at_elapsed_s']<=provenance_end]
    verify_export(packet['instance'],packet['config'],result,300,evidence_seconds=effective)
    result.update(recovery='FINAL_RETURN' if returned and 'result' in returned else
                  ('PREEXISTING_CHECKPOINT_ONLY' if checkpoint else 'NO_COMPLETE_EVIDENCE'),
                  final_request_unresolved=not (returned and 'result' in returned))
    return result


def recover_post(job,output,process):
    technical=process.get('classification') in ('NONZERO_EXIT_FAULT','SPAWN_FAULT','SUPERVISOR_FAULT','PROCESS_CLEANUP_FAULT')
    effective=min(60,job['slot_deadline']-job['root_origin'],job['batch_deadline']-job['root_origin'])
    result=dict(state='UNRESOLVED',reason='POST_BUDGET_EXHAUSTED',stop_required=technical)
    returned=None
    if (output/'worker_return.json').exists():
        returned=read_json(output/'worker_return.json')
        require(returned['job_sha256']==sha(job) and returned['kind']==job['mode'],'POST_RETURN_IDENTITY')
        if 'result' in returned:
            require(returned['manifest_sha256']==job['scope_sha256'] and returned['packet_sha256']==sha(job['packet']),
                    'POST_RETURN_CONTEXT')
            result=returned['result']; result['stop_required']=technical or result.get('stop_required') is True
            require(returned['returned_at_s']<=process['method_elapsed_s'],'POST_RETURN_FUTURE_TIMESTAMP')
    # A formed receipt may survive a crash before worker_return. Validate the
    # same frozen candidate; do not evaluate, repair or look at another option.
    if (output/'post_receipt.json').exists():
        stored=read_json(output/'post_receipt.json');require(stored['job_sha256']==sha(job),'POST_RAW_CONTEXT')
        receipt=stored['receipt'];result['raw_receipt']=receipt
        from h02_pair_preflight.receipts import safe_receipt,technical_issues
        from h02_pair_preflight.common import exact,timely
        packet=job['packet'];candidate=job['planning_result']['safe_candidate'];i=packet['instance']
        require(receipt.get('evidence_identity')==dict(input_sha256=sha(i),candidate_sha256=sha(candidate)) and
                receipt.get('problem_id')==i['id'],'POST_RAW_IDENTITY')
        require(not technical_issues(receipt),'POST_RAW_TECHNICAL_FAILURE')
        if receipt.get('state')=='SAFE' and timely(receipt.get('completed_at_elapsed_s'),effective):
            require(receipt['completed_at_elapsed_s']<=process['method_elapsed_s'] and
                    (returned is None or receipt['completed_at_elapsed_s']<=returned['returned_at_s']),
                    'POST_FUTURE_FORMATION_TIMESTAMP')
            safe_receipt(i,candidate,receipt,packet['config']['accuracy_targets'],effective)
            require(receipt['legality']==job['planning_result']['evaluation']['legality'],'POST_LEGALITY_CONTRADICTION')
            a,b=map(exact,job['planning_result']['evaluation']['weighted_energy_J']);c,d=map(exact,receipt['weighted_energy_J'])
            require(max(a,c)<=min(b,d),'PLAN_POST_ENERGY_CONTRADICTION')
            result.update(state='POST_SAFE',candidate_sha256=sha(candidate),evaluation=receipt)
        elif receipt.get('state') in ('THERMAL_VIOLATION','INVALID_SCHEDULE'):
            result.update(state='UNRESOLVED',reason='POST_CONTRADICTS_SELECTED_SAFE',stop_required=True)
        else:
            # A late SAFE is archive-only; do not keep a worker's mistaken SAFE label.
            result.update(state='UNRESOLVED',evaluation=None,reason='POST_UNRESOLVED_OR_LATE')
    require(result.get('state')!='POST_SAFE' or ((output/'post_receipt.json').exists() and
            result.get('evaluation')==result.get('raw_receipt')),'POST_SAFE_WITHOUT_RAW_RECEIPT')
    return result


def run_phase(ledger,gate,manifest,run_dir,ordinal,phase,*,slot_origin,batch_origin,
              packet_loader=None,planning_result=None,packet=None,mock_behavior='normal',
              mock_prior_elapsed_s=0,grace_s=5,forbidden_probe_path=None):
    mode=gate['kind']
    require(phase in ('PLAN','POST'),'PHASE')
    require(mode=='MOCK_PROCESS' or (mock_prior_elapsed_s==0 and mock_behavior=='normal' and grace_s==5),
            'MOCK_CONTROLS_CANNOT_CHANGE_REAL_LIMITS')
    origin=time.monotonic()-mock_prior_elapsed_s  # Nonzero offset is explicitly MOCK only.
    validate_gate(gate,manifest,mode,run_dir)
    limit=BUDGETS[phase.lower()+'_s']; slot_deadline=slot_origin+420;batch_deadline=batch_origin+1800
    out=Path(run_dir)/('slot_'+str(ordinal))/phase.lower()
    problem,objective=SLOTS[ordinal-1]
    if phase=='PLAN':
        expected=manifest['inputs'][problem] if mode=='REAL_RESEARCH' else manifest['mock_input']
        ctx=dict(input_sha256=expected['input_sha256'],config_sha256=expected['config_sha256'],
                 accuracy_sha256=expected['accuracy_sha256'],objective=objective if mode=='REAL_RESEARCH' else expected['objective'],
                 packet_sha256=expected['packet_sha256'][objective if mode=='REAL_RESEARCH' else expected['objective']],
                 manifest_sha256=sha(manifest))
        claim=ledger.claim_plan(ordinal,origin,ctx)
    else:
        token=selected_token(packet,planning_result)
        claim=ledger.claim_post(ordinal,origin,token)
    # The call is already consumed before input expansion, bundle, process start.
    out.mkdir(parents=True,exist_ok=False)
    job=None;process=None
    try:
        _root_check(origin,limit,slot_deadline,batch_deadline)
        if phase=='PLAN':
            packet=(packet_loader() if packet_loader else _fresh_packet(problem,objective))
        else: packet=deepcopy(packet)
        _root_check(origin,limit,slot_deadline,batch_deadline)
        worker=build_bundle(out/'bundle',manifest,mode)
        _root_check(origin,limit,slot_deadline,batch_deadline)
        job=dict(mode=mode,phase=phase,ordinal=ordinal,root_origin=origin,limit_s=limit,
                 slot_deadline=slot_deadline,batch_deadline=batch_deadline,scope_sha256=sha(manifest),
                 run_dir=str(Path(run_dir).resolve()),packet=packet,claim=claim,authorization=gate)
        if phase=='POST':job.update(selected_token=token,planning_result=planning_result)
        if mode=='MOCK_PROCESS':
            job.update(mock_behavior=mock_behavior,mock_prior_elapsed_s=mock_prior_elapsed_s)
            if forbidden_probe_path is not None:job['forbidden_probe_path']=str(Path(forbidden_probe_path).resolve())
        save(out/'job.json',job)
        command=[sys.executable,'-I','-S','-B',str(worker.resolve()),'--job',str((out/'job.json').resolve()),
                 '--job-sha',sha(job),'--bundle',str((out/'bundle').resolve()),'--output',str(out.resolve())]
        if mode=='MOCK_PROCESS':command.append('--e1-mock-worker')
        process=supervise(command,cwd=out,root_origin=origin,limit_s=limit,
                slot_deadline=slot_deadline,batch_deadline=batch_deadline,
                stop_file=out/'STOP.json',receipt_file=out/'worker_return.json',grace_s=grace_s)
        save(out/'process.json',process)
        if phase=='PLAN':
            try:result=recover_plan(packet,job,out,process)
            except Exception as error:
                # A malformed final return cannot erase a separately valid old
                # checkpoint. Recovery remains technical and stops the batch.
                if not (out/'checkpoint.json').exists():raise
                result=recover_plan(packet,job,out,{**process,'classification':'NONZERO_EXIT_FAULT'},ignore_return=True)
                result.update(stop_required=True,reason='FINAL_RETURN_IDENTITY_OR_CONTENT_ERROR',
                              final_return_error=type(error).__name__+':'+str(error))
        else:result=recover_post(job,out,process)
    except RootBudgetExpired:
        process=dict(classification='PREPARATION_CUTOFF',method_elapsed_s=time.monotonic()-origin,
                     finished_monotonic=time.monotonic(),pid=None,reaped=False)
        result=dict(state='UNRESOLVED',reason='PREPARATION_BUDGET_EXHAUSTED',stop_required=False)
    except Exception as error:
        result=dict(state='UNRESOLVED',reason='TECHNICAL_FAILURE',error=type(error).__name__+':'+str(error),stop_required=True)
    if phase=='POST' and not (ledger.root/f'{ordinal:02d}_post_launch.json').exists() and not result.get('stop_required'):
        if time.monotonic()<origin+60 and time.monotonic()>=min(slot_deadline,batch_deadline):
            # The declared slot/batch limit ended the phase before its nominal
            # 60s root. No restart is possible within that ended authorization.
            result.update(stop_required=True,reason='DECLARED_TOTAL_BUDGET_EXHAUSTED',technical_failure=False)
    save(out/'accepted_result.json',dict(kind=mode,result=result,process=process,
          usable_as_research_evidence=mode=='REAL_RESEARCH',consumed_budget_slots=1,
          formal_research_calls=0 if mode=='MOCK_PROCESS' else None,
          real_backend_entry_marked=(out/'real_backend_entry.json').exists(),
          new_real_SAFE=0 if mode=='MOCK_PROCESS' else None))
    if phase=='PLAN':
        chosen=selected_token(packet,result) if result.get('state')=='SAFE' and not result.get('stop_required') else None
        ledger.finish_plan(ordinal,sha(result),selected_token=chosen,stop_required=result.get('stop_required') is True)
    else:
        proof=None
        if not (ledger.root/f'{ordinal:02d}_post_launch.json').exists() and not result.get('stop_required'):
            proof=dict(reason='ROOT_DEADLINE_BEFORE_SPAWN',observed_monotonic=time.monotonic())
        ledger.finish_post(ordinal,sha(result),stop_required=result.get('stop_required') is True,not_launched_deadline=proof)
    return dict(result=result,packet=packet,process=process,output=str(out),job=job)


def run_batch(manifest_path,authorization_path,run_dir):
    batch_origin=time.monotonic()
    manifest,gate=read_json(manifest_path),read_json(authorization_path)
    validate_gate(gate,manifest,'REAL_RESEARCH',run_dir)  # Before claims, output or processes.
    ledger=Ledger(gate['authority_store'],gate,run_dir,kind='REAL_RESEARCH')
    ledger.claim_batch(dict(manifest_sha256=sha(manifest),batch_origin=batch_origin))
    outputs=[]
    for ordinal in range(1,5):
        if time.monotonic()>=batch_origin+1800:ledger.stop('BATCH_WALL_LIMIT');break
        slot_origin=time.monotonic()
        plan=run_phase(ledger,gate,manifest,run_dir,ordinal,'PLAN',slot_origin=slot_origin,batch_origin=batch_origin)
        outputs.append(dict(ordinal=ordinal,phase='PLAN',result=plan['result']))
        if plan['result'].get('stop_required'):break
        if plan['result'].get('state')=='SAFE':
            post=run_phase(ledger,gate,manifest,run_dir,ordinal,'POST',slot_origin=slot_origin,
                 batch_origin=batch_origin,packet=plan['packet'],planning_result=plan['result'])
            outputs.append(dict(ordinal=ordinal,phase='POST',result=post['result']))
            if post['result'].get('stop_required'):break
    save(Path(run_dir)/'batch_summary.json',dict(outputs=outputs,wall_s=time.monotonic()-batch_origin,
          planned_slots=4,retries=0,authorization_id=gate['authorization_id']))
    return outputs

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--authorization',default=str(DEFAULT_GATE));p.add_argument('--out',required=True)
    a=p.parse_args();run_batch(a.manifest,a.authorization,a.out)
