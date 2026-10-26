"""K195: prepare a separately approved, one-shot original whole small-domain run.

This stage prepares only. A future launch requires an exact plan-bound human
approval file; neither preparation nor passing fixtures creates that approval.
Original scientific sources are snapshotted, never edited by this adapter.
"""
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
from pathlib import Path
import argparse
import importlib
import inspect
import json
import os
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SCIENCE = HERE.parent
REPO = SCIENCE.parents[1]
RESULTS = SCIENCE/'results'
PROPOSAL = RESULTS/'small_exact_protocol01/protocol_proposal.json'
OLD = RESULTS/'whole_long_budget01/declaration.json'
METHOD_S, POST_S, CALENDAR_S = 300, 60, 480
CLEANUP_RESERVE_S = 15


def now(): return datetime.now(timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_bytes())
def digest(path): return sha256(Path(path).read_bytes()).hexdigest()
def canonical(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.writing')
    if path.exists(): raise FileExistsError(path)
    with temporary.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.rename(temporary, path)


def prepare(folder):
    """Freeze bytes and a disabled proposal; no model, SAFE or process creation."""
    folder = Path(folder).resolve()
    proposal, original = read(PROPOSAL), read(OLD)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/'plan.json').exists(): raise FileExistsError('Plan already frozen')
    payloads = {'input_instance.json': REPO/proposal['input_path'],
                'input_config.json': REPO/proposal['config_path']}
    for name, source in payloads.items():
        expected = proposal['input_sha256' if name.startswith('input_instance') else 'config_sha256']
        if digest(source) != expected: raise ValueError('K193 payload drift')
        with (folder/name).open('xb') as stream: stream.write(source.read_bytes())
    snapshot = folder/'source_snapshot'
    snapshot.mkdir(exist_ok=False)
    sources = {name: digest(REPO/name) for name in original['source_sha256']}
    if len(sources) != 197: raise ValueError('Unexpected original source inventory')
    compatibility = read(folder/'source_compatibility.json')
    if sources != {row['path']: row['current_sha256'] for row in compatibility['sources']}:
        raise ValueError('Current sources differ from reviewed compatibility record')
    for name in sources:
        target = snapshot/name; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream: stream.write((REPO/name).read_bytes())
    wrappers = {p.relative_to(REPO).as_posix(): digest(p) for p in sorted(HERE.glob('*.py'))}
    instance, config = map(read, [folder/'input_instance.json', folder/'input_config.json'])
    spec = {'problem_id': instance['id'], 'input_sha256': canonical(instance),
        'config_sha256': canonical(config), 'scene_spec': {
            s['id']: {'window_s': '2/5', 'weight': s['weight'],
                'limits': dict(zip(instance['platform']['node_order'], s['maximum_temperature_degC']))}
            for s in instance['scenarios']}}
    executable = Path('F:/Matlab2023/Program_Files/MATLAB_R2023b/bin/matlab.exe')
    plan = {'protocol': 'K195-original-whole-small-once-preparation-v1',
        'prepared_utc': now(), 'authorized': False, 'execution_enabled': False,
        'fixture_only': False, 'method': 'whole_milp',
        'numeric_version': 'original_whole_small_v1_not_augmented',
        'method_calls': 1, 'method_seconds': METHOD_S, 'post_calls_at_most': 1,
        'post_seconds': POST_S, 'calendar_seconds': CALENDAR_S,
        'method_watchdog_seconds': 420, 'post_watchdog_seconds': 75,
        'calendar_cleanup_reserve_seconds': CLEANUP_RESERVE_S,
        'no_retry_or_resume': True, 'source_sha256': sources, 'wrapper_sha256': wrappers,
        'support_sha256': {'research/chapter3_experiments/long_budget_diagnostic/run_once.py':
            digest(SCIENCE/'long_budget_diagnostic/run_once.py')},
        'payload_sha256': {name: digest(source) for name, source in payloads.items()},
        'proposal_sha256': digest(PROPOSAL), 'original_declaration_sha256': digest(OLD),
        'compatibility_sha256': digest(folder/'source_compatibility.json'),
        'reference_sha256': digest(RESULTS/'small_exact_execution01/reference.json'),
        'reference_read_by_search': False, 'historical_candidate_or_cache_input': False,
        'spec': spec, 'builder_flags': proposal['whole_proposal']['builder_flags'],
        'native_options': proposal['whole_proposal']['native_options_reference']['options_except_MaxTime'],
        'native_executable': str(executable),
        'native_executable_sha256': digest(executable) if executable.is_file() else None,
        'expected_matlab_release': '2023b', 'feedback_kind': 'conditional',
        'clock_scope': 'Original MethodBudget before case input read; fresh input/hash/L0/model/init/MATLAB/solve/thermal feedback share 300s. Python startup/import and final archive/cleanup separately in 480s calendar.',
        'minimum_resources': {'physical_GiB': 2, 'commit_GiB': 4, 'disk_GiB': 2},
        'activation': 'Separate explicit human budget approval, exact plan SHA, fixed fresh output and single-use approval.json required; passing precheck does not activate.',
        'material_passport': {'mode': 'plan', 'status': 'PREPARED_NOT_EXECUTED',
            'source': 'K193 domain/protocol and K194 accepted finite reference'}}
    write_new(folder/'plan.json', plan)
    return plan


