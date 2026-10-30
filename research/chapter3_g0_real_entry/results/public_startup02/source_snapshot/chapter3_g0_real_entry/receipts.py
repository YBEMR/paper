"""Permit-gated G0 receipt profile for real wiring and simulation.

The shared validators remain in chapter3_g0.receipts. This module adds an
explicit provenance profile; it never relabels raw PARTIAL receipts, changes
their hashes/timestamps, evaluates temperature, or creates real permission.
"""
from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import sys

from ..chapter3_g0.receipts import (
    Archive as ManualArchive, ReceiptBridge as ManualReceiptBridge,
    EvidenceConflict, DEFAULT_ACCURACY, canonical_hash, model_digest)
from .gating import require_permit, require_simulation_dependencies


def receipt_source_identity():
    """Exact source set used by original PARTIAL, including control policy."""
    root = Path(__file__).resolve().parents[1]
    folder = root / 'chapter3_experiments'
    paths = [folder / 'scene_adapter.py', folder / 'schedules.py',
             folder / 'thermal.py', folder / 'start_domain.py',
             root / 'v1_evaluator' / 'interval.py', folder / 'control_policy.py']
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _legacy(name):
    """Load definitions only after a real permit; no work at module import."""
    folder = Path(__file__).resolve().parents[1] / 'chapter3_experiments'
    inserted = str(folder) not in sys.path
    if inserted:
        sys.path.insert(0, str(folder))
    try:
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != (folder / (name+'.py')).resolve():
            raise ImportError('wrong original receipt module: '+name)
        return module
    finally:
        if inserted:
            sys.path.remove(str(folder))


def production_dependencies(permit):
    """Lazy original function binding. Current gating cannot grant REAL."""
    if require_permit(permit) != 'REAL':
        raise PermissionError('REAL_RECEIPT_BINDING_REQUIRES_APPROVED_REAL_PERMIT')
    adapter, schedules = _legacy('scene_adapter'), _legacy('schedules')
    return {'evidence_kind':'REAL', 'validate_schedule':schedules.validate_schedule,
        'evaluate_partial_scene':adapter.evaluate_partial_scene,
        'aggregate_partial_scene_receipts':adapter.aggregate_partial_scene_receipts,
        'source_identity':receipt_source_identity}


def bind_model_view(raw, model_instance, candidate, budget, source_hashes, *,
                    permit, accuracy=None, scope=None, origin=None):
    """Separate outer provenance, preserving every original receipt field."""
    kind = require_permit(permit)
    if 'g0_context' in raw:
        raise EvidenceConflict('model-view envelope is already bound')
    if raw.get('evidence_kind') not in (None, kind):
        raise EvidenceConflict('model-view raw provenance differs from wiring profile')
    if source_hashes != receipt_source_identity():
        raise EvidenceConflict('model-view source set is not the original PARTIAL source set')
    origin = kind+'_CURRENT_CALL' if origin is None else origin
    if not isinstance(origin, str) or not origin.startswith(kind+'_'):
        raise EvidenceConflict('model-view origin differs from wiring profile')
    requested = dict(DEFAULT_ACCURACY)
    if accuracy is not None:
        requested.update(deepcopy(accuracy))
    out = deepcopy(raw)
    out['g0_context'] = {
        'protocol':'g0-model-view-envelope-v1', 'evidence_kind':kind,
        'root_identity':budget.root_identity,
        'input_sha256':model_digest(model_instance),
        'candidate_sha256':model_digest(candidate),
        'accuracy_sha256':canonical_hash(requested),
        'source_sha256':deepcopy(source_hashes), 'raw_sha256':canonical_hash(raw),
        'scope':budget.capture_scope() if scope is None else deepcopy(scope),
        'origin':origin}
    return out


class RealArchive(ManualArchive):
    """Shared complete-U validator under an explicitly gated wiring profile.

    The class name describes the target interface. Current instances can only
    carry SIMULATION evidence, because the gate cannot create REAL permits.
    """
    def __init__(self, config, instance, budget, source_hashes, *, permit, accuracy=None):
        kind = require_permit(permit)
        if source_hashes != receipt_source_identity():
            raise EvidenceConflict('archive source set must include original control policy source')
        self.permit = permit
        self._initialize(config,instance,budget,source_hashes,accuracy=accuracy,
                         evidence_kind=kind)

    def commit(self,candidate,aggregate,*,source,scope=None):
        accepted=super().commit(candidate,aggregate,source=source,scope=scope)
        writer=getattr(self,'_checkpoint_writer',None)
        if accepted and writer is not None:
            writer(self.generations[-1])
        return accepted


class RealReceiptBridge(ManualReceiptBridge):
    def __init__(self, config, instance, budget, archive, dependencies=None, *,
                 permit, accuracy=None, source_hashes=None):
        kind = require_simulation_dependencies(permit,dependencies)
        if archive.permit is not permit:
            raise EvidenceConflict('bridge and archive must use the same wiring permit')
        deps = production_dependencies(permit) if dependencies is None else dict(dependencies)
        if deps.get('evidence_kind') != kind:
            raise EvidenceConflict('dependency profile differs from wiring permit')
        expected_sources = receipt_source_identity()
        provider = deps.get('source_identity')
        supplied = source_hashes if source_hashes is not None else provider() if callable(provider) else provider
        if supplied != expected_sources:
            raise EvidenceConflict('bridge source identity is missing or changed')
        self.permit = permit
        self._initialize(config,instance,budget,archive,deps,accuracy=accuracy,
            source_hashes=supplied,evidence_kind=kind,origin_prefix=kind+'_',
            require_raw_view_kind=False)

    def bind_model_view(self, model_instance, candidate, raw, *, scope=None):
        return bind_model_view(raw,model_instance,candidate,self.budget,self.archive.sources,
            permit=self.permit,accuracy=self.accuracy,scope=scope)
