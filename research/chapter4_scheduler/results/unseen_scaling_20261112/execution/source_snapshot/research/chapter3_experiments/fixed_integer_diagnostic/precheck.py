"""Frozen, pure preflight: no native process, optimizer or thermal evaluator."""
from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

import run_once as run


def main():
    declaration = run.admission()
    if (run.OUT / 'launch.claim.json').exists():
        raise RuntimeError('Preflight must precede the one execution claim')
    # platform.platform()/machine() can use Windows `ver`; inventory this read
    # before blocking child processes, then keep all tests/native work guarded.
    environment = run.check_python_environment(declaration['original_python_environment'])
    with patch('subprocess.Popen', side_effect=AssertionError('NATIVE_FORBIDDEN')) as guard:
        import numpy as np
        import core
        import test_core
        import test_runner
        stream = io.StringIO()
        suite = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromModule(test_core),
            unittest.defaultTestLoader.loadTestsFromModule(test_runner)])
        tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        with (run.OUT / 'pure_tests.txt').open('x', encoding='utf-8', newline='\n') as f:
            f.write(stream.getvalue())
        if not tests.wasSuccessful():
            raise AssertionError('Pure tests failed; no execution permitted')
        original, source = core.load_original_mat(run.OLD / 'method/matlab/request_000001.mat')
        expected = declaration['source_files'][(run.OLD / 'method/matlab/request_000001.mat').relative_to(run.REPO).as_posix()]
        assert source['sha256'] == expected['sha256']
        fixed, transform = core.fix_actual_intcon(original)
        identity = core.assert_only_fixed_integer_bounds_changed(original, fixed)
        initial = core.verify_vector(original['x0'], original, fixed, require_objective=False)
        assert initial['accepted']
        bridge = run.bind_bridge()
        with patch.object(bridge, 'MatlabSession', side_effect=AssertionError('SESSION_FORBIDDEN')) as session_guard:
            exported = bridge._prepare(fixed, x0=original['x0'])
            assert np.array_equal(exported['intcon'], original['intcon'] + 1)
            assert exported['x0_validation']['accepted_numerically']
            restored = {k: exported[k] for k in core.KEYS}
            restored['intcon'] = (exported['intcon'] - 1).astype(np.int64)
            export_identity = core.assert_only_fixed_integer_bounds_changed(original, restored)
            assert session_guard.call_count == 0
        forbidden = [name for name in sys.modules if name in
            ('milp', 'thermal', 'formal_milp', 'method_runner', 'initial_schedule', 'initial_point')]
        assert not forbidden
        assert guard.call_count == 0
        run.admission()
        receipt = dict(passed=True, utc=run.now(), declaration_sha256=run.sha(run.OUT / 'declaration.json'),
            test_count=tests.testsRun, environment=environment, archived_source=source,
            transform=transform, input_identity=identity, original_x0_admission=initial,
            frozen_bridge_export_identity=export_identity, original_bridge_x0_admission=exported['x0_validation'],
            original_integer_ones=int(np.sum(original['x0'][original['intcon']] == 1)),
            original_integer_zeros=int(np.sum(original['x0'][original['intcon']] == 0)),
            native_starts=0, research_calls=0, thermal_integrations=0, model_constructions=0,
            actual_candidate_evaluations=0, subprocess_guard_calls=guard.call_count,
            imported_forbidden_modules=forbidden)
        run.write_new(run.OUT / 'pure_checks.json', receipt)
        print({'passed': True, 'test_count': tests.testsRun, 'archived_payload_identity': True,
               'native_starts': 0, 'thermal_integrations': 0})


if __name__ == '__main__':
    main()
