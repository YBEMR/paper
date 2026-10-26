"""Freeze known E2/E3/E4 inputs using only static checks and MOCK workers."""
from copy import deepcopy
import io,json,subprocess,sys,time,unittest
from pathlib import Path
CORE=Path(__file__).resolve().parents[1];REPO=CORE.parents[1]
sys.path.insert(0,str(CORE));sys.dont_write_bytecode=True
from e1_objective.execution_io import runtime_paths,sha,file_sha,read_json,save,protocol_limits


def main(destination,*,protocol_id='E2_RESOURCES_V1'):
    if protocol_id=='E2_RESOURCES_V1':
        from e2_resources.protocol import SLOTS
        from e2_resources.input_contract import prepare_inputs,validate_inputs
        from e2_resources.test_protocol import mock_materials
    elif protocol_id=='E3_DEPLOYMENT_V1':
        from e3_deployment.protocol import SLOTS
        from e3_deployment.input_contract import prepare_inputs,validate_inputs
        from e3_deployment.test_protocol import mock_materials
    elif protocol_id=='E4_DEADLINE_V1':
        from e4_deadline.protocol import SLOTS
        from e4_deadline.input_contract import prepare_inputs,validate_inputs
        from e4_deadline.test_protocol import mock_materials
    elif protocol_id=='E4_REQUESTS_V1':
        from e4_requests.protocol import SLOTS
        from e4_requests.input_contract import prepare_inputs,validate_inputs
        from e4_requests.test_protocol import mock_materials
    else: raise ValueError('UNKNOWN_PRECHECK_PROTOCOL')
    limits=protocol_limits(dict(protocol_id=protocol_id));budgets=limits['budgets']
    out=Path(destination).resolve()
    if out.exists():raise FileExistsError('precheck directory cannot be reused')
    out.mkdir(parents=True)
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip()
    previous=read_json(REPO/'research/e1_e4_validation/evidence/e1_mock_precheck02/source_manifest.json')
    unchanged=[]
    for row in previous['sources']:
        if row['base_unchanged']:
            if file_sha(REPO/row['path'])!=row['sha256']:raise ValueError('ORIGINAL_SOURCE_DRIFT:'+row['path'])
            unchanged.append(row)
    gate=read_json(CORE/'e1_objective/execution_gate.json')
    if gate.get('authorized') is not False or gate.get('four_slot_authorized') is not False:
        raise ValueError('REAL_GATE_MUST_REMAIN_CLOSED_FOR_PRECHECK')
    # Bind every executable dependency and test to committed bytes; results can
    # be committed subsequently without rewriting this immutable source SHA.
    all_source=set(runtime_paths('MOCK_PROCESS'))
    for folder in ('e1_objective','e2_resources','e3_deployment','e4_deadline','e4_requests'):
        all_source.update(str(p.relative_to(REPO)).replace('\\','/') for p in (CORE/folder).glob('*.py'))
    dirty=subprocess.run(['git','diff','--name-only','HEAD','--',*sorted(all_source)],cwd=REPO,
                         capture_output=True,text=True,check=True).stdout
    untracked=subprocess.run(['git','ls-files','--others','--exclude-standard','--',*sorted(all_source)],cwd=REPO,
                         capture_output=True,text=True,check=True).stdout
    if dirty.strip() or untracked.strip():raise ValueError('SOURCE_NOT_COMMITTED:'+dirty+untracked)
    hashes={rel:file_sha(REPO/rel) for rel in sorted(all_source)}
    for rel in hashes:compile((REPO/rel).read_bytes(),rel,'exec')
    save(out/'implementation_source_manifest.json',dict(source_sha=commit,files=hashes,
         original_files_unchanged=unchanged,source_committed=True))
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
    result=None;failure=None;summaries=[];manifests={}
    try:
        sys.setprofile(guard)
        packets=prepare_inputs();contract=validate_inputs(packets)
        save(out/'input_contract.json',contract)
        pairs={}
        for pid,packet in packets.items():
            save(out/(pid+'.json'),packet)
            pairs[pid]=dict(input_sha256=sha(packet['instance']),config_sha256=sha(packet['config']),
                accuracy_sha256=sha(packet['config']['accuracy_targets']),packet_sha256={'FULL':sha(packet)})
        for mode,name in [('REAL_RESEARCH','frozen_real_manifest.json'),('MOCK_PROCESS','frozen_mock_manifest.json')]:
            manifest=dict(schema=protocol_id+'_PROCESS_FREEZE_V1',protocol_id=protocol_id,mode=mode,source_sha=commit,
                slots=[list(s) for s in SLOTS],budgets=deepcopy(budgets),
                supervision=deepcopy(limits['supervision']),
                files={rel:file_sha(REPO/rel) for rel in runtime_paths(mode)},inputs=pairs,
                config_source_sha256=file_sha(CORE/'config_v01.json'))
            save(out/name,manifest);manifests[mode]=manifest
        save(out/'authorization_template_CLOSED.json',dict(kind='REAL_RESEARCH',protocol_id=protocol_id,authorized=False,
            stage_authorized=False,four_slot_authorized=False,approval_reference=None,authorization_id=None,
            authority_store=None,allowed_run_directory=None,source_sha=commit,
            scope_sha256=sha(manifests['REAL_RESEARCH']),budgets=deepcopy(budgets)))
        suite=unittest.defaultTestLoader.loadTestsFromNames([
            'e1_objective.test_search','e1_objective.test_scoring','e1_objective.test_runner',
            'e1_objective.test_ledger','e1_objective.test_process_control','e1_objective.test_execution',
            'e2_resources.test_input_contract','e2_resources.test_protocol',
            'e3_deployment.test_input_contract','e3_deployment.test_protocol',
            'e4_deadline.test_input_contract','e4_deadline.test_protocol',
            'e4_requests.test_input_contract','e4_requests.test_protocol'])
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        if not result.wasSuccessful():raise AssertionError('STATIC_MOCK_REGRESSIONS_FAILED')
        from e1_objective.controller import run_phase
        kept=out/'mock_records';kept.mkdir();(kept/'.gitignore').write_bytes(b'**/bundle/\n')
        p,m,g,r,l=mock_materials(kept,source_sha=commit)
        begin=time.monotonic()
        plan=run_phase(l,g,m,r,1,'PLAN',slot_origin=begin,batch_origin=begin,packet_loader=lambda:deepcopy(p))
        if plan['result']['state']!='SAFE' or plan['result']['objective']!='FULL':raise AssertionError('MOCK_SELECTED_PROTOCOL_PLAN_FAILED')
        post=run_phase(l,g,m,r,1,'POST',slot_origin=begin,batch_origin=begin,packet=p,planning_result=plan['result'])
        if post['result']['state']!='POST_SAFE':raise AssertionError('MOCK_SELECTED_PROTOCOL_POST_FAILED')
        if post['result']['candidate_sha256']!=plan['result']['selected_candidate_sha256']:
            raise AssertionError('MOCK_SELECTED_PROTOCOL_CANDIDATE_DRIFT')
        for phase,item in [('PLAN',plan),('POST',post)]:
            ret=read_json(Path(item['output'])/'worker_return.json')
            if ret['guard']['science_modules_loaded'] or ret['guard']['real_backend_entered']:
                raise AssertionError('MOCK_SCIENTIFIC_ENTRY')
            summaries.append(dict(phase=phase,state=item['result']['state'],
                stop_required=item['result'].get('stop_required'),classification=item['process']['classification'],
                reaped=item['process']['reaped'],objective='FULL',protocol_id=protocol_id,
                mock_only=True,new_real_SAFE=0))
    except Exception as error:
        failure=type(error).__name__+':'+str(error)
    finally:
        sys.setprofile(original_profile);collect[0]=False
        (out/'mock_tests.txt').write_bytes(stream.getvalue().encode())
        save(out/'mock_process_launches.json',dict(processes=processes,scientific_function_attempts=blocked))
    changed=[rel for rel,digest in hashes.items() if file_sha(REPO/rel)!=digest]
    real_entries=list((out/'mock_records').rglob('real_backend_entry.json')) if (out/'mock_records').exists() else []
    save(out/'retained_mock_summary.json',summaries)
    summary=dict(passed=failure is None and result is not None and result.wasSuccessful() and not blocked and not changed and not real_entries,
        tests=result.testsRun if result else 0,failures=len(result.failures) if result else None,
        errors=len(result.errors) if result else None,error=failure,wall_s=time.monotonic()-started,
        source_sha=commit,source_committed=True,protocol_id=protocol_id,
        real_gate_authorized=False,original_files_unchanged=len(unchanged),actual_mock_process_launches=len(processes),
        retained_mock_phases=len(summaries),formal_research_calls=0,true_thermal_evaluations=0,
        MILP_calls=0,MATLAB_starts=0,new_real_SAFE=0,scientific_function_attempts=blocked,
        source_changed_during_precheck=changed,real_backend_entry_files=[str(x) for x in real_entries],
        mock_SAFE_is_not_research_evidence=True,
        real_manifest_sha256=sha(manifests['REAL_RESEARCH']) if 'REAL_RESEARCH' in manifests else None)
    save(out/'precheck_result.json',summary);print(json.dumps(summary,ensure_ascii=False))
    if not summary['passed']:raise SystemExit(1)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True)
    main(parser.parse_args().out)
