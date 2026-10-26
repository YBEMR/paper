"""Method-identity and process regressions for a mock-only fallback protocol.

Static input expansion and hand-authored mock workers are allowed; no real
constructor, scheduler, thermal propagator, MILP or MATLAB is invoked here.
"""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from .protocol import PROTOCOL_ID, METHODS, SLOTS, BUDGETS, SUPERVISION
from .input_contract import prepare_inputs
from e1_objective.execution_io import (
    REPO, DEFAULT_GATE, protocol_slots, protocol_limits, protocol_methods,
    sha, file_sha, runtime_paths, validate_gate, save, read_json, verify_job)
from e1_objective.ledger import Ledger, LedgerError
from e1_objective.controller import (
    run_phase, run_batch, _fresh_packet, recover_plan, recover_post)
from e1_objective.mock_fixtures import make_fixture


def materials(base, mode='MOCK_PROCESS', source_sha='a' * 40):
    manifest = dict(protocol_id=PROTOCOL_ID, source_sha=source_sha, mode=mode,
                    slots=[list(slot) for slot in SLOTS], methods=list(METHODS),
                    budgets=dict(BUDGETS), supervision=dict(SUPERVISION),
                    files={}, inputs={})
    run = base / 'run'
    gate = dict(protocol_id=PROTOCOL_ID, kind=mode,
                authorized=mode == 'REAL_RESEARCH', four_slot_authorized=False,
                stage_authorized=True, methods=list(METHODS),
                mock_only=mode == 'MOCK_PROCESS',
                approval_reference='TEST_ONLY_NOT_REAL_AUTHORIZATION',
                authorization_id='mock-e4-fallback-' + uuid.uuid4().hex,
                source_sha=source_sha, budgets=dict(BUDGETS),
                authority_store=str((base / 'authority').resolve()),
                allowed_run_directory=str(run.resolve()))
    gate['scope_sha256'] = sha(manifest)
    return manifest, gate, run


def mock_materials(base, source_sha='a' * 40):
    manifest, gate, run = materials(base, source_sha=source_sha)
    fixture = make_fixture(h_activity_power_W='4')
    packet = dict(config=dict(accuracy_targets=fixture['accuracy']),
                  instance=fixture['instance'], objective='FULL')
    manifest['mock_input'] = dict(
        input_sha256=sha(packet['instance']),
        config_sha256=sha(packet['config']),
        accuracy_sha256=sha(fixture['accuracy']), objective='FULL',
        packet_sha256={'FULL': sha(packet)})
    manifest['files'] = {rel: file_sha(REPO / rel)
                         for rel in runtime_paths('MOCK_PROCESS')}
    gate['scope_sha256'] = sha(manifest)
    validate_gate(gate, manifest, 'MOCK_PROCESS', run)
    ledger = Ledger(gate['authority_store'], gate, run, kind='MOCK_PROCESS')
    ledger.claim_batch(dict(manifest_sha256=sha(manifest)))
    return packet, manifest, gate, run, ledger


# Public fixture entry for the common protected precheck. It is not a test case
# and is never a real-backend authorization.
testmock_materials = mock_materials


def context(packet, policy):
    return dict(input_sha256=sha(packet['instance']),
                config_sha256=sha(packet['config']),
                accuracy_sha256=sha(packet['config']['accuracy_targets']),
                objective=packet['objective'], packet_sha256=sha(packet),
                method_policy=policy)


def static_real_job(base, ordinal):
    """An in-memory job contract, never persisted or launched as real work."""
    manifest, gate, run = materials(base, 'REAL_RESEARCH')
    packets = prepare_inputs()
    manifest['inputs'] = {
        pid: dict(input_sha256=sha(packet['instance']),
                  config_sha256=sha(packet['config']))
        for pid, packet in packets.items()}
    gate['scope_sha256'] = sha(manifest)
    problem, objective = SLOTS[ordinal - 1]
    packet = deepcopy(packets[problem])
    policy = METHODS[ordinal - 1]
    claim = dict(phase='PLAN', ordinal=ordinal, root_origin=1, limit_s=300,
                 source_sha=manifest['source_sha'], kind='REAL_RESEARCH',
                 run_dir=str(run), job_context=context(packet, policy))
    job = dict(mode='REAL_RESEARCH', run_dir=str(run),
               scope_sha256=sha(manifest), phase='PLAN', ordinal=ordinal,
               root_origin=1, limit_s=300, claim=claim, packet=packet,
               method_policy=policy)
    return manifest, gate, run, job