def verify_frozen(folder, plan):
    if digest(folder/'source_compatibility.json') != plan.get('compatibility_sha256'):
        raise ValueError('Reviewed compatibility record drift')
    for name, expected in plan['source_sha256'].items():
        if digest(folder/'source_snapshot'/name) != expected: raise ValueError('Frozen science drift: '+name)
    for name, expected in plan['wrapper_sha256'].items():
        if digest(REPO/name) != expected: raise ValueError('Execution adapter drift: '+name)
    for name, expected in plan['payload_sha256'].items():
        if digest(folder/name) != expected: raise ValueError('Input/config drift: '+name)
    for name, expected in plan.get('support_sha256', {}).items():
        if digest(REPO/name) != expected: raise ValueError('Host/resource helper drift: '+name)


def authorize(folder, output, approval_path, *, allow_fixture=False):
    """Check a separate exact-scope record, without creating one or consuming it."""
    folder, output = Path(folder).resolve(), Path(output).resolve()
    plan = read(folder/'plan.json')
    approval = read(approval_path)
    if plan['fixture_only'] and not allow_fixture: raise ValueError('Fixture cannot launch science')
    if (plan.get('authorized') is not False or plan.get('execution_enabled') is not False
            or approval.get('approved_by_user') is not True
            or not approval.get('human_authorization_text')
            or approval.get('plan_sha256') != digest(folder/'plan.json')
            or approval.get('output_directory') != str(output)
            or tuple(approval.get(k) for k in ('method_calls', 'method_seconds', 'post_calls_at_most', 'post_seconds', 'calendar_seconds'))
                 != (1, 300, 1, 60, 480)):
        raise ValueError('Missing or mismatched exact human authorization')
    if not output.is_relative_to(RESULTS.resolve()): raise ValueError('Output must stay within experiment results')
    if tuple(plan[k] for k in ('method_calls', 'method_seconds', 'post_calls_at_most', 'post_seconds', 'calendar_seconds')) != (1, 300, 1, 60, 480):
        raise ValueError('Frozen budget drift')
    verify_frozen(folder, plan)
    return plan


def bind(folder, plan):
    """Fresh subprocess only: load one consistent current-science snapshot."""
    snapshot = folder/'source_snapshot'
    production = snapshot/'research/chapter3_experiments'
    sys.path[:0] = [str(HERE), str(production/'p0_batch'), str(production)]
    formal, milp, bridge, thermal, bounds, whole, heuristic, pairing = [importlib.import_module(name)
        for name in ('formal_milp','milp','matlab_bridge','thermal','partial_bounds','audit_whole','audit_heuristic','run_anchor_pair')]
    bridge.REPO = REPO  # Original preference directory only, no scientific setting.
    if inspect.signature(formal.execute_formal_milp).parameters['diagnostic_solver'].default is not None:
        raise ValueError('Unexpected nondefault whole solver injection')
    if inspect.signature(formal.solve_formal_diagnostic).parameters['recorder_factory'].default is not formal.Recorder:
        raise ValueError('Unexpected nondefault recorder')
    engine = SimpleNamespace(formal=formal, milp=milp, bridge=bridge, thermal=thermal,
        bounds=bounds, original_audit=whole.result_records,
        receipt_issues=heuristic.receipt_issues, exact_enclosure=pairing.exact_enclosure,
        domain=importlib.import_module('domain_contract'), native=importlib.import_module('native_contract'))
    loaded_sources(folder, plan)
    return engine


