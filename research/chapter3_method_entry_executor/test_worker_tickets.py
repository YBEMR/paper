"""Pure ticket/handshake/post mocks. No real claim, process or evaluator.

Every artifact lives below the current manual test run. The global batch
claim read is mocked; the authorization file stays the real false template.
"""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

from . import common, worker, test_executor as te


def _replace_mock(path, value):
    # Deliberate mutation of test artifacts, never production evidence.
    Path(path).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def ticket_case(mode='method', mid='heft'):
    ctx, out = te.case()
    batch = out/'mock_batch'
    slot = batch/'slots'/(mid+'__'+mode)
    path = slot/'ticket.json'
    global_claim = Path(worker.__file__).resolve().parent/'claims'/(ctx['plan_sha256']+'.json')
    ticket = {'schema': 'ch3-method-entry-ticket-v1',
        'plan_sha256': ctx['plan_sha256'], 'input_sha256': ctx['plan']['common_input_sha256'],
        'job_id': mid, 'mode': mode, 'slot_id': slot.name, 'worker_token': 'manual-token',
        'created_at_monotonic_s': 100.0,
        'absolute_deadline_monotonic_s': 160.0 if mode == 'post' else 580.0,
        'method_output': str(batch/'slots'/(mid+'__method')/'worker') if mode == 'post' else None,
        'ticket_claim_path': str(slot/'worker_started.json'),
        'batch_claim_path': str(global_claim), 'batch_output': str(batch)}
    common.save(path, ticket)
    common.save(slot/'slot_claim.json', {'ticket_sha256': common.sha(path), 'slot_id': slot.name})
    record = {'plan_sha256': ctx['plan_sha256'], 'input_sha256': ctx['plan']['common_input_sha256'],
              'batch_output': str(batch), 'authorization_sha256': common.sha(ctx['authorization_path'])}
    original_load = worker._load

    def loader(p):
        return deepcopy(record) if Path(p).resolve() == global_claim.resolve() else original_load(p)

    return ctx, out, ticket, path, slot/'worker', record, loader


class FakePostBudget:
    def __init__(self, seconds):
        self.seconds = seconds
        self.start = None


def post_case():
    ctx, out = te.case()
    value = common.verify_input(ctx)
    raw = te.fake_safe(value['instance'])
    method_out = out/'mock_method'/'worker'
    common.save(method_out/'worker_result.json', {
        'method_id': 'heft', 'plan_sha256': ctx['plan_sha256'],
        'common_input_sha256': ctx['plan']['common_input_sha256'],
        'safe_witness_preserved': True, 'safe_candidate': raw['safe_candidate'], 'raw_result': raw,
        'simulation_only': True})
    ticket = {'job_id': 'heft', 'method_output': str(method_out), 'absolute_deadline_monotonic_s': 60.0}
    return ctx, out, ticket, value, raw


def post_bindings(value, result, clock, *, returned_at=40.0, calls=None, error=None):
    def evaluate(*args):
        if calls is not None: calls.append(args)
        clock.value = returned_at
        if error is not None: raise error
        return deepcopy(result)
    return {'verify_input': lambda context: deepcopy(value), 'Budget': FakePostBudget,
            'evaluate': evaluate}


