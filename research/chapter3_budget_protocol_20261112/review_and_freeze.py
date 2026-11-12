"""Read saved evidence, run synthetic controls, freeze an UNAPPROVED candidate.

No scientific imports, matrix load/preflight, process launch, optimization or evaluation.
Run once from the prepared workspace; exclusive artifact writes prevent silent refreezing.
"""
from pathlib import Path
import hashlib
import difflib
import importlib.abc
import io
import json
import math
import sys
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PACKAGE=HERE/'candidate_on'
REPO=ROOT/'work/publish_repo'
BASE='143629e86cfa5a3951ab23da218ca9c8f260a277'
sys.path.insert(0,str(PACKAGE))
from guard import read,save,sha,verify_plan
from budget_policy import BudgetPolicy,NEXT_ON,ABC_DYNAMIC


def forbidden(*a,**k):raise AssertionError('No scientific work or process creation in this engineering review')


class NoScience(importlib.abc.MetaPathFinder):
    names={'thermal','matlab_bridge','formal_milp','milp','complement_gate','initial_point','schedules'}
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in self.names:forbidden()


def audit_hook(event,args):
    if event in ('subprocess.Popen','os.system','os.posix_spawn','os.spawn','os.startfile'):forbidden()


def bind(bindings,path):
    name=path.relative_to(ROOT).as_posix();value=sha(path)
    if name in bindings:assert bindings[name]==value,name
    bindings[name]=value


def verify(bindings):
    for name,expected in bindings.items():assert sha(ROOT/name)==expected,name


def excerpts(path,ranges):
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    return '\n'.join([path.relative_to(ROOT).as_posix()+' SHA256='+sha(path)]+[
        '\n'.join(f'{i+1}: {lines[i]}' for i in range(a-1,min(b,len(lines)))) for a,b in ranges])+'\n\n'