def loaded_sources(folder, plan):
    snapshot = folder/'source_snapshot'
    modules = {}
    for name, module in list(sys.modules.items()):
        location = getattr(module, '__file__', None)
        if not location: continue
        path = Path(location).resolve()
        if path.is_relative_to(snapshot):
            relative = path.relative_to(snapshot).as_posix()
            if plan['source_sha256'].get(relative) != digest(path): raise ValueError('Unbound science import: '+relative)
            modules[name] = relative
        elif path.is_relative_to(SCIENCE) and not path.is_relative_to(HERE):
            raise ValueError('Live/historical science import outside frozen snapshot: '+str(path))
    return modules


def session_factory(engine, plan):
    """The original session and options; extra checks fail closed, never repair."""
    def create(*args, **kwargs):
        if 'cut_max_iterations' in kwargs: raise ValueError('Cut override forbidden')
        if digest(plan['native_executable']) != plan['native_executable_sha256']:
            raise ValueError('Native executable identity drift')
        session = engine.bridge.MatlabSession(*args, **kwargs, cut_max_iterations=10)
        try:
            check = engine.native.validate_ready(read(session.workdir/'ready.json'))
            write_new(session.workdir.parent/'native_ready_admission.json', check)
        except BaseException:
            session.close(); raise
        original_solve = session.solve
        def solve(payload, **kw):
            returned = original_solve(payload, **kw)
            prefix = session.workdir/f'request_{session.counter:06d}'
            response_path = prefix.with_suffix('.response.json')
            if response_path.exists():
                response = read(response_path)
                if response.get('options'):
                    check = engine.native.validate_request_response(
                        read(prefix.with_suffix('.request.json')), response, plan['native_options'])
                    write_new(prefix.with_suffix('.options_admission.json'), check)
                elif returned.get('status') == 'SOLVED':
                    raise ValueError('Solved native response lacks effective options')
            return returned
        session.solve = solve
        return session
    return create


def require_phase(folder, output, approval_path, phase, plan):
    launch = read(output/'launch.claim.json')
    request = read(output/(phase+'.request.json'))
    if (launch.get('plan_sha256') != digest(folder/'plan.json')
            or launch.get('approval_sha256') != digest(approval_path)
            or launch.get('deadline') != launch.get('start')+480
            or time.monotonic() >= launch['deadline']
            or request.get('phase') != phase
            or request.get('calendar_deadline') != launch['deadline']
            or request.get('plan_sha256') != launch['plan_sha256']):
        raise ValueError('Missing/expired matching supervisor phase request')


def method(folder, output, approval_path, *, engine=None):
    folder, output = Path(folder).resolve(), Path(output).resolve()
    plan = authorize(folder, output, approval_path, allow_fixture=engine is not None)
    if plan['fixture_only'] and engine is None: raise ValueError('Fixture cannot execute science')
    if not plan['fixture_only']: require_phase(folder,output,approval_path,'method',plan)
    write_new(output/'method.claim.json', {'utc': now(), 'plan_sha256': digest(folder/'plan.json'), 'seconds': 300, 'retry': False})
    imported = time.monotonic()
    engine = bind(folder, plan) if engine is None else engine
    write_new(output/'imports.json', {'seconds': time.monotonic()-imported, 'scope': 'startup before original MethodBudget; in calendar'})
    call = output/'method'
    instance_box, identity, lower, errors = {}, {'input_valid': None}, {}, []
    def loader(budget):
        write_new(call/'method_budget_identity.json', {'start': budget.start, 'deadline': budget.deadline,
            'limit_s': 300, 'clock': 'monotonic'})
        verify_frozen(folder, plan); budget.check()
        config, instance = read(folder/'input_config.json'), read(folder/'input_instance.json')
        identity['input_valid'] = canonical(instance) == plan['spec']['input_sha256'] and canonical(config) == plan['spec']['config_sha256']
        if not identity['input_valid']: raise ValueError('Wrong restricted input/config')
        instance_box.update(instance=instance, config=config)
        # Preserve original independent quality accounting; no enumeration data.
        with budget.phase('comparison_independent_lower_bound'):
            lower['L0'] = engine.bounds.independent_lower_bound(instance, None, budget)
        budget.check(); return config, instance
    def builder(instance, config, **kw):
        flags = {k: v for k, v in kw.items() if k not in ('budget', 'progress')}
        if flags != plan['builder_flags']: raise ValueError('Original whole flags drift')
        model = engine.milp.build_model(instance, config, **kw)
        guard = engine.domain.validate_model(model, instance, config)
        write_new(call/'model_domain_admission.json', guard)
        kw['budget'].check()
        return model
    # warm adds its four original FLAGS; only the other original options here.
    extra = {k:v for k,v in plan['builder_flags'].items() if k not in
        ('fix_late_options','aggregate_opp_locks','relax_auxiliary_integrality','strengthen_energy_lower_bounds')}
    result = None
    started = time.monotonic()
    try:
        result = engine.formal.execute_formal_milp(loader, call, seconds=300,
            feedback_kind='conditional', model_builder=partial(builder, **extra),
            session_factory=session_factory(engine, plan))
    except BaseException: errors.append(traceback.format_exc())
    wall = time.monotonic()-started
    if result is not None: write_new(call/'wrapper_raw_result.json', result)
    if lower: write_new(call/'independent_bounds.json', lower)
    source_valid, modules = True, {}
    try:
        verify_frozen(folder, plan)
        if not plan['fixture_only']: modules = loaded_sources(folder, plan)
    except Exception: source_valid = False; errors.append(traceback.format_exc())
    from admission import method_records
    def candidate_check(candidate):
        return engine.domain.validate_candidate(instance_box['instance'], candidate, instance_box['config'])
    records = method_records(result, plan['spec'], call, input_valid=identity['input_valid'],
        source_valid=source_valid, errors=errors, original_audit=engine.original_audit,
        candidate_validator=candidate_check)
    write_new(output/'method_return.json', {'utc': now(), 'records': records, 'errors': errors,
        'identity': identity, 'source_valid': source_valid, 'loaded_modules': modules,
        'raw_result_sha256': digest(call/'wrapper_raw_result.json') if result is not None else None,
        'wall_including_cleanup_s': wall, 'post_eligible': records['post_eligible'],
        'fixture_only': plan['fixture_only'], 'retry': False})
    return 0 if records['normal_terminal'] else 2


