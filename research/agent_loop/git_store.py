"""Remote Git compare-and-swap ledger; never modifies the subject checkout.

Only normal, non-forced pushes are used. A failed or indeterminate push is a
hard failure: callers must not execute or retry an experiment after it.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, NamedTuple
import uuid


class StoreError(RuntimeError):
    pass


class CASConflict(StoreError):
    pass


class Snapshot(NamedTuple):
    head: str | None
    ledger: dict[str, Any] | None


class GitLedgerStore:
    """Uses a private temporary bare object database and one remote branch.

    The remote must preserve history (no external deletion/force-push). Git
    server access controls remain an operational trust boundary.
    """

    def __init__(self, remote_url: str, ref: str, *, temporary_parent=None):
        if not isinstance(remote_url, str) or not remote_url or remote_url.startswith("-"):
            raise StoreError("invalid remote URL")
        if not re.fullmatch(r"refs/heads/[A-Za-z0-9_./-]+", ref) or ".." in ref:
            raise StoreError("invalid ledger branch ref")
        self.remote_url = remote_url
        self.ref = ref
        self._temp = tempfile.TemporaryDirectory(prefix="agent-loop-ledger-", dir=temporary_parent)
        self.path = Path(self._temp.name)
        self._git("init", "--bare", "--quiet")
        self._git("check-ref-format", ref)

    def close(self) -> None:
        self._temp.cleanup()

    def _git(self, *args: str, data: bytes | None = None, check: bool = True):
        env = os.environ.copy()
        # Ignore caller-supplied object/worktree overrides; do not alter user's Git.
        for key in list(env):
            if key.startswith("GIT_") and key not in ("GIT_SSH_COMMAND", "GIT_ASKPASS", "GIT_TERMINAL_PROMPT"):
                del env[key]
        env.update({"GIT_AUTHOR_NAME": "Agent loop ledger", "GIT_AUTHOR_EMAIL": "ledger@invalid",
                    "GIT_COMMITTER_NAME": "Agent loop ledger", "GIT_COMMITTER_EMAIL": "ledger@invalid",
                    "GIT_TERMINAL_PROMPT": "0"})
        try:
            p = subprocess.run(["git", "--no-replace-objects", "-C", str(self.path), *args], input=data,
                               capture_output=True, env=env, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StoreError("Git operation unavailable or indeterminate") from exc
        if check and p.returncode:
            raise StoreError("Git operation failed: " + p.stderr.decode("utf-8", "replace")[-1200:])
        return p

    def remote_head(self) -> str | None:
        output = self._git("ls-remote", "--refs", "--", self.remote_url, self.ref).stdout.decode().strip()
        if not output:
            return None
        lines = output.splitlines()
        if len(lines) != 1:
            raise StoreError("ambiguous remote ledger ref")
        sha, found_ref = lines[0].split("\t", 1)
        if found_ref != self.ref or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            raise StoreError("malformed remote ledger ref")
        return sha

    def read(self) -> Snapshot:
        head = self.remote_head()
        if head is None:
            return Snapshot(None, None)
        self._git("fetch", "--quiet", "--no-tags", "--", self.remote_url, self.ref)
        raw = self._git("show", f"{head}:ledger.json").stdout
        try:
            value = self._parse(raw)
        except (ValueError, UnicodeError) as exc:
            raise StoreError("invalid remote ledger JSON") from exc
        if not isinstance(value, dict):
            raise StoreError("remote ledger is not an object")
        self._validate_history(head)
        return Snapshot(head, value)

    @staticmethod
    def _parse(raw):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise StoreError("duplicate remote ledger JSON key")
                result[key] = value
            return result
        def constant(value):
            raise StoreError("non-finite remote ledger number")
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)

    def _validate_history(self, head):
        """Detect deletion/rollback within ordinary FF history, not signer authority.

        Repository administrators can still rewrite/delete the whole branch.
        Protecting that external trust boundary requires Git server policy.
        """
        commits = self._git("rev-list", "--first-parent", "--reverse", head).stdout.decode().splitlines()
        if len(commits) > 10000:
            raise StoreError("ledger history limit reached; manual inspection required")
        previous = None
        previous_commit = None
        for index, commit in enumerate(commits, 1):
            parents = self._git("rev-list", "--parents", "-n", "1", commit).stdout.decode().split()[1:]
            if parents != ([] if previous_commit is None else [previous_commit]):
                raise StoreError("ledger must have one linear parent chain")
            try:
                current = self._parse(self._git("show", f"{commit}:ledger.json").stdout)
                self._validate_transition(previous, current, index)
            except (KeyError, TypeError, ValueError, UnicodeError) as exc:
                raise StoreError("invalid ledger history") from exc
            previous, previous_commit = current, commit

    @staticmethod
    def _validate_transition(previous, current, sequence):
        if not isinstance(current, dict) or type(current["sequence"]) is not int or current["sequence"] != sequence:
            raise StoreError("non-monotonic ledger sequence")
        expected_hash = None if previous is None else hashlib.sha256(json.dumps(
            previous, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        if current["previous_state_sha256"] != expected_hash:
            raise StoreError("ledger history binding mismatch")
        for field in ("rounds_consumed", "calls_reserved", "budget_reserved_seconds"):
            value = current[field]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise StoreError("invalid ledger counter")
            old_value = 0 if previous is None else previous[field]
            if value < old_value:
                raise StoreError("ledger quota rollback")
        if previous is None:
            if len(current["claims"]) > 1 or current["rounds_consumed"] > 1:
                raise StoreError("invalid initial ledger transition")
            return
        if previous["stop"] is not None:
            raise StoreError("ledger STOP cannot be cleared or advanced")
        for field in ("schema_version", "mode", "config_sha256"):
            if current[field] != previous[field]:
                raise StoreError("ledger trust binding changed")
        if previous.get("run_started_utc") is not None:
            for field in ("run_started_utc", "run_deadline_utc"):
                if current.get(field) != previous[field]:
                    raise StoreError("global wall-clock timer reset")
        for field in ("consumed_rounds", "consumed_approvals"):
            if any(current[field].get(key) != value for key, value in previous[field].items()):
                raise StoreError("ledger consumption rollback")
        if len(current["claims"]) > len(previous["claims"]) + 1:
            raise StoreError("more than one reservation in a transition")
        for key, old_claim in previous["claims"].items():
            new_claim = current["claims"].get(key)
            if not new_claim:
                raise StoreError("deleted claim")
            for field in ("review", "review_sha256", "deadline_utc"):
                if new_claim[field] != old_claim[field]:
                    raise StoreError("modified immutable claim")
            if old_claim["status"] == "COMPLETED" and new_claim != old_claim:
                raise StoreError("completed claim modified")
            if (new_claim["calls_issued"] < old_claim["calls_issued"]
                    or new_claim["budget_charged_seconds"] < old_claim["budget_charged_seconds"]
                    or new_claim["permits"][:len(old_claim["permits"])] != old_claim["permits"]):
                raise StoreError("permit accounting rollback")

    def compare_and_swap(self, expected_head: str | None, ledger: dict[str, Any]) -> str:
        """Publish a unique child of expected_head; a fork must fail to push.

        No automatic retry is allowed. If the caller loses the network response,
        a possible successful reservation remains consumed on the remote.
        """
        if self.remote_head() != expected_head:
            raise CASConflict("ledger changed; reservation not granted")
        raw = json.dumps(ledger, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
        blob = self._git("hash-object", "-w", "--stdin", data=raw).stdout.decode().strip()
        tree = self._git("mktree", data=f"100644 blob {blob}\tledger.json\n".encode()).stdout.decode().strip()
        args = ["commit-tree", tree]
        if expected_head:
            args += ["-p", expected_head]
        # Entropy matters: two simultaneous identical reservations MUST fork.
        commit = self._git(*args, data=f"Agent loop CAS {uuid.uuid4().hex}\n".encode()).stdout.decode().strip()
        result = self._git("push", "--porcelain", "--", self.remote_url,
                           f"{commit}:{self.ref}", check=False)
        if result.returncode:
            raise CASConflict("remote CAS rejected or uncertain; no permit granted")
        if self.remote_head() != commit:
            raise CASConflict("remote ledger advanced after push; no permit granted")
        return commit
