"""K134 small-domain integration checks; native optimizers are forbidden."""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch
from uuid import uuid4

import scipy.optimize
import matlab_bridge

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REFERENCE = '8b486a06934b67e2ca23e0e80b8c7275839ebebd'
MODULES = ('test_augmented_method', 'test_fixed_unit_method',
           'test_partial_slice', 'test_solver_consistency')
CHANGED = {'research/chapter3_experiments/fixed_unit_method.py'}

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False, default=str)+'\n', encoding='utf-8')

def sources():
    files = list(HERE.glob('*.py')) + [HERE/'config_v01.json', HERE/'solve_model.m',
                                     HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(files)}

def unchanged_base(before):
    previous = read(HERE/'results/augmented_native_check01/declaration.json')['source_sha256']
    mismatch = [name for name, h in previous.items()
                if name not in CHANGED and before.get(name) != h]
    old = subprocess.check_output(['git', 'show', REFERENCE+':research/chapter3_experiments/fixed_unit_method.py'], cwd=REPO)
    old_tree = ast.parse(old.decode('utf-8-sig'))
    new_tree = ast.parse((HERE/'fixed_unit_method.py').read_text(encoding='utf-8-sig'))
    fn = lambda tree: next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                           and n.name == 'execute_fixed_unit_opp_start')
    old_default_same = ast.dump(fn(old_tree), include_attributes=False) == ast.dump(fn(new_tree), include_attributes=False)
    protocol = lambda tree: next(ast.literal_eval(n.value) for n in tree.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='PROTOCOL' for t in n.targets))
    protocol_same = protocol(old_tree) == protocol(new_tree)
    assert not mismatch, mismatch
    assert old_default_same and protocol_same
    return {'reference_commit': REFERENCE, 'unchanged_base_count': len(previous)-len(CHANGED),
            'mismatches': mismatch, 'old_fixed_unit_entry_AST_equal': old_default_same,
            'old_fixed_unit_protocol_equal': protocol_same,
            'milp_bridge_partial_N1_and_physical_inputs_unchanged': True}

def histories():
    old = read(HERE/'results/numerical_conflict_audit01/declaration.json')['K131_artifact_sha256']
    assert all(sha(REPO/n)==h for n,h in old.items())
    latest = HERE/'results/augmented_native_check01'
    files = {p.relative_to(REPO).as_posix():sha(p) for p in latest.rglob('*') if p.is_file()}
    return dict(old, **files)

def run(out):
    out = out.resolve()
    out.relative_to(REPO)
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    before = sources()
    historical = histories()
    base = unchanged_base(before)
    # Windows platform discovery may invoke `ver`. Do it before the strict
    # process-launch guard; no optimizer is involved in environment metadata.
    environment = {'python': sys.version, 'platform': platform.platform(),
                   'machine': platform.machine()}
    inherited = read(HERE/'results/augmented_native_check01/declaration.json')['source_sha256']
    for name,h in before.items():
        if inherited.get(name) != h:
            target = out/'source_snapshot'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((REPO/name).read_bytes())
    save(out/'declaration.json', {
        'stage': 'K134', 'declared_at_utc': datetime.now(timezone.utc).isoformat(),
        'reference_commit': REFERENCE, 'source_sha256': before,
        'historical_artifact_sha256': historical,
        'scope': 'small-domain method integration only; no research call or native solver',
        'modules': MODULES, 'physical_parameters_changed': False,
        'original_scale_models': 0, 'native_calls': 0, 'research_calls': 0,
        'success_does_not_establish_energy_improvement': True,
    })
    captured = io.StringIO()
    results, details, error = {}, {}, None
    fixture_root = REPO/'.runtime/augmented_method_precheck'
    fixture_root.mkdir(parents=True, exist_ok=True)

    class Folder:
        def __init__(self, *args, **kw):
            requested = kw.get('dir', args[2] if len(args)>2 else None)
            parent = Path(requested).resolve() if requested is not None else fixture_root
            parent.relative_to(REPO)
            parent.mkdir(parents=True, exist_ok=True)
            path = parent/('case_'+uuid4().hex)
            path.mkdir()
            self.name = str(path)
        def __enter__(self): return self.name
        def __exit__(self, *args): return False
        def cleanup(self): pass

    def forbidden(*args, **kwargs):
        raise AssertionError('Native optimizer/process launch forbidden in K134 precheck')

    try:
        with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
            stack.enter_context(patch.object(tempfile, 'TemporaryDirectory', Folder))
            stack.enter_context(patch.object(matlab_bridge.MatlabSession, '__init__', side_effect=forbidden))
            stack.enter_context(patch.object(subprocess, 'Popen', side_effect=forbidden))
            for name in ('milp', 'linprog'):
                stack.enter_context(patch.object(scipy.optimize, name, side_effect=forbidden))
            for name in MODULES:
                suite = unittest.defaultTestLoader.loadTestsFromName(name)
                result = unittest.TextTestRunner(stream=captured, verbosity=2).run(suite)
                results[name] = {'passed': result.wasSuccessful(), 'count': result.testsRun,
                                 'errors': len(result.errors), 'failures': len(result.failures)}
                module = sys.modules.get(name)
                details[name] = getattr(module, 'RECORDS', getattr(module, 'PHYSICAL_RECORDS', {}))
    except BaseException:
        error = traceback.format_exc()
        captured.write(error)
    after = sources()
    historical_mismatch = [n for n,h in historical.items() if sha(REPO/n)!=h]
    (out/'unittest.txt').write_bytes(captured.getvalue().encode('utf-8'))
    save(out/'fixture_records.json', details)
    report = {
        'protocol': 'K134-augmented-fixed-unit-method-integration-precheck-v1',
        'passed': bool(results and all(r['passed'] for r in results.values())
                       and before==after and not historical_mismatch and error is None),
        'modules': results, 'count': sum(r['count'] for r in results.values()),
        'source_sha256': after, 'source_unchanged': before==after,
        'historical_artifacts_unchanged': not historical_mismatch,
        'historical_mismatches': historical_mismatch, 'unchanged_base': base,
        'native_calls': 0, 'research_calls': 0, 'original_scale_models': 0,
        'elapsed_s': time.monotonic()-started, 'error': error,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'environment': environment,
        'scope': 'tiny correctness with fake/echo worker; no optimization or energy quality evidence',
    }
    save(out/'checks.json', report)
    print(json.dumps({k:report[k] for k in ('passed','count','error','elapsed_s')}, ensure_ascii=False), flush=True)
    return report['passed']

if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    raise SystemExit(0 if run(parser.parse_args().out) else 1)
