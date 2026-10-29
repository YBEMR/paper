"""Data-only process monitor tests. No actual OS/resource/process probes."""
from copy import deepcopy
import unittest

from .monitor import ProcessMonitor, host_gate, GIB


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


class FakeProvider:
    def __init__(self):
        self.records = {
            10: {'pid': 10, 'create_time': 100.0, 'state': 'ACTIVE', 'name': 'python.exe', 'rss_bytes': 100},
            20: {'pid': 20, 'create_time': 101.0, 'state': 'ACTIVE', 'name': 'MATLAB.exe', 'rss_bytes': 300},
            99: {'pid': 99, 'create_time': 90.0, 'state': 'ACTIVE', 'name': 'MATLAB.exe', 'rss_bytes': 900},
        }
        self.links = {10: [20]}
        self.signals = []
        self.scan_unknown = False
        self.signal_error = False

    def describe(self, pid):
        return deepcopy(self.records.get(pid, {'pid': pid, 'state': 'EXITED'}))

    def children(self, pid):
        return {'state': 'UNKNOWN' if self.scan_unknown else 'OK',
                'processes': [self.describe(x) for x in self.links.get(pid, [])]}

    def signal(self, pid, create_time, *, force=False):
        if self.signal_error: raise PermissionError('injected no permission')
        self.signals.append((pid, create_time, force))
        if self.records[pid]['create_time'] != create_time:
            return {'state': 'NOT_SIGNALLED', 'reason': 'PID_REUSED'}
        self.records[pid]['state'] = 'EXITED'
        return {'state': 'SIGNALLED'}


def good_host():
    return {'state': 'AVAILABLE', 'physical_available_bytes': 2*GIB,
            'commit_available_bytes': 4*GIB, 'disk_free_bytes': 2*GIB,
            'token_is_appcontainer': False, 'matlab_processes': [],
            'matlab_scan_complete': True, 'errors': []}


