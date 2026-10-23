"""K150 bounded implementation gate; no native worker/solver/research run.

Fresh output directories preserve failures. Includes inherited regressions,
independent Cartesian projection and tiny physical warm/complement checks.
"""
import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import traceback
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PROTOCOL = 'K150-closed-anchor-exact-projection-and-fresh-warm-precheck-v1'
MODULES = ('test_anchor_preelimination', 'test_anchor_four_open', 'test_anchor_method',
           'test_linked_neighborhood', 'test_linked_method',
           'test_neighborhood_milp', 'test_fixed_unit_neighborhood', 'test_staged_method')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = list(HERE.glob('*.py')) + [HERE/'config_v01.json', HERE/'solve_model.m',
                                       HERE.parent/'v1_evaluator/interval.py']
    return {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)}


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
        allow_nan=False, default=str)+'\n', encoding='utf-8')


def run(out):
    out = out.resolve(); out.relative_to(REPO); out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic(); capture = io.StringIO(); error = None; tests = {}; details = {}
    # Cache the Windows environment query before subprocess guards; platform
    # itself may use a read-only system command on its first invocation.
    environment = {'python': sys.version, 'platform': platform.platform()}
    before = sources(); baseline = json.loads((REPO/'.runtime/k150_baseline.json').read_text(encoding='utf-8'))
    save(out/'parent_baseline.json', baseline)
    for name in before:
        target = out/'source_snapshot'/name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO/name).read_bytes())
    guards = {n: 0 for n in ('subprocess.Popen', 'MatlabSession.__init__',
        'scipy.optimize.milp', 'scipy.optimize.linprog', 'original_scale_build_model')}
    builds = {'tiny_structural': 0, 'tiny_physical': 0}

    def forbidden(name):
        def fail(*args, **kwargs):
            guards[name] += 1
            raise AssertionError('Forbidden K150 precheck call: '+name)
        return fail

    try:
        import scipy.optimize
        import matlab_bridge
        import milp
        original_build = milp.build_model

        @wraps(original_build)
        def bounded_build(instance, *args, **kwargs):
            # One inherited test uses this exact renamed tiny input solely to
            # verify the existing production reduced-start rejection.
            negative = (instance.get('id') == 'not_a_fixture_n1_interface'
                and kwargs.get('include_physics') is False and kwargs.get('starts') is not None)
            domain = instance.get('start_domain', {}).get('by_scene_stage_ms', {})
            tiny = (str(instance.get('id', '')).startswith('fixture_')
                and sum(len(s.get('stage_instances', [])) for s in instance['scenarios']) <= 12
                and domain and all(len(v) <= 8 for by_stage in domain.values() for v in by_stage.values()))
            if not (tiny or negative):
                return forbidden('original_scale_build_model')()
            key = 'tiny_physical' if kwargs.get('include_physics', True) else 'tiny_structural'
            builds[key] += 1
            return original_build(instance, *args, **kwargs)

        fixture_root = REPO/'.runtime/k150_fixtures'; fixture_root.mkdir(parents=True, exist_ok=True)

        class Folder:
            def __init__(self, *args, **kwargs):
                parent = Path(kwargs.get('dir') or fixture_root).resolve(); parent.relative_to(REPO)
                parent.mkdir(parents=True, exist_ok=True)
                self.name = str(parent/('case_'+uuid4().hex)); Path(self.name).mkdir()
            def __enter__(self):
                return self.name
            def __exit__(self, *args):
                return False
            def cleanup(self):
                pass  # retain diagnostic fixture files; never manually delete user paths

        with ExitStack() as stack:
            stack.enter_context(patch('subprocess.Popen', side_effect=forbidden('subprocess.Popen')))
            stack.enter_context(patch.object(matlab_bridge.MatlabSession, '__init__', side_effect=forbidden('MatlabSession.__init__')))
            stack.enter_context(patch.object(scipy.optimize, 'milp', side_effect=forbidden('scipy.optimize.milp')))
            stack.enter_context(patch.object(scipy.optimize, 'linprog', side_effect=forbidden('scipy.optimize.linprog')))
            stack.enter_context(patch.object(milp, 'build_model', bounded_build))
            stack.enter_context(patch('tempfile.TemporaryDirectory', Folder))
            with redirect_stdout(capture), redirect_stderr(capture):
                for name in MODULES:
                    suite = unittest.defaultTestLoader.loadTestsFromName(name)
                    result = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
                    tests[name] = {'count': result.testsRun, 'passed': result.wasSuccessful(),
                        'errors': len(result.errors), 'failures': len(result.failures), 'skipped': len(result.skipped)}
                    details[name] = getattr(sys.modules.get(name), 'RECORDS', {})
    except BaseException:
        error = traceback.format_exc(); capture.write(error)
    after = sources()
    changed = sorted(n for n, h in baseline['source_sha256'].items() if after.get(n) != h)
    history_bad = [n for n, h in baseline['historical_sha256'].items() if not (REPO/n).is_file() or sha(REPO/n) != h]
    snapshot_bad = [n for n, h in before.items() if sha(out/'source_snapshot'/n) != h]
    report = {'protocol': PROTOCOL, 'stage': 'K150', 'parent_commit': baseline['parent_commit'],
        'passed': bool(len(tests) == len(MODULES) and all(t['passed'] and not t['skipped'] for t in tests.values())
            and before == after and not history_bad and not snapshot_bad and not any(guards.values()) and error is None
            and set(changed) == set(baseline['allowed_changes'])),
        'modules': tests, 'count': sum(t['count'] for t in tests.values()),
        'source_sha256': after, 'source_count': len(after), 'source_unchanged_during_precheck': before == after,
        'changed_inherited_sources': changed, 'allowed_changes': baseline['allowed_changes'],
        'unchanged_inherited_source_count': len(baseline['source_sha256'])-len(changed),
        'historical_artifact_count': len(baseline['historical_sha256']),
        'historical_artifacts_unchanged': not history_bad, 'historical_mismatches': history_bad,
        'snapshot_mismatches': snapshot_bad, 'blocked_calls': guards, 'tiny_model_builds': builds,
        'research_calls': 0, 'native_calls': 0, 'original_scale_models': 0,
        'error': error, 'elapsed_s': time.monotonic()-start,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'environment': environment,
        'scope': 'implementation correctness only; no quality, root-LP speed or energy-saving evidence'}
    save(out/'checks.json', report); save(out/'fixture_records.json', details)
    (out/'unittest.txt').write_text(capture.getvalue(), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'count', 'elapsed_s', 'error')}, ensure_ascii=False))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args().out) else 1)