def post(folder, output, approval_path):
    started = time.monotonic()  # All preparation, imports and checks cost this 60s.
    folder, output = Path(folder).resolve(), Path(output).resolve()
    plan = authorize(folder, output, approval_path)
    require_phase(folder,output,approval_path,'post',plan)
    method_return = read(output/'method_return.json')
    if not method_return.get('post_eligible'): raise ValueError('No normal complete SAFE for post')
    if digest(output/'method/wrapper_raw_result.json') != method_return.get('raw_result_sha256'):
        raise ValueError('Original method result changed after admission')
    write_new(output/'post.claim.json', {'utc':now(),'start':started,'deadline':started+60,
        'seconds':60,'retry':False,'new_U':False})
    call = output/'method'; before = digest(call/'wrapper_raw_result.json')
    record = {'passed':False,'evaluation_calls':0,'new_U':False,'errors':[]}
    try:
        engine = bind(folder, plan)
        budget = engine.thermal.Budget(seconds=60); budget.start = started; budget.check()
        original = read(call/'wrapper_raw_result.json')
        config, instance = read(folder/'input_config.json'), read(folder/'input_instance.json')
        candidate = original['safe_candidate']
        legality = engine.domain.validate_candidate(instance, candidate, config)['legality']
        budget.check(); record['evaluation_calls'] = 1
        fresh = engine.thermal.evaluate_candidate(instance, candidate, config['accuracy_targets'], budget)
        write_new(output/'postcheck.json', fresh)
        from admission import post_records
        record.update(post_records(original, fresh, candidate, plan['spec'],
            receipt_issues=engine.receipt_issues, exact_enclosure=engine.exact_enclosure, legality=legality))
        verify_frozen(folder, plan); loaded_sources(folder, plan)
        if digest(call/'wrapper_raw_result.json') != before: raise ValueError('Post changed original U/result')
    except BaseException: record['passed']=False; record['errors'].append(traceback.format_exc())
    record.update(wall_s=time.monotonic()-started, original_result_sha256=before,
        original_result_unchanged=digest(call/'wrapper_raw_result.json')==before)
    write_new(output/'post_return.json', record)
    return 0 if record['passed'] else 2


def host_context():
    # Same established host/memory gates, no MATLAB startup or study input.
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('k187_resource_helpers', SCIENCE/'long_budget_diagnostic/run_once.py')
    module = module_from_spec(spec); spec.loader.exec_module(module)
    return module.context(), module.resource_ok


