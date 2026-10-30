"""G0 REAL-target receipt wiring tested only with explicit SIMULATION fakes."""
from copy import deepcopy
from fractions import Fraction as F
from types import SimpleNamespace
import unittest

from ...chapter3_g0.budget import G0Budget
from ...chapter3_g0.contract import derive_deployment, make_scene_view
from ...chapter3_g0.local_domain import make_condition
from ...chapter3_g0.receipts import hash_payload, model_digest, Archive as ManualArchive
from ...chapter3_g0.tests.fixtures import bundle, FakeClock
from ...chapter3_g0.tests.manual_backend import ManualLedger, schedules
from ..gating import WiringPermit
from ..receipts import (RealArchive, RealReceiptBridge, receipt_source_identity,
                        bind_model_view, production_dependencies)


def setup_profile(config,instance,clock,*,seconds=300):
    budget=G0Budget(seconds,clock=clock)
    ledger=ManualLedger(config,instance,clock)
    permit=WiringPermit(kind='SIMULATION')
    sources=receipt_source_identity()
    deps=ledger.deps();deps['evidence_kind']='SIMULATION'
    archive=RealArchive(config,instance,budget,sources,permit=permit)
    bridge=RealReceiptBridge(config,instance,budget,archive,deps,permit=permit)
    return budget,ledger,permit,archive,bridge


def model_view(instance,scene_id,d0):
    view=make_scene_view(instance,scene_id)
    for shared,modes in view['stage_modes'].items():
        view['stage_modes'][shared]=[m for m in modes if m['unit_id']==d0[shared]]
    return view


