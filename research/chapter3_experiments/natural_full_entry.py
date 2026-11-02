"""One natural full-domain MILP / HEFT / SA101 manual-approved batch.

No algorithm or thermal module is imported by freeze/authorization/supervision.
The separate USER approval is the K195/K196 manual route, not agent_loop review.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / 'research/chapter3_experiments'
RESULTS = EXP / 'results'
ENTRY = 'research/chapter3_experiments/natural_full_entry.py'
INPUT = 'research/chapter3_experiments/results/natural_full_preparation01/input_instance.json'
CONFIG = 'research/chapter3_experiments/results/natural_full_preparation01/input_config.json'
PREPARATION = RESULTS / 'natural_full_preparation01'
STATIC = PREPARATION / 'static_size.json'
DOMAIN = PREPARATION / 'domain_identity.json'
JOBS = [{'id':'whole_milp','method':'whole_milp','seed':None},
        {'id':'heft','method':'heft','seed':None}, {'id':'sa101','method':'sa','seed':101}]
SCOPE = {'method_calls':3,'method_seconds_each':300,'method_seconds_total':900,
         'post_calls_at_most':3,'post_seconds_each':60,'post_seconds_total_at_most':180,
         'job_calendar_seconds':480,'batch_calendar_seconds':1440,'retries':0}
BUILDER_FLAGS = dict(include_physics=True, prefilter_deadlines=True,
    cumulative_precedence=False, fixed_deployment=None, fixed_shared_deployment=None,
    fixed_scene_id=None, neighborhood_condition=None, preeliminate_closed_anchors=False,
    fix_late_options=True, aggregate_opp_locks=True, relax_auxiliary_integrality=True,
    strengthen_energy_lower_bounds=True)



def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        f.write('\n')


def git_bytes(*args):
    return subprocess.check_output(['git', *args], cwd=str(ROOT))


def verify_sources(plan):
    for rel, digest in plan['source_sha256'].items():
        path = (ROOT / rel).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == digest, 'SOURCE_DRIFT:'+rel)
    require(sha(ROOT / INPUT) == plan['input_sha256'] and sha(ROOT / CONFIG) == plan['config_sha256'], 'INPUT_DRIFT')
    require(sha(STATIC) == plan['static_size_sha256'] and sha(DOMAIN) == plan['domain_identity_sha256'], 'DOMAIN_EVIDENCE_DRIFT')


def receipt_failure(value):
    """Numerical/technical failures must not be hidden by an older SAFE."""
    if isinstance(value, dict):
        if value.get('reason') in ('NUMERICAL_ERROR', 'INTERNAL_CONSISTENCY_ERROR', 'RESOURCE_LIMIT'):
            return value['reason']
        if value.get('error_type') or value.get('error'):
            return str(value.get('error_type') or value.get('error'))
        for item in value.values():
            failure = receipt_failure(item)
            if failure:
                return failure
    elif isinstance(value, list):
        for item in value:
            failure = receipt_failure(item)
            if failure:
                return failure
    return None


def freeze(folder):
    from importlib import metadata
    folder = Path(folder).resolve()
    require(folder == PREPARATION and not (folder/'plan.json').exists() and not (folder/'approval_template.json').exists(), 'NEW_PLAN_REQUIRED')
    identity = read(DOMAIN); size = read(STATIC)
    require(identity['state']=='PASS' and all(identity['checks'].values()), 'FULL_DOMAIN_IDENTITY')
    require(size['deadline_legal_options']==613 and size['predicted_total_variables']==10956
            and size['predicted_total_rows']==70513 and size['explicit_start_domain_present'] is False, 'STATIC_SIZE_SCOPE')
    native = read(RESULTS/'small_whole_preparation01/plan.json')
    old = read(RESULTS/'small_whole_preparation01/plan.json')['source_sha256']
    require(len(old) == 197, 'SCIENCE_SOURCE_COUNT')
    for rel, digest in old.items():
        require(sha(ROOT/rel) == digest, 'K195_SCIENCE_DRIFT:'+rel)
    sources = dict(old)
    for rel in (ENTRY, 'research/chapter3_method_entry_executor/common.py',
                'research/chapter3_method_entry_executor/monitor.py',
                'research/chapter3_method_entry_executor/__init__.py',
                'research/chapter3_experiments/small_whole_execution/native_contract.py',
                'research/chapter3_experiments/full_domain_size.py',
                'research/chapter3_experiments/natural_full_input.py'):
        sources[rel] = sha(ROOT/rel)
    plan = {'schema': 'natural-full-three-manual-v1', 'execution_authorized': False,
            'baseline_commit': git_bytes('rev-parse', 'HEAD').decode().strip(),
            'input_file': INPUT, 'input_sha256': sha(ROOT/INPUT),
            'config_file': CONFIG, 'config_sha256': sha(ROOT/CONFIG),
            'static_size_sha256':sha(STATIC), 'domain_identity_sha256':sha(DOMAIN),
            'builder_flags':BUILDER_FLAGS, 'native_executable':native['native_executable'],
            'native_executable_sha256':native['native_executable_sha256'],
            'native_options':native['native_options'], 'feedback_kind':'conditional', 'cut_max_iterations':10,
            'source_sha256': sources, 'science_source_count': 197,
            'jobs': JOBS, 'scope': SCOPE, 'python_executable': str(Path(sys.executable).resolve()),
            'python_version': sys.version,
            'dependencies': {n: metadata.version(n) for n in ('numpy', 'scipy', 'psutil')},
            'method_process_watchdog_seconds': 405,
            'clock_origin': 'parent monotonic before per-job preparation, imports and interpreter startup',
            'historical_candidate_or_cache_input': False, 'reference_read_by_search': False,
            'approval_path': 'separate immutable-subject/plan-bound USER manual approval; not external agent_loop review'}
    verify_sources(plan)
    save(folder/'plan.json', plan)
    save(folder/'approval_template.json', {
        'schema': 'natural-full-three-user-approval-v1', 'approved_by_user': False,
        'approval_source': 'USER_CURRENT_CONVERSATION', 'human_authorization_text': '',
        'subject_commit': None, 'plan_sha256': sha(folder/'plan.json'), 'scope': SCOPE,
        'output_directory': None, 'not_an_external_agent_loop_review': True})
    return {'plan': str(folder/'plan.json'), 'sha256': sha(folder/'plan.json'), 'authorized': False}


def validate_plan(plan):
    require(plan.get('schema') == 'natural-full-three-manual-v1' and plan.get('execution_authorized') is False,
            'PLAN_SCHEMA')
    require(plan.get('jobs') == JOBS and plan.get('scope') == SCOPE, 'PLAN_SCOPE')
    require((plan.get('input_file'), plan.get('config_file')) == (INPUT, CONFIG), 'PLAN_INPUT')
    require(plan.get('builder_flags') == BUILDER_FLAGS and plan.get('feedback_kind')=='conditional'
            and plan.get('cut_max_iterations')==10, 'PLAN_SCIENCE_FLAGS')
    require(plan.get('method_process_watchdog_seconds') == 405
            and plan.get('historical_candidate_or_cache_input') is False
            and plan.get('reference_read_by_search') is False, 'PLAN_BOUNDARIES')
    require(plan.get('science_source_count') == 197 and ENTRY in plan['source_sha256'], 'SOURCE_MANIFEST')


def authorize(plan_path, approval_path, output, *, verify_subject=True):
    plan_path, approval_path, output = map(lambda p: Path(p).resolve(), (plan_path, approval_path, output))
    plan, auth = read(plan_path), read(approval_path)
    validate_plan(plan)
    require(plan_path.is_relative_to(RESULTS) and output.is_relative_to(RESULTS), 'PATH_SCOPE')
    require(auth.get('schema') == 'natural-full-three-user-approval-v1' and auth.get('approved_by_user') is True
            and auth.get('approval_source') == 'USER_CURRENT_CONVERSATION'
            and isinstance(auth.get('human_authorization_text'), str) and auth['human_authorization_text'].strip(),
            'SEPARATE_USER_APPROVAL_REQUIRED')
    require(auth.get('plan_sha256') == sha(plan_path) and auth.get('scope') == SCOPE
            and Path(auth.get('output_directory') or '').resolve() == output
            and auth.get('not_an_external_agent_loop_review') is True, 'APPROVAL_BINDING')
    subject = auth.get('subject_commit')
    require(isinstance(subject, str) and len(subject) == 40 and all(c in '0123456789abcdef' for c in subject),
            'IMMUTABLE_SUBJECT_REQUIRED')
    verify_sources(plan)
    if verify_subject:
        require(hashlib.sha256(git_bytes('show', subject+':'+plan_path.relative_to(ROOT).as_posix())).hexdigest()
                == sha(plan_path), 'SUBJECT_PLAN_DRIFT')
        for rel, digest in plan['source_sha256'].items():
            require(hashlib.sha256(git_bytes('show', subject+':'+rel)).hexdigest() == digest,
                    'SUBJECT_SOURCE_DRIFT:'+rel)
    from importlib import metadata
    require(str(Path(sys.executable).resolve()) == plan['python_executable'] and sys.version == plan['python_version'],
            'PYTHON_DRIFT')
    require(all(metadata.version(n) == v for n, v in plan['dependencies'].items()), 'DEPENDENCY_DRIFT')
    return plan


def validate_ticket(ticket_path, token):
    from research.chapter3_method_entry_executor.monitor import PsutilProvider
    path = Path(ticket_path).resolve()
    ticket = read(path)
    root = Path(ticket['output']).resolve()
    require(root.is_relative_to(RESULTS) and path == root/'slots'/ticket['slot_id']/'ticket.json', 'TICKET_PATH')
    require(ticket['token'] == token and ticket['job'] in JOBS and ticket['mode'] in ('method', 'post'), 'TICKET_SCOPE')
    require(ticket['slot_id'] == ticket['job']['id']+'__'+ticket['mode'], 'SLOT_ID')
    origin, cutoff = ticket['origin'], ticket['scientific_deadline']
    seconds = 300 if ticket['mode'] == 'method' else 60
    require(type(origin) in (float, int) and math.isfinite(origin) and cutoff == origin+seconds
            and origin <= time.monotonic() < cutoff, 'TICKET_DEADLINE')
    plan = authorize(ticket['plan'], ticket['approval'], root, verify_subject=False)
    require(sha(ticket['plan']) == ticket['plan_sha256'], 'TICKET_PLAN_DRIFT')
    claim = read(RESULTS/'natural_full_claims'/(ticket['plan_sha256']+'.json'))
    require(claim['output'] == str(root) and claim['approval_sha256'] == sha(ticket['approval']), 'CLAIM_BINDING')
    require(read(path.parent/'slot_claim.json')['ticket_sha256'] == sha(path), 'SLOT_CLAIM_BINDING')
    if ticket['mode'] == 'post':
        method_path = root/'slots'/(ticket['job']['id']+'__method')/'worker'/'raw_result.json'
        require(ticket.get('method_receipt_sha256') == sha(method_path), 'POST_SOURCE_DRIFT')
    else:
        require(ticket.get('method_receipt_sha256') is None, 'METHOD_FOREIGN_RECEIPT')
    provider = PsutilProvider()
    parent = provider.describe(os.getppid())
    require(parent.get('state') == 'ACTIVE' and [parent['pid'], parent.get('create_time')] == ticket['parent_identity'],
            'PARENT_IDENTITY')
    go = path.parent/'go.json'
    while not go.exists() and time.monotonic() < cutoff:
        time.sleep(.02)
    require(go.exists(), 'NO_MONITOR_HANDSHAKE')
    hand = read(go); own = provider.describe(os.getpid())
    require(hand['ticket_sha256'] == sha(path) and hand['worker_identity'] == [own.get('pid'), own.get('create_time')],
            'WORKER_IDENTITY')
    save(path.parent/'worker_started.json', {'pid': os.getpid(), 'ticket_sha256': sha(path)})
    return ticket, plan


class ParentOriginClock:
    """Install the known parent origin at MethodBudget's first clock read.

    The frozen formal->warm->method entry first calls this in
    MethodBudget.__init__. Every later read is the real monotonic clock.
    No elapsed interval is scaled, replenished or shifted after construction.
    """
    def __init__(self, origin, clock=time.monotonic):
        require(type(origin) in (int,float) and math.isfinite(origin) and origin <= clock(), 'PARENT_CLOCK_ORIGIN')
        self.origin, self.clock, self.first = origin, clock, True

    def __call__(self):
        if self.first:
            self.first = False
            return self.origin
        return self.clock()


def declaration(instance, config):
    from research.chapter3_method_entry_executor.common import canonical
    return {'problem_id':instance['id'], 'input_sha256':canonical(instance),
            'config_sha256':canonical(config), 'scene_spec':{
                s['id']:{'window_s':str(F(instance['window_ms'])/1000), 'weight':s['weight'],
                         'limits':dict(zip(instance['platform']['node_order'],s['maximum_temperature_degC']))}
                for s in instance['scenarios']}}


def admit_model(model, estimate):
    """Observe completed original model metadata; never add/remove rows."""
    require(model.instance.get('start_domain') is None, 'EXPLICIT_START_RESTRICTION')
    require(len(model.options)==estimate['deadline_legal_options'], 'MODEL_OPTION_COUNT')
    require(len(model.names)==estimate['predicted_total_variables'], 'MODEL_VARIABLE_COUNT')
    require(len(model.rows)==estimate['predicted_total_rows'], 'MODEL_ROW_COUNT')
    require(set(model.integer)==set(model.option_vars) and len(model.integer)==estimate['stage_binary_variables'],
            'STAGE_INTEGER_CHOICES_CHANGED')
    require(all(model.lb[i]==0 and model.ub[i]==1 for i in model.option_vars), 'STAGE_BINARY_BOUNDS')
    require(model.coefficients.calls==estimate['unique_state_duration_coefficient_keys'], 'COEFFICIENT_KEY_COUNT')
    for scene in estimate['scenes']:
        events = [str(x) for x in model.scenes[scene['id']]['events']]
        digest = hashlib.sha256(json.dumps(events,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        require(len(events)==scene['events'] and digest==scene['event_times_s_sha256'], 'MODEL_EVENT_DOMAIN')
    nnz=sum(len(row['coef']) for row in model.rows)
    require(nnz<=estimate['nonzeros_upper_bound'], 'MODEL_NONZERO_UPPER_BOUND')
    return {'state':'PASS','variables':len(model.names),'rows':len(model.rows),
            'stage_integer_options':len(model.integer),'actual_nonzeros':nnz,
            'scope':'completed model metadata only; original options/rows unchanged'}


def native_session_factory(plan):
    from matlab_bridge import MatlabSession
    from research.chapter3_experiments.small_whole_execution import native_contract
    def create(*args, **kwargs):
        require('cut_max_iterations' not in kwargs, 'NATIVE_CUT_OVERRIDE')
        require(sha(plan['native_executable'])==plan['native_executable_sha256'], 'NATIVE_BINARY_DRIFT')
        session=MatlabSession(*args,**kwargs,matlab_path=plan['native_executable'],cut_max_iterations=10)
        try:
            save(session.workdir.parent/'native_ready_admission.json',
                 native_contract.validate_ready(read(session.workdir/'ready.json')))
        except BaseException:
            session.close()
            raise
        original=session.solve
        def solve(payload, **kw):
            returned=original(payload,**kw)
            prefix=session.workdir/f'request_{session.counter:06d}'
            response_path=prefix.with_suffix('.response.json')
            if response_path.exists():
                response=read(response_path)
                if response.get('options'):
                    checked=native_contract.validate_request_response(read(prefix.with_suffix('.request.json')),
                              response,plan['native_options'])
                    save(prefix.with_suffix('.options_admission.json'),checked)
                elif returned.get('status')=='SOLVED':
                    raise ValueError('SOLVED_RESPONSE_WITHOUT_NATIVE_OPTIONS')
            return returned
        session.solve=solve
        return session
    return create


def run_whole(ticket, plan, folder):
    """One unchanged whole lifecycle, with parent-root timing and pure guards."""
    from functools import partial
    sys.path.insert(0,str(EXP/'p0_batch'))
    from formal_milp import execute_formal_milp
    from milp import build_model
    from partial_bounds import independent_lower_bound
    from audit_whole import result_records
    call=folder/'method'; identity={'input':False}; bounds={}
    config, instance=read(ROOT/CONFIG),read(ROOT/INPUT)
    spec=declaration(instance,config)
    def loader(budget):
        require(budget.start==ticket['origin'] and budget.deadline==ticket['scientific_deadline'], 'ROOT_CLOCK_NOT_INSTALLED')
        save(call/'method_budget_identity.json',{'start':budget.start,'deadline':budget.deadline,
             'limit_s':300,'clock':'monotonic','origin_scope':'parent before preparation/import/startup'})
        verify_sources(plan);budget.check()
        loaded_config,loaded_instance=read(ROOT/CONFIG),read(ROOT/INPUT)
        require(declaration(loaded_instance,loaded_config)==spec,'LOADER_INPUT_DRIFT')
        identity['input']=True
        with budget.phase('comparison_independent_lower_bound'):
            bounds['L0']=independent_lower_bound(loaded_instance,None,budget)
        budget.check()
        return loaded_config,loaded_instance
    def builder(instance,config,**kwargs):
        require({k:v for k,v in kwargs.items() if k not in ('budget','progress')}==BUILDER_FLAGS,
                'WHOLE_BUILDER_FLAGS_DRIFT')
        model=build_model(instance,config,**kwargs)
        save(call/'full_domain_model_admission.json',admit_model(model,read(STATIC)))
        kwargs['budget'].check()
        return model
    extra={k:v for k,v in BUILDER_FLAGS.items() if k not in
           ('fix_late_options','aggregate_opp_locks','relax_auxiliary_integrality','strengthen_energy_lower_bounds')}
    raw=execute_formal_milp(loader,call,seconds=300,clock=ParentOriginClock(ticket['origin']),
          feedback_kind='conditional',model_builder=partial(builder,**extra),
          session_factory=native_session_factory(plan))
    if bounds:save(call/'independent_bounds.json',bounds)
    verify_sources(plan)
    audit=result_records(raw,spec,call,input_valid=identity['input'],source_valid=True,errors=[])
    save(folder/'whole_audit.json',audit)
    save(folder/'clock_contract.json',{'origin':ticket['origin'],'deadline':ticket['scientific_deadline'],
         'scope':'Parent preparation/imports/startup included by first constructor clock read; raw legacy clock_origin text is superseded by this record.'})
    return raw,audit


def worker(ticket_path, token):
    ticket, plan = validate_ticket(ticket_path, token)
    folder = Path(ticket_path).parent/'worker'
    folder.mkdir()
    # The original budget class must share the exact thermal module imported by the method.
    sys.path.insert(0, str(EXP))
    from timing import MethodBudget
    from thermal import Exhausted
    from research.chapter3_method_entry_executor.common import inspect_safe_receipt
    from schedules import validate_schedule
    def validate_candidate(instance, candidate, config):
        require(validate_schedule(instance,candidate)['state']=='SCHEDULE_VALID_THERMAL_UNCHECKED', 'FULL_DOMAIN_SCHEDULE_INVALID')
    seconds = 300 if ticket['mode'] == 'method' else 60
    budget = MethodBudget(seconds)
    budget.start, budget.deadline = ticket['origin'], ticket['scientific_deadline']
    result = {'state': 'UNRESOLVED', 'status': 'NORMAL_TIME_LIMIT', 'error': None,
              'job': ticket['job'], 'plan_sha256': ticket['plan_sha256'],
              'origin': budget.start, 'scientific_deadline': budget.deadline}
    try:
        budget.check()
        if ticket['mode'] == 'method':
            if ticket['job']['method']=='whole_milp':
                raw,audit=run_whole(ticket,plan,folder)
                save(folder/'raw_result.json',raw)
                instance,config=read(ROOT/INPUT),read(ROOT/CONFIG)
                safe=inspect_safe_receipt(instance,raw,300)
                if safe['preserved']:
                    validate_candidate(instance,safe['candidate'],config)
                result.update(state=raw.get('state'),status=audit['execution']['execution_status'],
                              safe=safe,whole_audit=audit,method_reason=raw.get('reason'))
                require((raw.get('safe_upper_bound_J') is None or safe['preserved'])
                        and audit.get('usable_U_J')==safe.get('U_J'),'WHOLE_FINAL_SAFE_ADMISSION')
                result['worker_elapsed_s']=time.monotonic()-ticket['origin']
                save(folder/'worker_result.json',result)
                return result
            from heuristic_runner import execute_heuristic
            from thermal import evaluate_candidate
            def guarded_evaluate(*args, **kwargs):
                ev = evaluate_candidate(*args, **kwargs)
                failure = receipt_failure(ev)
                if failure:
                    save(folder/'evaluation_failure.json', ev)
                    raise RuntimeError('EVALUATION_TECHNICAL_FAILURE:'+failure)
                return ev
            def loader(root_budget):
                root_budget.check()
                verify_sources(plan)
                config, instance = read(ROOT/CONFIG), read(ROOT/INPUT)
                root_budget.check()
                return config, instance
            raw = execute_heuristic(loader, folder/'method', method=ticket['job']['method'],
                                    seed=ticket['job']['seed'], seconds=300, budget=budget, allow_auto_low=True,
                                    evaluator=guarded_evaluate)
            save(folder/'raw_result.json', raw)
            instance, config = read(ROOT/INPUT), read(ROOT/CONFIG)
            safe = inspect_safe_receipt(instance, raw, 300)
            if safe['preserved']:
                validate_candidate(instance, safe['candidate'], config)
            malformed_safe = raw.get('state') == 'SAFE' and not safe['preserved']
            # The original recorder never promotes a late or malformed SAFE to raw.state=SAFE.
            abnormal = receipt_failure(raw) or raw.get('reason') == 'INTERFACE_ERROR' or malformed_safe
            result.update(state=raw.get('state'), status='TECHNICAL_FAILURE' if abnormal else
                          ('NORMAL_TIME_LIMIT' if raw.get('budget_exhausted') else 'NORMAL_COMPLETION'),
                          safe=safe, error=raw.get('error') or ('INVALID_FINAL_SAFE_RECEIPT' if malformed_safe else None),
                          method_reason=raw.get('reason'))
        else:
            from thermal import evaluate_candidate
            source = Path(ticket['output'])/'slots'/(ticket['job']['id']+'__method')/'worker'/'raw_result.json'
            require(sha(source) == ticket['method_receipt_sha256'], 'POST_SOURCE_DRIFT')
            raw = read(source)
            instance, config = read(ROOT/INPUT), read(ROOT/CONFIG)
            previous = inspect_safe_receipt(instance, raw, 300)
            require(previous['preserved'], 'POST_WITHOUT_COMPLETE_SAFE')
            validate_candidate(instance, previous['candidate'], config)
            budget.check()
            ev = evaluate_candidate(instance, previous['candidate'], config['accuracy_targets'], budget)
            require(sha(source) == ticket['method_receipt_sha256'], 'POST_SOURCE_CHANGED_DURING_CHECK')
            if receipt_failure(ev):
                save(folder/'evaluation_failure.json', ev)
                raise RuntimeError('POST_EVALUATION_TECHNICAL_FAILURE:'+receipt_failure(ev))
            checked = inspect_safe_receipt(instance, {'safe_candidate': previous['candidate'], 'evaluation': ev,
                                            'safe_upper_bound_J': ev.get('safe_upper_bound_J')}, 60)
            state = ev.get('state')
            if checked['preserved']:
                a,b = map(F, raw['evaluation']['weighted_energy_J']); c,d = map(F, ev['weighted_energy_J'])
                require(max(a,c) <= min(b,d), 'POST_ENERGY_INTERVAL_CONFLICT')
            require(state in ('SAFE', 'UNRESOLVED', 'THERMAL_VIOLATION', 'INVALID_SCHEDULE'), 'POST_STATE')
            if state == 'SAFE' and not checked['preserved']:
                formed = ev.get('completed_at_elapsed_s')
                require(type(formed) in (int, float) and math.isfinite(formed) and formed >= 60,
                        'INVALID_POST_SAFE_RECEIPT')
                state = 'UNRESOLVED'
            post = {'state': state, 'evaluation': ev, 'method_receipt_sha256': sha(source),
                    'same_candidate': previous['candidate'], 'new_method_result_accepted': False,
                    'safe': checked, 'elapsed_s': budget.elapsed}
            save(folder/'post_result.json', post)
            result.update(state=state, status='NORMAL_COMPLETION' if state == 'SAFE' else
                          ('NORMAL_UNRESOLVED' if state == 'UNRESOLVED' else 'SAFETY_FAILURE'))
    except Exhausted:
        result.update(state='UNRESOLVED', status='NORMAL_TIME_LIMIT')
    except Exception as error:
        result.update(status='TECHNICAL_FAILURE', error=type(error).__name__+': '+str(error))
    result['worker_elapsed_s'] = budget.elapsed
    save(folder/'worker_result.json', result)
    return result


def run_slot(plan_path, approval_path, plan, output, job, mode, origin, job_deadline, batch_deadline):
    from research.chapter3_method_entry_executor.monitor import ProcessMonitor, PsutilProvider
    slot = output/'slots'/(job['id']+'__'+mode)
    slot.mkdir(parents=True)
    parent = PsutilProvider().describe(os.getpid())
    require(parent.get('state') == 'ACTIVE' and parent.get('create_time') is not None, 'PARENT_IDENTITY_UNKNOWN')
    token = secrets.token_hex(24)
    ticket = {'plan': str(plan_path), 'approval': str(approval_path), 'plan_sha256': sha(plan_path),
              'output': str(output), 'job': job, 'mode': mode, 'slot_id': slot.name,
              'origin': origin, 'scientific_deadline': origin+(300 if mode == 'method' else 60),
              'parent_identity': [parent['pid'], parent['create_time']], 'token': token,
              'method_receipt_sha256': sha(output/'slots'/(job['id']+'__method')/'worker'/'raw_result.json')
                if mode == 'post' else None}
    save(slot/'ticket.json', ticket)
    save(slot/'slot_claim.json', {'ticket_sha256': sha(slot/'ticket.json')})
    watchdog = min(origin+(405 if mode == 'method' else 60), job_deadline-15, batch_deadline-15)
    process = monitor = None
    record = {'job': job['id'], 'mode': mode, 'origin': origin, 'watchdog': watchdog,
              'status': 'TECHNICAL_FAILURE', 'error': None}
    try:
        require(time.monotonic() < ticket['scientific_deadline'], 'BUDGET_EXHAUSTED_BEFORE_SPAWN')
        with (slot/'stdout.txt').open('w', encoding='utf-8') as log:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen([sys.executable, '-B', '-m', 'research.chapter3_experiments.natural_full_entry',
                'worker', '--ticket', str(slot/'ticket.json'), '--token', token],
                cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            monitor = ProcessMonitor(process.pid)
            require(monitor.root_identity is not None, 'ROOT_IDENTITY_UNKNOWN')
            save(slot/'go.json', {'ticket_sha256': sha(slot/'ticket.json'), 'worker_identity': list(monitor.root_identity)})
            while process.poll() is None and time.monotonic() < watchdog:
                monitor.sample()
                time.sleep(.05)
            if process.poll() is None:
                record['watchdog_fired'] = True
                monitor.terminate_owned(force=True)
            process.wait(timeout=max(.1, min(10, job_deadline-time.monotonic(), batch_deadline-time.monotonic())))
        record['returncode'] = process.returncode
        result_path = slot/'worker'/'worker_result.json'
        if result_path.exists():
            record['worker'] = read(result_path)
            record['status'] = record['worker']['status']
        saved_post = slot/'worker'/'post_result.json'
        post_violation = mode == 'post' and saved_post.exists() and read(saved_post).get('state') in (
            'THERMAL_VIOLATION', 'INVALID_SCHEDULE')
        if record.get('watchdog_fired'):
            known_failure = ((record.get('worker') or {}).get('status') in ('TECHNICAL_FAILURE', 'SAFETY_FAILURE')
                             or (slot/'worker'/'evaluation_failure.json').exists() or post_violation)
            record['status'] = ('POST_TIME_LIMIT_UNRESOLVED' if mode == 'post' and not known_failure
                                else 'TECHNICAL_FAILURE')
        elif process.returncode != 0:
            record['status'] = 'TECHNICAL_FAILURE'
        if post_violation:
            record['status'] = 'SAFETY_FAILURE'
    except Exception as error:
        record['error'] = type(error).__name__+': '+str(error)
        record['status'] = 'TECHNICAL_FAILURE'
    finally:
        if process is not None and process.poll() is None:
            # Popen's original OS handle identifies our child even if psutil capture failed.
            try:
                process.kill()
                process.wait(timeout=max(.1, min(10, job_deadline-time.monotonic(), batch_deadline-time.monotonic())))
                record['own_child_handle_closed'] = True
            except Exception as error:
                record['own_child_handle_error'] = type(error).__name__+': '+str(error)
                record['status'] = 'CLEANUP_FAILURE'
        if monitor is not None:
            closed=(record.get('worker',{}).get('whole_audit') or {}).get('cleanup') or {}
            identities=(closed.get('process_tree_verification') or {}).get('identities') or []
            if identities:
                try:
                    monitor.register_identities(identities,source='original MATLAB cleanup receipt')
                except Exception as error:
                    record['native_identity_registration_error']=type(error).__name__+': '+str(error)
                    record['status']='CLEANUP_FAILURE'
            if monitor.cleanup_verified() is not True:
                record['cleanup_signals'] = monitor.terminate_owned(force=True)
                until = min(time.monotonic()+10, job_deadline, batch_deadline)
                while monitor.cleanup_verified() is False and time.monotonic() < until:
                    time.sleep(.05)
            record['monitor'] = monitor.summary()
            save(slot/'memory_samples.json', monitor.samples)
            if record['monitor']['cleanup_verified_observed_tree'] is not True:
                record['status'] = 'CLEANUP_FAILURE'
        else:
            record['status'] = 'TECHNICAL_FAILURE'
        record['total_wall_s'] = time.monotonic()-origin
        if time.monotonic() >= min(job_deadline, batch_deadline):
            record['status'] = 'CALENDAR_LIMIT_FAILURE'
        save(slot/'slot_result.json', record)
    return record


def run(plan_path, approval_path, output):
    from research.chapter3_method_entry_executor.monitor import default_host_probe, host_gate
    plan_path, approval_path, output = map(lambda p: Path(p).resolve(), (plan_path, approval_path, output))
    plan = authorize(plan_path, approval_path, output)
    require(not output.exists(), 'NEW_OUTPUT_REQUIRED')
    # Admission only; each method rechecks sources/resources within its own root.
    probe = default_host_probe(ROOT)
    require(host_gate(probe)['passed'], 'HOST_RESOURCE_GATE_FAILED')
    started = time.monotonic(); deadline = started+1440
    save(RESULTS/'natural_full_claims'/(sha(plan_path)+'.json'), {
        'output': str(output), 'approval_sha256': sha(approval_path), 'scope': SCOPE,
        'started_monotonic': started, 'no_resume_or_retry': True})
    output.mkdir(parents=True)
    batch = {'state': 'RUNNING', 'plan_sha256': sha(plan_path), 'methods': [], 'posts': [],
             'not_run': [j['id'] for j in JOBS], 'error': None, 'method_attempts': 0, 'post_attempts': 0}
    save(output/'host_prelaunch.json', probe)
    try:
        for job in JOBS:
            origin = time.monotonic(); job_deadline = min(origin+480, deadline)
            require(deadline-origin >= 480, 'INSUFFICIENT_BATCH_CALENDAR')
            verify_sources(plan)
            probe = default_host_probe(ROOT)
            save(output/('host_'+job['id']+'.json'), probe)
            require(host_gate(probe)['passed'], 'HOST_RESOURCE_GATE_FAILED')
            batch['method_attempts'] += 1; batch['not_run'].remove(job['id'])
            record = run_slot(plan_path, approval_path, plan, output, job, 'method', origin, job_deadline, deadline)
            batch['methods'].append(record)
            verify_sources(plan)
            require(record['status'] in ('NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST'), 'METHOD_ABNORMAL_STOP')
            if (record.get('worker', {}).get('safe') or {}).get('preserved'):
                origin_post = time.monotonic()
                require(min(job_deadline, deadline)-origin_post >= 75, 'INSUFFICIENT_POST_CALENDAR')
                batch['post_attempts'] += 1
                post = run_slot(plan_path, approval_path, plan, output, job, 'post', origin_post, job_deadline, deadline)
                batch['posts'].append(post)
                verify_sources(plan)
                require(post['status'] in ('NORMAL_COMPLETION', 'NORMAL_UNRESOLVED', 'NORMAL_TIME_LIMIT',
                                           'POST_TIME_LIMIT_UNRESOLVED'), 'POST_ABNORMAL_STOP')
            save(output/'progress'/(job['id']+'.json'), batch)
        batch['state'] = 'COMPLETED'
    except Exception as error:
        batch.update(state='STOPPED', error=type(error).__name__+': '+str(error))
    batch['total_wall_s'] = time.monotonic()-started
    save(output/'batch.json', batch)
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    f = sub.add_parser('freeze'); f.add_argument('--out', required=True)
    r = sub.add_parser('run'); r.add_argument('--plan', required=True); r.add_argument('--approval', required=True); r.add_argument('--out', required=True)
    w = sub.add_parser('worker'); w.add_argument('--ticket', required=True); w.add_argument('--token', required=True)
    args = parser.parse_args()
    if args.action == 'freeze': result = freeze(args.out)
    elif args.action == 'run': result = run(args.plan, args.approval, args.out)
    else: result = worker(args.ticket, args.token)
    print(json.dumps({'state': result.get('state'), 'status': result.get('status'),
                      'plan': result.get('plan'), 'sha256': result.get('sha256')}, ensure_ascii=False))
    return 0 if result.get('state') != 'STOPPED' and result.get('status') != 'TECHNICAL_FAILURE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