class TicketTests(unittest.TestCase):
    def test_valid_method_ticket_without_real_global_claim(self):
        ctx, out, ticket, path, output, record, loader = ticket_case()
        with patch.object(worker, '_load', side_effect=loader):
            accepted, job = worker.validate_ticket(ctx, path, 'manual-token', output, now=101)
        self.assertEqual(accepted, ticket); self.assertEqual(job['id'], 'heft')
        self.assertFalse(Path(ticket['ticket_claim_path']).exists())

    def test_valid_post_ticket_binds_same_job_method_output(self):
        ctx, out, ticket, path, output, record, loader = ticket_case('post')
        with patch.object(worker, '_load', side_effect=loader):
            accepted, job = worker.validate_ticket(ctx, path, 'manual-token', output, now=101)
        self.assertEqual(accepted['method_output'], ticket['method_output'])

    def test_token_plan_input_and_unknown_job_rejected(self):
        for kind in ('token', 'plan', 'input', 'job'):
            with self.subTest(kind=kind):
                ctx, out, ticket, path, output, record, loader = ticket_case()
                token = 'wrong' if kind == 'token' else 'manual-token'
                if kind == 'plan': ticket['plan_sha256'] = 'wrong'
                if kind == 'input': ticket['input_sha256'] = 'wrong'
                if kind == 'job': ticket['job_id'] = 'unknown'
                _replace_mock(path, ticket)
                with patch.object(worker, '_load', side_effect=loader), self.assertRaises(ValueError):
                    worker.validate_ticket(ctx, path, token, output, now=101)

    def test_deadline_and_budget_extension_rejected(self):
        for kind in ('expired', 'extended', 'nonfinite'):
            with self.subTest(kind=kind):
                ctx, out, ticket, path, output, record, loader = ticket_case()
                now = 580 if kind == 'expired' else 101
                if kind == 'extended': ticket['absolute_deadline_monotonic_s'] = 581
                if kind == 'nonfinite': ticket['absolute_deadline_monotonic_s'] = float('inf')
                _replace_mock(path, ticket)
                _replace_mock(path.parent/'slot_claim.json', {'ticket_sha256': common.sha(path), 'slot_id': path.parent.name})
                with patch.object(worker, '_load', side_effect=loader), self.assertRaises(ValueError):
                    worker.validate_ticket(ctx, path, 'manual-token', output, now=now)

    def test_slot_claim_hash_and_batch_authorization_drift_rejected(self):
        for kind in ('slot_hash', 'batch_auth', 'batch_output'):
            with self.subTest(kind=kind):
                ctx, out, ticket, path, output, record, loader = ticket_case()
                if kind == 'slot_hash':
                    _replace_mock(path.parent/'slot_claim.json', {'ticket_sha256': 'wrong', 'slot_id': path.parent.name})
                if kind == 'batch_auth': record['authorization_sha256'] = 'wrong'
                if kind == 'batch_output': record['batch_output'] = str(out/'other_batch')
                with patch.object(worker, '_load', side_effect=loader), self.assertRaises(ValueError):
                    worker.validate_ticket(ctx, path, 'manual-token', output, now=101)

    def test_wrong_output_and_existing_worker_claim_rejected(self):
        for kind in ('output', 'consumed'):
            with self.subTest(kind=kind):
                ctx, out, ticket, path, output, record, loader = ticket_case()
                if kind == 'output': output = out/'foreign_worker'
                else: common.save(Path(ticket['ticket_claim_path']), {'simulation_only': True})
                with patch.object(worker, '_load', side_effect=loader), self.assertRaises(ValueError):
                    worker.validate_ticket(ctx, path, 'manual-token', output, now=101)

    def test_post_cannot_read_another_job_output(self):
        ctx, out, ticket, path, output, record, loader = ticket_case('post')
        ticket['method_output'] = str(out/'mock_batch'/'slots'/'whole_milp__method'/'worker')
        _replace_mock(path, ticket)
        _replace_mock(path.parent/'slot_claim.json', {'ticket_sha256': common.sha(path), 'slot_id': path.parent.name})
        with patch.object(worker, '_load', side_effect=loader), self.assertRaises(ValueError):
            worker.validate_ticket(ctx, path, 'manual-token', output, now=101)

    def test_monitor_wait_without_ready_expires_without_production(self):
        ctx, out = te.case(); clock = te.Clock()
        ticket = {'ticket_claim_path': str(out/'worker_started.json'), 'worker_token': 'token',
                  'absolute_deadline_monotonic_s': 0.03}
        with self.assertRaises(TimeoutError):
            worker.wait_monitor_ready(ctx, ticket, clock=clock, sleep=clock.sleep, pid=10)
        self.assertGreaterEqual(clock.value, 0.03)

    def test_monitor_ready_identity_mismatch_is_rejected(self):
        ctx, out = te.case(); clock = te.Clock()
        ticket = {'ticket_claim_path': str(out/'worker_started.json'), 'worker_token': 'token',
                  'absolute_deadline_monotonic_s': 1}
        common.save(out/'monitor_ready.json', {'worker_token': 'foreign', 'plan_sha256': ctx['plan_sha256'], 'pid': 10})
        with self.assertRaises(ValueError):
            worker.wait_monitor_ready(ctx, ticket, clock=clock, sleep=clock.sleep, pid=10)


