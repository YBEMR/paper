"""A17/A18/A20/A21/A25/A28: actual PARTIAL bridge, fake physical ledger."""
from copy import deepcopy
from fractions import Fraction as F

from ..budget import G0Budget
from ..contract import derive_deployment, make_scene_view
from ..local_domain import make_condition
from ..receipts import (PARTIAL_PROTOCOL, hash_payload, canonical_hash,
                        bind_manual_model_view)
from .fixtures import bundle, FakeClock
from .manual_backend import ManualLedger


def _seal(raw):
    raw["receipt_sha256"] = hash_payload(raw)
    return raw


def _view(instance, d0, sid="X"):
    out = make_scene_view(instance, sid)
    for shared, modes in out["stage_modes"].items():
        out["stage_modes"][shared] = [mode for mode in modes if mode["unit_id"] == d0[shared]]
    return out


def A17(ctx):
    config, instance, candidate = bundle()
    clock = FakeClock(); budget = G0Budget(100, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        raw = bridge.assess(candidate, "MANUAL_INITIALIZATION")
        ctx.check(raw["state"] == "SAFE" and raw["protocol"] == PARTIAL_PROTOCOL,
                  "original scene evaluator and aggregator generated actual PARTIAL identities")
        ctx.check(raw == ledger.raw_responses[-1] and raw == archive.best["aggregate"],
                  "raw protocol/hash/timestamp preserved without relabeling")
        ctx.check(archive.best["evidence_kind"] == "MANUAL_FIXTURE" and
                  "evidence_kind" not in raw,
                  "fake physical provenance is an outer envelope, not altered PARTIAL evidence")
        for field in ("protocol", "source", "budget", "candidate"):
            broken = deepcopy(raw)
            if field == "protocol":
                broken["protocol"] = "raw-heft-safe"
            elif field == "source":
                broken["identity"]["source_sha256"]["schedules.py"] = "WRONG_SOURCE"
            elif field == "budget":
                broken["identity"]["budget"]["token"] = "OTHER_INVOCATION"
            else:
                broken["identity"]["candidate_sha256"] = "OTHER_CANDIDATE"
            _seal(broken)
            ctx.rejects(lambda broken=broken: archive.commit(candidate, broken, source="SPOOF"),
                        "raw " + field + " drift rejected")
        spoof = {"protocol": PARTIAL_PROTOCOL, "state":"SAFE", "rankable_energy":True,
                 "weighted_energy_J":["0","0"]}
        _seal(spoof)
        ctx.rejects(lambda: archive.commit(candidate, spoof, source="RAW_HEFT_RELABEL"),
                    "changing a raw HEFT protocol does not create a PARTIAL witness")
        ctx.check(archive.best["candidate"] == candidate, "bad evidence did not replace prior SAFE")


def A18(ctx):
    config, instance, candidate = bundle()
    clock = FakeClock(); budget = G0Budget(100, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        bridge.assess(candidate, "FIRST")
        low = deepcopy(candidate)
        for rows in low["scenes"].values():
            for row in rows:
                row["opp"] = "L"
        bridge.assess(low, "LOW_TRIAL")
        accepted = archive.best
        latest = deepcopy(candidate)
        for rows in latest["scenes"].values():
            rows[0]["unit"] = "GPU0"
        ledger.status_by_scene["X"] = "THERMAL_VIOLATION"
        failed = bridge.assess(latest, "LATEST_FAILED_MAPPING")
        ctx.check(failed["state"] == "THERMAL_VIOLATION", "last trial can differ and be unsafe")
        frozen = archive.freeze("S0")
        ctx.check(frozen["candidate"] == accepted["candidate"] and
                  frozen["d0"] == derive_deployment(config, instance, accepted["candidate"]),
                  "D0 comes from accepted best S0, not the latest trial's mapping")
        ctx.check(frozen["d0"] != derive_deployment(config, instance, latest),
                  "unsafe latest mapping is not accidentally frozen")
        frozen["candidate"]["scenes"]["X"][0]["start_ms"] = "999"
        ctx.check(archive.frozen("S0")["candidate"] == accepted["candidate"],
                  "external mutation cannot change frozen generation")
        ledger.status_by_scene.clear()
        ctx.rejects(lambda: bridge.assess(latest, "AFTER_FREEZE_REMAP"),
                    "device change after S0 freeze rejected")
        ctx.check(archive.best["generation_sha256"] == accepted["generation_sha256"],
                  "failed/rejected trials retain previous complete SAFE")


def A20(ctx):
    config, instance, candidate = bundle()
    clock = FakeClock(); budget = G0Budget(100, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        bridge.assess(candidate, "INITIAL")
        anchor = archive.freeze("S0")
        sid = "X"; local = {"scenes": {sid:deepcopy(candidate["scenes"][sid])}}
        condition = make_condition(config, instance, candidate, anchor["d0"], sid,
                                   [local["scenes"][sid][0]["stage_id"]], phase=1)
        model_instance = _view(instance, anchor["d0"], sid)
        view = ledger.view(model_instance, local, budget)
        for key in ("root_identity", "source_sha256", "accuracy_sha256"):
            broken = deepcopy(view)
            broken["g0_context"][key] = {"wrong":True} if key != "accuracy_sha256" else "WRONG"
            ctx.rejects(lambda broken=broken: bridge.validate_model_view(model_instance, local, broken),
                        "model view rejects " + key + " drift")
        raw = {key:deepcopy(value) for key,value in view.items() if key != "g0_context"}
        raw["weighted_energy_J"] = [str(F(raw["weighted_energy_J"][0])+1)]*2
        raw["scenes"][sid]["energy_J"] = deepcopy(raw["weighted_energy_J"])
        wrong_energy = bind_manual_model_view(raw, model_instance, local, budget, ledger.sources())
        before = archive.best
        ctx.rejects(lambda: bridge.publish_local(sid, local, wrong_energy, condition,
                        model_instance=model_instance, source="DISJOINT_LEDGER"),
                    "disjoint original/model-view intervals stop publication")
        ctx.check(archive.best == before, "energy conflict preserves original complete anchor")
        changed_physics = deepcopy(model_instance); changed_physics["window_ms"] = "999"
        ctx.rejects(lambda: bridge.publish_local(sid, local, view, condition,
                        model_instance=changed_physics),
                    "arbitrary caller model view cannot change W or physics")


def A21(ctx):
    config, instance, candidate = bundle(scene_ids=("X","Y","Z"))
    for scene, weight in zip(instance["scenarios"], ("1/4","3/4","0")):
        scene["weight"] = weight
    clock = FakeClock(); budget = G0Budget(100, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        raw = bridge.assess(candidate, "NONUNIFORM_AND_ZERO")
        expected = sum(F(scene["weight"])*F(raw["scenes"][scene["id"]]["energy_J"][0])
                       for scene in instance["scenarios"])
        ctx.check(raw["state"] == "SAFE" and F(raw["weighted_energy_J"][0]) == expected,
                  "nonuniform weights applied exactly once including complete zero-weight scene")
        for kind in ("missing_zero_scene", "unsafe_zero_scene", "double_weight", "prefix"):
            broken = deepcopy(raw)
            if kind == "missing_zero_scene":
                del broken["scenes"]["Z"]
            elif kind == "unsafe_zero_scene":
                broken["scenes"]["Z"]["state"] = "UNRESOLVED"
                _seal(broken["scenes"]["Z"])
            elif kind == "double_weight":
                broken["weighted_energy_J"] = [str(expected*2)]*2
                broken["safe_upper_bound_J"] = str(expected*2)
            else:
                broken["scenes"]["X"]["result"]["covered_until_s"] = "0"
                _seal(broken["scenes"]["X"])
            _seal(broken)
            ctx.rejects(lambda broken=broken: archive.commit(candidate, broken, source=kind),
                        kind + " cannot create a complete weighted U")
        ctx.check(len(archive.records) == 1, "invalid aggregate variants never enter SAFE archive")


def A25(ctx):
    config, instance, candidate = bundle()
    clock = FakeClock(); budget = G0Budget(10, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    ledger.scene_delay_s = 0.1; ledger.aggregate_delay_after_s = 6
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        with budget.scope("phase1",5,kind="phase") as token:
            raw = bridge.assess(candidate, "TIMELY_FORMED_LATE_RETURN", scope=token)
            ctx.check(raw["completed_at_elapsed_s"] < 5 < budget.elapsed and archive.best is not None,
                      "timely full aggregate returned late is retained before scope seal")
            old = archive.best
        n = len(archive.records)
        ctx.check(not archive.commit(candidate, raw, source="SEALED_CALLBACK", scope=token) and
                  len(archive.records) == n and archive.best == old,
                  "late callback cannot mutate a sealed phase generation")
    clock = FakeClock(); budget = G0Budget(10, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        with budget.scope("phase1",5,kind="phase") as token:
            bridge.assess(candidate, "PRIOR_COMPLETE", scope=token)
            prior = archive.best
            ledger.scene_delay_s = 0.1; ledger.aggregate_delay_before_s = 6
            late = bridge.assess(candidate, "TIMELY_SCENES_LATE_AGGREGATE", scope=token)
            ctx.check(late["state"] == "UNRESOLVED" and archive.best == prior,
                      "timely individual scenes do not authorize late complete aggregation")
            ctx.check(len(archive.records) == 1, "late aggregation did not add a new U")


def A28(ctx):
    config, instance, candidate = bundle()
    clock = FakeClock(); budget = G0Budget(100, clock=clock)
    ledger = ManualLedger(config, instance, clock)
    with ledger.patched():
        archive, bridge = ledger.setup(budget)
        bridge.assess(candidate, "INITIAL")
        safe = archive.best
        invalid = deepcopy(candidate); invalid["scenes"]["X"][0]["start_ms"] = "-5"
        count = len(ledger.calls)
        bad = bridge.assess(invalid, "INVALID_TIME")
        ctx.check(bad["state"] == "INVALID_SCHEDULE" and len(ledger.calls) == count,
                  "invalid timing is rejected before physical replay and not a backend failure")
        ledger.status_by_scene["X"] = "THERMAL_VIOLATION"
        hot = bridge.assess(candidate, "HANDMADE_HOT")
        ctx.check(hot["state"] == "THERMAL_VIOLATION" and archive.violations,
                  "real-shaped handmade violation evidence preserved without technical relabeling")
        ledger.status_by_scene["X"] = "UNRESOLVED"
        unknown = bridge.assess(candidate, "HANDMADE_UNRESOLVED")
        ctx.check(unknown["state"] == "UNRESOLVED" and not unknown.get("rankable_energy"),
                  "unresolved scene cannot rank prefix energy")
        ledger.status_by_scene.clear()
        original = bridge.dependencies["evaluate_partial_scene"]
        def broken_backend(*args, **kwargs):
            raise MemoryError("MANUAL_BACKEND_MEMORY_FAILURE")
        bridge.dependencies["evaluate_partial_scene"] = broken_backend
        ctx.rejects(lambda: bridge.assess(candidate, "TECHNICAL_ERROR"),
                    "genuine backend failure propagates for method-level fault classification",
                    exceptions=(MemoryError,))
        bridge.dependencies["evaluate_partial_scene"] = original
        ctx.check(archive.best == safe, "all rejected, unsafe, unresolved and fault outcomes preserve prior SAFE")
