"""Static/read-only freeze. Never imports the executor's Runtime or starts MATLAB."""
from pathlib import Path
import ast,difflib,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parent.parent
PACKAGE=ROOT/'work/root_tail_observer_v1'
sys.path.insert(0,str(PACKAGE))
from guard import sha,read,save,environment_snapshot,PROTOCOL,ARM,verify_plan

old=ROOT/'work/mechanism_trials_v1';oldplan=read(old/'plan.json')
checks={}
for key,base in [('workspace_files',ROOT),('package_files',old)]:
    bad=[p for p,h in oldplan[key].items() if sha(base/p)!=h]
    assert not bad,bad
    checks['historical_'+key]=dict(count=len(oldplan[key]),changed=bad)
baseline=(old/'native_none/solve_model.m').read_text(encoding='utf-8')
native=(PACKAGE/'native/solve_model.m').read_text(encoding='utf-8')
def options(s):
    block=re.search(r"opts = optimoptions\(.*?\);",s,re.S).group(0)
    assignments=re.findall(r'opts\.[A-Za-z]+\s*=.*?;',s,re.S)
    return [block]+assignments
assert options(baseline.replace("'Display','off'","'Display','iter'"))==options(native)
call=re.compile(r'\[x,fval,exitflag,output\] = intlinprog\(.*?\);',re.S)
assert call.findall(baseline)==call.findall(native) and len(call.findall(native))==1
checks['native_search_options_unchanged_except_Display']=True
checks['native_intlinprog_arguments_unchanged']=True
checks['native_adapter_one_request']=native.count('= intlinprog(')==1 and 'Exactly one request' in native
assert "profile('on','-timestamp','-historysize','100000','-timer','performance')" in native
checks['python_syntax_files']=[]
for p in sorted(PACKAGE.glob('*.py')):
    ast.parse(p.read_text(encoding='utf-8'),filename=str(p));checks['python_syntax_files'].append(p.name)
test=read(ROOT/'work/root_tail_control_tests.json');assert test['passed']
assert not (ROOT/'work/root_tail_observation_execution_v1').exists()
checks['new_execution_ledger_absent']=True
installed=Path('F:/Matlab2023/Program_Files/MATLAB_R2023b')
vendor=[installed/'toolbox/matlab/codetools/profile.m',installed/'toolbox/optim/optim/intlinprog.m',
    installed/'toolbox/optim/+optim/+options/Intlinprog.m',installed/'toolbox/optim/+optim/+algorithm/IntlinprogBranchAndCut.p']
text=vendor[0].read_text(encoding='utf-8')
assert all(x in text for x in ['-TIMESTAMP','-HISTORYSIZE','performance','HistoryTracking','HistorySize'])
vopts=vendor[2].read_text(encoding='utf-8')
assert 'iter' in vopts and 'reliability' in vopts
checks['R2023b_public_profile_static_interface']=True
checks['MATLAB_runtime_compatibility']='NOT_EXECUTED_NO_AUTHORIZATION'
saved=ROOT/'work/mechanism_trials_execution_v1/C_noheur'
saved_names=['original_zero_based.mat','matlab/request_000001.mat','representation_certificate.json',
    'options.json','initialization.json','reduction_verification.json','native_receipt.json']
