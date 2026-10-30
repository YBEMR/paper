"""Explicit fake physical ledger under the original PARTIAL interfaces.

Only exact bookkeeping arithmetic is replayed. The supplied constant 10 K
temperature correction is handmade; it is NOT a thermal trajectory/integral.
Original evaluate_partial_scene and aggregation are exercised with this fake
physical dependency. Their output protocol, hashes and timestamps are intact.
"""
from contextlib import contextmanager
from copy import deepcopy
from fractions import Fraction as F
from decimal import Decimal, localcontext
import importlib
from pathlib import Path
import sys
from unittest.mock import patch

from ..contract import canonical_hash, derive_deployment, cross_projection, make_scene_view
from ..receipts import Archive, ReceiptBridge, model_digest


LEGACY = str(Path(__file__).resolve().parents[2] / 'chapter3_experiments')
if LEGACY not in sys.path:
    sys.path.insert(0, LEGACY)
import scene_adapter as sa
import schedules


class ManualLedger:
    def __init__(self, config, instance, clock):
        if instance.get('status') != 'MANUAL_FIXTURE_NOT_SCIENTIFIC_INPUT':
            raise ValueError('handmade fixtures only')
        self.config, self.instance, self.clock = config, instance, clock
        self.calls = []
        self.status_by_scene = {}
        self.scene_delay_s = 0
        self.aggregate_delay_before_s = 0
        self.aggregate_delay_after_s = 0
        self.raw_responses = []

    def sources(self):
        sources = sa._source_identity()
        source = Path(sa.__file__).with_name('control_policy.py')
        import hashlib
        sources[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
        return sources

    def piecewise(self, platform, entry, maximum, segments, window_ms, accuracy, budget, *, scene_id):
        self.calls.append({'kind':'FAKE_PHYSICAL_LEDGER', 'scene':scene_id,
                           'segments':deepcopy(segments), 'thermal_propagation':False})
        budget.check()
        self.clock.advance(self.scene_delay_s)
        terms = dict(baseline=F(0), activity=F(0), external=F(0), temperature_correction=F(0))
        for segment in segments:
            dt = F(segment['duration_ms'])/1000
            terms['baseline'] += sum(map(F,segment['baseline_by_power_group_W'].values()))*dt
            terms['activity'] += sum(map(F,segment['activity_by_node_W'].values()))*dt
            terms['external'] += F(segment['external_common_power_W'])*dt
            terms['temperature_correction'] += sum(map(F,segment['local_leakage_slope_W_per_K'].values()))*10*dt
        energy = sum(terms.values())
        with localcontext() as context:
            context.prec = 80
            decimal_energy = str(Decimal(energy.numerator)/Decimal(energy.denominator))
        if F(decimal_energy) != energy:
            raise ValueError('manual ledger needs exact terminating decimal energy')
        state = self.status_by_scene.get(scene_id,'SAFE')
        violations = ([dict(scene_id=scene_id,node='CPU1',kind='HANDMADE_VIOLATION_WITNESS')]
                      if state=='THERMAL_VIOLATION' else [])
        complete = state=='SAFE'
        return dict(state=state,reason='MANUAL_PHYSICAL_REPLAY_ONLY',scene_id=scene_id,
            complete=complete,rankable_energy=complete,energy_accuracy_met=complete,
            covered_until_s=str(F(window_ms)/1000 if complete else 0),
            energy_J=[decimal_energy,decimal_energy] if complete else None,
            violations=violations,completed_at_elapsed_s=budget.elapsed,
            evidence_kind='MANUAL_FIXTURE',manual_terms_J={k:str(v) for k,v in terms.items()},
            temperature_trajectory_computed=False)

    @contextmanager
    def patched(self):
        with patch.object(sa,'evaluate_piecewise',self.piecewise):
            yield self

    def partial(self, *args, **kwargs):
        self.calls.append({'kind':'ORIGINAL_PARTIAL_INTERFACE'})
        raw=sa.evaluate_partial_scene(*args,**kwargs)
        self.raw_responses.append(deepcopy(raw))
        return raw

    def aggregate(self, *args, **kwargs):
        self.calls.append({'kind':'ORIGINAL_AGGREGATE_INTERFACE'})
        self.clock.advance(self.aggregate_delay_before_s)
        raw=sa.aggregate_partial_scene_receipts(*args,**kwargs)
        self.raw_responses.append(deepcopy(raw))
        self.clock.advance(self.aggregate_delay_after_s)
        return raw

    def deps(self):
        return dict(evidence_kind='MANUAL_FIXTURE',validate_schedule=schedules.validate_schedule,
            evaluate_partial_scene=self.partial, aggregate_partial_scene_receipts=self.aggregate,
            source_identity=self.sources)

    def setup(self, budget):
        archive=Archive(self.config,self.instance,budget,self.sources(),manual=True)
        bridge=ReceiptBridge(self.config,self.instance,budget,archive,self.deps(),manual=True)
        return archive,bridge

    def view(self, model_instance, candidate, budget):
        checked=schedules.validate_schedule(model_instance,candidate)
        if checked['state']!='SCHEDULE_VALID_THERMAL_UNCHECKED':
            raise ValueError('invalid manual model-view candidate')
        scene=model_instance['scenarios'][0]
        result=self.piecewise(model_instance['platform'],scene['entry']['temperature_degC'],
            scene['maximum_temperature_degC'],checked['scenes'][scene['id']]['segments'],
            model_instance['window_ms'],{},budget,scene_id=scene['id'])
        raw=dict(state=result['state'],rankable_energy=result['rankable_energy'],
            weighted_energy_J=result['energy_J'], scenes={scene['id']:result},
            violations=result['violations'],completed_at_elapsed_s=budget.elapsed,
            evidence_identity={'input_sha256':model_digest(model_instance),
                               'candidate_sha256':model_digest(candidate)},
            evidence_kind='MANUAL_FIXTURE')
        # ReceiptBridge adds only a G0 envelope; original fields remain intact.
        from ..receipts import bind_manual_model_view
        return bind_manual_model_view(raw, model_instance, candidate, budget,
                                      self.sources())
