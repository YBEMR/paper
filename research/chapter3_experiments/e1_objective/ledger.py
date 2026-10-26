"""Persistent, fail-closed one-use claims. No scheduling or thermal execution.

An authorization identifier has one directory in a caller-fixed authority store,
regardless of output path. Never delete records or an abandoned lock to retry a
consumed scientific call. This is a local software contract, not an OS security
boundary against an operator who can modify the authority store.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re


class LedgerError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise LedgerError(reason)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _hash(value, name="HASH"):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             "INVALID_" + name)
    return value


def _path(value):
    return str(Path(value).resolve())


def _write_once(path, value):
    # An existing/truncated file remains consumed after a crash: never replace it.
    import os
    with path.open("xb") as stream:
        stream.write(_bytes(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def _read(path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise LedgerError("MISSING_OR_CORRUPT_RECORD:" + path.name) from error


TOKEN_FIELDS = frozenset({"input_sha256", "config_sha256", "accuracy_sha256", "objective",
                         "planning_score_sha256", "receipt_sha256", "candidate_sha256"})
TOKEN_OPTIONAL = frozenset({"semantic_candidate_sha256"})
BUDGETS = dict(plan_s=300, post_s=60, plan_calls=4, post_calls=4)
KINDS = frozenset({"MOCK_PROCESS", "REAL_RESEARCH"})


def validate_token(token):
    _require(isinstance(token, dict) and TOKEN_FIELDS <= set(token)
             and set(token) <= TOKEN_FIELDS | TOKEN_OPTIONAL, "SELECTED_TOKEN_FIELDS")
    _require(token["objective"] in ("FULL", "OMIT_TEMP"), "SELECTED_TOKEN_OBJECTIVE")
    for key, value in token.items():
        if key != "objective":
            _hash(value, key.upper())
    return deepcopy(token)


class Ledger:
    def __init__(self, authority_store, authorization, run_dir, kind="MOCK_PROCESS"):
        _require(isinstance(authorization, dict), "AUTHORIZATION_NOT_OBJECT")
        _require(kind in KINDS and authorization.get("kind") == kind, "AUTHORIZATION_KIND_MISMATCH")
        aid = authorization.get("authorization_id")
        _require(isinstance(aid, str) and 0 < len(aid) <= 256, "AUTHORIZATION_ID")
        _hash(authorization.get("scope_sha256"), "SCOPE_SHA256")
        source = authorization.get("source_sha")
        _require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) is not None,
                 "SOURCE_SHA")
        _require(authorization.get("budgets") == BUDGETS, "AUTHORIZATION_BUDGETS")
        self.authorization = deepcopy(authorization)
        self.authorization_sha256 = digest(authorization)
        self.kind = kind
        self.run_dir = _path(run_dir)
        self.root = Path(authority_store).resolve() / digest({"authorization_id": aid})
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self):
        lock = self.root / "mutation.lock"
        try:
            _write_once(lock, {"authorization_sha256": self.authorization_sha256,
                               "run_dir": self.run_dir})
        except FileExistsError as error:
            raise LedgerError("AUTHORITY_BUSY_OR_ABANDONED_LOCK") from error
        try:
            yield
        finally:
            # Only the process that created this lock removes it on normal exit.
            lock.unlink()

    def _batch(self, active=True):
        batch = _read(self.root / "batch.json")
        _require(batch["authorization_sha256"] == self.authorization_sha256
                 and batch["kind"] == self.kind and batch["run_dir"] == self.run_dir,
                 "BATCH_SCOPE_SOURCE_KIND_OR_OUTPUT_DRIFT")
        if active:
            _require(not (self.root / "stop.json").exists(), "BATCH_STOPPED")
        return batch

    def claim_batch(self, context):
        _require(isinstance(context, dict) and context, "EMPTY_BATCH_CONTEXT")
        with self._lock():
            _require(not (self.root / "stop.json").exists(), "BATCH_STOPPED")
            record = dict(schema="E1_PERSISTENT_CLAIM_V1", authorization_id=self.authorization["authorization_id"],
                          authorization_sha256=self.authorization_sha256,
                          scope_sha256=self.authorization["scope_sha256"],
                          source_sha=self.authorization["source_sha"], kind=self.kind,
                          run_dir=self.run_dir, context=deepcopy(context), context_sha256=digest(context))
            try:
                _write_once(self.root / "batch.json", record)
            except FileExistsError as error:
                raise LedgerError("BATCH_AUTHORIZATION_ALREADY_CONSUMED") from error
            return record

    @staticmethod
    def _ordinal(ordinal):
        _require(type(ordinal) is int and 1 <= ordinal <= 4, "SLOT_ORDINAL")

    def _record(self, name):
        return _read(self.root / name)

    def _claim(self, phase, ordinal, root_origin, context):
        self._ordinal(ordinal)
        _require(type(root_origin) in (int, float) and math.isfinite(root_origin)
                 and root_origin >= 0, "ROOT_ORIGIN")
        _require(isinstance(context, dict) and context, "EMPTY_JOB_CONTEXT")
        batch = self._batch()
        record = dict(schema="E1_CALL_CLAIM_V1", authorization_sha256=self.authorization_sha256,
                      batch_sha256=digest(batch), kind=self.kind, phase=phase, ordinal=ordinal,
                      root_origin=root_origin, limit_s=BUDGETS[phase.lower() + "_s"],
                      run_dir=self.run_dir, source_sha=self.authorization["source_sha"],
                      job_context=deepcopy(context), context_sha256=digest(context))
        record["claim_sha256"] = digest(record)
        try:
            _write_once(self.root / f"{ordinal:02d}_{phase.lower()}_claim.json", record)
        except FileExistsError as error:
            raise LedgerError(phase + "_ALREADY_CONSUMED") from error
        return record

    def claim_plan(self, ordinal, root_origin, job_context):
        self._ordinal(ordinal)
        _require(isinstance(job_context, dict), "PLAN_JOB_CONTEXT")
        for key in ("input_sha256", "config_sha256", "accuracy_sha256"):
            _hash(job_context.get(key), key.upper())
        _require(job_context.get("objective") in ("FULL", "OMIT_TEMP"), "PLAN_OBJECTIVE")
        with self._lock():
            self._batch()
            if ordinal > 1:
                prior = self._record(f"{ordinal-1:02d}_plan_finish.json")
                if prior.get("selected_token") is not None:
                    self._record(f"{ordinal-1:02d}_post_finish.json")
            return self._claim("PLAN", ordinal, root_origin, job_context)

    def finish_plan(self, ordinal, result_sha, selected_token=None, stop_required=False):
        self._ordinal(ordinal)
        _hash(result_sha, "RESULT_SHA256")
        _require(type(stop_required) is bool, "STOP_REQUIRED_BOOLEAN")
        token = validate_token(selected_token) if selected_token is not None else None
        with self._lock():
            self._batch(active=False)
            claim = self._record(f"{ordinal:02d}_plan_claim.json")
            if token is not None:
                for key in ("input_sha256", "config_sha256", "accuracy_sha256", "objective"):
                    _require(token[key] == claim["job_context"][key], "SELECTED_TOKEN_PLAN_SCOPE_DRIFT")
                self._record(f"{ordinal:02d}_plan_launch.json")
            record = dict(claim_sha256=claim["claim_sha256"], result_sha256=result_sha,
                          selected_token=token, selected_token_sha256=digest(token) if token else None,
                          stop_required=stop_required)
            try:
                _write_once(self.root / f"{ordinal:02d}_plan_finish.json", record)
            except FileExistsError as error:
                raise LedgerError("PLAN_FINISH_ALREADY_RECORDED") from error
            if stop_required:
                self._stop("PLAN_REQUIRES_STOP")
            return record

    def claim_post(self, ordinal, root_origin, token):
        self._ordinal(ordinal)
        token = validate_token(token)
        with self._lock():
            self._batch()
            prior = self._record(f"{ordinal:02d}_plan_finish.json")
            _require(prior["selected_token"] == token and prior["selected_token_sha256"] == digest(token),
                     "POST_NOT_FINAL_SELECTED_CANDIDATE")
            return self._claim("POST", ordinal, root_origin,
                               {"selected_token": token, "selected_token_sha256": digest(token),
                                "plan_result_sha256": prior["result_sha256"]})

    def finish_post(self, ordinal, result_sha, stop_required=False, not_launched_deadline=None):
        self._ordinal(ordinal)
        _hash(result_sha, "RESULT_SHA256")
        _require(type(stop_required) is bool, "STOP_REQUIRED_BOOLEAN")
        with self._lock():
            self._batch(active=False)
            claim = self._record(f"{ordinal:02d}_post_claim.json")
            launched = (self.root / f"{ordinal:02d}_post_launch.json").exists()
            if not_launched_deadline is not None:
                proof = not_launched_deadline
                _require(not launched and not stop_required, "POST_DEADLINE_LAUNCH_OR_STOP_CONTRADICTION")
                _require(isinstance(proof, dict) and set(proof) == {"reason", "observed_monotonic"}
                         and proof["reason"] == "ROOT_DEADLINE_BEFORE_SPAWN", "POST_NOT_LAUNCHED_PROOF")
                observed = proof["observed_monotonic"]
                _require(type(observed) in (int, float) and math.isfinite(observed)
                         and observed >= claim["root_origin"] + claim["limit_s"],
                         "POST_NOT_LAUNCHED_NOT_EXPIRED")
            elif not stop_required:
                self._record(f"{ordinal:02d}_post_launch.json")
            record = dict(claim_sha256=claim["claim_sha256"], result_sha256=result_sha,
                          stop_required=stop_required,
                          not_launched_deadline=deepcopy(not_launched_deadline))
            try:
                _write_once(self.root / f"{ordinal:02d}_post_finish.json", record)
            except FileExistsError as error:
                raise LedgerError("POST_FINISH_ALREADY_RECORDED") from error
            if stop_required:
                self._stop("POST_REQUIRES_STOP")
            return record

    def consume_launch(self, claim, job_sha, worker_dir):
        _hash(job_sha, "JOB_SHA256")
        _require(isinstance(claim, dict) and claim.get("phase") in ("PLAN", "POST"), "LAUNCH_CLAIM")
        ordinal, phase = claim.get("ordinal"), claim["phase"]
        self._ordinal(ordinal)
        with self._lock():
            self._batch()
            saved = self._record(f"{ordinal:02d}_{phase.lower()}_claim.json")
            _require(saved == claim, "LAUNCH_PARENT_CLAIM_MISMATCH")
            expected = claim["job_context"].get("job_sha256")
            _require(expected is None or expected == job_sha, "LAUNCH_JOB_HASH_MISMATCH")
            record = dict(claim_sha256=saved["claim_sha256"], job_sha256=job_sha,
                          worker_dir=_path(worker_dir), kind=self.kind,
                          root_origin=claim["root_origin"], limit_s=claim["limit_s"])
            try:
                _write_once(self.root / f"{ordinal:02d}_{phase.lower()}_launch.json", record)
            except FileExistsError as error:
                raise LedgerError("WORKER_LAUNCH_ALREADY_CONSUMED") from error
            return record

    def _stop(self, reason):
        record = dict(reason=reason, authorization_sha256=self.authorization_sha256, kind=self.kind)
        try:
            _write_once(self.root / "stop.json", record)
        except FileExistsError:
            return self._record("stop.json")
        return record

    def stop(self, reason):
        _require(isinstance(reason, str) and reason, "STOP_REASON")
        with self._lock():
            self._batch(active=False)
            return self._stop(reason)