sources=dict(oldplan['workspace_files'])
sources.update({(saved/p).relative_to(ROOT).as_posix():sha(saved/p) for p in saved_names})
sources['work/create_observer_native.py']=sha(ROOT/'work/create_observer_native.py')
prior_sources={str(p):sha(p) for p in vendor}
nativeoptions=dict(read(saved/'native_receipt.json')['options']);nativeoptions['Display']='iter';nativeoptions['MaxTime']='N(t), bounded by remaining native worker time'
assert nativeoptions['Heuristics']=='none'
plan=dict(protocol=PROTOCOL,base_commit='77d6a8e4086931fb73212d2899bd1a0464a10644',date='2026-11-13',
    execution_authorized=False,ready_to_request_one_independent_authorization=True,arms=[ARM],
    scope='Saved C_noheur observation only; not end-to-end ABC or a new improvement experiment',
    saved_directory='work/mechanism_trials_execution_v1/C_noheur',
    maximum_native_calls=1,maximum_MATLAB_sessions=1,maximum_LP_calls=0,maximum_full_builds=0,
    maximum_complete_evaluations=2,retries=0,total_window_s=600,response_cutoff_s=550,
    watchdog_s=680,cleanup_monitor_wait_s=10,native_session_cleanup_s=40,
    allocation_function='N(t)=floor(min(540,max(0,600-t-10-50))); require N>=30; t after MAT serialization before request JSON; no retry at boundary',
    native_cap_ceiling_s=540,native_cap_minimum_s=30,dispatch_reserve_s=10,validation_reserve_s=50,
    input_identity=oldplan['input_identity'],initial_candidate_identity=oldplan['initial_candidate_identity'],
    representation='complement_gate_split_constant_v1',native_options=nativeoptions,matlab=oldplan['matlab'],
    observation=dict(Display='iter',public_profile=dict(history='timestamp',timer='performance',history_limit=100000,
        detail='mmex default; status asserted, no undocumented detail option'),process_sampling_period_s=1,
        log_prefix_limit_bytes=8388608,profile_packet_limit_bytes=67108864,alignment_uncertainty_limit_s=.05,
        callback='original decisions preserved; add own measured spans and named root anchor',
        stopped_history='profile info only once after native return/error; closed begin/end markers required for interval completeness',
        overhead='All measured setup/snapshot/archive/callback/sampling costs included; intrinsic profiler/stdout/OS observer effect UNKNOWN'),
    O0='Timely native/observation packet, matched input/options/source/clock provenance, complete in-window archive, complete owned cleanup; parent controller can revoke',
    O1='O0 plus additional root-tail public function/resource/display evidence; no automatic mechanism attribution',
    O2='Independent read-only semantic review of archived evidence under the frozen REPORT rules; complete aligned exclusive intervals, source-bound semantics and competing mechanisms distinguished. >50% of root-tail for dominant attribution; unknown remainder explicit.',
    O2_automatic='NOT_ESTABLISHED; no function-name classifier or CPU-load proxy',
    O2_action='Only established O2 permits proposing a corresponding single-factor experiment; no O2 stops parameter scans. Any later experiment needs its own approval.',
    scientific_success='Timely final native vector, both matrices admitted, independent schedule legality, complete AB/AC SAFE, different common schedule, final full-energy upper < initial lower; no independent optimum claim',
    initialization='Load unchanged saved x0 and common schedule; fresh initial and final full evaluation inside window, maximum two total; no repair/recompletion',
    certificate_policy='Reuse hash-bound saved exact projection and reduction certificates; read array identities only, no full R1 rebuild or algebraic re-expansion',
    timing='Parent ENTRY precedes plan/approval/hash reads/imports/process launch. All input reads, MATLAB startup, observation, serialization, numerical admission, full evaluation, classification, hashes and scientific snapshot are within 600. Native response AND complete profile read before 550. Cleanup/admin after seal cannot read new scientific evidence or create credit; report actual wall separately.',
    archive='Explicit scientific-file manifest and scientific snapshot completed before600. Late files remain raw/uncredited. Post-cleanup receipt only revokes/references prior evidence.',
    ordinary_stop='Insufficient budget, timeout, empty vector, rejected candidate, incomplete SAFE, no improvement: end trial, no retry',
    integrity_stop='Input/options/source drift, energy identity conflict, unknown correctness scope, cleanup or controller failure: invalidate affected claims and stop; bound conflict with verified source trial-local. Persistent scope ledger never clears past affected model arms.',
    execution_directory='work/root_tail_observation_execution_v1',
    approval_policy='A new explicit user instruction bound to THIS plan SHA; approved=false template only in this delivery; all previous one-use authorizations remain consumed',
    software_guard_scope='Local integrity protocol, not a cryptographic privilege boundary',
    environment=environment_snapshot(),workspace_files=sources,vendor_files=prior_sources,
    package_files={p.relative_to(PACKAGE).as_posix():sha(p) for p in sorted(PACKAGE.rglob('*')) if p.is_file() and p.suffix in ('.py','.m')})
save(PACKAGE/'plan.json',plan);save(PACKAGE/'plan.identity.json',{'sha256':sha(PACKAGE/'plan.json')})
approval=dict(approved=False,protocol=PROTOCOL,plan_sha256=sha(PACKAGE/'plan.json'),arms=[ARM],maximum_native_calls=1,
    maximum_MATLAB_sessions=1,total_window_s=600,response_cutoff_s=550,retries=0,user_decision_reference=None)
save(PACKAGE/'approval.template.json',approval)
verify_plan(PACKAGE/'plan.json',ROOT,PACKAGE)
checks['frozen_plan_reverified']=True
out=ROOT/'work/root_tail_observer_preflight';out.mkdir(exist_ok=False)
save(out/'verification.json',dict(checks=checks,control_tests=test,plan_sha256=sha(PACKAGE/'plan.json'),
    scientific_calls=test['scientific_calls'],historical_frozen_files_modified=0))
(out/'native_observer.diff').write_text(''.join(difflib.unified_diff(baseline.splitlines(True),native.splitlines(True),
    fromfile='frozen_D277_C_noheur/solve_model.m',tofile='D279/native/solve_model.m')),encoding='utf-8')
save(out/'compatibility.json',dict(version='R2023b',static_interface_verified=True,real_runtime_verified=False,
    vendor_hashes=prior_sources,protected_kernel_policy='Hash only, never decoded or modified',
    evidence_sources=[dict(url='https://www.mathworks.com/help/releases/R2023b/matlab/ref/profile.html',
        supports='Public options/status, info stopping, history cap, timestamp history, inclusive time, reserved Overhead'),
      dict(url='https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog.html',supports='Display iter, original solver settings'),
      dict(url='https://www.mathworks.com/help/releases/R2023b/optim/ug/intlinprog-output-functions-and-plot-functions.html',
        supports='Event semantics, not phase timers')],
    checked_date='2026-11-13',untested=['MATLAB syntax/runtime execution','Profiler native-kernel visibility','Actual observer overhead','Available 50-second validation/archive reserve']))
print(json.dumps({'plan_sha256':sha(PACKAGE/'plan.json'),'package_files':len(plan['package_files']),
    'source_files':len(sources),'tests':test['tests'],'historical_checks':checks['historical_package_files'],'scientific_calls':test['scientific_calls']}))