class PostTests(unittest.TestCase):
    def test_fake_full_SAFE_post_is_accepted_without_new_method_result(self):
        ctx, out, ticket, value, raw = post_case(); clock = te.Clock(); calls = []
        with patch.object(worker.time, 'monotonic', side_effect=clock):
            result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, raw['evaluation'], clock, calls=calls))
        self.assertEqual(result['post_state'], 'SAFE', result)
        self.assertTrue(result['cleanup_verified']); self.assertFalse(result['new_method_result_accepted'])
        self.assertEqual(len(calls), 1); self.assertEqual(calls[0][3].start, 0)

    def test_late_SAFE_post_remains_unresolved(self):
        ctx, out, ticket, value, raw = post_case(); clock = te.Clock()
        with patch.object(worker.time, 'monotonic', side_effect=clock):
            result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, raw['evaluation'], clock, returned_at=61))
        self.assertEqual(result['post_state'], 'UNRESOLVED')
        self.assertFalse(result['within_absolute_deadline'])

    def test_partial_wrong_identity_or_untimely_SAFE_is_not_accepted(self):
        for kind in ('partial', 'identity', 'untimely'):
            with self.subTest(kind=kind):
                ctx, out, ticket, value, raw = post_case(); clock = te.Clock()
                ev = deepcopy(raw['evaluation'])
                if kind == 'partial': next(iter(ev['scenes'].values()))['complete'] = False
                if kind == 'identity': ev['evidence_identity']['input_sha256'] = 'wrong'
                if kind == 'untimely': ev['completed_at_elapsed_s'] = 60
                with patch.object(worker.time, 'monotonic', side_effect=clock):
                    result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, ev, clock))
                self.assertEqual(result['post_state'], 'ERROR', result)
                self.assertTrue(result['errors'])

    def test_missing_method_SAFE_or_wrong_job_rejected_before_evaluation(self):
        for kind in ('missing_safe', 'wrong_job'):
            with self.subTest(kind=kind):
                ctx, out, ticket, value, raw = post_case(); clock = te.Clock(); calls = []
                p = Path(ticket['method_output'])/'worker_result.json'; saved = common.read(p)
                if kind == 'missing_safe': saved['safe_witness_preserved'] = False
                else: saved['method_id'] = 'sa101'
                _replace_mock(p, saved)
                with patch.object(worker.time, 'monotonic', side_effect=clock):
                    result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, raw['evaluation'], clock, calls=calls))
                self.assertEqual(result['post_state'], 'ERROR'); self.assertEqual(calls, [])

    def test_timely_strict_violation_survives_late_return(self):
        ctx, out, ticket, value, raw = post_case(); clock = te.Clock()
        ev = deepcopy(raw['evaluation']); ev.update(state='THERMAL_VIOLATION', rankable_energy=False,
            weighted_energy_J=None, safe_upper_bound_J=None,
            violations=[{'scene_id': 'C1', 'node': 'CPU1', 'time_s': '1/10',
                         'temperature_degC': ['81', '81'], 'limit_degC': '80', 'formed_at_elapsed_s': 10}])
        with patch.object(worker.time, 'monotonic', side_effect=clock):
            result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, ev, clock, returned_at=61))
        self.assertEqual(result['post_state'], 'THERMAL_VIOLATION', result)
        self.assertEqual(len(result['timely_violations_preserved']), 1)
        self.assertFalse(result['within_absolute_deadline'])

    def test_late_or_wrong_identity_violation_does_not_become_timely_evidence(self):
        for kind in ('late', 'identity', 'outside_window'):
            with self.subTest(kind=kind):
                ctx, out, ticket, value, raw = post_case(); clock = te.Clock()
                ev = deepcopy(raw['evaluation']); ev.update(state='THERMAL_VIOLATION', rankable_energy=False,
                    violations=[{'scene_id': 'C1', 'node': 'CPU1', 'time_s': '1/10',
                                 'temperature_degC': ['81', '81'], 'limit_degC': '80', 'formed_at_elapsed_s': 10}])
                if kind == 'late': ev['violations'][0]['formed_at_elapsed_s'] = 60
                if kind == 'identity': ev['evidence_identity']['input_sha256'] = 'wrong'
                if kind == 'outside_window': ev['violations'][0]['time_s'] = '1'
                with patch.object(worker.time, 'monotonic', side_effect=clock):
                    result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, ev, clock, returned_at=61))
                self.assertEqual(result['post_state'], 'UNRESOLVED', result)
                self.assertFalse(result['timely_violations_preserved'])

    def test_expired_post_and_evaluator_fault_preserve_terminal_state(self):
        for kind in ('expired', 'fault'):
            with self.subTest(kind=kind):
                ctx, out, ticket, value, raw = post_case(); clock = te.Clock(); calls = []
                if kind == 'expired': clock.value = 60
                error = ArithmeticError('manual numeric fault') if kind == 'fault' else None
                with patch.object(worker.time, 'monotonic', side_effect=clock):
                    result = worker.run_post(ctx, ticket, out/'post', bindings=post_bindings(value, raw['evaluation'], clock, calls=calls, error=error))
                self.assertEqual(result['post_state'], 'UNRESOLVED' if kind == 'expired' else 'ERROR', result)
                self.assertEqual(len(calls), 0 if kind == 'expired' else 1)