def simulated_view_raw(ledger,view,candidate,budget):
    """Known fake provider; no old MANUAL envelope is rewritten as real."""
    checked=schedules.validate_schedule(view,candidate)
    if checked['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED':
        raise ValueError('invalid handcrafted simulation view')
    scene=view['scenarios'][0];sid=scene['id']
    fake=ledger.piecewise(view['platform'],scene['entry']['temperature_degC'],
        scene['maximum_temperature_degC'],checked['scenes'][sid]['segments'],
        view['window_ms'],{},budget,scene_id=sid)
    return {'state':fake['state'],'rankable_energy':fake['rankable_energy'],
        'problem_id':view['id'],'weighted_energy_J':deepcopy(fake['energy_J']),
        'scenes':{sid:fake},'violations':deepcopy(fake['violations']),
        'completed_at_elapsed_s':budget.elapsed,
        'evidence_identity':{'input_sha256':model_digest(view),
                             'candidate_sha256':model_digest(candidate)}}


class ReceiptProfileTests(unittest.TestCase):
    def test_original_partial_raw_preserved_and_outer_simulation(self):
        config,instance,candidate=bundle()
        clock=FakeClock();budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        with ledger.patched():
            raw=bridge.assess(candidate,'SIMULATION_HEFT_ASSESS')
        self.assertEqual(raw['state'],'SAFE')
        self.assertEqual(raw,ledger.raw_responses[-1])
        self.assertEqual(archive.best['aggregate'],raw)
        self.assertNotIn('evidence_kind',raw)
        self.assertEqual(archive.best['evidence_kind'],'SIMULATION')
        self.assertIs(archive.permit,permit)
        self.assertIs(bridge.archive,archive)
        self.assertIn('control_policy.py',raw['identity']['source_sha256'])
        self.assertTrue(all(not e['thermal_propagation'] for e in ledger.calls
                            if e['kind']=='FAKE_PHYSICAL_LEDGER'))

    def test_real_permission_and_implicit_dependencies_are_closed(self):
        config,instance,_=bundle()
        clock=FakeClock();budget,ledger,permit,archive,_=setup_profile(config,instance,clock)
        with self.assertRaises(PermissionError):
            WiringPermit(kind='REAL')
        with self.assertRaises(PermissionError):
            production_dependencies(permit)
        with self.assertRaises(PermissionError):
            RealArchive(config,instance,budget,ledger.sources(),permit=SimpleNamespace(kind='REAL'))
        with self.assertRaises(PermissionError):
            RealReceiptBridge(config,instance,budget,archive,permit=permit)
        wrong=ledger.deps()  # MANUAL_FIXTURE cannot enter the new SIMULATION profile.
        with self.assertRaises(ValueError):
            RealReceiptBridge(config,instance,budget,archive,wrong,permit=permit)
        self.assertEqual(ledger.calls,[])

    def test_control_policy_source_is_mandatory_and_bound(self):
        config,instance,candidate=bundle()
        clock=FakeClock();budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        bad=receipt_source_identity();bad.pop('control_policy.py')
        with self.assertRaises(ValueError):
            RealArchive(config,instance,budget,bad,permit=permit)
        with ledger.patched():
            raw=bridge.assess(candidate)
        broken=deepcopy(raw)
        broken['identity']['source_sha256']['control_policy.py']='OTHER_SOURCE'
        broken['receipt_sha256']=hash_payload(broken)
        with self.assertRaises(ValueError):
            archive.commit(candidate,broken,source='SIMULATION_BAD_SOURCE')
        self.assertEqual(len(archive.records),1)

    def test_view_envelope_retains_raw_and_rejects_wrong_profile_root(self):
        config,instance,candidate=bundle()
        clock=FakeClock();budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        d0=derive_deployment(config,instance,candidate)
        view=model_view(instance,'X',d0)
        local={'scenes':{'X':deepcopy(candidate['scenes']['X'])}}
        raw=simulated_view_raw(ledger,view,local,budget)
        original=deepcopy(raw)
        envelope=bridge.bind_model_view(view,local,raw)
        self.assertEqual(raw,original)
        self.assertEqual({k:v for k,v in envelope.items() if k!='g0_context'},original)
        self.assertEqual(envelope['g0_context']['evidence_kind'],'SIMULATION')
        self.assertEqual(envelope['completed_at_elapsed_s'],original['completed_at_elapsed_s'])
        self.assertEqual(bridge.validate_model_view(view,local,envelope),envelope)
        for field,value in [('evidence_kind','MANUAL_FIXTURE'),('origin','REAL_CURRENT_CALL')]:
            broken=deepcopy(envelope);broken['g0_context'][field]=value
            with self.assertRaises(ValueError):
                bridge.validate_model_view(view,local,broken)
        broken=deepcopy(envelope)
        broken['g0_context']['root_identity']['token']='OTHER_ROOT'
        with self.assertRaises(ValueError):
            bridge.validate_model_view(view,local,broken)
        bad=deepcopy(raw);bad['evidence_kind']='MANUAL_FIXTURE'
        with self.assertRaises(ValueError):
            bind_model_view(bad,view,local,budget,ledger.sources(),permit=permit)

    def test_matching_local_candidate_aggregates_without_changing_d0(self):
        config,instance,candidate=bundle()
        clock=FakeClock();budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        with ledger.patched():
            bridge.assess(candidate,'SIMULATION_INITIALIZATION')
            s0=archive.freeze('S0');d0=s0['d0']
            opened=[candidate['scenes']['X'][0]['stage_id']]
            condition=make_condition(config,instance,candidate,d0,'X',opened,phase=1)
            local={'scenes':{'X':deepcopy(candidate['scenes']['X'])}}
            local['scenes']['X'][0]['opp']='L'
            view=model_view(instance,'X',d0)
            raw=simulated_view_raw(ledger,view,local,budget)
            envelope=bridge.bind_model_view(view,local,raw)
            aggregate=bridge.publish_local('X',local,envelope,condition,model_instance=view,
                                           source='SIMULATION_LOCAL')
        self.assertEqual(aggregate['state'],'SAFE')
        self.assertEqual(archive.best['d0'],d0)
        self.assertEqual(archive.best['candidate']['scenes']['Y'],candidate['scenes']['Y'])
        self.assertLessEqual(F(archive.best['U_J']),F(s0['U_J']))
        self.assertEqual(archive.best['evidence_kind'],'SIMULATION')
        self.assertNotIn('evidence_kind',aggregate)

    def test_late_or_foreign_view_cannot_replace_existing_safe(self):
        config,instance,candidate=bundle()
        clock=FakeClock();budget,ledger,permit,archive,bridge=setup_profile(config,instance,clock)
        with ledger.patched():
            bridge.assess(candidate);s0=archive.freeze('S0')
        view=model_view(instance,'X',s0['d0'])
        local={'scenes':{'X':deepcopy(candidate['scenes']['X'])}}
        with budget.scope('SIMULATION_SLOT',1,kind='slot') as token:
            raw=simulated_view_raw(ledger,view,local,budget)
            envelope=bridge.bind_model_view(view,local,raw,scope=token)
            clock.advance(1)
            # Timestamp is not refreshed. Once the dispatch is sealed, no
            # callback can create a new generation even if it formed earlier.
        with self.assertRaises(ValueError):
            bridge.validate_model_view(view,local,envelope,scope=token)
        self.assertEqual(archive.best,s0)

    def test_manual_archive_profile_remains_manual_and_real_flag_unchanged(self):
        from ...chapter3_g0 import receipts as old
        config,instance,_=bundle()
        budget=G0Budget(300,clock=FakeClock())
        manual=ManualArchive(config,instance,budget,receipt_source_identity(),manual=True)
        self.assertEqual(manual.evidence_kind,'MANUAL_FIXTURE')
        self.assertFalse(old.REAL_EXECUTION_ENABLED)
        with self.assertRaises(old.RealExecutionDisabled):
            ManualArchive(config,instance,budget,receipt_source_identity(),manual=False)


if __name__=='__main__':
    unittest.main()
