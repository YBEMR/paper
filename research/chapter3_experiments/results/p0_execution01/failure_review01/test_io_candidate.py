"""Small workspace-only Windows file fixtures; zero research/solver/heat."""
import json
from pathlib import Path
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
import safe_ledger_candidate as fix

REPO=next(p for p in Path(__file__).resolve().parents if (p/'AGENTS.md').exists())


def denied(code):
    error=PermissionError('MOCK_WINDOWS_ACCESS_ERROR');error.winerror=code
    return error


class IOTemperatureIndependentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=REPO/'.runtime')
        # Verify the absolute deletion target remains inside this workspace.
        self.root=Path(self.temp.name).resolve();self.root.relative_to(REPO.resolve())
        self.addCleanup(self.temp.cleanup)
        self.path=self.root/'ledger.json';self.path.write_text('{"old":1}',encoding='utf-8')

    def test_01_windows_open_reader_reproduces_original_error(self):
        pending=self.path.with_suffix('.json.pending');pending.write_text('{"new":1}',encoding='utf-8')
        with self.path.open('r',encoding='utf-8'):
            with self.assertRaises(PermissionError) as caught:os.replace(pending,self.path)
        self.assertIn(caught.exception.winerror,(5,32))
        self.assertTrue(pending.exists());self.assertEqual(json.loads(self.path.read_text()),{'old':1})

    def test_02_bounded_retry_survives_short_reader(self):
        reader=self.path.open('r',encoding='utf-8')
        timer=threading.Timer(.08,reader.close);timer.start()
        try:result=fix.save(self.path,{'new':2})
        finally:timer.join();reader.close()
        self.assertGreater(result['attempts'],1)
        self.assertLess(result['replace_wait_s'],1.)
        self.assertEqual(json.loads(self.path.read_text()),{'new':2})
        self.assertFalse(self.path.with_suffix('.json.pending').exists())

    def test_03_permanent_rejection_stops_with_pending_retained(self):
        replace=Mock(side_effect=denied(5))
        with self.assertRaises(PermissionError):fix.save(self.path,{'new':3},max_wait_s=.04,replace=replace)
        self.assertLessEqual(replace.call_count,5)
        self.assertEqual(json.loads(self.path.read_text()),{'old':1})
        self.assertEqual(json.loads(self.path.with_suffix('.json.pending').read_text()),{'new':3})

    def test_04_unrelated_error_is_not_swallowed_or_retried(self):
        replace=Mock(side_effect=denied(13))
        with self.assertRaises(PermissionError):fix.save(self.path,{'new':4},replace=replace)
        self.assertEqual(replace.call_count,1)

    def test_05_stale_pending_is_not_removed_or_reused(self):
        pending=self.path.with_suffix('.json.pending');pending.write_text('OLD_CRASH',encoding='utf-8')
        with self.assertRaises(FileExistsError):fix.save(self.path,{'new':5})
        self.assertEqual(pending.read_text(),'OLD_CRASH')

    def test_06_atomic_old_value_stays_until_success(self):
        calls=[]
        def replace(source,dest):
            self.assertEqual(json.loads(Path(dest).read_text()),{'old':1})
            self.assertEqual(json.loads(Path(source).read_text()),{'new':6})
            calls.append(1)
            if len(calls)<3:raise denied(32)
            os.replace(source,dest)
        result=fix.save(self.path,{'new':6},replace=replace)
        self.assertEqual(result['attempts'],3)
        self.assertEqual(json.loads(self.path.read_text()),{'new':6})

    def test_07_zero_wait_attempts_once(self):
        replace=Mock(side_effect=denied(5))
        with self.assertRaises(PermissionError):fix.save(self.path,{'new':7},max_wait_s=0,replace=replace)
        self.assertEqual(replace.call_count,1)

    def test_08_large_or_negative_wait_is_rejected(self):
        for value in (-1,2):
            with self.assertRaises(ValueError):fix.save(self.path,{},max_wait_s=value)
        self.assertFalse(self.path.with_suffix('.json.pending').exists())


if __name__=='__main__':
    import io
    log=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(IOTemperatureIndependentTests)
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    out=Path(__file__).resolve().parent
    (out/'io_unittest.txt').write_text(log.getvalue(),encoding='utf-8')
    report={'passed':result.wasSuccessful(),'tests_run':result.testsRun,
        'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
        'research_calls':0,'native_calls':0,'thermal_evaluations':0,
        'source_scope':'isolated candidate fix only, NOT applied to frozen K155 source or ledger',
        'finding':'held Python read handle reproduces WinError5/32; does not identify actual lock holder'}
    with (out/'io_checks.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(report)
    raise SystemExit(0 if result.wasSuccessful() else 1)
