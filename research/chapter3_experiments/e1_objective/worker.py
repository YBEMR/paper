"""One frozen worker. Parent time and one-use claims precede backend entry."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import sys
import time
CORE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CORE)); sys.dont_write_bytecode=True
from e1_objective.execution_io import read_json, save, sha, require, verify_job, verify_bundle
from e1_objective.ledger import Ledger
from h02_pair_b0.budget import RootClock, RootBudgetExpired, anchored_budget_class


class MockBudget:
    def __init__(self,seconds,*,clock): self.seconds,self.clock,self.start=seconds,clock,clock()
    def check(self):
        if self.clock()-self.start>=self.seconds: raise RootBudgetExpired('mock_root_expired')
    @contextmanager
    def phase(self,name):
        self.check(); yield
    def summary(self,stopped_s=None): return dict(limit_s=self.seconds,method_elapsed_s=self.clock()-self.start)


def controlled_budget(base,root,job,stop_file):
    anchored=anchored_budget_class(base,root,root.clock)
    class Controlled(anchored):
        def check(self):
            super().check()
            if stop_file.exists() or self.clock()>=min(job['slot_deadline'],job['batch_deadline']):
                raise RootBudgetExpired('parent_stop_or_total_deadline')
    return Controlled(seconds=job['limit_s'],clock=root.clock)


def execute_worker(job,bundle,output):
    gate,manifest=job['authorization'],read_json(bundle/'runtime_manifest.json')
    verify_bundle(bundle,manifest)
    verify_job(job,gate,manifest,output)
    root=RootClock(job['limit_s'],origin=job['root_origin'],clock=time.monotonic)
    root.check()
    ledger=Ledger(gate['authority_store'],gate,job['run_dir'],kind=job['mode'])
    ledger.consume_launch(job['claim'],sha(job),output)
    # All later file reads are confined to frozen source, this worker's files,
    # and standard library. The ledger was consumed before the application guard.
    from h02_pair_b0.boundary import install_worker_boundary
    libs=[Path(sys.base_prefix)/'Lib',Path(sys.base_prefix)/'DLLs',Path(sys.base_prefix)/'python312.zip',
          Path(sys.base_prefix)/'python313.zip']
    boundary_events=install_worker_boundary(bundle,output,stdlib_roots=libs)
    mode=job['mode']; prohibited={'thermal','timing','heft_method','e1_objective.search'}
    denied=[]
    if mode=='MOCK_PROCESS':
        require(job.get('mock_behavior','normal') in ('normal','crash_after_checkpoint','hang_after_checkpoint',
                 'late_archive','import_delay','bad_identity','probe'),'UNKNOWN_MOCK_BEHAVIOR')
        def no_science(event,args):
            if event=='import' and args[0] in prohibited:
                denied.append(args[0]); raise PermissionError('MOCK_SCIENCE_IMPORT_FORBIDDEN:'+args[0])
        sys.addaudithook(no_science)
        require(not prohibited.intersection(sys.modules),'SCIENCE_PRELOADED_IN_MOCK')
        if job.get('mock_behavior')=='import_delay': time.sleep(job.get('mock_delay_s',0.1))
        from e1_objective.mock_fixtures import make_fixture
        from schedules import validate_schedule
        fixtures=[make_fixture(opp=x,temperature_energy_J=t,h_activity_power_W='4')
                  for x,t in [('L','1/10'),('H','1/100')]]
        packet=job['packet']
        require(all(sha(f['instance'])==sha(packet['instance']) for f in fixtures),'MOCK_PACKET_DRIFT')
        def evaluator(i,c,a,budget):
            table={sha(f['candidate']):f['receipt'] for f in fixtures}
            receipt=deepcopy(table[sha(c)]); receipt['completed_at_elapsed_s']=root.elapsed
            if job.get('mock_behavior')=='bad_identity': receipt['evidence_identity']['candidate_sha256']='wrong'
            return receipt
        def search(i,c,budget,assess,**kwargs):
            for f in fixtures: assess(f['candidate'],'mock-process')
            return dict(status='MOCK_SEQUENCE_FINISHED')
        validator,base,exhausted=validate_schedule,MockBudget,RootBudgetExpired
    else:
        # This branch is unreachable without the separately approved REAL gate,
        # fixed source/input identities and one-use worker launch above.
        root.check()
        save(output/'real_backend_entry.json',dict(phase=job['phase'],at_s=root.elapsed,
             research_calls='entry_consumed; completion may be unknown after abrupt stop'))
        from thermal import evaluate_candidate, Exhausted
        from timing import MethodBudget
        from schedules import validate_schedule
        from e1_objective.search import run_search
        evaluator,validator,base,exhausted=evaluate_candidate,validate_schedule,MethodBudget,Exhausted
        search=run_search
    budget=controlled_budget(base,root,job,output/'STOP.json')
    packet=job['packet']
    from e1_objective import runner
    from e1_objective.exports import verify_export
    def checkpoint(snapshot):
        save(output/'checkpoint.json',dict(job_sha256=sha(job),manifest_sha256=sha(manifest),
             kind=mode,packet_sha256=sha(packet),snapshot=snapshot,archived_at_s=root.elapsed))
    if job['phase']=='PLAN':
        original=runner.ObjectiveRecorder
        class Observing(original):
            def assess(self,candidate,source):
                try: return super().assess(candidate,source)
                finally: checkpoint(self.snapshot())  # observation only, even on exception
        runner.ObjectiveRecorder=Observing
        def loader(b): b.check(); return deepcopy(packet['config']),deepcopy(packet['instance'])
        try:
            result=runner.execute(loader,budget,packet['objective'],search=search,validator=validator,
                 evaluator=evaluator,exhausted=(exhausted,),checkpoint=checkpoint)
        finally: runner.ObjectiveRecorder=original
        verify_export(packet['instance'],packet['config'],result,300,evidence_seconds=min(300,job['slot_deadline']-root.origin,job['batch_deadline']-root.origin))
    else:
        result=dict(state='UNRESOLVED',stop_required=False,reason=None)
        raw=None
        try:
            budget.check()
            planned=job['planning_result']; verify_export(packet['instance'],packet['config'],planned,300)
            candidate=deepcopy(planned['safe_candidate']); instance=deepcopy(packet['instance'])
            accuracy=deepcopy(packet['config']['accuracy_targets'])
            before=sha(instance),sha(candidate),sha(accuracy)
            legal=validator(instance,candidate); budget.check()
            require(legal.get('state')=='SCHEDULE_VALID_THERMAL_UNCHECKED','POST_LEGALITY_CONTRADICTION')
            raw=evaluator(instance,candidate,accuracy,budget)
            # Archive the complete raw receipt before outer deadline checks.
            save(output/'post_receipt.json',dict(job_sha256=sha(job),receipt=raw))
            require(before==(sha(instance),sha(candidate),sha(accuracy)),'POST_INPUT_MUTATION')
            require(raw.get('problem_id')==instance['id'] and raw.get('evidence_identity')==dict(
                    input_sha256=before[0],candidate_sha256=before[1]),'POST_RECEIPT_IDENTITY')
            from h02_pair_preflight.receipts import safe_receipt, technical_issues
            from h02_pair_preflight.common import timely, exact
            require(not technical_issues(raw),'POST_TECHNICAL_FAILURE')
            if raw.get('state')=='SAFE':
                if timely(raw.get('completed_at_elapsed_s'),min(60,job['slot_deadline']-root.origin,job['batch_deadline']-root.origin)):
                    require(raw['completed_at_elapsed_s']<=root.elapsed,'POST_FUTURE_TIMESTAMP')
                    safe_receipt(instance,candidate,raw,accuracy,60)
                    require(raw.get('legality')==legal,'POST_LEGALITY_MISMATCH')
                    a,b=map(exact,planned['evaluation']['weighted_energy_J'])
                    c,d=map(exact,raw['weighted_energy_J'])
                    require(max(a,c)<=min(b,d),'PLAN_POST_ENERGY_CONTRADICTION')
                    result.update(state='POST_SAFE',candidate_sha256=before[1],evaluation=raw)
                else: result['reason']='LATE_POST_NOT_ACCEPTED'
            elif raw.get('state')=='UNRESOLVED': result['reason']=raw.get('reason')
            else: result.update(stop_required=True,reason='POST_CONTRADICTS_SELECTED_SAFE',raw_receipt=raw)
        except (RootBudgetExpired,exhausted): result['reason']='POST_BUDGET_EXHAUSTED'
        except Exception as error:
            result.update(stop_required=True,reason=type(error).__name__+':'+str(error),raw_receipt=raw)
        result['timing']=budget.summary()
    behavior=job.get('mock_behavior')
    if mode=='MOCK_PROCESS' and behavior=='probe':
        for name in ('thermal','e1_objective.search'):
            try: __import__(name)
            except PermissionError: pass
            else: raise ValueError('SCIENCE_IMPORT_WAS_NOT_DENIED')
        try: Path(job['forbidden_probe_path']).read_bytes()
        except PermissionError: denied.append('outside-file')
        else: raise ValueError('OUTSIDE_READ_WAS_NOT_DENIED')
        try:
            import subprocess
            subprocess.run([sys.executable,'-c','pass'])
        except PermissionError: denied.append('child-process')
        else: raise ValueError('CHILD_PROCESS_WAS_NOT_DENIED')
    if mode=='MOCK_PROCESS' and behavior=='crash_after_checkpoint': os._exit(7)
    if mode=='MOCK_PROCESS' and behavior=='hang_after_checkpoint':
        while True: time.sleep(0.01)
    if mode=='MOCK_PROCESS' and behavior=='late_archive':
        while root.elapsed<job['limit_s']+0.02: time.sleep(0.01)
    guard=dict(kind=mode,science_modules_loaded=sorted(prohibited.intersection(sys.modules)),
               denied=denied,boundary_events=boundary_events,
               real_backend_entered=(output/'real_backend_entry.json').exists())
    save(output/'worker_return.json',dict(job_sha256=sha(job),manifest_sha256=sha(manifest),kind=mode,
         packet_sha256=sha(packet),phase=job['phase'],result=result,guard=guard,
         returned_at_s=root.elapsed,usable_as_research_evidence=mode=='REAL_RESEARCH'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True);parser.add_argument('--job-sha',required=True)
    parser.add_argument('--bundle',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--e1-mock-worker',action='store_true')
    args=parser.parse_args();output=Path(args.output).resolve()
    job=read_json(args.job); require(sha(job)==args.job_sha,'JOB_HASH')
    require(args.e1_mock_worker==(job['mode']=='MOCK_PROCESS'),'MOCK_CLI_KIND_MISMATCH')
    try: execute_worker(job,Path(args.bundle).resolve(),output)
    except RootBudgetExpired:
        save(output/'worker_return.json',dict(job_sha256=sha(job),kind=job['mode'],phase=job['phase'],
             pre_backend_root_exhausted=True,returned_at_s=time.monotonic()-job['root_origin']))
    return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        sys.stderr.write(type(error).__name__+':'+str(error)+'\n'); raise SystemExit(3)