class MonitorTests(unittest.TestCase):
    def make(self):
        provider, clock = FakeProvider(), Clock()
        return provider, clock, ProcessMonitor(10, provider=provider, clock=clock)

    def test_sample_same_time_sum_is_not_sum_of_individual_peaks(self):
        p, clock, monitor = self.make()
        self.assertEqual(monitor.sample()['same_sample_rss_sum_bytes'], 400)
        p.records[10]['rss_bytes'] = 500
        p.records[20]['rss_bytes'] = 50
        clock.now = 1
        self.assertEqual(monitor.sample()['same_sample_rss_sum_bytes'], 550)
        summary = monitor.summary()
        self.assertEqual(summary['sampled_peak_same_time_rss_sum_bytes'], 550)
        self.assertEqual(sum(x['sampled_peak_rss_bytes'] for x in summary['sampled_peak_by_identity']), 800)
        self.assertNotIn(99, [x['pid'] for x in summary['sampled_peak_by_identity']])

    def test_one_second_sample_interval(self):
        p, clock, monitor = self.make()
        monitor.sample()
        clock.now = 0.5
        self.assertEqual(monitor.poll()['state'], 'NOT_DUE')
        clock.now = 1
        self.assertTrue(monitor.poll()['sampled'])
        self.assertEqual(monitor.summary()['sample_count'], 2)

    def test_missing_memory_remains_unknown_not_zero(self):
        p, clock, monitor = self.make()
        p.records[20]['rss_bytes'] = None
        r = monitor.sample()
        self.assertIsNone(r['same_sample_rss_sum_bytes'])
        self.assertEqual(r['known_rss_sum_bytes'], 100)
        self.assertFalse(r['memory_sample_complete'])
        self.assertIsNone(monitor.summary()['sampled_peak_same_time_rss_sum_bytes'])

    def test_pid_reuse_never_signals_replacement(self):
        p, clock, monitor = self.make()
        monitor.sample()
        p.records[10]['create_time'] = 200
        p.records[20]['create_time'] = 201
        monitor.terminate_owned(force=True)
        self.assertEqual(p.signals, [])
        self.assertTrue(monitor.cleanup_verified())

    def test_known_matlab_remains_after_python_exit(self):
        p, clock, monitor = self.make()
        monitor.sample()
        p.records[10]['state'] = 'EXITED'
        self.assertFalse(monitor.cleanup_verified())

    def test_only_owned_process_tree_is_terminated(self):
        p, clock, monitor = self.make()
        monitor.sample()
        r = monitor.terminate_owned()
        self.assertEqual([x[0] for x in p.signals], [20, 10])
        self.assertEqual(p.records[99]['state'], 'ACTIVE')
        self.assertTrue(monitor.cleanup_verified())

    def test_unknown_identity_is_not_signalled_or_verified(self):
        p, clock, monitor = self.make()
        monitor.sample()
        p.records[20] = {'pid': 20, 'state': 'UNKNOWN'}
        r = monitor.terminate_owned(force=True)
        self.assertNotIn(20, [x[0] for x in p.signals])
        self.assertIsNone(monitor.cleanup_verified())

    def test_worker_receipt_adds_observed_orphan_identity(self):
        p, clock, monitor = self.make()
        p.links[10] = []
        monitor.sample()
        p.records[10]['state'] = 'EXITED'
        self.assertEqual(monitor.register_identities([p.describe(20)], source='bound closed.json'), [True])
        self.assertFalse(monitor.cleanup_verified())

    def test_invalid_registration_rejected(self):
        p, clock, monitor = self.make()
        self.assertEqual(monitor.register_identities([p.describe(99)], source='fixture'), [False])
        self.assertIn('DESCENDANT_PREDATES_ROOT', monitor.summary()['identity_errors'])
        with self.assertRaises(ValueError): monitor.register_identities([], source='')

    def test_worker_identity_creation_time_aliases(self):
        p, clock, monitor = self.make()
        item = p.describe(20)
        item['creation_time'] = item.pop('create_time')
        self.assertEqual(monitor.register_identities([item], source='bound worker receipt'), [True])
        item['created_at'] = 999
        self.assertEqual(monitor.register_identities([item], source='bound worker receipt'), [False])

    def test_incomplete_tree_scan_prevents_cleanup_success(self):
        p, clock, monitor = self.make()
        p.scan_unknown = True
        monitor.sample()
        p.records[10]['state'] = p.records[20]['state'] = 'EXITED'
        self.assertIsNone(monitor.cleanup_verified())

    def test_termination_failure_is_recorded(self):
        p, clock, monitor = self.make()
        monitor.sample(); p.signal_error = True
        r = monitor.terminate_owned(force=True)
        self.assertTrue(all(x['state'] == 'NOT_SIGNALLED' for x in r))
        self.assertFalse(monitor.cleanup_verified())

    def test_unverified_initial_root_cannot_be_verified_later_by_pid_only(self):
        p, clock = FakeProvider(), Clock()
        p.records[10] = {'pid': 10, 'state': 'UNKNOWN'}
        m = ProcessMonitor(10, provider=p, clock=clock)
        self.assertIsNone(m.cleanup_verified())
        self.assertEqual(m.terminate_owned(), [])

    def test_host_gate_accepts_exact_frozen_thresholds(self):
        self.assertTrue(host_gate(good_host())['passed'])

    def test_host_gate_rejects_shortage_unknown_and_existing_matlab(self):
        for key, value in [('physical_available_bytes', 2*GIB-1),
                           ('commit_available_bytes', 4*GIB-1), ('disk_free_bytes', None),
                           ('token_is_appcontainer', True), ('token_is_appcontainer', None),
                           ('matlab_processes', [{'pid': 99}]), ('matlab_scan_complete', False),
                           ('state', 'UNAVAILABLE')]:
            with self.subTest(key=key):
                probe = good_host(); probe[key] = value
                self.assertFalse(host_gate(probe)['passed'])

    def test_provider_os_error_becomes_unknown(self):
        class Broken(FakeProvider):
            def describe(self, pid): raise OSError('injected')
        m = ProcessMonitor(10, provider=Broken(), clock=Clock())
        r = m.sample()
        self.assertIsNone(r['same_sample_rss_sum_bytes'])
        self.assertIsNone(m.cleanup_verified())

    def test_unknown_descendant_scan_is_not_complete_memory(self):
        p, clock, monitor = self.make()
        p.scan_unknown=True; p.links[10]=[]
        r=monitor.sample()
        self.assertFalse(r['memory_sample_complete'])
        self.assertIsNone(r['same_sample_rss_sum_bytes'])
        self.assertEqual(r['known_rss_sum_bytes'],100)
