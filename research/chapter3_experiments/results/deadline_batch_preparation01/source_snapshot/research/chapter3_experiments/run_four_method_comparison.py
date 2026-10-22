"""K152: one frozen original-input auto-L four-method comparison, no retries."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction as F
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BASE = HERE/'results/anchor_quality_pair01/declaration.json'
PROTOCOL_FILE = HERE/'results/four_method_preparation01/protocol.md'
TARGET = HERE/'results/four_method_comparison01'
GLOBAL_CLAIM = HERE/'results/four_method_comparison_claim01.json'
NEW = ('run_four_method_comparison.py', 'test_four_method_comparison.py',
       'four_whole_status.py', 'test_four_whole_status.py')
METHOD_GATE = HERE/'results/anchor_precheck02/checks.json'
METHOD_GATE_SHA256 = '11e77b40ab5d3430e625b16304f3a1156a658258c1a4025ba78b618b9f859bf5'
PROTOCOL = 'K152-original-autoL-four-method-fair-comparison-v1'
CHECK_PROTOCOL = 'K152-four-method-pure-precheck-v1'
SECONDS, SCENE_SECONDS, CUT = 300, 60, 10


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    pending = path.with_suffix(path.suffix+'.pending')
    with pending.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False, default=str)
        stream.write('\n')
    pending.replace(path)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def jobs():
    return [{'id':'whole_milp','method':'milp'},
            {'id':'anchor_linked4','method':'linked_fixed_unit_opp_start',
             'opened_count':4,'preeliminate_closed_anchors':True},
            {'id':'heft','method':'heft','seed':None},
            {'id':'sa101','method':'sa','seed':101}]


def local(path):
    path = Path(path).resolve()
    path.relative_to(REPO)
    if path != TARGET.resolve():
        raise ValueError('Only the frozen K152 output is allowed')
    return path


def sources():
    paths = list(HERE.glob('*.py'))+[HERE/'config_v01.json', HERE/'solve_model.m',
                                            HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}


CUTOFF_ADAPTER = HERE/'results/anchor_pair_preparation01/resume_unstarted.py'
CUTOFF_CHECKS = HERE/'results/anchor_pair_preparation01/recovery_precheck01.json'


def dependencies():
    return {str(p.relative_to(REPO).as_posix()):sha(p)
        for p in (BASE, METHOD_GATE, CUTOFF_ADAPTER, CUTOFF_CHECKS,
                  PROTOCOL_FILE.parent/'launch_once.py')}


def source_gate():
    base=read(BASE)['source_sha256'];current=sources()
    extra={(HERE/n).relative_to(REPO).as_posix() for n in NEW}
    if (len(base)!=174 or len(current)!=178 or set(current)!=set(base)|extra
            or any(current.get(n)!=h for n,h in base.items())):
        raise ValueError('Unchanged K151 174 sources plus four K152 files required')
    g=read(METHOD_GATE);cut=read(CUTOFF_CHECKS)
    if (sha(METHOD_GATE)!=METHOD_GATE_SHA256 or g.get('passed') is not True
        or g.get('count')!=80 or cut.get('passed') is not True
        or cut.get('adapter_sha256')!=sha(CUTOFF_ADAPTER)
        or cut.get('source_sha256')!=base or not cut.get('cases')
        or not all(c.get('passed') is True for c in cut['cases'])):
        raise ValueError('Inherited implementation/cutoff evidence changed')
    return current


def settings():
    import run_linked_pair as inherited
    return deepcopy(inherited.SHARED), deepcopy(inherited.BUILD_OPTIONS)


def masks(instance, count):
    if count not in (4, 5):
        raise ValueError('Only the predeclared four/five opening is allowed')
    result = {}
    for scene in instance['scenarios']:
        stages = scene['stage_instances']
        ids = [s['id'] for s in stages if s['shared_stage_id'] in
               ('A.pre', 'A.main', 'A.post', 'B.pre', 'C.pre') or
               (count == 5 and s['shared_stage_id'] in ('B.main', 'C.main'))]
        if len(stages) != 6 or len(ids) != count or len(set(ids)) != count:
            raise ValueError('Original two full three-Stage chains required')
        result[scene['id']] = sorted(ids)
    return result


def fresh_input(budget=None):
    from run_neighborhood_diagnostic import fresh_input as inherited
    return inherited(budget)


def entry_points():
    from run_minimal_comparison import common_entry_points
    return common_entry_points()


def rules():
    from run_minimal_comparison import rules as inherited
    value=inherited()
    value.update(protocol=PROTOCOL,jobs=jobs(),preparation_only_this_stage=False,
        run_requires_separate_execution_authorization=False,
        execution_authorization='direct user: four once-only independent 300s calls',
        method_call_limit=4,hard_outer_watchdog_s=1800,
        preeliminate_closed_anchors_linked_second_pass_only=True,
        candidate_cache_or_witness_shared=False,
        normal_deadline_can_continue_after_isolation=True,
        technical_or_unresolved_stops_remaining=True,
        primary_comparison='original full-safe U and first-safe time; one run per method',
        postcheck_scope='post-only independent evaluation, no search or late U replacement',
        no_historical_witness_initialisation=True)
    return value


def check_gate(path, current):
    value = read(path)
    if (value.get('protocol') != CHECK_PROTOCOL or value.get('passed') is not True
            or value.get('source_sha256') != current or value.get('source_unchanged') is not True
            or value.get('errors') != 0 or value.get('failures') != 0
            or value.get('skipped') != 0 or value.get('error') is not None
            or not value.get('tests_run') or not isinstance(value.get('blocked_calls'), dict)
            or not value['blocked_calls'] or any(value['blocked_calls'].values())
            or any(value.get(k) != 0 for k in
                ('research_calls', 'native_calls', 'physical_models', 'thermal_evaluations'))):
        raise ValueError('Matching zero-research-call K152 precheck required')
    return value


def scene_spec(instance):
    return {s['id']: {'weight': s['weight'], 'window_s': str(F(instance['window_ms'])/1000),
        'limits': dict(zip(instance['platform']['node_order'], s['maximum_temperature_degC']))}
        for s in instance['scenarios']}


def prepare(out, checks):
    from run_neighborhood_diagnostic import opened_stages
    out = local(out)
    if out.exists() or GLOBAL_CLAIM.exists():
        raise FileExistsError('K152 output or single-use claim already exists')
    current = source_gate()
    check_gate(checks, current)
    raw, config, instance = fresh_input()
    identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
                           map(canonical, (raw, config, instance))))
    if identities != read(BASE)['input_identities']:
        raise ValueError('Frozen original input changed')
    out.mkdir(parents=True)
    (out/'claims').mkdir()
    names = ('input_raw.json', 'input_config.json', 'input_instance.json')
    for name, value in zip(names, (raw, config, instance)):
        save(out/name, value)
    for name, digest in current.items():
        destination = out/'source_snapshot'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO/name, destination)
        if sha(destination) != digest:
            raise ValueError('Source changed during snapshot')
    for name,digest in dependencies().items():
        destination=out/'dependency_snapshot'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPO/name,destination)
        if sha(destination)!=digest:raise ValueError('Dependency changed during snapshot')
    shutil.copyfile(checks, out/'precheck.json')
    shutil.copyfile(PROTOCOL_FILE, out/'protocol.md')
    declaration = {**rules(), **identities, 'input_identities': identities,
        'source_sha256': current, 'baseline_declaration_sha256': sha(BASE), 'dependency_sha256':dependencies(),
        'precheck_sha256': sha(out/'precheck.json'), 'scene_spec': scene_spec(instance),
        'protocol_file_sha256': sha(PROTOCOL_FILE),
        'first_opened_by_scene': opened_stages(instance),
        'linked_opened_by_job': {j['id']: masks(instance, j['opened_count']) for j in jobs() if j.get('opened_count')},
        'input_file_sha256': {n: sha(out/n) for n in names}, 'declared_at_utc': now()}
    save(out/'declaration.json', declaration)
    save(out/'ledger.json', {'protocol': PROTOCOL, 'state': 'DECLARED', 'consumed': 0,
        'reserved_method_budget_s': 0, 'calls': []})
    save(out/'environment.json', {'python': sys.version, 'platform': platform.platform()})
    admission(out)
    return {'prepared': True, 'source_files': len(current), 'research_calls': 0}


def admission(out):
    from run_neighborhood_diagnostic import opened_stages
    out = local(out)
    declaration, current = read(out/'declaration.json'), source_gate()
    if (any(declaration.get(k) != v for k, v in rules().items())
            or declaration.get('source_sha256') != current
            or declaration.get('baseline_declaration_sha256') != sha(BASE)
            or declaration.get('dependency_sha256') != dependencies()
            or declaration.get('precheck_sha256') != sha(out/'precheck.json')
            or declaration.get('protocol_file_sha256') != sha(PROTOCOL_FILE)
            or declaration.get('protocol_file_sha256') != sha(out/'protocol.md')):
        raise ValueError('Frozen rule/source/baseline/precheck changed')
    check_gate(out/'precheck.json', current)
    for name,digest in declaration['dependency_sha256'].items():
        if sha(out/'dependency_snapshot'/name)!=digest:
            raise ValueError('Frozen dependency snapshot changed: '+name)
    for name, digest in current.items():
        if sha(out/'source_snapshot'/name) != digest:
            raise ValueError('Frozen source snapshot changed: '+name)
    for name, digest in declaration['input_file_sha256'].items():
        if sha(out/name) != digest:
            raise ValueError('Frozen input bytes changed: '+name)
    identities = dict(zip(('raw_config_sha256', 'config_sha256', 'input_sha256'),
        (canonical(read(out/n)) for n in ('input_raw.json', 'input_config.json', 'input_instance.json'))))
    instance = read(out/'input_instance.json')
    if (identities != declaration['input_identities'] or identities != read(BASE)['input_identities']
            or any(declaration[k] != v for k, v in identities.items())
            or declaration['scene_spec'] != scene_spec(instance)
            or declaration['first_opened_by_scene'] != opened_stages(instance)
            or declaration['linked_opened_by_job'] != {j['id']: masks(instance, j['opened_count']) for j in jobs() if j.get('opened_count')}):
        raise ValueError('Original input/domain identity changed')
    return declaration


def execute(job,out,declaration,entries):
    if job not in jobs():raise ValueError('Unknown frozen method')
    identity={'input_verified':None};lower={}
    def loader(budget):
        raw,config,instance=fresh_input(budget)
        actual=dict(zip(('raw_config_sha256','config_sha256','input_sha256'),
                        map(canonical,(raw,config,instance))))
        identity['input_verified']=actual==declaration['input_identities']
        if identity['input_verified'] is not True:raise ValueError('Fresh billed input changed')
        if job['method']=='milp':
            from partial_bounds import independent_lower_bound
            folder.mkdir(parents=True,exist_ok=True)
            save(folder/'method_budget_identity.json',{'start':budget.start,
                'deadline':budget.deadline,'limit_s':SECONDS,'clock':'monotonic'})
            with budget.phase('comparison_independent_lower_bound'):
                lower['L0']=independent_lower_bound(instance,None,budget)
        budget.check();return config,instance
    folder=out/job['id'];factory=partial(entries['session'],cut_max_iterations=CUT)
    if job['method']=='milp':
        result=entries['whole'](loader,folder,seconds=SECONDS,feedback_kind='conditional',
            model_builder=partial(entries['builder'],prefilter_deadlines=True,cumulative_precedence=False),
            session_factory=factory)
    elif job['method']=='linked_fixed_unit_opp_start':
        # Identical K151 root start: internal lazy setup is billed.
        from timing import MethodBudget
        budget=MethodBudget(float(SECONDS),clock=time.monotonic)
        shared,build=settings()
        def update(r,record):
            print(json.dumps({'event':'SAFE_AGGREGATE_UPDATE','method':job['id'],
                'elapsed_s':record['committed_at_s'],'U_J':record['safe_upper_bound_J']}),flush=True)
        result=entries['linked'](loader,folder,seconds=SECONDS,budget=budget,clock=budget.clock,
            shared_deployment=shared,scene_slice_s=SCENE_SECONDS,builder_options=build,
            session_factory=factory,opened_by_scene=deepcopy(declaration['first_opened_by_scene']),
            linked_opened_by_scene=deepcopy(declaration['linked_opened_by_job'][job['id']]),
            on_global_update=update,preeliminate_closed_anchors=True)
    else:
        result=entries['heuristic'](loader,folder,method=job['method'],seconds=SECONDS,
                                    seed=job['seed'],allow_auto_low=True)
    if lower:save(folder/'independent_bounds.json',lower)
    return result,identity


def cutoff_adapter():
    import importlib.util
    spec=importlib.util.spec_from_file_location('k152_bound_k151_cutoff_audit',CUTOFF_ADAPTER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def result_records(job,result,declaration,folder,*,input_valid,source_valid,errors=None):
    kw=dict(input_valid=input_valid,source_valid=source_valid,errors=errors)
    if job['method']=='linked_fixed_unit_opp_start':
        adapter=cutoff_adapter()
        record=adapter.correct_records(job,result,declaration,folder,**kw)
        if record.get('cutoff_audit',{}).get('applied'):
            from execution_status import classify_execution
            _,python,_,_=adapter._last_mapping(result,folder)
            cancel=Path(folder)/'matlab'/f"request_{python['request_number']:06d}.cancel"
            valid=cancel.is_file() and cancel.read_text(encoding='ascii').strip()=='budget'
            record['cutoff_audit']['cancel_file_verified']=valid
            if not valid:
                record['context']['hard_errors'].append('MISSING_MATCHING_ROOT_CANCEL_FILE')
                record['execution']=classify_execution(result,record['context'])
        return record
    if job['method']=='milp':
        from four_whole_status import result_records as whole_records
        return whole_records(result,declaration,folder,**kw)
    from run_heuristic_followup import result_records as heuristic_records
    return heuristic_records(result,declaration,**kw)


def run(out, *, execution_authorized=False):
    out = local(out)
    ledger = read(out/'ledger.json')
    if (ledger.get('state') != 'DECLARED' or ledger.get('consumed') != 0
            or ledger.get('calls') or GLOBAL_CLAIM.exists()
            or any((out/'claims'/(j['id']+'.json')).exists() for j in jobs())):
        raise FileExistsError('K152 already claimed/consumed; no retry or restart')
    if execution_authorized is not True:
        raise PermissionError('Explicit execution authorization required')
    declaration = admission(out)
    started_all = time.monotonic()
    imports = time.monotonic()
    entries = entry_points()
    save(out/'runtime_imports.json', {'wall_s': time.monotonic()-imports,
        'scope': 'imports only; no candidates, model, heat or worker'})
    with GLOBAL_CLAIM.open('x', encoding='utf-8') as stream:
        json.dump({'protocol': PROTOCOL, 'out': out.relative_to(REPO).as_posix(),
            'declaration_sha256': sha(out/'declaration.json'), 'claimed_utc': now(), 'no_retry': True}, stream)
    okay = True
    for job in jobs():
        admission(out)
        with (out/'claims'/(job['id']+'.json')).open('x', encoding='utf-8') as stream:
            json.dump({**job, 'seconds': SECONDS, 'claimed_utc': now(), 'no_retry': True}, stream)
        row = {**job, 'state': 'RUNNING', 'started_utc': now()}
        ledger['calls'].append(row)
        ledger.update(state='RUNNING', consumed=ledger['consumed']+1,
                      reserved_method_budget_s=ledger['reserved_method_budget_s']+SECONDS)
        save(out/'ledger.json', ledger)
        result, identity, errors = None, {'input_verified': None}, []
        started = time.monotonic()
        try:
            result, identity = execute(job, out, declaration, entries)
        except BaseException:
            errors.append(traceback.format_exc())
        returned = time.monotonic()-started
        source_valid = True
        try:
            admission(out)
        except Exception:
            source_valid = False
            errors.append(traceback.format_exc())
        post = time.monotonic()
        if isinstance(result, dict):
            save(out/job['id']/'wrapper_raw_result.json', result)
        try:
            records = result_records(job, result, declaration, out/job['id'],
                input_valid=identity['input_verified'], source_valid=source_valid, errors=errors)
        except Exception:
            errors.append(traceback.format_exc())
            records = {'execution': {'execution_status': 'TECHNICAL_FAILURE_CONFIRMED'},
                       'usable_U_J': None, 'record_errors': errors}
        acceptable = records['execution']['execution_status'] in (
            'NORMAL_COMPLETION', 'NORMAL_TIME_LIMIT', 'NORMAL_TIME_LIMIT_PENDING_LAST_REQUEST')
        row.update(state='COMPLETED' if acceptable else 'BLOCKED', completed_utc=now(),
            errors=errors, method_return_inclusive_wall_s=returned,
            source_identity_valid=source_valid, **records)
        save(out/'claims'/(job['id']+'_result.json'), row)
        row['post_method_record_wall_s'] = time.monotonic()-post
        artifacts = {p.relative_to(out/job['id']).as_posix(): sha(p)
                     for p in sorted((out/job['id']).rglob('*')) if p.is_file()}
        save(out/'claims'/(job['id']+'_artifact_sha256.json'), artifacts)
        ledger['state'] = 'RUNNING' if acceptable else 'BLOCKED'
        save(out/'ledger.json', ledger)
        print(json.dumps({'method': job['id'], 'execution_status': records['execution']['execution_status'],
                          'usable_U_J': records.get('usable_U_J')}), flush=True)
        if not acceptable:
            okay = False
            break
    if okay:
        ledger['state'] = 'COMPLETED'
        save(out/'ledger.json', ledger)
    save(out/'wrapper_timing.json', {'wall_s': time.monotonic()-started_all,
        'scope': 'imports, method returns/cleanup, stored-record review and primary archives; no late physical evidence'})
    return okay


def precheck(out):
    from contextlib import ExitStack, redirect_stdout, redirect_stderr
    import io
    import tempfile
    import unittest
    from unittest.mock import patch
    out = Path(out).resolve(); out.relative_to(REPO); out.mkdir(parents=True, exist_ok=False)
    before = sources(); log = io.StringIO(); error = None
    environment = {'python': sys.version, 'platform': platform.platform()}
    guards = {name: 0 for name in ('research_entry', 'MatlabSession.__init__',
        'scipy.optimize.milp', 'scipy.optimize.linprog', 'subprocess.Popen', 'build_model', 'evaluate_piecewise')}
    def blocked(name):
        guards.setdefault(name,0)
        def fail(*a, **kw):
            guards[name] += 1
            raise AssertionError('Forbidden K152 mock-precheck entry: '+name)
        return fail
    tests = None
    try:
        import scipy.optimize, matlab_bridge, milp, scene_adapter, thermal, linked_method
        import formal_milp, heuristic_runner
        with ExitStack() as stack:
            for module, name, label in ((linked_method,'execute_linked_fixed_unit_opp_start','research_entry'),
                (formal_milp,'execute_formal_milp','whole_research_entry'),
                (heuristic_runner,'execute_heuristic','heuristic_research_entry'),
                (matlab_bridge.MatlabSession,'__init__','MatlabSession.__init__'),
                (scipy.optimize,'milp','scipy.optimize.milp'), (scipy.optimize,'linprog','scipy.optimize.linprog'),
                (milp,'build_model','build_model'),(scene_adapter,'evaluate_piecewise','evaluate_piecewise'),
                (thermal,'evaluate_piecewise','evaluate_piecewise'),
                (thermal,'evaluate_candidate','evaluate_candidate')):
                stack.enter_context(patch.object(module,name,side_effect=blocked(label)))
            stack.enter_context(patch('subprocess.Popen',side_effect=blocked('subprocess.Popen')))
            # Test fixtures may write files but never use the user's output or claims.
            original_temp = tempfile.TemporaryDirectory
            fixture_root = REPO/'.runtime/k152_wrapper_fixtures';fixture_root.mkdir(parents=True,exist_ok=True)
            def folder(*a,**kw):
                kw.setdefault('dir',str(fixture_root))
                return original_temp(*a,**kw)
            stack.enter_context(patch('tempfile.TemporaryDirectory',side_effect=folder))
            with redirect_stdout(log),redirect_stderr(log):
                tests=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite(
                    unittest.defaultTestLoader.loadTestsFromName(n) for n in
                    ('test_four_method_comparison','test_four_whole_status','test_execution_status','test_completion_metrics')))
    except BaseException:
        error=traceback.format_exc();log.write(error)
    after=sources()
    result={'protocol':CHECK_PROTOCOL,'passed':bool(tests and tests.wasSuccessful() and not tests.skipped
            and before==after and not any(guards.values()) and error is None),
        'tests_run':tests.testsRun if tests else 0,'errors':len(tests.errors) if tests else 1,
        'failures':len(tests.failures) if tests else 0,'skipped':len(tests.skipped) if tests else 0,
        'source_sha256':after,'source_unchanged':before==after,'blocked_calls':guards,
        'research_calls':0,'native_calls':0,'physical_models':0,'thermal_evaluations':0,
        'error':error,'environment':environment,'completed_at_utc':now()}
    save(out/'checks.json',result);(out/'unittest.txt').write_text(log.getvalue(),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','tests_run','errors','failures','error')}))
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--precheck', action='store_true')
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--checks', type=Path)
    parser.add_argument('--execution-authorized', action='store_true')
    args = parser.parse_args()
    if args.precheck:
        raise SystemExit(0 if precheck(args.out) else 1)
    elif args.prepare:
        if args.checks is None:
            parser.error('--prepare requires --checks')
        print(json.dumps(prepare(args.out, args.checks)))
    else:
        raise SystemExit(0 if run(args.out, execution_authorized=args.execution_authorized) else 1)
