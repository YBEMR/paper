"""Owned-process supervisor regressions. Children are stdlib-only mocks."""
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from .process_control import supervise, ProcessContractError


class Clock:
    def __init__(self, at=100.): self.at = at
    def __call__(self): return self.at
    def sleep(self, amount): self.at += amount


class FakeProcess:
    def __init__(self, clock, finish_at=None, code=0):
        self.clock, self.finish_at, self.code = clock, finish_at, code
        self.pid, self.returncode, self.kills, self.waits = 987654, None, 0, 0
    def poll(self):
        if self.returncode is None and self.finish_at is not None and self.clock() >= self.finish_at:
            self.returncode = self.code
        return self.returncode
    def kill(self):
        self.kills += 1
        self.returncode = -9
    def wait(self, timeout=None):
        self.waits += 1
        return self.returncode


MOCK_SCRIPT = r"""
import json, pathlib, sys, time
assert sys.argv[1] == '--e1-mock-worker'
mode, stop, receipt = sys.argv[2], pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[4])
print('mock-stdout', flush=True)
print('mock-stderr', file=sys.stderr, flush=True)
if mode == 'normal':
    receipt.write_text(json.dumps({'state':'MOCK_ONLY','new_real_SAFE':0}))
elif mode == 'fault':
    sys.exit(7)
elif mode == 'ack':
    while not stop.exists(): time.sleep(.005)
    receipt.write_text(json.dumps({'state':'MOCK_ARCHIVE_ONLY','new_real_SAFE':0}))
elif mode == 'hang':
    while True: time.sleep(.01)
else:
    raise RuntimeError('unknown mock')
"""


class ProcessControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='e1-process-mock-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def fake(self, *, at=100., limit=300, slot=520., batch=1900., finish=None,
             code=0, spawn_cost=0., grace=5., **changes):
        clock = Clock(at)
        process = FakeProcess(clock, finish, code)
        calls=[]
        def launch(command, **kwargs):
            calls.append((command, kwargs))
            clock.at += spawn_cost
            return process
        kwargs=dict(cwd=self.path, root_origin=100., limit_s=limit,
                    slot_deadline=slot, batch_deadline=batch,
                    stop_file=self.path/'stop.json', receipt_file=self.path/'receipt.json',
                    grace_s=grace, clock=clock, popen=launch, sleep=clock.sleep)
        kwargs.update(changes)
        result=supervise(['mock-program','--e1-mock-worker'],**kwargs)
        return result, process, calls, clock

    def test_natural_exit_and_logs_metadata(self):
        r,p,c,k=self.fake(finish=101.)
        self.assertEqual(r['classification'],'NATURAL_EXIT')
        self.assertTrue(r['reaped']); self.assertEqual(p.waits,1); self.assertEqual(p.kills,0)
        self.assertEqual(r['pid'],987654); self.assertEqual(len(r['command_sha256']),64)
        self.assertFalse(c[0][1]['shell']); self.assertFalse(r['usable_as_research_evidence'])
        self.assertTrue(Path(r['stdout_file']).is_file())

    def test_preparation_and_spawn_time_are_charged(self):
        r,p,c,k=self.fake(at=110., spawn_cost=3., finish=114.)
        self.assertEqual(r['launch_requested_elapsed_s'],10.)
        self.assertEqual(r['spawned_elapsed_s'],13.)
        self.assertEqual(r['startup_elapsed_s'],3.)
        self.assertGreaterEqual(r['method_elapsed_s'],14.)
        self.assertEqual(r['root_deadline'],400.)

    def test_root_stop_then_grace_kill_reaps_owned_handle(self):
        r,p,c,k=self.fake()
        self.assertEqual(r['classification'],'WATCHDOG_KILLED')
        self.assertEqual(p.kills,1); self.assertEqual(p.waits,1)
        self.assertAlmostEqual(r['stop_signal_elapsed_s'],300.,places=7)
        self.assertAlmostEqual(r['kill_elapsed_s'],305.,places=7)
        self.assertEqual(r['stop_reason'],['ROOT_LIMIT'])
        self.assertEqual(json.loads((self.path/'stop.json').read_text())['state'],'ARCHIVE_ONLY_STOP_NEW_WORK')

    def test_exit_during_grace_is_normal_time_cutoff(self):
        r,p,c,k=self.fake(finish=402.)
        self.assertEqual(r['classification'],'NORMAL_TIME_CUTOFF')
        self.assertFalse(r['killed']); self.assertEqual(p.kills,0)
        self.assertGreater(r['deadline_overshoot_s'],0)

    def test_nonzero_exit_is_fault_even_during_grace(self):
        r,p,c,k=self.fake(finish=401., code=8)
        self.assertEqual(r['classification'],'NONZERO_EXIT_FAULT')
        self.assertEqual(r['returncode'],8)

    def test_slot_deadline_can_precede_root(self):
        r,p,c,k=self.fake(slot=150.)
        self.assertEqual(r['evidence_deadline'],150.)
        self.assertEqual(r['hard_deadline'],150.)
        self.assertEqual(r['stop_reason'],['SLOT_LIMIT'])
        self.assertAlmostEqual(r['kill_elapsed_s'],50.)

    def test_batch_deadline_truncates_archive_grace(self):
        r,p,c,k=self.fake(batch=403.)
        self.assertEqual(r['hard_deadline'],403.)
        self.assertAlmostEqual(r['kill_elapsed_s'],303.)

    def test_expired_before_spawn_never_starts_process(self):
        r,p,c,k=self.fake(at=401.)
        self.assertEqual(r['classification'],'START_SKIPPED_DEADLINE')
        self.assertEqual(c,[]); self.assertIsNone(r['pid']); self.assertFalse(r['reaped'])

    def test_expiry_during_log_setup_does_not_spawn(self):
        values=iter([100.,400.,400.,400.])
        called=[]
        r=supervise(['mock'],cwd=self.path,root_origin=100.,limit_s=300,
            slot_deadline=600.,batch_deadline=2000.,stop_file=self.path/'stop',
            receipt_file=self.path/'receipt',clock=lambda: next(values),
            popen=lambda *a,**k: called.append(True))
        self.assertEqual(r['classification'],'START_SKIPPED_DEADLINE')
        self.assertEqual(called,[])

    def test_short_limit_cannot_start_real_or_unmarked_command(self):
        for command,flag in ((['real-worker'],False),(['real-worker'],True),
                             (['mock','--e1-mock-worker'],False)):
            with self.subTest(command=command,flag=flag):
                with self.assertRaises(ProcessContractError):
                    supervise(command,cwd=self.path,root_origin=0,limit_s=.1,
                        slot_deadline=2,batch_deadline=3,stop_file=self.path/'stop',
                        receipt_file=self.path/'receipt',allow_test_limits=flag)

    def test_bad_clock_and_stale_artifacts_rejected(self):
        with self.assertRaises(ProcessContractError): self.fake(at=99.)
        (self.path/'receipt.json').write_text('stale')
        with self.assertRaises(ProcessContractError): self.fake()

    def test_spawn_error_preserves_fault_and_no_pid(self):
        def fail(*a,**k): raise OSError('mock launch failure')
        r,p,c,k=self.fake(popen=fail)
        self.assertEqual(r['classification'],'SPAWN_FAULT')
        self.assertEqual(r['error_type'],'OSError'); self.assertIsNone(r['pid'])

    def test_cleanup_failure_is_bounded_and_explicit(self):
        clock=Clock(100.)
        process=FakeProcess(clock)
        timeouts=[]
        def failed_wait(timeout=None):
            timeouts.append(timeout)
            raise subprocess.TimeoutExpired('mock',timeout)
        process.wait=failed_wait
        r=supervise(['mock'],cwd=self.path,root_origin=100.,limit_s=60,
            slot_deadline=500.,batch_deadline=2000.,stop_file=self.path/'stop',
            receipt_file=self.path/'receipt',clock=clock,sleep=clock.sleep,
            popen=lambda *a,**k: process)
        self.assertEqual(r['classification'],'PROCESS_CLEANUP_FAULT')
        self.assertTrue(r['cleanup_pending']); self.assertFalse(r['reaped'])
        self.assertEqual(timeouts,[2.]); self.assertEqual(process.kills,1)

    def test_real_stdlib_mock_nonzero_is_fault(self):
        origin=time.monotonic()
        r=supervise([sys.executable,'-I','-B','-c',MOCK_SCRIPT,'--e1-mock-worker',
                     'fault',str(self.path/'stop'),str(self.path/'receipt')],
            cwd=self.path,root_origin=origin,limit_s=2.,slot_deadline=origin+3.,
            batch_deadline=origin+4.,stop_file=self.path/'stop',receipt_file=self.path/'receipt',
            allow_test_limits=True)
        self.assertEqual(r['classification'],'NONZERO_EXIT_FAULT')
        self.assertEqual(r['returncode'],7); self.assertTrue(r['reaped'])

    def test_real_stdlib_mock_natural_exit(self):
        origin=time.monotonic()
        r=supervise([sys.executable,'-I','-B','-c',MOCK_SCRIPT,'--e1-mock-worker',
                     'normal',str(self.path/'stop'),str(self.path/'receipt')],
            cwd=self.path,root_origin=origin,limit_s=2.,slot_deadline=origin+3.,
            batch_deadline=origin+4.,stop_file=self.path/'stop',receipt_file=self.path/'receipt',
            allow_test_limits=True)
        self.assertEqual(r['classification'],'NATURAL_EXIT')
        self.assertTrue(r['reaped']); self.assertIn('mock-stdout',Path(r['stdout_file']).read_text())
        self.assertIn('mock-stderr',Path(r['stderr_file']).read_text())
        self.assertEqual(r['receipt_arrival'],'OBSERVED_BEFORE_CUTOFF_UNVERIFIED')
        self.assertFalse(r['usable_as_research_evidence'])

    def test_real_stdlib_mock_stop_and_archive(self):
        origin=time.monotonic()
        r=supervise([sys.executable,'-I','-B','-c',MOCK_SCRIPT,'--e1-mock-worker',
                     'ack',str(self.path/'stop'),str(self.path/'receipt')],
            cwd=self.path,root_origin=origin,limit_s=.25,slot_deadline=origin+2.,
            batch_deadline=origin+3.,stop_file=self.path/'stop',receipt_file=self.path/'receipt',
            grace_s=.5,allow_test_limits=True)
        self.assertEqual(r['classification'],'NORMAL_TIME_CUTOFF')
        self.assertTrue(r['stop_signal_written']); self.assertFalse(r['killed'])
        self.assertEqual(r['receipt_arrival'],'LATE_ARCHIVAL_ONLY')
        self.assertEqual(json.loads(Path(r['receipt_file']).read_text())['new_real_SAFE'],0)

    def test_real_stdlib_mock_hang_is_killed_and_reaped(self):
        origin=time.monotonic()
        r=supervise([sys.executable,'-I','-B','-c',MOCK_SCRIPT,'--e1-mock-worker',
                     'hang',str(self.path/'stop'),str(self.path/'receipt')],
            cwd=self.path,root_origin=origin,limit_s=.12,slot_deadline=origin+2.,
            batch_deadline=origin+3.,stop_file=self.path/'stop',receipt_file=self.path/'receipt',
            grace_s=.08,allow_test_limits=True)
        self.assertEqual(r['classification'],'WATCHDOG_KILLED')
        self.assertTrue(r['killed']); self.assertTrue(r['reaped'])
        self.assertIsNotNone(r['returncode'])


if __name__ == '__main__': unittest.main()