def capture_owned(proc):
    """Capture only the just-created Popen identity, before polling its work."""
    import psutil
    if proc.poll() is not None:
        return {'pid': proc.pid, 'created': None, 'state': 'EXITED_BEFORE_CAPTURE'}
    process = psutil.Process(proc.pid)
    return {'pid': process.pid, 'created': process.create_time(), 'state': 'CAPTURED'}


def stop_owned(proc, identity):
    """Best-effort owned-tree cleanup, refusing a recycled root PID.

    A missing identity permits only the Popen handle fallback, never a PID/tree
    lookup that could refer to an unrelated process. Cleanup does not retry any
    scientific call or admit any late evidence.
    """
    import psutil
    record = {'attempted': False, 'root_identity': identity,
              'identities': [], 'errors': [], 'verified_closed': False}
    try:
        if proc.poll() is not None:
            record.update(reason='OWNED_ROOT_ALREADY_EXITED', verified_closed=True)
            return record
    except BaseException as error:
        record['errors'].append('ROOT_POLL:'+repr(error))
    if not isinstance(identity, dict) or identity.get('pid') != proc.pid or identity.get('created') is None:
        # Popen methods use its original process handle on Windows. Do not use
        # taskkill or enumerate a PID whose creation time was not established.
        record.update(attempted=True, reason='OWNED_HANDLE_ONLY_IDENTITY_UNAVAILABLE')
        try:
            proc.kill(); proc.wait(timeout=10)
            record['verified_closed'] = proc.returncode is not None
        except BaseException as error:
            record['errors'].append('OWNED_HANDLE_CLEANUP:'+repr(error))
        record['descendant_cleanup_unverified'] = True
        return record
    try:
        parent = psutil.Process(proc.pid)
        if parent.create_time() != identity['created']:
            record.update(reason='ROOT_PID_REUSED_NOT_KILLED', verified_closed=True)
            return record
        # Children are captured while the original root identity still matches.
        targets = list(reversed(parent.children(recursive=True)))+[parent]
        record['identities'] = [{'pid':p.pid, 'created':p.create_time()} for p in targets]
        record['attempted'] = True
        for process, captured in zip(targets, record['identities']):
            try:
                if process.create_time() == captured['created']: process.terminate()
            except psutil.NoSuchProcess: pass
            except BaseException as error: record['errors'].append('TERMINATE:'+repr(error))
        _, alive = psutil.wait_procs(targets, timeout=5)
        for process in alive:
            try: process.kill()
            except psutil.NoSuchProcess: pass
            except BaseException as error: record['errors'].append('KILL:'+repr(error))
        _, remaining = psutil.wait_procs(alive, timeout=5)
        record['remaining_pids'] = [p.pid for p in remaining]
        record['verified_closed'] = not remaining
    except psutil.NoSuchProcess:
        record.update(reason='ORIGINAL_ROOT_EXITED_DURING_CLEANUP', verified_closed=True)
    except BaseException as error:
        record['errors'].append('OWNED_TREE_CLEANUP:'+repr(error))
        # Still terminate the original Popen handle if tree inspection failed.
        try: proc.kill(); proc.wait(timeout=10)
        except BaseException as fallback: record['errors'].append('OWNED_HANDLE_CLEANUP:'+repr(fallback))
    return record