def mock_plan(base, ordinal=1, behavior='normal', prior=0, grace=5):
    packet, manifest, gate, run, ledger = mock_materials(base)
    # Slot2 has a preceding completed no-candidate plan in this synthetic
    # ledger; no worker or physical evidence is fabricated for that record.
    if ordinal == 2:
        ledger.claim_plan(1, time.monotonic(), context(packet, METHODS[0]))
        ledger.finish_plan(1, sha(dict(state='MOCK_NO_SAFE')), selected_token=None)
    start = time.monotonic()
    plan = run_phase(ledger, gate, manifest, run, ordinal, 'PLAN',
                     slot_origin=start, batch_origin=start,
                     packet_loader=lambda: deepcopy(packet),
                     mock_behavior=behavior, mock_prior_elapsed_s=prior,
                     grace_s=grace)
    return packet, manifest, gate, run, ledger, start, plan


class DeadlineFallbackProtocolTests(unittest.TestCase):
    def test_fixed_two_methods_share_one_physical_slot_identity(self):
        self.assertEqual(PROTOCOL_ID, 'E4_DEADLINE_FALLBACK_V1')
        self.assertEqual(list(METHODS), ['ORIGINAL_HEFT', 'DEADLINE_FALLBACK'])
        self.assertEqual(list(SLOTS), [('requests_2__R1', 'FULL')] * 2)
        self.assertEqual(protocol_slots({'protocol_id': PROTOCOL_ID}),
                         [list(slot) for slot in SLOTS])
        self.assertEqual(protocol_methods({'protocol_id': PROTOCOL_ID}),
                         list(METHODS))
        limits = protocol_limits({'protocol_id': PROTOCOL_ID})
        self.assertEqual(limits['budgets'], BUDGETS)
        self.assertEqual(limits['supervision'], SUPERVISION)
        self.assertEqual(2 * 300 + 2 * 60, 720)
        self.assertEqual(SUPERVISION['batch_wall_s'], 960)

    def test_method_list_is_not_a_mutable_global_policy(self):
        methods = protocol_methods({'protocol_id': PROTOCOL_ID})
        methods.reverse()
        self.assertEqual(protocol_methods({'protocol_id': PROTOCOL_ID}),
                         ['ORIGINAL_HEFT', 'DEADLINE_FALLBACK'])

    def test_previous_protocols_do_not_acquire_custom_methods(self):
        for protocol, count, wall in [
                ('E1_OBJECTIVE_V1', 4, 1800), ('E2_RESOURCES_V1', 4, 1800),
                ('E3_DEPLOYMENT_V1', 2, 960), ('E4_DEADLINE_V1', 3, 1380),
                ('E4_REQUESTS_V1', 2, 960)]:
            with self.subTest(protocol=protocol):
                self.assertIsNone(protocol_methods({'protocol_id': protocol}))
                limits = protocol_limits({'protocol_id': protocol})
                self.assertEqual(limits['budgets']['plan_calls'], count)
                self.assertEqual(limits['supervision']['batch_wall_s'], wall)

    def test_gate_binds_fixed_method_order_even_when_rehashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for edit in ('missing_manifest', 'missing_gate', 'reverse_manifest',
                         'reverse_gate', 'both_reverse', 'extra_method'):
                manifest, gate, run = materials(Path(tmp), 'REAL_RESEARCH')
                if edit == 'missing_manifest': del manifest['methods']
                elif edit == 'missing_gate': del gate['methods']
                elif edit == 'reverse_manifest': manifest['methods'].reverse()
                elif edit == 'reverse_gate': gate['methods'].reverse()
                elif edit == 'both_reverse':
                    manifest['methods'].reverse(); gate['methods'].reverse()
                else: manifest['methods'].append('CUSTOM')
                gate['scope_sha256'] = sha(manifest)
                with self.subTest(edit=edit), self.assertRaises(ValueError):
                    validate_gate(gate, manifest, 'REAL_RESEARCH', run)

    def test_new_gate_requires_explicit_protocol_stage_and_fixed_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, gate, run = materials(Path(tmp), 'REAL_RESEARCH')
            self.assertEqual(validate_gate(gate, manifest, 'REAL_RESEARCH', run), gate)
            for field in ('protocol_id', 'stage_authorized'):
                changed = deepcopy(gate); del changed[field]
                with self.subTest(field=field), self.assertRaises(ValueError):
                    validate_gate(changed, manifest, 'REAL_RESEARCH', run)
            changed = deepcopy(gate); changed['budgets']['plan_calls'] = 4
            with self.assertRaises(ValueError):
                validate_gate(changed, manifest, 'REAL_RESEARCH', run)

    def test_old_authorization_and_default_gate_rejected_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); manifest, gate, run = materials(base, 'REAL_RESEARCH')
            save(base / 'manifest.json', manifest)
            old = deepcopy(gate); old['protocol_id'] = 'E4_REQUESTS_V1'
            old.pop('methods'); save(base / 'old.json', old)
            for authorization in (base / 'old.json', DEFAULT_GATE):
                with self.subTest(auth=str(authorization)), \
                     patch('e1_objective.controller.Ledger', side_effect=AssertionError('no claim')), \
                     self.assertRaises(ValueError):
                    run_batch(base / 'manifest.json', authorization, run)
            self.assertFalse(run.exists())

    def test_same_packet_for_both_methods_has_no_method_scientific_field(self):
        packets = prepare_inputs()
        self.assertEqual(set(packets), {'requests_2__R1'})
        first = _fresh_packet(*SLOTS[0]); second = _fresh_packet(*SLOTS[1])
        self.assertEqual(first, second)
        self.assertEqual(first, packets['requests_2__R1'])
        self.assertEqual(set(first), {'config', 'instance', 'objective'})
        self.assertNotIn('method_policy', first['instance'])

    def test_static_real_job_requires_method_in_job_and_plan_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ordinal in (1, 2):
                manifest, gate, run, job = static_real_job(Path(tmp), ordinal)
                output = run / ('slot_' + str(ordinal)) / 'plan'
                self.assertTrue(verify_job(job, gate, manifest, output))
                for target in ('job', 'claim', 'both', 'missing_job', 'missing_claim'):
                    wrong = deepcopy(job); other = METHODS[ordinal % 2]
                    if target in ('job', 'both'): wrong['method_policy'] = other
                    if target in ('claim', 'both'):
                        wrong['claim']['job_context']['method_policy'] = other
                    if target == 'missing_job': del wrong['method_policy']
                    if target == 'missing_claim':
                        del wrong['claim']['job_context']['method_policy']
                    with self.subTest(slot=ordinal, target=target), self.assertRaises(ValueError):
                        verify_job(wrong, gate, manifest, output)

    def test_method_cannot_be_smuggled_into_scientific_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, gate, run, job = static_real_job(Path(tmp), 1)
            job['packet']['method_policy'] = METHODS[0]
            with self.assertRaises(ValueError):
                verify_job(job, gate, manifest, run / 'slot_1' / 'plan')

    def test_ledger_plan_claim_requires_correct_fixed_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet, manifest, gate, run, ledger = mock_materials(Path(tmp))
            good = context(packet, METHODS[0])
            wrong = deepcopy(good); wrong['method_policy'] = METHODS[1]
            absent = deepcopy(good); absent.pop('method_policy')
            for ctx in (wrong, absent):
                with self.assertRaises(LedgerError):
                    ledger.claim_plan(1, time.monotonic(), ctx)
            self.assertFalse((ledger.root / '01_plan_claim.json').exists())
            ledger.claim_plan(1, time.monotonic(), good)
            with self.assertRaises(LedgerError):
                ledger.claim_plan(1, time.monotonic(), good)

    def test_third_slot_and_unknown_method_refused_without_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet, manifest, gate, run, ledger = mock_materials(Path(tmp))
            ctx = context(packet, METHODS[0])
            for ordinal in (0, 3, True):
                with self.subTest(slot=ordinal), self.assertRaises(LedgerError):
                    ledger.claim_plan(ordinal, time.monotonic(), ctx)
                with self.subTest(phase=ordinal), self.assertRaises(ValueError):
                    run_phase(ledger, gate, manifest, run, ordinal, 'PLAN',
                              slot_origin=time.monotonic(), batch_origin=time.monotonic(),
                              packet_loader=lambda: deepcopy(packet))
            self.assertFalse((ledger.root / '03_plan_claim.json').exists())
            self.assertFalse(run.exists())

    def test_legacy_manifest_rejects_custom_method_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            from e4_requests.test_protocol import materials as old_materials
            manifest, gate, run = old_materials(Path(tmp), 'REAL_RESEARCH')
            for target in ('manifest', 'gate', 'both'):
                m, g = deepcopy(manifest), deepcopy(gate)
                if target in ('manifest', 'both'): m['methods'] = list(METHODS)
                if target in ('gate', 'both'): g['methods'] = list(METHODS)
                g['scope_sha256'] = sha(m)
                with self.subTest(target=target), self.assertRaises(ValueError):
                    validate_gate(g, m, 'REAL_RESEARCH', run)

    def test_old_job_rejects_method_policy_without_changing_packet(self):
        from e4_requests.test_protocol import materials as old_materials
        with tempfile.TemporaryDirectory() as tmp:
            manifest, gate, run = old_materials(Path(tmp), 'REAL_RESEARCH')
            packets = prepare_inputs(); packet = packets['requests_2__R1']
            manifest['inputs'] = {'requests_2__R1': dict(
                input_sha256=sha(packet['instance']), config_sha256=sha(packet['config']))}
            gate['scope_sha256'] = sha(manifest)
            ctx = context(packet, METHODS[1])
            claim = dict(phase='PLAN', ordinal=2, root_origin=1, limit_s=300,
                         source_sha=manifest['source_sha'], kind='REAL_RESEARCH',
                         run_dir=str(run), job_context=ctx)
            job = dict(mode='REAL_RESEARCH', run_dir=str(run), scope_sha256=sha(manifest),
                       phase='PLAN', ordinal=2, root_origin=1, limit_s=300,
                       claim=claim, packet=packet, method_policy=METHODS[1])
            with self.assertRaises(ValueError):
                verify_job(job, gate, manifest, run / 'slot_2' / 'plan')

    def test_mock_both_method_policies_bind_plan_post_and_return(self):
        with tempfile.TemporaryDirectory(prefix='e4_fallback_mock_') as tmp:
            packet, manifest, gate, run, ledger = mock_materials(Path(tmp))
            batch = time.monotonic()
            for ordinal, policy in enumerate(METHODS, 1):
                start = time.monotonic()
                plan = run_phase(ledger, gate, manifest, run, ordinal, 'PLAN',
                                 slot_origin=start, batch_origin=batch,
                                 packet_loader=lambda: deepcopy(packet))
                self.assertEqual(plan['result']['state'], 'SAFE', plan)
                self.assertEqual(plan['result']['method_policy'], policy)
                self.assertEqual(plan['job']['method_policy'], policy)
                self.assertEqual(plan['job']['claim']['job_context']['method_policy'], policy)
                checkpoint = read_json(Path(plan['output']) / 'checkpoint.json')
                self.assertEqual(checkpoint['method_policy'], policy)
                post = run_phase(ledger, gate, manifest, run, ordinal, 'POST',
                                 slot_origin=start, batch_origin=batch, packet=packet,
                                 planning_result=plan['result'])
                self.assertEqual(post['result']['state'], 'POST_SAFE', post)
                self.assertEqual(post['result']['method_policy'], policy)
                self.assertEqual(post['job']['claim']['job_context']['method_policy'], policy)
                self.assertEqual(post['result']['candidate_sha256'],
                                 plan['result']['selected_candidate_sha256'])
                self.assertEqual(plan['job']['batch_deadline'], batch + 960)
                for phase in (plan, post):
                    returned = read_json(Path(phase['output']) / 'worker_return.json')
                    self.assertEqual(returned['method_policy'], policy)
                    self.assertEqual(returned['result']['method_policy'], policy)
                    self.assertFalse(returned['guard']['real_backend_entered'])
                    self.assertEqual(returned['guard']['science_modules_loaded'], [])
                token = post['job']['selected_token']
                with self.assertRaises(LedgerError):
                    ledger.claim_post(ordinal, time.monotonic(), token,
                                      method_policy=policy)
            self.assertEqual(len(list(ledger.root.glob('*_claim.json'))), 4)

    def test_post_claim_rejects_missing_or_wrong_policy_without_consuming(self):
        with tempfile.TemporaryDirectory(prefix='e4_post_policy_') as tmp:
            packet, manifest, gate, run, ledger, start, plan = mock_plan(Path(tmp))
            self.assertEqual(plan['result']['state'], 'SAFE', plan)
            from e1_objective.execution_io import selected_token
            token = selected_token(packet, plan['result'])
            for policy in (None, METHODS[1]):
                with self.subTest(policy=policy), self.assertRaises(LedgerError):
                    ledger.claim_post(1, time.monotonic(), token,
                                      method_policy=policy)
            self.assertFalse((ledger.root / '01_post_claim.json').exists())
            claim = ledger.claim_post(1, time.monotonic(), token,
                                      method_policy=METHODS[0])
            self.assertEqual(claim['job_context']['method_policy'], METHODS[0])

    def test_post_job_cannot_relabel_frozen_plan_result(self):
        with tempfile.TemporaryDirectory(prefix='e4_post_result_') as tmp:
            packet, manifest, gate, run, ledger, start, plan = mock_plan(Path(tmp))
            post = run_phase(ledger, gate, manifest, run, 1, 'POST',
                             slot_origin=start, batch_origin=start, packet=packet,
                             planning_result=plan['result'])
            self.assertEqual(post['result']['state'], 'POST_SAFE', post)
            wrong = deepcopy(post['job'])
            wrong['planning_result']['method_policy'] = METHODS[1]
            wrong['claim']['job_context']['plan_result_sha256'] = sha(wrong['planning_result'])
            with self.assertRaises(ValueError):
                verify_job(wrong, gate, manifest, Path(post['output']))

    def test_corrupt_final_return_method_is_not_accepted(self):
        with tempfile.TemporaryDirectory(prefix='e4_return_policy_') as tmp:
            packet, manifest, gate, run, ledger, start, plan = mock_plan(Path(tmp))
            path = Path(plan['output']) / 'worker_return.json'
            returned = read_json(path)
            returned['result']['method_policy'] = METHODS[1]
            save(path, returned)
            with self.assertRaises(ValueError):
                recover_plan(packet, plan['job'], Path(plan['output']), plan['process'])

    def test_corrupt_post_return_method_is_not_accepted(self):
        with tempfile.TemporaryDirectory(prefix='e4_post_return_') as tmp:
            packet, manifest, gate, run, ledger, start, plan = mock_plan(Path(tmp))
            post = run_phase(ledger, gate, manifest, run, 1, 'POST',
                             slot_origin=start, batch_origin=start, packet=packet,
                             planning_result=plan['result'])
            path = Path(post['output']) / 'worker_return.json'
            returned = read_json(path); returned['method_policy'] = METHODS[1]
            save(path, returned)
            with self.assertRaises(ValueError):
                recover_post(post['job'], Path(post['output']), post['process'])

    def test_checkpoint_only_recovery_keeps_fixed_fallback_identity(self):
        with tempfile.TemporaryDirectory(prefix='e4_fallback_crash_') as tmp:
            packet, manifest, gate, run, ledger, start, plan = mock_plan(
                Path(tmp), ordinal=2, behavior='crash_after_checkpoint')
            self.assertEqual(plan['process']['classification'], 'NONZERO_EXIT_FAULT', plan)
            self.assertEqual(plan['result']['state'], 'SAFE', plan)
            self.assertEqual(plan['result']['method_policy'], METHODS[1])
            self.assertEqual(plan['result']['recovery'], 'PREEXISTING_CHECKPOINT_ONLY')
            self.assertTrue(plan['result']['stop_required'])
            self.assertTrue((ledger.root / 'stop.json').exists())

    def test_controller_stops_at_two_methods_without_real_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); manifest, gate, run = materials(base, 'REAL_RESEARCH')
            save(base / 'manifest.json', manifest); save(base / 'gate.json', gate)
            class NoResearchLedger:
                def __init__(self, *args, **kwargs): run.mkdir()
                def claim_batch(self, *args): pass
                def stop(self, *args): pass
            with patch('e1_objective.controller.Ledger', NoResearchLedger), \
                 patch('e1_objective.controller.run_phase', return_value=dict(
                     result=dict(state='UNRESOLVED', stop_required=False))) as phase:
                run_batch(base / 'manifest.json', base / 'gate.json', run)
            self.assertEqual([call.args[4] for call in phase.call_args_list], [1, 2])
            self.assertEqual(read_json(run / 'batch_summary.json')['planned_slots'], 2)

    def test_parent_preparation_cannot_reset_original_300_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet, manifest, gate, run, ledger = mock_materials(Path(tmp))
            start = time.monotonic()
            def delayed():
                time.sleep(.2)
                return deepcopy(packet)
            plan = run_phase(ledger, gate, manifest, run, 1, 'PLAN',
                             slot_origin=start, batch_origin=start, packet_loader=delayed,
                             mock_prior_elapsed_s=299.9)
            self.assertEqual(plan['result']['state'], 'UNRESOLVED', plan)
            self.assertFalse(plan['result']['stop_required'])
            self.assertEqual(plan['process']['classification'], 'PREPARATION_CUTOFF')
            self.assertFalse((ledger.root / '01_plan_launch.json').exists())


if __name__ == '__main__':
    unittest.main()
