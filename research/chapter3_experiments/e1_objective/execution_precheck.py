"""Final execution-control precheck: genuine mock processes, zero research."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

CORE=Path(__file__).resolve().parents[1];REPO=CORE.parents[1]
sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from e1_objective.execution_io import runtime_paths,sha,file_sha,read_json,save,SLOTS,BUDGETS


def main(destination):
    out=Path(destination).resolve()
    if out.exists():raise FileExistsError('precheck directory cannot be reused')
    out.mkdir(parents=True)
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip()
    previous=read_json(REPO/'research/e1_e4_validation/evidence/e1_mock_precheck02/source_manifest.json')
    for row in previous['sources']:
        if row['base_unchanged']:
            if file_sha(REPO/row['path'])!=row['sha256']:raise ValueError('ORIGINAL_SOURCE_DRIFT:'+row['path'])
    gate=read_json(Path(__file__).with_name('execution_gate.json'))
    if gate.get('authorized') is not False or gate.get('four_slot_authorized') is not False:
        raise ValueError('REAL_GATE_MUST_REMAIN_CLOSED_FOR_PRECHECK')
    pairs={}
    for problem in ('base__R1','base__R3'):
        value=read_json(REPO/('research/e1_e4_validation/evidence/e1_mock_precheck02/'+problem+'.json'))
        c,i=value['config'],value['instance']
        pairs[problem]=dict(input_sha256=sha(i),config_sha256=sha(c),accuracy_sha256=sha(c['accuracy_targets']),
             packet_sha256={o:sha(dict(config=c,instance=i,objective=o)) for o in ('FULL','OMIT_TEMP')})
    manifests={}
    for mode,name in [('REAL_RESEARCH','frozen_real_manifest.json'),('MOCK_PROCESS','frozen_mock_manifest.json')]:
        manifest=dict(schema='E1_PROCESS_FREEZE_V1',mode=mode,source_sha=commit,slots=SLOTS,budgets=BUDGETS,
                      files={rel:file_sha(REPO/rel) for rel in runtime_paths(mode)},inputs=pairs,
                      config_source_sha256=file_sha(CORE/'config_v01.json'))
        save(out/name,manifest);manifests[mode]=manifest
    all_py={str(p.relative_to(REPO)).replace('\\','/'):file_sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
    save(out/'implementation_source_manifest.json',dict(source_sha=commit,files=all_py,
         original_files_unchanged=15,score_and_search_source_unchanged={name:file_sha(Path(__file__).parent/name)
         for name in ('search.py','scoring.py','runner.py')}))
    save(out/'authorization_template_CLOSED.json',dict(kind='REAL_RESEARCH',authorized=False,four_slot_authorized=False,
        approval_reference=None,authorization_id=None,authority_store=None,allowed_run_directory=None,
        source_sha=commit,scope_sha256=sha(manifests['REAL_RESEARCH']),budgets=BUDGETS))
    import thermal,heft_method
    forbidden={thermal.__file__.lower(),str(thermal.KERNEL_PATH).lower()}
    builder=heft_method.build_heft_candidate.__code__;blocked=[];processes=[];collect=[True]
    def guard(frame,event,arg):
        if event=='call' and (frame.f_code is builder or frame.f_code.co_filename.lower() in forbidden):
            blocked.append(frame.f_code.co_name);raise AssertionError('SCIENTIFIC_FUNCTION_FORBIDDEN')
    def audit(event,args):
        if collect[0] and event=='subprocess.Popen':
            argv=args[1];processes.append(dict(argv_sha256=sha(argv),mock_marker='--e1-mock-worker' in argv,
                stdlib_or_ledger_test='-c' in argv,executable=str(args[0])))
    sys.addaudithook(audit);original_profile=sys.getprofile();stream=io.StringIO();started=time.monotonic()
    try:
        sys.setprofile(guard)
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'e1_objective.test_search','e1_objective.test_scoring','e1_objective.test_runner',
            'e1_objective.test_ledger','e1_objective.test_process_control','e1_objective.test_execution'])
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        if not result.wasSuccessful():raise AssertionError('MOCK_REGRESSIONS_FAILED')
        from e1_objective.test_execution import mock_materials
        from e1_objective.controller import run_phase
        kept=out/'mock_records';kept.mkdir();(kept/'.gitignore').write_bytes(b'**/bundle/\n')
        summaries=[]
        for behavior in ('normal','crash_after_checkpoint','hang_after_checkpoint'):
            base=kept/behavior;base.mkdir()
            packet,manifest,mock_gate,run,ledger=mock_materials(base,source_sha=commit)
            begin=time.monotonic()
            plan=run_phase(ledger,mock_gate,manifest,run,1,'PLAN',slot_origin=begin,batch_origin=begin,
                  packet_loader=lambda:deepcopy(packet),mock_behavior=behavior,
                  mock_prior_elapsed_s=299 if behavior=='hang_after_checkpoint' else 0,
                  grace_s=.2 if behavior=='hang_after_checkpoint' else 5)
            summaries.append(dict(behavior=behavior,phase='PLAN',state=plan['result']['state'],
                stop_required=plan['result'].get('stop_required'),classification=plan['process']['classification'],
                reaped=plan['process']['reaped'],selected_at_s=plan['result'].get('selected_at_s')))
            if behavior=='normal':
                post=run_phase(ledger,mock_gate,manifest,run,1,'POST',slot_origin=begin,batch_origin=begin,
                     packet=plan['packet'],planning_result=plan['result'])
                summaries.append(dict(behavior=behavior,phase='POST',state=post['result']['state'],
                    stop_required=post['result'].get('stop_required'),classification=post['process']['classification'],reaped=post['process']['reaped']))
                if post['result']['state']!='POST_SAFE':raise AssertionError('RETAINED_MOCK_POST_FAILED')
            if plan['result']['state']!='SAFE':raise AssertionError('RETAINED_MOCK_CHECKPOINT_FAILED')
    finally:
        sys.setprofile(original_profile);collect[0]=False
        (out/'mock_tests.txt').write_bytes(stream.getvalue().encode())
        save(out/'mock_process_launches.json',dict(processes=processes,scientific_function_attempts=blocked))
    save(out/'retained_mock_summary.json',summaries)
    for rel,digest in all_py.items():
        if file_sha(REPO/rel)!=digest:raise ValueError('SOURCE_CHANGED_DURING_PRECHECK:'+rel)
    safe_files=list((out/'mock_records').rglob('real_backend_entry.json'))
    summary=dict(passed=result.wasSuccessful() and not blocked and not safe_files,tests=result.testsRun,
         failures=len(result.failures),errors=len(result.errors),wall_s=time.monotonic()-started,
         source_sha=commit,source_frozen=True,real_gate_authorized=False,original_files_unchanged=15,
         actual_mock_process_launches=len(processes),retained_mock_phases=len(summaries),
         formal_research_calls=0,true_thermal_evaluations=0,MILP_calls=0,MATLAB_starts=0,new_real_SAFE=0,
         scientific_function_attempts=blocked,real_backend_entry_files=[str(x) for x in safe_files],
         mock_SAFE_is_not_research_evidence=True,real_manifest_sha256=sha(manifests['REAL_RESEARCH']))
    save(out/'precheck_result.json',summary)
    print(json.dumps(summary,ensure_ascii=False))
    if not summary['passed']:raise SystemExit(1)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);main(p.parse_args().out)
