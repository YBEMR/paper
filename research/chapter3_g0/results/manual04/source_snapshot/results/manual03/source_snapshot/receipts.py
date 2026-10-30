"""G0 receipt bridge and atomic complete-SAFE archive.

Real planners/evaluators are disabled in this isolation stage. Manual backends
must identify themselves and construct their own original-format receipts;
this module never changes a raw receipt's protocol or completion timestamp.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math

PARTIAL_PROTOCOL = "partial-shared-deployment-unweighted-scene-v1"
EVIDENCE_KIND = "MANUAL_FIXTURE"
REAL_EXECUTION_ENABLED = False
DEFAULT_ACCURACY = {"temperature_enclosure_width_K": "0.001",
                    "energy_absolute_error_J": "0.000001",
                    "energy_relative_error": "0.000001"}


class RealExecutionDisabled(RuntimeError):
    pass


class EvidenceConflict(ValueError):
    pass


def canonical_hash(value):
    def encode(item):
        if isinstance(item, Fraction):
            return {"__exact_fraction__": str(item)}
        raise TypeError("non-JSON identity value: " + type(item).__name__)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=encode, allow_nan=False).encode("utf-8")).hexdigest()


def model_digest(value):
    # Exactly the original milp._digest convention, not PARTIAL's Fraction tag.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def hash_payload(receipt):
    return canonical_hash({k: v for k, v in receipt.items() if k != "receipt_sha256"})


def bind_manual_model_view(raw, model_instance, candidate, budget, source_hashes,
                           accuracy=None, *, scope=None, origin="MANUAL_CURRENT_CALL"):
    """Attach a separate G0 context without changing raw physical evidence.

    This helper is only for an explicit current-call manual backend. It does
    not run an evaluator, refresh a completion time, or authorize cached data.
    """
    if "g0_context" in raw:
        raise EvidenceConflict("model-view envelope is already bound")
    if not isinstance(origin, str) or not origin.startswith("MANUAL"):
        raise ValueError("manual model-view provenance is required")
    requested = dict(DEFAULT_ACCURACY)
    if accuracy is not None:
        requested.update(accuracy)
    out = deepcopy(raw)
    out["g0_context"] = {
        "protocol": "g0-model-view-envelope-v1", "evidence_kind": EVIDENCE_KIND,
        "root_identity": budget.root_identity,
        "input_sha256": model_digest(model_instance),
        "candidate_sha256": model_digest(candidate),
        "accuracy_sha256": canonical_hash(requested),
        "source_sha256": deepcopy(source_hashes), "raw_sha256": canonical_hash(raw),
        "scope": budget.capture_scope() if scope is None else deepcopy(scope),
        "origin": origin}
    return out


def _q(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError("receipt physical values must be exact")
    return Fraction(value)


def energy_interval(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("complete energy interval required")
    lo, hi = map(_q, value)
    if lo < 0 or lo > hi:
        raise ValueError("invalid energy interval")
    return lo, hi


def _formed(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _scenes(instance):
    scenes = {s["id"]: s for s in instance["scenarios"]}
    if not scenes or len(scenes) != len(instance["scenarios"]):
        raise ValueError("empty or duplicate scenario ids")
    return scenes


def _project(candidate, scene_id):
    return {"scenes": {scene_id: deepcopy(candidate["scenes"][scene_id])}}


def _deployment(config, instance, candidate):
    from .contract import derive_deployment
    return derive_deployment(config, instance, candidate)


def _cross(instance, d0):
    from .contract import cross_projection
    return cross_projection(instance, d0)


def production_dependencies():
    """Reserved lazy wiring; this stage cannot enable a real evaluator."""
    if not REAL_EXECUTION_ENABLED:
        raise RealExecutionDisabled("G0 real evaluation/HEFT/solver entry is not authorized")
    # There is deliberately no enabling argument, environment variable or CLI.
    # A later approved real-entry change must be separately reviewed.
    from scene_adapter import (evaluate_partial_scene, aggregate_partial_scene_receipts,
                               _source_identity)
    from schedules import validate_schedule
    return {"validate_schedule": validate_schedule,
            "evaluate_partial_scene": evaluate_partial_scene,
            "aggregate_partial_scene_receipts": aggregate_partial_scene_receipts,
            "source_identity": _source_identity, "evidence_kind": "REAL"}


class Archive:
    """Append complete generations atomically; best and snapshots are copies."""
    def __init__(self, config, instance, budget, source_hashes, *, accuracy=None, manual=True):
        if not manual or REAL_EXECUTION_ENABLED:
            raise RealExecutionDisabled("this archive is limited to manual isolation evidence")
        if not isinstance(source_hashes, dict) or not source_hashes:
            raise ValueError("explicit backend source identity required")
        self.config, self.instance = deepcopy(config), deepcopy(instance)
        self.budget, self.sources = budget, deepcopy(source_hashes)
        self.accuracy = dict(DEFAULT_ACCURACY)
        if accuracy is not None:
            self.accuracy.update(deepcopy(accuracy))
        self._best, self._frozen, self._fixed_deployment = None, {}, None
        self.generations, self.events, self.violations = [], [], []
        self.first_safe_elapsed_s = None
        self.first_legal_elapsed_s = None

    @property
    def best(self):
        return deepcopy(self._best)

    @property
    def records(self):
        return deepcopy(self.generations)

    def snapshot(self):
        return self.best

    def expected_identity(self, candidate, d0, *, scene_id=None, local_deployment=None):
        cross = _cross(self.instance, d0)
        rules = self.instance["execution_rules"]
        policy = rules.get("idle_policy", "legacy_idle_holds_last_opp")
        out = {"protocol": PARTIAL_PROTOCOL,
            "full_input_sha256": canonical_hash(self.instance),
            "shared_stage_ids": sorted(cross),
            "shared_deployment_sha256": canonical_hash(cross),
            "platform_sha256": canonical_hash(self.instance["platform"]),
            "execution_rules_sha256": canonical_hash(rules),
            "control_policy": policy,
            "accuracy_sha256": canonical_hash(self.accuracy),
            "source_sha256": deepcopy(self.sources), "budget": self.budget.root_identity}
        if scene_id is not None:
            scene = _scenes(self.instance)[scene_id]
            out.update(scenario_id=scene_id, scenario_sha256=canonical_hash(scene),
                       entry_sha256=canonical_hash(scene["entry"]))
        if candidate is not None:
            out["candidate_sha256"] = canonical_hash(candidate)
        if local_deployment is not None:
            out["local_deployment_sha256"] = canonical_hash(local_deployment)
        return out

    def _check_common(self, receipt):
        if receipt.get("protocol") != PARTIAL_PROTOCOL:
            raise EvidenceConflict("raw receipt is not the original PARTIAL protocol")
        # Manual dependency provenance belongs to the G0 envelope, not to
        # invented fields in an already hashed legacy PARTIAL receipt.
        if receipt.get("evidence_kind") not in (None, EVIDENCE_KIND):
            raise EvidenceConflict("conflicting raw receipt provenance")
        if receipt.get("receipt_sha256") != hash_payload(receipt):
            raise EvidenceConflict("receipt payload identity mismatch")

    def validate_scene(self, scene_id, candidate, receipt, d0):
        self._check_common(receipt)
        used = {i["shared_stage_id"] for i in _scenes(self.instance)[scene_id]["stage_instances"]}
        local = {key: d0[key] for key in sorted(used)}
        expected = self.expected_identity(candidate, d0, scene_id=scene_id, local_deployment=local)
        if (receipt.get("identity") != expected or receipt.get("scenario_id") != scene_id
                or receipt.get("local_deployment") != local
                or receipt.get("shared_deployment") != _cross(self.instance, d0)
                or receipt.get("shared_stage_ids") != sorted(_cross(self.instance, d0))
                or receipt.get("unweighted") is not True):
            raise EvidenceConflict("original-input scene identity mismatch")
        if receipt.get("state") != "SAFE":
            return False
        result = receipt.get("result") or {}
        interval = energy_interval(receipt.get("energy_J"))
        formation = receipt.get("completed_at_elapsed_s")
        inner = result.get("completed_at_elapsed_s")
        if (receipt.get("rankable_energy") is not True or receipt.get("violations")
                or result.get("state") != "SAFE" or result.get("complete") is not True
                or result.get("rankable_energy") is not True
                or result.get("energy_accuracy_met") is not True
                or result.get("scene_id") != scene_id
                or _q(result.get("covered_until_s", "-1")) != _q(self.instance["window_ms"])/1000
                or result.get("energy_J") != receipt.get("energy_J")
                or _q(receipt.get("safe_upper_bound_J", "-1")) != interval[1]
                or not all(_formed(t) and t < self.budget.seconds for t in (formation, inner))
                or inner > formation or result.get("violations")):
            raise EvidenceConflict("incomplete or inconsistent scene SAFE")
        return True

    def validate_aggregate(self, candidate, receipt):
        self._check_common(receipt)
        d0 = _deployment(self.config, self.instance, candidate)
        expected = self.expected_identity(candidate, d0, local_deployment=d0)
        scenes = _scenes(self.instance)
        if (receipt.get("identity") != expected
                or receipt.get("safe_candidate") != candidate
                or receipt.get("shared_deployment") != _cross(self.instance, d0)
                or receipt.get("merged_deployment") != d0
                or receipt.get("shared_stage_ids") != sorted(_cross(self.instance, d0))
                or set(receipt.get("scenes", {})) != set(scenes)
                or receipt.get("receipt_errors") or receipt.get("violations")
                or receipt.get("rankable_energy") is not True
                or receipt.get("legality", {}).get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED"):
            raise EvidenceConflict("complete aggregate identity/scope mismatch")
        lo, hi = Fraction(0), Fraction(0)
        weights = [_q(s["weight"]) for s in scenes.values()]
        if any(w < 0 for w in weights) or sum(weights) != 1:
            raise EvidenceConflict("invalid original scenario weights")
        formation = receipt.get("completed_at_elapsed_s")
        if not _formed(formation):
            raise EvidenceConflict("aggregate formation timestamp missing")
        for scene_id, scene in scenes.items():
            local = receipt["scenes"][scene_id]
            if not self.validate_scene(scene_id, _project(candidate, scene_id), local, d0):
                raise EvidenceConflict("even zero-weight scene must be complete SAFE")
            if local["completed_at_elapsed_s"] > formation:
                raise EvidenceConflict("aggregate predates a scene receipt")
            a, b = energy_interval(local["energy_J"])
            weight = _q(scene["weight"])
            lo, hi = lo + a*weight, hi + b*weight
        total = energy_interval(receipt.get("weighted_energy_J"))
        # Directed-Decimal output can outwardly widen exact rational sums.
        if total[0] > lo or total[1] < hi or _q(receipt["safe_upper_bound_J"]) != total[1]:
            raise EvidenceConflict("weighted energy is missing, double-counted or inconsistent")
        allowed = max(_q(self.accuracy["energy_absolute_error_J"]),
                      _q(self.accuracy["energy_relative_error"])*total[0])
        if total[1]-total[0] > allowed:
            raise EvidenceConflict("weighted energy accuracy target is not met")
        if self._fixed_deployment is not None and d0 != self._fixed_deployment:
            raise EvidenceConflict("deployment changed after S0 was frozen")
        return d0, total

    def commit(self, candidate, aggregate, *, source, scope=None):
        event = {"source": str(source), "received_at_s": self.budget.elapsed,
                 "aggregate": deepcopy(aggregate), "accepted": False}
        self.events.append(event)
        if aggregate.get("state") != "SAFE":
            # Retain only identity-matched scene witnesses as accepted
            # violation evidence. The raw diagnostic envelope is always kept.
            if aggregate.get("violations"):
                d0 = _deployment(self.config, self.instance, candidate)
                for sid, raw in aggregate.get("scenes", {}).items():
                    if sid in _scenes(self.instance) and raw.get("violations"):
                        self.validate_scene(sid, _project(candidate, sid), raw, d0)
                        self.violations.extend(deepcopy(raw["violations"]))
            event["reason"] = aggregate.get("state", "UNRESOLVED")
            return False
        d0, interval = self.validate_aggregate(candidate, aggregate)
        formed = aggregate["completed_at_elapsed_s"]
        if not self.budget.accept_formed(formed, scope=scope):
            event["reason"] = "LATE_OR_SEALED_COMPLETE_AGGREGATE"
            return False
        record = {"candidate": deepcopy(candidate), "aggregate": deepcopy(aggregate),
            "d0": deepcopy(d0), "weighted_energy_J": deepcopy(aggregate["weighted_energy_J"]),
            "U_J": str(interval[1]), "completed_at_elapsed_s": formed, "source": str(source),
            "input_sha256": canonical_hash(self.instance), "config_sha256": canonical_hash(self.config),
            "source_sha256": deepcopy(self.sources), "scope": self.budget.capture_scope() if scope is None else deepcopy(scope),
            "evidence_kind": EVIDENCE_KIND,
            "strict_improvement": self._best is not None and interval[1] < energy_interval(self._best["weighted_energy_J"])[0]}
        record["generation_sha256"] = canonical_hash(record)
        self.generations.append(deepcopy(record))
        event["accepted"] = True
        event["generation_sha256"] = record["generation_sha256"]
        if self.first_safe_elapsed_s is None:
            self.first_safe_elapsed_s = formed
        if self._best is None or interval[1] < _q(self._best["U_J"]):
            self._best = deepcopy(record)
            event["best_updated"] = True
        else:
            event["best_updated"] = False
        return True

    def freeze(self, label):
        if label in self._frozen:
            raise ValueError("snapshot label already sealed")
        snapshot = self.best
        self._frozen[label] = deepcopy(snapshot)
        if label == "S0" and snapshot is not None:
            self._fixed_deployment = deepcopy(snapshot["d0"])
        return deepcopy(snapshot)

    def frozen(self, label):
        return deepcopy(self._frozen[label])


class ReceiptBridge:
    """The same assess callable is used by the same-call HEFT kernel.

    Dependency injection is explicit; no default fake or default real backend
    is selected. Manual fixtures and raw receipts stay visibly distinguished.
    """
    def __init__(self, config, instance, budget, archive, dependencies, *, accuracy=None,
                 manual=True, source_hashes=None):
        if not manual or REAL_EXECUTION_ENABLED:
            raise RealExecutionDisabled("real G0 bridge entry is closed")
        if not isinstance(dependencies, dict) or dependencies.get("evidence_kind") != EVIDENCE_KIND:
            raise ValueError("explicit MANUAL_FIXTURE dependency set required")
        self.config, self.instance = deepcopy(config), deepcopy(instance)
        self.budget, self.archive, self.dependencies = budget, archive, dict(dependencies)
        self.accuracy = deepcopy(archive.accuracy)
        if accuracy is not None:
            requested = dict(DEFAULT_ACCURACY); requested.update(accuracy)
            if requested != self.accuracy:
                raise ValueError("bridge/archive accuracy mismatch")
        actual_sources = source_hashes
        if actual_sources is None:
            provider = self.dependencies.get("source_identity")
            actual_sources = provider() if callable(provider) else provider
        if actual_sources != archive.sources:
            raise ValueError("bridge/archive backend sources mismatch")
        if archive.instance != instance or archive.config != config or archive.budget is not budget:
            raise ValueError("bridge/archive input or root mismatch")
        for name in ("validate_schedule", "evaluate_partial_scene", "aggregate_partial_scene_receipts"):
            if not callable(self.dependencies.get(name)):
                raise ValueError("missing dependency: " + name)

    def expected_identity(self, candidate, d0, *, scene_id=None, local_deployment=None):
        return self.archive.expected_identity(candidate, d0, scene_id=scene_id,
                                              local_deployment=local_deployment)

    @staticmethod
    def hash_payload(receipt):
        return hash_payload(receipt)

    def _check_legality(self, instance, candidate):
        self.budget.check()
        checked = self.dependencies["validate_schedule"](instance, candidate)
        if checked.get("state") == "SCHEDULE_VALID_THERMAL_UNCHECKED":
            if self.archive.first_legal_elapsed_s is None:
                self.archive.first_legal_elapsed_s = self.budget.elapsed
        return checked

    def assess(self, candidate, source="initialization", *, scope=None):
        scope = self.budget.capture_scope() if scope is None else scope
        checked = self._check_legality(self.instance, candidate)
        if checked.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
            out = {"state": "INVALID_SCHEDULE", "reason": checked.get("reason"),
                   "rankable_energy": False, "weighted_energy_J": None,
                   "legality": deepcopy(checked), "evidence_kind": EVIDENCE_KIND}
            self.archive.events.append({"source": source, "aggregate": deepcopy(out), "accepted": False})
            return out
        d0 = _deployment(self.config, self.instance, candidate)
        if self.archive._fixed_deployment is not None and d0 != self.archive._fixed_deployment:
            raise EvidenceConflict("initialization tried to change frozen D0")
        receipts, candidates = {}, {}
        for sid in sorted(_scenes(self.instance)):
            self.budget.check()
            candidates[sid] = _project(candidate, sid)
            raw = self.dependencies["evaluate_partial_scene"](self.instance, sid,
                _cross(self.instance, d0), candidates[sid], self.accuracy, self.budget)
            receipts[sid] = deepcopy(raw)
            if raw.get("violations"):
                # Identity-only transfer precedes an outer expiry check.
                self.archive.validate_scene(sid, candidates[sid], raw, d0)
                self.archive.violations.extend(deepcopy(raw["violations"]))
            if raw.get("state") != "SAFE":
                # Legacy evaluators can return an unresolved shell after a
                # cooperative cutoff; do not misclassify that as bad identity.
                self.budget.check()
            self.archive.validate_scene(sid, candidates[sid], raw, d0)
            self.budget.check()
        aggregate = self.dependencies["aggregate_partial_scene_receipts"](self.instance,
            _cross(self.instance, d0), receipts, candidates, self.accuracy, self.budget)
        # No deadline check before evidence transfer: complete timely output
        # returned late can be retained, while a late aggregate is rejected.
        self.archive.commit(candidate, aggregate, source=source, scope=scope)
        return deepcopy(aggregate)

    def validate_model_view(self, model_instance, candidate, receipt, *, scope=None):
        raw = {key: deepcopy(value) for key, value in receipt.items() if key != "g0_context"}
        context = receipt.get("g0_context") or {}
        expected_scope = self.budget.capture_scope() if scope is None else scope
        if isinstance(expected_scope, str):
            expected_scope = self.budget.scope_snapshot(expected_scope)
        if (context.get("protocol") != "g0-model-view-envelope-v1"
                or context.get("evidence_kind") != EVIDENCE_KIND
                or context.get("root_identity") != self.budget.root_identity
                or context.get("input_sha256") != model_digest(model_instance)
                or context.get("candidate_sha256") != model_digest(candidate)
                or context.get("accuracy_sha256") != canonical_hash(self.accuracy)
                or context.get("source_sha256") != self.archive.sources
                or context.get("raw_sha256") != canonical_hash(raw)
                or context.get("scope") != expected_scope
                or not str(context.get("origin", "")).startswith("MANUAL")):
            raise EvidenceConflict("model-view G0 source/root/accuracy/scope binding mismatch")
        expected = {"input_sha256": model_digest(model_instance),
                    "candidate_sha256": model_digest(candidate)}
        if receipt.get("evidence_identity") != expected:
            raise EvidenceConflict("model-view evidence identity mismatch")
        if receipt.get("evidence_kind") != EVIDENCE_KIND:
            raise EvidenceConflict("model-view manual source must be explicit")
        self.archive.violations.extend(deepcopy(receipt.get("violations", [])))
        if receipt.get("state") != "SAFE":
            return deepcopy(receipt)
        if (receipt.get("rankable_energy") is not True or receipt.get("violations")
                or not self.budget.accept_formed(receipt.get("completed_at_elapsed_s"), scope=scope)):
            raise EvidenceConflict("model-view SAFE is incomplete, late or sealed")
        total = energy_interval(receipt.get("weighted_energy_J"))
        scenes = _scenes(model_instance)
        if (set(receipt.get("scenes", {})) != set(scenes)
                or set(candidate.get("scenes", {})) != set(scenes)):
            raise EvidenceConflict("model-view SAFE has missing scenes")
        lower, upper = Fraction(0), Fraction(0)
        for sid, physical in receipt["scenes"].items():
            if (physical.get("state") != "SAFE" or physical.get("complete") is not True
                    or physical.get("rankable_energy") is not True
                    or physical.get("energy_accuracy_met") is not True
                    or physical.get("violations")
                    or not _formed(physical.get("completed_at_elapsed_s"))
                    or physical["completed_at_elapsed_s"] > receipt["completed_at_elapsed_s"]
                    or _q(physical.get("covered_until_s", "-1")) != _q(model_instance["window_ms"])/1000):
                raise EvidenceConflict("model-view prefix is not complete SAFE")
            interval = energy_interval(physical.get("energy_J"))
            weight = _q(scenes[sid]["weight"])
            if weight < 0:
                raise EvidenceConflict("model-view weight is negative")
            lower += interval[0]*weight
            upper += interval[1]*weight
        if (sum(_q(scene["weight"]) for scene in scenes.values()) != 1
                or total[0] > lower or total[1] < upper):
            raise EvidenceConflict("model-view weighted energy ledger mismatch")
        return deepcopy(receipt)

    def publish_local(self, scene_id, candidate, view_evaluation, condition, *, model_instance,
                      source="local", scope=None):
        from .local_domain import assert_member
        from .contract import make_scene_view
        scope = self.budget.capture_scope() if scope is None else scope
        current = self.archive.best
        if current is None or self.archive._fixed_deployment is None:
            raise EvidenceConflict("local search requires frozen complete S0")
        expected_view = make_scene_view(self.instance, scene_id)
        for shared, modes in expected_view["stage_modes"].items():
            expected_view["stage_modes"][shared] = [mode for mode in modes
                if mode["unit_id"] == self.archive._fixed_deployment[shared]]
        if canonical_hash(expected_view) != canonical_hash(model_instance):
            raise EvidenceConflict("local model view changes scientific input or D0")
        view = self.validate_model_view(model_instance, candidate, view_evaluation, scope=scope)
        if view.get("state") != "SAFE":
            return view
        # Membership is against the immutable phase anchor, not current latest.
        assert_member(self.config, self.instance, candidate, condition)
        merged = deepcopy(current["candidate"])
        merged["scenes"][scene_id] = deepcopy(candidate["scenes"][scene_id])
        checked = self._check_legality(self.instance, merged)
        if checked.get("state") != "SCHEDULE_VALID_THERMAL_UNCHECKED":
            raise EvidenceConflict("SAFE model candidate conflicts with full-input legality")
        d0 = _deployment(self.config, self.instance, merged)
        local = _project(merged, scene_id)
        self.budget.check()
        raw = self.dependencies["evaluate_partial_scene"](self.instance, scene_id,
            _cross(self.instance, d0), local, self.accuracy, self.budget)
        if raw.get("violations"):
            self.archive.validate_scene(scene_id, local, raw, d0)
            self.archive.violations.extend(deepcopy(raw["violations"]))
        if raw.get("state") != "SAFE":
            self.budget.check()
        if not self.archive.validate_scene(scene_id, local, raw, d0):
            if raw.get("state") in ("THERMAL_VIOLATION", "INVALID_SCHEDULE"):
                raise EvidenceConflict("SAFE model-view conflicts with original scene")
            return deepcopy(raw)
        left, right = energy_interval(view["weighted_energy_J"]), energy_interval(raw["energy_J"])
        if max(left[0], right[0]) > min(left[1], right[1]):
            raise EvidenceConflict("model-view/original-input energy intervals are disjoint")
        receipts = deepcopy(current["aggregate"]["scenes"])
        receipts[scene_id] = deepcopy(raw)
        candidates = {sid: _project(merged, sid) for sid in sorted(_scenes(self.instance))}
        self.budget.check()
        aggregate = self.dependencies["aggregate_partial_scene_receipts"](self.instance,
            _cross(self.instance, d0), receipts, candidates, self.accuracy, self.budget)
        self.archive.commit(merged, aggregate, source=source, scope=scope)
        return deepcopy(aggregate)