def main():
    sys.addaudithook(audit_hook);sys.meta_path.insert(0,NoScience())
    assert not NoScience.names.intersection(sys.modules)
    old=ROOT/'work/on_diagnostic';run=ROOT/'work/on_diagnostic_execution_20261112'
    prior=REPO/'research/chapter3_validation_strategy_20261112'
    published=REPO/'research/chapter3_on_diagnostic_execution_20261112'
    oldplan=read(old/'plan.json')
    assert sha(old/'plan.json')==read(old/'plan.identity.json')['sha256']
    bindings=dict(oldplan['workspace_files']);verify(bindings)
    for name,expected in oldplan['package_files'].items():assert sha(old/name)==expected,name
    for p in sorted(old.rglob('*')):
        if p.is_file() and '.test_temp' not in p.parts and '__pycache__' not in p.parts:bind(bindings,p)
    execution_bindings=read(published/'source_bindings.json');verify(execution_bindings)
    bindings.update(execution_bindings)
    for directory in (prior,published):
        for p in sorted(directory.rglob('*')):
            if p.is_file():bind(bindings,p)
    extra=['work/execution/pair/off/method/result.json','work/execution/pair/on/method/result.json',
           'work/equality_pair_execution/pair/off/method/result.json','work/equality_pair_source/bundle_manifest.json',
           'work/stable_expression/full/summary.json']
    for name in extra:bind(bindings,ROOT/name)
    before=dict(bindings)
    a=read(published/'audit.json');r=read(run/'receipt.json');controller=read(run/'controller.json')
    timing=read(run/'timing_after_cleanup.json');session=read(run/'matlab/session.json')
    checks=dict(prior_audit_all_passed=a['passed'] and all(a['checks'].values()),
        original_sources_272= len(oldplan['workspace_files'])==272,
        old_300_240_scope=oldplan['total_window_s']==300 and oldplan['native_MaxTime_s']==240,
        consumed_claim_exists=(run/'claim.json').exists(),
        no_native_requests=r['native_request_attempts']==0 and not list((run/'matlab').glob('request_*')),
        correct_no_call_status=r['terminal_state']=='INSUFFICIENT_FIXED_CAP_RESERVE_NO_CALL',
        no_native_result=r['native'] is None,
        no_new_candidate=r['returned_evaluation'] is None,
        startup_read_evidence=session['ready_publication_read']['attempts']==11861
            and session['ready_publication_read']['transient_read_errors']=={'FileNotFoundError':11860},
        startup_matches_ledger=math.isclose(session['startup_wall_seconds'],timing['phases_exclusive_s']['native_startup']),
        fixed_cap_cannot_fit=300-r['method_elapsed_s']<240,
        normal_controller=controller['state']=='COMPLETED' and not controller['process_monitor']['forced_pids'],
        old_slot_remains_consumed=True)
    assert all(checks.values()),checks
    costs={}
    for arm in ('off','on'):
        name=f'work/execution/pair/{arm}/method/result.json'
        costs[arm]=dict(source=name,phases_exclusive_s=read(ROOT/name)['timing']['phases_exclusive_s'],
                       interpretation='Historical original representation; not a forecast for a fresh complement-gate arm.')
    cost_audit=read(prior/'cost_failure_audit.json')
    instance=read(ROOT/'work/stable_expression/full/input_instance.json')
    config=read(ROOT/'work/stable_expression/full/input_config.json')
    canonical=hashlib.sha256(json.dumps(instance,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    contract=dict(input_identity=canonical,stage_executions=sum(len(s['stage_instances']) for s in instance['scenarios']),
        original_modes=sum(len(v) for v in instance['stage_modes'].values()),
        stage_mode_counts={k:len(v) for k,v in instance['stage_modes'].items()},
        scenario_ids=[s['id'] for s in instance['scenarios']],window_ms=instance['window_ms'],start_grid_ms=instance['start_grid_ms'],
        accuracy_targets=config['accuracy_targets'],original_input_label_preserved=True)
    assert canonical==oldplan['input_identity'] and contract['stage_executions']==12 and contract['original_modes']==66
    review=dict(base_commit=BASE,preceding_commits=['7b723b13bae842eed95b33a6f5f2e1aea0775096','63ad11f4d94e2fcb13955ea9fabf30ad0a1e5385'],
        passed=True,checks=checks,classification='STOPPED_BEFORE_INTLINPROG_NOT_NUMERICAL_FAILURE',
        saved_costs=a['costs'],ready_read=session['ready_publication_read'],startup_cause='UNKNOWN_NO_INTERNAL_TIMESTAMPS',
        polling_nominal_sleep_sum_s=11860*.005,
        polling_interpretation='Requested sleep overlaps worker initialization; neither actual sleep duration nor avoidable delay measured.',
        input_contract=contract,historical_fresh_original_costs=costs,
        historical_complement_combined_cost=cost_audit['cost'],per_arm_complement_preparation_s=None,
        A_preparation_s=None,performance_claim=False,complement_gate_benefit='UNVERIFIED',
        current_review=dict(matlab_sessions=0,native_MILP_LP_calls=0,complete_thermal_evaluations=0,large_model_builds=0))
    save(HERE/'history_review.json',review);save(HERE/'history_bindings.json',before)
    bridge=ROOT/'work/equality_pair_source/research/chapter3_experiments/matlab_bridge.py'
    native=bridge.with_name('solve_model.m')
    text=excerpts(bridge,[(45,115),(451,560),(561,715)])+excerpts(native,[(1,40),(90,140),(270,310)])
    text+=excerpts(old/'control.py',[(1,18),(65,115)])+excerpts(old/'adapter.py',[(90,116),(186,211)])
    (HERE/'static_source_excerpts.txt').write_text(text,encoding='utf-8',newline='\n')
    diffs=[]
    for name in ('control.py','adapter.py','guard.py','run_on.py'):
        diffs.extend(difflib.unified_diff((old/name).read_text(encoding='utf-8-sig').splitlines(True),
            (PACKAGE/name).read_text(encoding='utf-8-sig').splitlines(True),fromfile='7b723b1/'+name,tofile='candidate_on/'+name))
    (HERE/'executor_changes.diff').write_text(''.join(diffs),encoding='utf-8',newline='\n')
    policies={'saved_A420':NEXT_ON,'formal_A600':BudgetPolicy(600.,'fixed',240.),
              'dynamic_B300':BudgetPolicy(300.,'dynamic',240.),'formal_B600':ABC_DYNAMIC}
    scenarios={name:[policy.allocate(t) for t in (0,71.047,120,120.001,150,250,300,350,510,510.01,600)] for name,policy in policies.items()}
    save(HERE/'budget_scenarios.json',dict(scope='ARITHMETIC_ONLY_NOT_PERFORMANCE_SIMULATION',scenarios=scenarios))
    common=read(ROOT/'work/equality_pair_source/bundle_manifest.json')['baseline_flags']
    save(HERE/'ABC_candidate.json',dict(status='PROTOCOL_CANDIDATE_NOT_EXECUTABLE_NOT_APPROVED',execution_authorized=False,
        entrypoint=None,contract=contract,groups={'A':dict(propagate_support=False,prune_joint_states=False),
        'B':dict(propagate_support=True,prune_joint_states=False),'C':dict(propagate_support=True,prune_joint_states=True)},
        common_flags=common,common_expression='UNDECIDED_MUST_FREEZE_BEFORE_ABC',order=['A','B','C'],
        per_group=dict(fresh_model=True,fresh_initialization=True,fresh_MATLAB_session=True,shared_scientific_cache=False,
            total_method_window_s=600,solver_response_cutoff_s=550,dispatch_reserve_s=10,validation_reserve_s=50,
            native_formula='floor(min(540,max(0,600-t-10-50)))',native_minimum_s=30,maximum_native_calls=1,retries=0,
            watchdog_threshold_s=680,cleanup_wait_timeout_s=10,cleanup_time_recorded_separately=True,
            native_algorithm_and_tolerances=oldplan['native_options'],MaxTime_rule_overrides_only_fixed_MaxTime_field=True),
        scientific_calls_this_turn=0,formal_lifecycle_wiring_complete=False,
        ordinary_timeout_policy='Continue other independent arms after verified cleanup',
        correctness_policy='Stop explicitly affected arms; shared or uncertain faults stop all possible dependents',
        late_evidence_policy='No credit after matching receipt/validation deadline',
        acceptance_layers=['root_LP_entry','root_LP_completion','native_bound_and_objective_identity','candidate_vector',
            'new_and_original_rows','schedule_legality','complete_SAFE','strict_energy_interval_improvement','independent_optimality_certificate']))
    checksdir=PACKAGE/'checks';checksdir.mkdir(exist_ok=False)
    stream=io.StringIO();started=time.monotonic()
    with patch('subprocess.Popen',side_effect=forbidden):
        suite=unittest.defaultTestLoader.discover(str(PACKAGE),pattern='test_*.py')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (checksdir/'control_tests.log').write_text(stream.getvalue(),encoding='utf-8',newline='\n')
    tests=dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        elapsed_s=time.monotonic()-started,process_launch_blocked=True,scientific_module_import_blocked=True,
        scientific_modules_loaded=sorted(NoScience.names.intersection(sys.modules)),matlab_sessions=0,native_calls=0,
        thermal_evaluations=0,model_builds=0,scope='Synthetic controls and tiny decode vectors only; no saved-matrix preflight.')
    save(checksdir/'control_tests.json',tests)
    assert result.wasSuccessful(),stream.getvalue()
    assert not tests['scientific_modules_loaded']
    from test_control import FakeRuntime,event
    from control import execute
    samples={}
    for case in ('slow_start_fits','insufficient_budget','normal_timeout','empty_return','late_bound','candidate_rejected','cleanup_unknown'):
        fake=FakeRuntime()
        if case=='slow_start_fits':fake.start_finish=71.047
        if case=='insufficient_budget':fake.start_finish=121.
        if case=='empty_return':fake.native.update(exitflag=2,x=[])
        if case=='late_bound':fake.events=[event('heuristics',.5,time=375.)];fake.solver_evidence_cutoff_s=370.
        if case=='candidate_rejected':
            fake.native.update(exitflag=2,x=[1.,0.],accepted_for_evaluation=True);fake.validation={'state':'REJECTED'}
        if case=='cleanup_unknown':fake.cleanup=False
        samples[case]=execute(fake)
    save(checksdir/'simulated_receipts.json',dict(scope='MOCK_ONLY_NOT_SCIENTIFIC_RESULTS',receipts=samples))
    verify(before)
    newledger=ROOT/'work/on_budget_candidate_A420_execution_v1';assert not newledger.exists()
    plan={k:v for k,v in oldplan.items() if k not in ('workspace_files','package_files')}
    plan.update(protocol='R1-ON-saved-A420-v2-candidate',status='NOT_APPROVED_NOT_RUN',base_commit=BASE,
        proposal_basis_commit=BASE,total_window_s=420,native_MaxTime_s=240,watchdog_s=500,
        validation_reserve_s=50,dispatch_reserve_s=10,solver_response_cutoff_s=370,
        execution_directory='work/on_budget_candidate_A420_execution_v1',execution_authorized=False,
        deadline_policy='Parent origin before configuration/imports; all method work charged. Final publication requires 240+10+50 remaining. Solver/response cutoff 370; full physical evaluation cutoff 420; no late credit.',
        watchdog_policy='At parent+500 terminate only recorded owned identities; wait_procs timeout10. Watchdog is a threshold, not a hard total wall bound. Report cleanup and full controller wall; no scientific credit during cleanup.',
        decision_policy='One slot/request at most; stop without retry on any outcome. Root-LP completion, bound above box lower bound or new SAFE are separate progress observations; not pruning speedup.',
        current_scope='SAVED_MATRIX_ENTRY_DIAGNOSTIC_NOT_FRESH_END_TO_END_PERFORMANCE',
        no_new_model_or_transform=True,workspace_files=dict(before))
    for name in ('README.md','REPORT.txt','ABC_PROTOCOL.txt','ABC_candidate.json','history_review.json',
                 'history_bindings.json','static_source_excerpts.txt','executor_changes.diff','budget_scenarios.json',
                 'review_and_freeze.py','package_delivery.py'):
        bind(plan['workspace_files'],HERE/name)
    paths=[*PACKAGE.glob('*.py'),PACKAGE/'README.md',*checksdir.glob('*')]
    plan['package_files']={p.relative_to(PACKAGE).as_posix():sha(p) for p in sorted(paths)}
    save(PACKAGE/'plan.json',plan);planhash=sha(PACKAGE/'plan.json')
    save(PACKAGE/'plan.identity.json',dict(sha256=planhash));verify_plan(PACKAGE/'plan.json',ROOT,PACKAGE)
    save(PACKAGE/'approval.template.json',dict(approved=False,plan_sha256=planhash,arm='ON',maximum_native_calls=1,
        total_window_s=420,native_MaxTime_s=240,retries=0,user_decision_reference=''))
    receipt=dict(state='FROZEN_TESTED_NOT_APPROVED_NOT_RUN',plan_sha256=planhash,tests=tests['tests'],tests_passed=True,
        history_checks=len(checks),history_verified=True,historical_files_unchanged=len(before),
        workspace_files_verified=len(plan['workspace_files']),saved_ON_preflight_this_turn=False,
        matlab_sessions=0,native_MILP_LP_calls=0,complete_thermal_evaluations=0,large_model_builds=0,
        new_algebraic_transforms=0,formal_ABC_runs=0,old_execution_slot_still_consumed=True,
        new_execution_ledger_exists=False,ready_to_request_new_single_ON_authorization=True,
        formal_ABC_ready_for_execution=False,performance_benefit_verified=False)
    save(PACKAGE/'freeze_receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
