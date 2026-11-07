"""K137 bounded two-pass correctness precheck; native optimization forbidden.

Run once with --out naming a fresh workspace directory. Failure artifacts are
retained. This entry never runs a research case or constructs an original-size
model; the explicitly listed tests use mocks or inherited tiny fixtures.
"""
from __future__ import annotations

import argparse
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

sys.dont_write_bytecode = True

import scipy.optimize
import matlab_bridge


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASELINE = REPO/'.runtime/k137_baseline.json'
MODULES = ('test_staged_method', 'test_neighborhood_method',
           'test_fixed_unit_method', 'test_augmented_method',
           'test_partial_slice', 'test_solver_consistency')
NEW_SOURCES = {'research/chapter3_experiments/staged_method.py',
               'research/chapter3_experiments/test_staged_method.py',
               'research/chapter3_experiments/run_staged_method_precheck.py'}
EXISTING_CHANGE = 'research/chapter3_experiments/neighborhood_method.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def sources():
    files = list(HERE.glob('*.py')) + [HERE/'config_v01.json', HERE/'solve_model.m',
                                     HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(files)}


def run(out):
    out = out.resolve(); out.relative_to(REPO)
    # Repeating into an existing folder is forbidden, including failed runs.
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    before, historical, inherited, base = {}, {}, {}, {}
    results, details, error, preflight_error = {}, {}, None, None
    captured = io.StringIO()
    guard_attempts = {'scipy.optimize.milp':0, 'scipy.optimize.linprog':0,
                      'MatlabSession.__init__':0, 'subprocess.Popen':0}
    environment = {}
    try:
        baseline = read(BASELINE)
        inherited = baseline['baseline_source_sha256']
        historical = baseline['historical_artifact_sha256']
        before = sources()
        allowed = set(baseline['allowed_existing_source_changes'])
        if allowed != {EXISTING_CHANGE}:
            raise AssertionError('Unexpected allowed existing-source changes in parent baseline')
        mismatches = [name for name,digest in inherited.items()
                      if name not in allowed and before.get(name) != digest]
        missing = sorted(set(inherited)-set(before))
        added = set(before)-set(inherited)
        if mismatches or missing or added != NEW_SOURCES:
            raise AssertionError({'unchanged_base_mismatch':mismatches,
                                  'missing_sources':missing,'new_sources':sorted(added)})
        history_before = [name for name,digest in historical.items()
                          if not (REPO/name).is_file() or sha(REPO/name) != digest]
        if history_before:
            raise AssertionError({'historical_preflight_mismatch':history_before})
        base = {'reference_commit':baseline['reference_commit'],
                'baseline_manifest_sha256':sha(BASELINE),
                'inherited_source_count':len(inherited),
                'unchanged_inherited_source_count':len(inherited)-len(allowed),
                'allowed_existing_source_changes':sorted(allowed),
                'new_sources':sorted(added),'mismatches':mismatches,
                'physical_inputs_and_evaluators_unchanged':True}
        # Windows metadata may invoke `ver`; gather it before launch guards.
        environment = {'python':sys.version,'platform':platform.platform(),
                       'machine':platform.machine()}
        for name in before:
            target = out/'source_snapshot'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((REPO/name).read_bytes())
        (out/'parent_baseline.json').write_bytes(BASELINE.read_bytes())
    except BaseException:
        preflight_error = traceback.format_exc(); captured.write(preflight_error)

    declaration = {'stage':'K137','protocol':'two-pass-fixed-unit-correctness-precheck-v1',
        'declared_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_sha256':before,'source_count':len(before),
        'historical_artifact_sha256':historical,'historical_artifact_count':len(historical),
        'unchanged_base':base,'modules':MODULES,
        'scope':'bounded mock and tiny-model correctness; no original-scale construction or optimization',
        'physical_parameters_changed':False,'native_calls':0,'research_calls':0,
        'original_scale_models':0,'quality_or_energy_improvement_claim':False,
        'preflight_error':preflight_error}
    save(out/'declaration.json',declaration)
    fixture_root = REPO/'.runtime/staged_method_precheck'
    fixture_root.mkdir(parents=True,exist_ok=True)

    class Folder:
        """Workspace-owned fixtures avoid Windows temporary-directory ACLs."""
        def __init__(self,*args,**kwargs):
            requested = kwargs.get('dir',args[2] if len(args)>2 else None)
            parent = Path(requested).resolve() if requested is not None else fixture_root
            parent.relative_to(REPO); parent.mkdir(parents=True,exist_ok=True)
            path = parent/('case_'+uuid4().hex); path.mkdir(); self.name = str(path)
        def __enter__(self):return self.name
        def __exit__(self,*args):return False
        def cleanup(self):pass

    def forbidden(name):
        def blocked(*args,**kwargs):
            guard_attempts[name] += 1
            raise AssertionError('Native optimizer/process launch forbidden in K137 precheck: '+name)
        return blocked

    if preflight_error is None:
        try:
            with ExitStack() as stack, redirect_stdout(captured), redirect_stderr(captured):
                stack.enter_context(patch.object(tempfile,'TemporaryDirectory',Folder))
                stack.enter_context(patch.object(matlab_bridge.MatlabSession,'__init__',
                                                side_effect=forbidden('MatlabSession.__init__')))
                stack.enter_context(patch.object(subprocess,'Popen',side_effect=forbidden('subprocess.Popen')))
                for name in ('milp','linprog'):
                    stack.enter_context(patch.object(scipy.optimize,name,
                        side_effect=forbidden('scipy.optimize.'+name)))
                for name in MODULES:
                    suite = unittest.defaultTestLoader.loadTestsFromName(name)
                    result = unittest.TextTestRunner(stream=captured,verbosity=2).run(suite)
                    results[name] = {'passed':result.wasSuccessful(),'count':result.testsRun,
                        'errors':len(result.errors),'failures':len(result.failures),
                        'skipped':len(result.skipped)}
                    module = sys.modules.get(name)
                    details[name] = getattr(module,'RECORDS',getattr(module,'PHYSICAL_RECORDS',{}))
        except BaseException:
            error = traceback.format_exc(); captured.write(error)
    else:
        error = preflight_error

    after = sources()
    historical_mismatch = [name for name,digest in historical.items()
        if not (REPO/name).is_file() or sha(REPO/name) != digest]
    snapshot_mismatch = [name for name,digest in before.items()
        if not (out/'source_snapshot'/name).is_file() or sha(out/'source_snapshot'/name) != digest]
    (out/'unittest.txt').write_bytes(captured.getvalue().encode('utf-8'))
    save(out/'fixture_records.json',details)
    report = {'protocol':'K137-two-pass-fixed-unit-correctness-precheck-v1',
        'passed':bool(len(results)==len(MODULES) and all(r['passed'] for r in results.values())
            and before==after and not historical_mismatch and not snapshot_mismatch and error is None),
        'modules':results,'count':sum(r['count'] for r in results.values()),
        'source_count':len(after),'source_sha256':after,'source_unchanged':before==after,
        'source_snapshot_mismatches':snapshot_mismatch,
        'historical_artifact_count':len(historical),
        'historical_artifacts_unchanged':not historical_mismatch,
        'historical_mismatches':historical_mismatch,'unchanged_base':base,
        'native_calls':0,'research_calls':0,'original_scale_models':0,
        'blocked_native_launch_attempts':guard_attempts,
        'elapsed_s':time.monotonic()-started,'error':error,
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'environment':environment,
        'scope':'fake and tiny echo correctness only; no quality or energy evidence',
        'failed_runs_are_retained':True}
    save(out/'checks.json',report)
    print(json.dumps({key:report[key] for key in ('passed','count','error','elapsed_s')},
                     ensure_ascii=False),flush=True)
    return report['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    raise SystemExit(0 if run(parser.parse_args().out) else 1)
