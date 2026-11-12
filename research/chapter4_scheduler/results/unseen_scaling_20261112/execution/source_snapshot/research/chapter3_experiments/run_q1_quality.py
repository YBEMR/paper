"""Q1: current warm MILP and an independent finite reference, once each.

precheck never solves/evaluates the research Q1. run requires matching passing
checks and atomically claims the two-call stage. Workers use fresh processes.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import unittest

from q1_case import load_q1, canonical_hash, independent_lower_bound, SECONDS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = HERE/'q1_quality_protocol.md'
METHODS = ('milp', 'reference')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def source_paths():
    # Explicit top-level code, never old results/answer libraries. Include all
    # current tests to bind the exact passing precheck to the code it checked.
    paths = [p for p in HERE.glob('*.py') if p.is_file()]
    paths += [HERE/'solve_model.m', HERE/'config_v01.json', PROTOCOL,
              HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): p for p in sorted(paths)}


def source_hashes():
    return {key: digest(p) for key, p in source_paths().items()}


def signature():
    config, instance = load_q1()
    return {'problem_id': instance['id'], 'input_sha256': canonical_hash(instance),
        'config_sha256': canonical_hash(config), 'source_sha256': source_hashes(),
        'seconds_per_method': SECONDS, 'method_order': list(METHODS)}


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({'name': test.id(), 'passed': True})
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({'name': test.id(), 'passed': False, 'kind': 'failure'})
    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({'name': test.id(), 'passed': False, 'kind': 'error'})


def precheck(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    before = signature()
    checks = []
    def check(name, action):
        try:
            value = action()
            if value is False:
                raise AssertionError(name)
            checks.append({'name': name, 'passed': True})
            return value
        except Exception as error:
            checks.append({'name': name, 'passed': False,
                           'error': f'{type(error).__name__}: {error}'})
            return None
    suite = unittest.TestSuite()
    for name in ('test_q1_domain', 'test_q1_reference', 'test_q1_driver'):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult)
    result = runner.run(suite)
    checks.extend(result.records)
    (out/'unit_checks.txt').write_text(stream.getvalue(), encoding='utf-8')
    # Current interfaces changed; recheck the actual numerical lift on one
    # pre-existing tiny correctness fixture, not a Q1 answer-producing pre-run.
    from run_milp_precheck import fixtures
    from inputs import load_config
    from milp import build_model
    from timing import MethodBudget
    from initial_point import prepare_initial_witness
    from run_warm_diagnostic import FLAGS
    from run_initial_point_precheck import state_checks, preparation_checks
    config = load_config()
    instance, starts = fixtures(config)['one_stage_energy']
    instance['start_domain'] = {'version': 1, 'kind': 'explicit_grid_subset',
                               'by_scene_stage_ms': starts}
    budget = MethodBudget(120)
    model = check('tiny/current_full_physics_model', lambda: build_model(instance, config,
                          budget=budget, **FLAGS))
    if model is not None:
        receipt = check('tiny/explicit_domain_safe_seed_x0_roundtrip',
                        lambda: prepare_initial_witness(model, config['accuracy_targets'], budget))
        save(out/'tiny_initial_receipt.json', {k: v for k, v in (receipt or {}).items() if k != 'x0'})
        check('tiny/seed_is_safe_and_numerically_admitted',
              lambda: receipt['state'] == 'SAFE_POINT_READY')
        if receipt and receipt.get('witness'):
            cases = out/'seed_state_checks'
            cases.mkdir()
            candidate = receipt['witness']['candidate']
            state_checks(cases, check, model, candidate)
            preparation_checks(cases, check, model, candidate, receipt['witness']['evaluation'])
    after = signature()
    checks.append({'name': 'frozen/source_and_input_unchanged_during_checks', 'passed': before == after})
    record = {'passed': bool(checks) and all(c['passed'] for c in checks), 'count': len(checks),
        'checks': checks, 'signature': after, 'research_Q1_thermal_or_solver_pre_run': False,
        'scope': 'necessary changed-interface and evidence checks; existing native bridge reused',
        'native_bridge_repeated': False}
    save(out/'checks.json', record)
    print(json.dumps({'passed': record['passed'], 'count': len(checks), 'out': str(out)}), flush=True)
    if not record['passed']:
        raise RuntimeError('Q1 precheck failed; failure artifacts retained')
    return record


def validate_gate(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    checks = raw.get('checks', [])
    if (raw.get('passed') is not True or not checks or raw.get('count') != len(checks)
        or not all(c.get('passed') is True for c in checks)
        or raw.get('research_Q1_thermal_or_solver_pre_run') is not False
        or raw.get('signature') != signature()):
        raise ValueError('Current complete passing Q1 source/input/rule credential required')
    return raw


def worker(method, out, declaration_path):
    declaration = json.loads(Path(declaration_path).read_text(encoding='utf-8'))
    if method not in METHODS or declaration['signature'] != signature():
        raise ValueError('Worker declaration/source/input mismatch')
    out = Path(out)
    claim = out.parent/(method+'_call_claim.json')
    with claim.open('x', encoding='utf-8') as stream:
        json.dump({'method': method, 'seconds': SECONDS, 'retries': 0}, stream)
    if method == 'reference':
        from q1_reference import execute_reference
        result = execute_reference(load_q1, out, seconds=SECONDS)
    else:
        from run_warm_diagnostic import execute_warm
        bound = {}
        def loader(budget):
            config, instance = load_q1(budget)
            computed = independent_lower_bound(instance)
            budget.check()
            bound.update(computed, formed_at_s=budget.elapsed)
            return config, instance
        result = execute_warm(loader, out, seconds=SECONDS)
        result.update(independent_lower_bound=bound or None,
                      certified_lower_bound_J=bound.get('lower_bound_J'),
                      coverage_complete=False,
                      remaining_domain='MILP_SEARCH_NOT_INDEPENDENTLY_CERTIFIED')
    result.update(quality_reference_only=True, full_chain_main_study_changed=False,
                  predeclared_seconds=SECONDS, method=method,
                  source_signature_matches_after_call=declaration['signature'] == signature())
    save(out/'result.json', result)
    print(json.dumps({'method': method, 'state': result.get('state'),
        'U': result.get('safe_upper_bound_J'), 'L': result.get('certified_lower_bound_J'),
        'coverage_complete': result.get('coverage_complete'),
        'timing': result.get('timing')}), flush=True)


def run(precheck_record, out):
    credential = validate_gate(precheck_record)
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(str(out))
    # This claim survives errors and prevents silently rerunning the stage.
    stage_claim = Path(precheck_record).parent/'q1_two_call_claim.json'
    with stage_claim.open('x', encoding='utf-8') as stream:
        json.dump({'out': str(out), 'methods': METHODS, 'seconds_each': SECONDS,
                   'retries': 0}, stream)
    out.mkdir(parents=True)
    declared = {'signature': credential['signature'], 'precheck_record': str(Path(precheck_record).resolve()),
        'precheck_sha256': digest(precheck_record), 'calls': METHODS, 'retries': 0,
        'scope': 'Q1 finite main-only optimization quality reference, not full-chain formal experiment',
        'clock': 'before each method case load; process launch/imports and entry identity validation excluded; process wall reported separately',
        'started_at_local': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    save(out/'declaration.json', declared)
    for key, path in source_paths().items():
        target = out/'source_snapshot'/key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    import numpy, scipy
    save(out/'environment.json', {'python': sys.version, 'executable': sys.executable,
        'platform': platform.platform(), 'numpy': numpy.__version__, 'scipy': scipy.__version__,
        'cwd': str(Path.cwd()), 'matlab': 'R2023b; actual readiness/version in bridge artifacts'})
    calls = []
    for method in METHODS:
        if signature() != declared['signature']:
            save(out/'source_mismatch_stop.json', {'before_method': method})
            break
        started = time.monotonic()
        print('START '+method+' '+time.strftime('%H:%M:%S'), flush=True)
        with (out/(method+'_stdout.txt')).open('w', encoding='utf-8') as log:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '_worker',
                '--method', method, '--out', str(out/method), '--declaration', str(out/'declaration.json')],
                cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        calls.append({'method': method, 'process_wall_s': time.monotonic()-started,
                      'returncode': completed.returncode})
        save(out/'calls.json', calls)
        print('END '+method+' '+time.strftime('%H:%M:%S')+' rc='+str(completed.returncode), flush=True)
    save(out/'source_integrity.json', {'before': declared['signature'], 'after': signature(),
         'unchanged': signature() == declared['signature']})
    return calls


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['precheck', 'run', '_worker'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--precheck-record', type=Path)
    parser.add_argument('--method', choices=METHODS)
    parser.add_argument('--declaration', type=Path)
    args = parser.parse_args()
    if args.mode == 'precheck': precheck(args.out)
    elif args.mode == 'run': run(args.precheck_record, args.out)
    else: worker(args.method, args.out, args.declaration)
