"""Run controls and read-only saved-ON preflight, then freeze. Never launch native work."""
import argparse
import io
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from guard import read, save, sha, verify_plan

PACKAGE = Path(__file__).resolve().parent


def forbidden(*args, **kwargs):
    raise AssertionError('Scientific execution/process launch forbidden during freeze preparation')


def main(workspace):
    workspace = Path(workspace).resolve()
    checks = PACKAGE/'checks'; checks.mkdir(exist_ok=False)
    prior = workspace/'work/publish_repo/research/chapter3_validation_strategy_20261112'
    proposal = read(prior/'ON_diagnostic_proposal.json')
    bindings = read(prior/'source_bindings.json')
    if sha(prior/'source_bindings.json') != proposal['source_bindings_sha256']:
        raise ValueError('Prior proposal bindings drift')
    for name, expected in bindings.items():
        if sha(workspace/name) != expected: raise ValueError('Prior frozen source drift: '+name)
    for name in ('ON_diagnostic_proposal.json','source_bindings.json','cost_failure_audit.json'):
        path=prior/name; bindings[path.relative_to(workspace).as_posix()]=sha(path)
    stream=io.StringIO(); started=time.monotonic()
    suite=unittest.defaultTestLoader.discover(str(PACKAGE),pattern='test_*.py')
    with patch('subprocess.Popen',side_effect=forbidden):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (checks/'control_tests.log').write_text(stream.getvalue(),encoding='utf-8',newline='\n')
    tests=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
               elapsed_s=time.monotonic()-started,native_calls=0,thermal_evaluations=0,model_builds=0,
               scientific_process_launch_guard=True,
               development_history=[dict(tests=29,errors=2,reason='TemporaryDirectory Windows access denied'),
                                    dict(tests=42,errors=7,reason='Same temporary-directory ACL behavior inside workspace'),
                                    dict(tests=42,errors=0,reason='Workspace test folders now inherit access; no scientific execution')])
    save(checks/'control_tests.json',tests)
    if not result.wasSuccessful(): raise RuntimeError('Control test gate failed')
    # Import the frozen original evaluator solely to replace its call entry with a prohibition.
    sys.path.insert(0,str(workspace/'work/equality_pair_source/research/chapter3_experiments'))
    import thermal
    from adapter import Runtime
    preflight=checks/'saved_ON_preflight';preflight.mkdir()
    started=time.monotonic()
    with patch('subprocess.Popen',side_effect=forbidden), patch.object(thermal,'evaluate_candidate',side_effect=forbidden):
        runtime=Runtime(workspace,PACKAGE,PACKAGE/'plan.json',proposal,preflight,started)
        runtime.prepare()
    save(checks/'saved_ON_preflight.json',dict(passed=True,elapsed_s=time.monotonic()-started,
        scene_count=runtime.scene_count,original_variables=len(runtime.old['c']),derived_variables=len(runtime.new['c']),
        original_integer_variables=len(runtime.old['intcon']),initial_schedule_identity_matched=True,
        native_calls=0,thermal_evaluations=0,model_builds=0,algebraic_transforms=0,
        note='Only load saved arrays, check numerical admission and decode archived x0; no new exact feasibility or solver-stability conclusion.'))
    plan={k:proposal[k] for k in ['arm','slots','maximum_native_calls','retries','total_window_s','native_MaxTime_s','watchdog_s',
        'physical_evaluation_limit','model_builds','native_options','input_identity','initial_candidate_identity','representation']}
    plan.update(protocol='R1-ON-once-frozen-executor-v1',execution_authorized=False,
        formal_ABC_runs=0,execution_directory='work/on_diagnostic_execution_20261112',
        proposal_basis_commit='63ad11f4d94e2fcb13955ea9fabf30ad0a1e5385',
        evidence_subject_commit='12bd7bdf507d9c5f2ccb0aac0f41efad702bdd3a',
        matlab='F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe',
        root_policy=proposal['root_policy'],bound_policy=proposal['bound_policy'],
        stop_rule='One claimed slot, one request at most; no retry even on no-call failure; no OFF or ABC launch.',
        deadline_policy='Parent entry before configuration and child imports. Evidence cutoff 300 s; fixed native cap 240 s. Minimum 10 s reserve before request publication. Actual option mismatch invalidates and never triggers a retry. Cleanup/watchdog adds no scientific evidence.',
        watchdog_policy='At 380 s, terminate only observed owned process identities. Abnormal worker exit also cleans captured survivors; any forced cleanup prevents a completed-run claim.',
        bound_scope='Numerical consistency against admitted saved/returned MILP objective only; no independently certified lower bound is produced by this adapter.',
        decision_policy='Progress dimensions independent. Normal timeout retained. Controller final integrity gates usability. No progress: stop; future LP-relaxation/scale analysis or other solver evaluation requires a separate scope.',
        approval_policy='Separate explicit user approval must bind this plan hash. The plan, tests, screenshot, commit and approval template do not authorize a run. Software guards are not a cryptographic identity or OS security boundary.',
        workspace_files=bindings,
        package_files={p.relative_to(PACKAGE).as_posix():sha(p) for p in sorted(PACKAGE.glob('*.py'))})
    for path in [checks/'control_tests.json',checks/'control_tests.log',checks/'saved_ON_preflight.json',preflight/'saved_input_admission.json',PACKAGE/'README.md']:
        plan['package_files'][path.relative_to(PACKAGE).as_posix()]=sha(path)
    # Check old material again after all pure/read-only work.
    for name, expected in bindings.items():
        if sha(workspace/name) != expected: raise ValueError('Source changed during preparation: '+name)
    save(PACKAGE/'plan.json',plan)
    save(PACKAGE/'plan.identity.json',dict(sha256=sha(PACKAGE/'plan.json')))
    verify_plan(PACKAGE/'plan.json',workspace,PACKAGE)
    save(PACKAGE/'approval.template.json',dict(approved=False,plan_sha256=sha(PACKAGE/'plan.json'),arm='ON',
        maximum_native_calls=1,total_window_s=300.,native_MaxTime_s=240.,retries=0,user_decision_reference=''))
    save(PACKAGE/'freeze_receipt.json',dict(state='FROZEN_TESTED_NOT_APPROVED_NOT_RUN',plan_sha256=sha(PACKAGE/'plan.json'),
        tests=tests['tests'],tests_passed=True,saved_ON_preflight_passed=True,workspace_files_verified=len(bindings),
        native_calls=0,thermal_evaluations=0,model_builds=0,algebraic_transforms=0,formal_ABC_runs=0,
        execution_ledger_exists=(workspace/plan['execution_directory']).exists()))
    print(read(PACKAGE/'freeze_receipt.json'))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('workspace',type=Path);main(ap.parse_args().workspace)
