"""Fail-closed signed one-step admission gate. This module executes no task.

Production trust anchors are supplied outside this repository through
AGENT_LOOP_TRUSTED_CONFIG_SHA256. Ed25519 private keys belong only to the
independent reviewer. A GitHub login is descriptive metadata, not authority.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any, Callable
import uuid

try:
    from .git_store import GitLedgerStore, StoreError
except ImportError:
    from git_store import GitLedgerStore, StoreError


class GateDenied(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(raw: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise GateDenied("duplicate JSON key")
            result[key] = value
        return result
    def reject_constant(value):
        raise GateDenied("non-finite JSON number")
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise GateDenied("invalid JSON") from exc
    if not isinstance(result, dict):
        raise GateDenied("JSON object required")
    return result


def signature_message(review: dict) -> bytes:
    """No signer is provided. External reviewers sign these precise bytes."""
    payload = {key: value for key, value in review.items() if key != "signature"}
    mode = payload.get("mode")
    if mode not in ("REAL", "TEST_ONLY"):
        raise GateDenied("invalid signing domain")
    return f"agent-loop:{mode}:v1\0".encode() + canonical_json(payload)


def _require_fields(obj, names, label):
    if not isinstance(obj, dict) or any(name not in obj for name in names):
        raise GateDenied(f"missing {label} field")


def _text(value, label):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise GateDenied(f"invalid {label}")
    return value


def _number(value, label, *, positive=False, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value):
        raise GateDenied(f"explicit numeric {label} required")
    if value < 0 or (positive and value <= 0):
        raise GateDenied(f"invalid {label}")
    return value


def _digest(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise GateDenied(f"invalid {label} SHA256")
    return value


def _time(value, label):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateDenied(f"{label} must be UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateDenied(f"invalid {label}") from exc
    return parsed


def _path(value):
    _text(value, "repository path")
    path = PurePosixPath(value)
    if (path.is_absolute() or str(path) != value or any(p in ("", ".", "..", ".git") for p in path.parts)
            or "\\" in value or ":" in value or "\0" in value):
        raise GateDenied("unsafe repository path")
    return value


def _scope(value):
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value) or len(set(value)) != len(value):
        raise GateDenied("nonempty unique allowed_scope required")
    return [_path(item) for item in value]


def _within(scope, allowed):
    return all(any(item == base or item.startswith(base + "/") for base in allowed) for item in scope)


class Gate:
    """Claim -> issue_permit* -> finish; every mutation uses remote Git CAS.

    A successful claim reserves the complete declared budget permanently.
    A permit charges its full requested budget before returning. No refund,
    retry, execution, auto-resume or reset API exists.
    """

    BUDGET_FIELDS = ("max_calls", "per_call_budget_seconds", "total_budget_seconds", "wall_clock_limit_seconds")
    REVIEW_FIELDS = ("schema_version", "mode", "repository", "config_sha256", "approval_id", "round_id",
                     "subject_commit_sha", "manifest_path", "manifest_sha256", "proposal_sha256",
                     "report_md_sha256", "evidence_class", "decision", "approved_action", "action_kind",
                     "allowed_scope", "max_calls", "per_call_budget_seconds", "total_budget_seconds",
                     "wall_clock_limit_seconds", "expiration", "review_identity", "review_report_path",
                     "review_report_sha256", "signature")

    def __init__(self, repo_path, config_path, *, mode="real", environ=None,
                 now: Callable[[], datetime] | None = None):
        self.repo_path = Path(repo_path).resolve()
        self.config_path = Path(config_path).resolve()
        if not self.repo_path.is_dir() or not self.config_path.is_file():
            raise GateDenied("repository/config unavailable")
        self.mode = {"real": "REAL", "REAL": "REAL", "TEST_ONLY": "TEST_ONLY"}.get(mode)
        if not self.mode:
            raise GateDenied("unknown gate mode")
        self._now = now or (lambda: datetime.now(timezone.utc))
        env = os.environ if environ is None else environ
        self._test_tmp_base = env.get("AGENT_LOOP_TEST_TMP", tempfile.gettempdir())
        self.config_sha256 = _digest(env.get("AGENT_LOOP_TRUSTED_CONFIG_SHA256"), "external config anchor")
        self._config_bytes = self.config_path.read_bytes()
        if sha256(self._config_bytes) != self.config_sha256:
            raise GateDenied("configuration does not match external trust anchor")
        self.config = strict_json(self._config_bytes)
        _require_fields(self.config, ("schema_version", "mode", "enabled", "ALLOW_REAL_EXPERIMENTS",
                                     "repository", "review_source", "limits", "allowed_scope", "test_only"), "config")
        if type(self.config["schema_version"]) is not int or self.config["schema_version"] != 1:
            raise GateDenied("unsupported config schema")
        if self.config["mode"] != self.mode:
            raise GateDenied("mode mismatch")
        if type(self.config["enabled"]) is not bool or type(self.config["ALLOW_REAL_EXPERIMENTS"]) is not bool:
            raise GateDenied("boolean switches required")
        _require_fields(self.config["repository"], ("remote_url", "ledger_ref"), "repository config")
        _require_fields(self.config["review_source"], ("source_id", "key_id", "public_key_ed25519_base64", "github_login"), "review source")
        self.remote_url = _text(self.config["repository"]["remote_url"], "remote URL")
        self.ref = _text(self.config["repository"]["ledger_ref"], "ledger ref")
        if self.mode == "TEST_ONLY":
            self._validate_test_environment()
        elif self.config["test_only"] is not None:
            raise GateDenied("REAL gate rejects test configuration")
        elif self.ref != "refs/heads/codex/agent-loop-ledger":
            raise GateDenied("REAL gate requires the fixed production ledger ref")
        self.store = GitLedgerStore(self.remote_url, self.ref,
                                    temporary_parent=self.test_root if self.mode == "TEST_ONLY" else None)

    def close(self):
        self.store.close()

    def _validate_test_environment(self):
        spec = self.config["test_only"]
        _require_fields(spec, ("namespace", "temporary_root"), "TEST_ONLY")
        namespace = _text(spec["namespace"], "TEST_ONLY namespace")
        if not re.fullmatch(r"TEST_ONLY-[A-Za-z0-9_-]+", namespace):
            raise GateDenied("test namespace required")
        root = Path(spec["temporary_root"]).resolve()
        temp_root = Path(self._test_tmp_base).resolve()
        if not root.is_dir() or not temp_root.is_dir():
            raise GateDenied("TEST_ONLY root unavailable")
        if root == temp_root or not root.is_relative_to(temp_root):
            raise GateDenied("TEST_ONLY must use a dedicated temporary directory under AGENT_LOOP_TEST_TMP/system temp")
        remote = Path(self.remote_url).resolve()
        if not remote.is_dir():
            raise GateDenied("TEST_ONLY requires a local bare remote")
        if not all(p.is_relative_to(root) for p in (self.repo_path, self.config_path, remote)):
            raise GateDenied("TEST_ONLY repository/config/remote must be inside its temporary root")
        if self.ref != "refs/heads/TEST_ONLY/" + namespace:
            raise GateDenied("TEST_ONLY ledger namespace mismatch")
        source = self.config["review_source"]
        if not all(isinstance(source[k], str) and source[k].startswith("TEST_ONLY-") for k in ("source_id", "key_id")):
            raise GateDenied("TEST_ONLY signer namespace required")
        self.test_root = root

    def _enabled(self):
        if self.config_path.read_bytes() != self._config_bytes:
            raise GateDenied("configuration changed after initialization")
        if not self.config["enabled"]:
            raise GateDenied("gate disabled")
        if self.mode == "REAL":
            activation = self.config.get("activation")
            required = ("real_runner_installed", "external_review_identity_verified", "external_review_writeback_verified")
            _require_fields(activation, required, "production activation")
            if any(activation[field] is not True for field in required):
                raise GateDenied("production runner/reviewer activation not independently verified")
        limits = self.config["limits"]
        _require_fields(limits, ("max_rounds", *self.BUDGET_FIELDS, "deadline_utc", "max_consecutive_failures",
                                 "max_consecutive_no_improvement"), "limits")
        _number(limits["max_rounds"], "max_rounds", positive=True, integer=True)
        for field in ("max_consecutive_failures", "max_consecutive_no_improvement"):
            _number(limits[field], field, positive=True, integer=True)
        for field in self.BUDGET_FIELDS:
            _number(limits[field], field, integer=(field == "max_calls"), positive=(field == "wall_clock_limit_seconds"))
        if self._now() >= _time(limits["deadline_utc"], "global deadline"):
            raise GateDenied("global deadline reached")
        _scope(self.config["allowed_scope"])

    def _git_blob(self, commit, path):
        _path(path)
        # Read committed bytes only. No fetch/index/ref writes to the checkout.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        try:
            p = subprocess.run(["git", "--no-replace-objects", "-C", str(self.repo_path), "show", f"{commit}:{path}"],
                               capture_output=True, timeout=30, env=env)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GateDenied("cannot read immutable subject") from exc
        if p.returncode:
            raise GateDenied("subject commit/artifact unavailable")
        return p.stdout

    def _artifact(self, commit, path, digest):
        _digest(digest, "artifact")
        raw = self._git_blob(commit, path)
        local = self.repo_path.joinpath(*PurePosixPath(path).parts)
        if (not local.is_file() or not local.resolve().is_relative_to(self.repo_path)
                or local.is_symlink() or sha256(raw) != digest or sha256(local.read_bytes()) != digest):
            raise GateDenied("committed/current artifact digest mismatch: " + path)
        return raw

    def _verify_review(self, approval_path):
        self._enabled()
        if isinstance(approval_path, dict):
            # Ledger records are not a substitute for independently signed reviews.
            review = approval_path
            approval_path = None
        else:
            approval_path = Path(approval_path).resolve()
            if self.mode == "TEST_ONLY" and not approval_path.is_relative_to(self.test_root):
                raise GateDenied("test approval must remain inside temporary namespace")
            review = strict_json(approval_path.read_bytes())
        _require_fields(review, self.REVIEW_FIELDS, "review")
        if type(review["schema_version"]) is not int or review["schema_version"] != 1:
            raise GateDenied("unsupported review schema")
        if review["mode"] != self.mode:
            raise GateDenied("review signing domain mismatch")
        expected_class = "TEST_ONLY" if self.mode == "TEST_ONLY" else "REAL_REVIEW"
        if review["evidence_class"] != expected_class:
            raise GateDenied("evidence class cannot enter this gate")
        if review["decision"] not in ("APPROVE_ONE_STEP", "REVISE", "STOP"):
            raise GateDenied("unknown review decision")
        if review["repository"] != self.remote_url or review["config_sha256"] != self.config_sha256:
            raise GateDenied("review repository/config binding mismatch")
        source = self.config["review_source"]
        identity = review["review_identity"]
        _require_fields(identity, ("source_id", "key_id", "reviewer_id", "github_login"), "review identity")
        for field in ("source_id", "key_id", "reviewer_id", "github_login"):
            _text(identity[field], "review identity " + field)
        for field in ("source_id", "key_id", "github_login"):
            if not source[field] or identity[field] != source[field]:
                raise GateDenied("review source identity mismatch")
        if self.mode == "REAL" and any("TEST_ONLY" in str(identity[k]).upper() for k in ("source_id", "key_id", "reviewer_id")):
            raise GateDenied("REAL gate rejects TEST_ONLY identity")
        signature = review["signature"]
        _require_fields(signature, ("algorithm", "value_base64"), "signature")
        if signature["algorithm"] != "Ed25519":
            raise GateDenied("only Ed25519 signatures accepted")
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            key = base64.b64decode(source["public_key_ed25519_base64"], validate=True)
            sig = base64.b64decode(signature["value_base64"], validate=True)
            Ed25519PublicKey.from_public_bytes(key).verify(sig, signature_message(review))
        except ImportError as exc:
            raise GateDenied("cryptography unavailable; cannot verify") from exc
        except Exception as exc:
            raise GateDenied("invalid independent-review signature") from exc
        if self._now() >= _time(review["expiration"], "approval expiration"):
            raise GateDenied("approval expired")
        self._review_report(review, approval_path)
        for field in ("approval_id", "round_id", "approved_action"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", _text(review[field], field)):
                raise GateDenied("invalid review identifier")
        commit = review["subject_commit_sha"]
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            raise GateDenied("full immutable subject commit SHA required")
        try:
            object_type = subprocess.run(["git", "--no-replace-objects", "-C", str(self.repo_path), "cat-file", "-t", commit],
                                         capture_output=True, timeout=30,
                                         env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GateDenied("subject object type unavailable") from exc
        if object_type.returncode or object_type.stdout.strip() != b"commit":
            raise GateDenied("subject must be a commit, not a tree/blob")
        manifest_raw = self._artifact(commit, review["manifest_path"], review["manifest_sha256"])
        manifest = strict_json(manifest_raw)
        _require_fields(manifest, ("schema_version", "mode", "repository", "config_sha256", "round_id", "proposal_path",
                                  "proposal_sha256", "report_md_path", "report_md_sha256", "evidence_class",
                                  "source_files", "evidence_files", "proposed_action"), "manifest")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise GateDenied("unsupported manifest schema")
        for field in ("mode", "repository", "config_sha256", "round_id", "proposal_sha256", "report_md_sha256", "evidence_class"):
            if manifest[field] != review[field]:
                raise GateDenied("subject manifest/review mismatch: " + field)
        self._artifact(commit, manifest["proposal_path"], review["proposal_sha256"])
        self._artifact(commit, manifest["report_md_path"], review["report_md_sha256"])
        for field in ("source_files", "evidence_files"):
            if not isinstance(manifest[field], dict):
                raise GateDenied("artifact digest map required")
            for path, digest in manifest[field].items():
                self._artifact(commit, path, digest)
        action = manifest["proposed_action"]
        _require_fields(action, ("action_id", "action_kind", "allowed_scope", *self.BUDGET_FIELDS), "proposed action")
        if action["action_id"] != review["approved_action"] or action["action_kind"] != review["action_kind"]:
            raise GateDenied("approved action differs from proposed action")
        scopes = _scope(review["allowed_scope"])
        if not _within(scopes, self.config["allowed_scope"]) or sorted(scopes) != sorted(_scope(action["allowed_scope"])):
            raise GateDenied("approval scope exceeds configuration or differs from proposal")
        if action["action_kind"] not in ("ANALYSIS_ONLY", "REAL_EXPERIMENT"):
            raise GateDenied("invalid action kind")
        for field in self.BUDGET_FIELDS:
            value = _number(review[field], field, integer=(field == "max_calls"), positive=(field == "wall_clock_limit_seconds"))
            _number(action[field], "proposed " + field, integer=(field == "max_calls"), positive=(field == "wall_clock_limit_seconds"))
            if action[field] != value or value > self.config["limits"][field]:
                raise GateDenied("approval budget exceeds limit or differs from proposal: " + field)
        if action["action_kind"] == "ANALYSIS_ONLY" and any(review[f] != 0 for f in self.BUDGET_FIELDS[:3]):
            raise GateDenied("ANALYSIS_ONLY cannot allocate research calls")
        if action["action_kind"] == "REAL_EXPERIMENT":
            if any(review[f] <= 0 for f in self.BUDGET_FIELDS[:3]):
                raise GateDenied("experiment requires positive explicit budgets")
            if self.mode == "REAL" and not self.config["ALLOW_REAL_EXPERIMENTS"]:
                raise GateDenied("real experiments disabled")
        return review, manifest

    def _initial_state(self):
        return {"schema_version": 1, "mode": self.mode, "config_sha256": self.config_sha256,
                "sequence": 0, "previous_state_sha256": None, "stop": None, "active_claim_id": None,
                "consecutive_failures": 0, "consecutive_no_improvement": 0,
                "run_started_utc": None, "run_deadline_utc": None,
                "rounds_consumed": 0, "calls_reserved": 0, "budget_reserved_seconds": 0,
                "claims": {}, "consumed_rounds": {}, "consumed_approvals": {}}

    def _load(self):
        try:
            snapshot = self.store.read()
        except StoreError as exc:
            raise GateDenied(str(exc)) from exc
        if snapshot.head is None and snapshot.ledger is None:
            state = self._initial_state()
        elif snapshot.head is None or not snapshot.ledger:
            raise GateDenied("existing or inconsistent empty remote ledger")
        else:
            state = snapshot.ledger
        _require_fields(state, self._initial_state().keys(), "ledger")
        if (type(state["schema_version"]) is not int or state["schema_version"] != 1
                or state["mode"] != self.mode or state["config_sha256"] != self.config_sha256):
            raise GateDenied("ledger trust-domain/config mismatch")
        if state["stop"] is not None:
            raise GateDenied("ledger has a permanent STOP/REVISE")
        if not all(isinstance(state[field], dict) for field in ("claims", "consumed_rounds", "consumed_approvals")):
            raise GateDenied("malformed ledger")
        for field in ("sequence", "rounds_consumed", "calls_reserved", "budget_reserved_seconds"):
            _number(state[field], field, integer=(field != "budget_reserved_seconds"))
        expected_rounds = {}
        expected_approvals = {}
        calls_reserved = 0
        seconds_reserved = 0
        running = []
        for field in ("consecutive_failures", "consecutive_no_improvement"):
            _number(state[field], field, integer=True)
        for claim_id, claim in state["claims"].items():
            if claim.get("status") not in ("RUNNING", "COMPLETED"):
                raise GateDenied("unknown ledger claim state")
            review = claim["review"]
            if claim["review_sha256"] != sha256(canonical_json(review)):
                raise GateDenied("ledger review digest mismatch")
            if review["round_id"] in expected_rounds or review["approval_id"] in expected_approvals:
                raise GateDenied("duplicate ledger consumption")
            expected_rounds[review["round_id"]] = review["approval_id"]
            expected_approvals[review["approval_id"]] = review["round_id"]
            calls_reserved += _number(review["max_calls"], "reserved calls", integer=True)
            seconds_reserved += _number(review["total_budget_seconds"], "reserved seconds")
            _number(claim["calls_issued"], "issued calls", integer=True)
            _number(claim["budget_charged_seconds"], "charged seconds")
            if not isinstance(claim["permits"], list) or len(claim["permits"]) != claim["calls_issued"]:
                raise GateDenied("invalid permit count")
            if (claim["calls_issued"] > review["max_calls"]
                    or sum(_number(p["budget_seconds"], "permit seconds", positive=True) for p in claim["permits"]) != claim["budget_charged_seconds"]
                    or claim["budget_charged_seconds"] > review["total_budget_seconds"]):
                raise GateDenied("invalid permit accounting")
            if claim["status"] == "RUNNING":
                running.append(claim_id)
        if (state["consumed_rounds"] != expected_rounds or state["consumed_approvals"] != expected_approvals
                or state["rounds_consumed"] != len(state["claims"]) or state["calls_reserved"] != calls_reserved
                or state["budget_reserved_seconds"] != seconds_reserved
                or running != ([] if state["active_claim_id"] is None else [state["active_claim_id"]])):
            raise GateDenied("ledger reservation accounting mismatch")
        for state_field, limit_field in (("consecutive_failures", "max_consecutive_failures"),
                                         ("consecutive_no_improvement", "max_consecutive_no_improvement")):
            limit = self.config["limits"].get(limit_field)
            if limit is not None and state[state_field] >= limit:
                raise GateDenied("failure/no-improvement limit reached")
        if state["claims"]:
            from datetime import timedelta
            started = _time(state["run_started_utc"], "global run start")
            run_deadline = _time(state["run_deadline_utc"], "global run deadline")
            expected_deadline = min(started + timedelta(seconds=self.config["limits"]["wall_clock_limit_seconds"]),
                                    _time(self.config["limits"]["deadline_utc"], "global absolute deadline"))
            if run_deadline != expected_deadline:
                raise GateDenied("global wall-clock binding mismatch")
            if self._now() >= run_deadline:
                raise GateDenied("global wall-clock deadline reached")
            if any(_time(c["deadline_utc"], "claim deadline") > run_deadline for c in state["claims"].values()):
                raise GateDenied("claim exceeds global wall-clock deadline")
        elif state["run_started_utc"] is not None or state["run_deadline_utc"] is not None:
            raise GateDenied("global timer without a consumed claim")
        return snapshot.head, state

    def _save(self, head, old, new):
        new["sequence"] = old["sequence"] + 1
        new["previous_state_sha256"] = sha256(canonical_json(old)) if head else None
        try:
            return self.store.compare_and_swap(head, new)
        except StoreError as exc:
            raise GateDenied(str(exc)) from exc

    def claim(self, approval_path, *, requested_action, requested_scope):
        """Verify immutable review, atomically consume once and reserve budget."""
        review, manifest = self._verify_review(approval_path)
        scopes = _scope(requested_scope)
        if requested_action != review["approved_action"] or not _within(scopes, review["allowed_scope"]):
            raise GateDenied("requested action/scope exceeds approval")
        head, old = self._load()
        new = copy.deepcopy(old)
        if review["decision"] in ("REVISE", "STOP"):
            new["stop"] = {"decision": review["decision"], "approval_id": review["approval_id"],
                           "review_sha256": sha256(canonical_json(review))}
            self._save(head, old, new)
            raise GateDenied("signed " + review["decision"] + " recorded; no action allowed")
        if old["active_claim_id"] is not None:
            raise GateDenied("RUNNING claim remains; no automatic restart")
        if review["approval_id"] in old["consumed_approvals"] or review["round_id"] in old["consumed_rounds"]:
            raise GateDenied("approval or round already consumed")
        limits = self.config["limits"]
        if (old["rounds_consumed"] + 1 > limits["max_rounds"]
                or old["calls_reserved"] + review["max_calls"] > limits["max_calls"]
                or old["budget_reserved_seconds"] + review["total_budget_seconds"] > limits["total_budget_seconds"]):
            raise GateDenied("cumulative round/call/time quota exhausted")
        claim_id = uuid.uuid4().hex
        now = self._now()
        from datetime import timedelta
        if old["run_started_utc"] is None:
            run_deadline = min(now + timedelta(seconds=limits["wall_clock_limit_seconds"]),
                               _time(limits["deadline_utc"], "deadline"))
            new["run_started_utc"] = now.isoformat().replace("+00:00", "Z")
            new["run_deadline_utc"] = run_deadline.isoformat().replace("+00:00", "Z")
        else:
            run_deadline = _time(old["run_deadline_utc"], "global run deadline")
        deadline = min(_time(review["expiration"], "expiration"), run_deadline)
        deadline = min(deadline, now + timedelta(seconds=review["wall_clock_limit_seconds"]))
        new["rounds_consumed"] += 1
        new["calls_reserved"] += review["max_calls"]
        new["budget_reserved_seconds"] += review["total_budget_seconds"]
        new["consumed_rounds"][review["round_id"]] = review["approval_id"]
        new["consumed_approvals"][review["approval_id"]] = review["round_id"]
        new["active_claim_id"] = claim_id
        new["claims"][claim_id] = {"status": "RUNNING", "review": review,
                                   "review_sha256": sha256(canonical_json(review)), "calls_issued": 0,
                                   "budget_charged_seconds": 0, "permits": [],
                                   "deadline_utc": deadline.isoformat().replace("+00:00", "Z")}
        published_head = self._save(head, old, new)
        if self.store.remote_head() != published_head:
            raise GateDenied("ledger changed before claim return; reservation remains consumed")
        self._verify_bound_review(review)
        self._enabled()
        if self._now() >= deadline:
            raise GateDenied("deadline passed during reservation; consumed without restart")
        return claim_id

    def issue_permit(self, claim_id, *, requested_action, requested_scope, budget_seconds):
        """Charge BEFORE a future caller would execute. Does not execute anything."""
        self._enabled()
        head, old = self._load()
        if old["active_claim_id"] != claim_id or claim_id not in old["claims"]:
            raise GateDenied("no active claim")
        claim = old["claims"][claim_id]
        review = claim["review"]
        if claim["status"] != "RUNNING" or self._now() >= _time(claim["deadline_utc"], "claim deadline"):
            raise GateDenied("claim expired or not RUNNING")
        if review["mode"] != self.mode or review["evidence_class"] != ("TEST_ONLY" if self.mode == "TEST_ONLY" else "REAL_REVIEW"):
            raise GateDenied("permit signing domain mismatch")
        if review["action_kind"] != "REAL_EXPERIMENT":
            raise GateDenied("analysis step has no research-call permits")
        if self.mode == "REAL" and not self.config["ALLOW_REAL_EXPERIMENTS"]:
            raise GateDenied("real experiments disabled")
        scopes = _scope(requested_scope)
        if requested_action != review["approved_action"] or not _within(scopes, review["allowed_scope"]):
            raise GateDenied("call exceeds approved action/scope")
        _number(budget_seconds, "call budget", positive=True)
        if (budget_seconds > review["per_call_budget_seconds"]
                or claim["calls_issued"] + 1 > review["max_calls"]
                or claim["budget_charged_seconds"] + budget_seconds > review["total_budget_seconds"]
                or (self._now().timestamp() + budget_seconds) > _time(claim["deadline_utc"], "claim deadline").timestamp()):
            raise GateDenied("call exceeds call/time/deadline budget")
        # Recheck every bound working file on every permit, not only at claim.
        self._verify_bound_review(review)
        new = copy.deepcopy(old)
        updated = new["claims"][claim_id]
        permit = {"permit_id": uuid.uuid4().hex, "claim_id": claim_id, "mode": self.mode,
                  "action_id": requested_action, "allowed_scope": scopes, "budget_seconds": budget_seconds,
                  "deadline_utc": claim["deadline_utc"], "sequence": old["sequence"] + 1}
        updated["calls_issued"] += 1
        updated["budget_charged_seconds"] += budget_seconds
        updated["permits"].append(permit)
        published_head = self._save(head, old, new)
        if self.store.remote_head() != published_head:
            raise GateDenied("ledger changed before permit return; budget remains charged")
        self._verify_bound_review(review)
        self._enabled()
        if self._now().timestamp() + budget_seconds > _time(claim["deadline_utc"], "claim deadline").timestamp():
            raise GateDenied("deadline passed during CAS; budget remains charged without permit")
        return permit

    def _verify_bound_review(self, review):
        self._verify_review(review)

    def _review_report(self, review, approval_path=None):
        path = _path(review["review_report_path"])
        expected_prefix = "TEST_ONLY-reviews/" if self.mode == "TEST_ONLY" else "research/agent_loop/reviews/"
        if not path.startswith(expected_prefix):
            raise GateDenied("review Markdown must be in the external-review namespace")
        report = self.repo_path.joinpath(*PurePosixPath(path).parts)
        if (not report.is_file() or report.is_symlink() or not report.resolve().is_relative_to(self.repo_path)
                or sha256(report.read_bytes()) != _digest(review["review_report_sha256"], "review Markdown")):
            raise GateDenied("independent review Markdown mismatch")
        if approval_path is not None and report.parent.resolve() != approval_path.parent:
            raise GateDenied("review JSON and Markdown must share one round directory")

    def finish(self, claim_id, *, outcome):
        """Explicit terminal acknowledgement; never refunds reserved budgets."""
        self._enabled()
        head, old = self._load()
        if old["active_claim_id"] != claim_id or old["claims"][claim_id]["status"] != "RUNNING":
            raise GateDenied("no matching RUNNING claim")
        if outcome not in ("IMPROVED", "NO_IMPROVEMENT", "FAILURE"):
            raise GateDenied("explicit outcome required; gate does not judge research improvement")
        new = copy.deepcopy(old)
        new["claims"][claim_id]["status"] = "COMPLETED"
        new["claims"][claim_id]["outcome"] = outcome
        new["active_claim_id"] = None
        new["consecutive_failures"] = old["consecutive_failures"] + 1 if outcome == "FAILURE" else 0
        new["consecutive_no_improvement"] = 0 if outcome == "IMPROVED" else old["consecutive_no_improvement"] + 1
        if (new["consecutive_failures"] >= self.config["limits"]["max_consecutive_failures"]
                or new["consecutive_no_improvement"] >= self.config["limits"]["max_consecutive_no_improvement"]):
            new["stop"] = {"decision": "STOP", "reason": "failure/no-improvement threshold"}
        self._save(head, old, new)

    def stop(self, reason):
        """Safety stop only. No reset exists; stale RUNNING reservations remain."""
        _text(reason, "stop reason")
        head, old = self._load()
        new = copy.deepcopy(old)
        new["stop"] = {"decision": "STOP", "reason": reason}
        self._save(head, old, new)