def launch(folder, output, approval_path, *, popen=subprocess.Popen, clock=time.monotonic,
           sleep=time.sleep, context_factory=host_context, terminator=stop_owned,
           capturer=capture_owned):
    started = clock(); deadline = started+480
    folder, output = Path(folder).resolve(), Path(output).resolve()
    authorize(folder, output, approval_path)
    checks = read(folder/'pure_checks.json')
    if checks.get('passed') is not True or checks.get('plan_sha256') != digest(folder/'plan.json'):
        raise ValueError('Matching pure precheck required')
    if output.exists(): raise FileExistsError('One-shot output already exists; no resume/retry')
    host, resource_ok = context_factory()
    if not resource_ok(host): return {'state':'NOT_STARTED_RESOURCE_GATE','research_calls':0,'host':host}
    if clock()>=deadline: raise TimeoutError('Calendar exhausted before launch')
    output.mkdir(exist_ok=False)
    phases=[]; post_skip=None; errors=[]; proc=None; identity=None
    try:
        write_new(output/'launch.claim.json',{'utc':now(),'plan_sha256':digest(folder/'plan.json'),
            'approval_sha256':digest(approval_path),'start':started,'deadline':deadline,'host':host,'retry':False})
        for phase, watchdog in [('method',420),('post',75)]:
            if phase=='post':
                if not read(output/'method_return.json').get('post_eligible'):
                    post_skip='NO_NORMAL_COMPLETE_SAFE'; break
                if clock()+75+CLEANUP_RESERVE_S>=deadline:
                    post_skip='INSUFFICIENT_CALENDAR_FOR_FULL_POST_AND_RETURN'; break
            child_started=clock(); stopped=False; terminated=None; proc=None; identity=None
            phase_record={'phase':phase,'returncode':None,'wall_s':None,
                          'watchdog_stop':False,'terminated':None,'owned_identity':None}
            try:
                write_new(output/(phase+'.request.json'), {'phase':phase,
                    'plan_sha256':digest(folder/'plan.json'),'calendar_deadline':deadline})
                with (output/(phase+'.stdout.txt')).open('xb') as log:
                    proc=popen([sys.executable,'-B',str(HERE/'run_once.py'),phase,
                        '--preparation',str(folder),'--out',str(output),'--approval',str(Path(approval_path).resolve())],
                        cwd=str(REPO),stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    identity=capturer(proc)
                    while proc.poll() is None:
                        if clock()>=min(child_started+watchdog,deadline-CLEANUP_RESERVE_S):
                            stopped=True; break
                        sleep(.25)
                    if not stopped: proc.wait(timeout=10)
            finally:
                # Complete owned cleanup before any terminal serialization.
                # A failing poll is not permission to leave a live child.
                if proc is not None:
                    try: active=proc.poll() is None
                    except BaseException: active=proc.returncode is None
                    if active:
                        try: terminated=terminator(proc,identity)
                        except BaseException:
                            errors.append({'phase':phase,'cleanup_error':traceback.format_exc()})
                            try: proc.kill(); proc.wait(timeout=10)
                            except BaseException: errors.append({'phase':phase,'handle_cleanup_error':traceback.format_exc()})
                    phase_record['returncode']=proc.returncode
                phase_record.update(wall_s=clock()-child_started,watchdog_stop=stopped,
                                    terminated=terminated,owned_identity=identity)
                phases.append(phase_record)
                proc=None
            if stopped or phase_record['returncode']!=0 or errors: break
    except BaseException:
        errors.append({'phase':'supervisor','error':traceback.format_exc()})
    finally:
        # Covers errors in phase-finalization as well. This is process cleanup,
        # never a second method/post invocation or late scientific acceptance.
        if proc is not None:
            try: terminator(proc,identity)
            except BaseException:
                errors.append({'phase':'supervisor_finally','cleanup_error':traceback.format_exc()})
                try: proc.kill(); proc.wait(timeout=10)
                except BaseException: errors.append({'phase':'supervisor_finally','handle_cleanup_error':traceback.format_exc()})
    wall=clock()-started
    terminal={'state':'STOPPED_EXCEPTION' if errors else 'STOPPED_CALENDAR_OVERRUN' if wall>480 else 'COMPLETED' if phases and all(p['returncode']==0 and not p['watchdog_stop'] for p in phases) else 'STOPPED',
        'phases':phases,'calendar_s':wall,'calendar_limit_s':480,'post_skip':post_skip,
        'calendar_limit_respected':wall<=480,'calendar_cleanup_reserve_s':CLEANUP_RESERVE_S,
        'calendar_overshoot_s':max(0.,wall-480),
        'research_calls':int((output/'method.claim.json').exists()),
        'post_calls':int((output/'post.claim.json').exists()),'no_retry':True,'errors':errors}
    try: write_new(output/'terminal.json',terminal)
    except BaseException:
        terminal['state']='STOPPED_EXCEPTION'
        terminal['errors'].append({'phase':'terminal_archive','error':traceback.format_exc()})
        # Children are already finalized even if both archive channels fail.
        try: write_new(output/'terminal_archive_failure.json',terminal)
        except BaseException: print(json.dumps(terminal,ensure_ascii=False),file=sys.stderr,flush=True)
    return terminal


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','launch','method','post'])
    parser.add_argument('--preparation',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    if args.action=='prepare':
        print(json.dumps({'prepared':True,'authorized':prepare(args.preparation)['authorized']}))
    else:
        if args.out is None or args.approval is None: parser.error('Explicit output and separate approval are required')
        result=globals()[args.action](args.preparation,args.out,args.approval)
        if isinstance(result,int): raise SystemExit(result)
        print(json.dumps(result,ensure_ascii=False))
