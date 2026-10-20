"""Read-only approval detector. This module never verifies or consumes approval.

Only fixed Git objects and local files are read. No proposal command, experiment,
network request, review generation, or ChatGPT wakeup is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


SCHEMA_VERSION = 1
MAX_FILE_BYTES = 8 * 1024 * 1024
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ROUND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
SEVERITY = {
    "NO_ROUNDS": 0,
    "APPROVAL_REQUIRES_MACHINE_GATE": 1,
    "WAITING_REVIEW": 2,
    "UNPUBLISHED_WAITING_REVIEW": 3,
    "REVISE": 4,
    "UNRESOLVED": 5,
    "STOP": 6,
}


class DetectionError(ValueError):
    """An incomplete or invalid read must never become an approval."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DetectionError("duplicate JSON key")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        def reject_constant(value: str) -> None:
            raise DetectionError("non-finite JSON number")
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                           parse_constant=reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise DetectionError(f"invalid JSON: {label}") from exc
    if not isinstance(value, dict):
        raise DetectionError(f"JSON object required: {label}")
    return value


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise DetectionError("invalid repository-relative path")
    parts = value.split("/")
    if (
        any(part in ("", ".", "..") for part in parts)
        or any(ord(char) < 32 for char in value)
        or "\\" in value
        or ":" in value
        or PurePosixPath(value).is_absolute()
    ):
        raise DetectionError("unsafe repository-relative path")
    return value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise DetectionError(f"invalid SHA-256: {label}")
    return value


class ReadOnlyRepository:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, relative: str) -> Path:
        relative = _relative(relative)
        path = self.root
        for part in relative.split("/"):
            path = path / part
            if path.is_symlink():
                raise DetectionError(f"symlink not accepted: {relative}")
        try:
            path.resolve().relative_to(self.root)
        except ValueError as exc:
            raise DetectionError("path escaped repository") from exc
        return path

    def exists(self, relative: str) -> bool:
        path = self.path(relative)
        if path.exists() and not path.is_file():
            raise DetectionError(f"regular file required: {relative}")
        return path.is_file()

    def read(self, relative: str) -> bytes:
        path = self.path(relative)
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                raise DetectionError(f"missing or oversized file: {relative}")
            value = path.read_bytes()
        except OSError as exc:
            raise DetectionError(f"cannot read file: {relative}") from exc
        if len(value) > MAX_FILE_BYTES:
            raise DetectionError(f"oversized file: {relative}")
        return value

    def _git(self, arguments: list[str], label: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", "--no-replace-objects", "--no-pager", "--no-optional-locks", "-c",
                 "core.fsmonitor=false", *arguments],
                cwd=self.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DetectionError(f"cannot read subject Git object: {label}") from exc
        if result.returncode != 0 or len(result.stdout) > MAX_FILE_BYTES:
            raise DetectionError(f"missing or unreadable subject Git object: {label}")
        return result.stdout

    def require_commit(self, subject: str) -> None:
        if not FULL_SHA.fullmatch(subject):
            raise DetectionError("subject must be a full lowercase 40-character commit SHA")
        if self._git(["cat-file", "-t", subject], "subject type").strip() != b"commit":
            raise DetectionError("subject object is not a commit")

    def committed(self, subject: str, relative: str) -> bytes:
        if not FULL_SHA.fullmatch(subject):
            raise DetectionError("subject must be a full lowercase 40-character commit SHA")
        relative = _relative(relative)
        return self._git(["show", f"{subject}:{relative}"], relative)


def _manifest_bindings(manifest: dict[str, Any], round_id: str) -> dict[str, str]:
    if manifest.get("schema_version") != 1 or manifest.get("round_id") != round_id:
        raise DetectionError("manifest schema or round_id mismatch")
    bindings: dict[str, str] = {}

    def add(path: Any, digest: Any, label: str) -> None:
        path = _relative(path)
        digest = _sha256(digest, label)
        if path in bindings and bindings[path] != digest:
            raise DetectionError(f"conflicting manifest binding: {path}")
        bindings[path] = digest

    for prefix in ("proposal", "report_md"):
        add(manifest.get(f"{prefix}_path"), manifest.get(f"{prefix}_sha256"), prefix)
    for key in ("source_files", "evidence_files"):
        values = manifest.get(key)
        if not isinstance(values, dict):
            raise DetectionError(f"manifest {key} must be a path-to-hash object")
        for path, digest in values.items():
            add(path, digest, key)
    if manifest.get("evidence_class") not in ("TEST_ONLY", "REAL_REVIEW"):
        raise DetectionError("unknown evidence_class")
    if manifest.get("mode") not in ("REAL", "TEST_ONLY"):
        raise DetectionError("unknown manifest mode")
    return bindings


def inspect_round(repo: ReadOnlyRepository, request: Any, config_path: str,
                  config_raw: bytes, config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "round_id": None,
        "subject_commit_sha": None,
        "status": "UNRESOLVED",
        "reasons": [],
        "bindings": {},
        "review": {"present": False, "verified": False},
        "machine_gate_required": True,
        "real_experiments_started": False,
    }
    try:
        if not isinstance(request, dict):
            raise DetectionError("round request must be an object")
        round_id = request.get("round_id")
        if not isinstance(round_id, str) or not ROUND_ID.fullmatch(round_id):
            raise DetectionError("invalid round_id")
        result["round_id"] = round_id
        subject = request.get("subject_commit_sha")
        result["subject_commit_sha"] = subject
        if subject is None:
            result.update(status="UNPUBLISHED_WAITING_REVIEW", reasons=["SUBJECT_NOT_PUBLISHED"])
            return result
        if not isinstance(subject, str) or not FULL_SHA.fullmatch(subject):
            raise DetectionError("subject must be a full lowercase 40-character commit SHA")
        repo.require_commit(subject)
        manifest_path = _relative(request.get("manifest_path"))
        manifest_raw = repo.committed(subject, manifest_path)
        manifest = _json(manifest_raw, "subject manifest")
        bindings = _manifest_bindings(manifest, round_id)
        configured_repository = config.get("repository")
        if not isinstance(configured_repository, dict):
            raise DetectionError("config.repository must be an object")
        remote_url = configured_repository.get("remote_url")
        if manifest.get("repository") != remote_url or not remote_url:
            raise DetectionError("manifest repository does not match configured remote_url")
        if manifest.get("mode") != config.get("mode"):
            raise DetectionError("manifest mode does not match config")
        config_digest = _sha256(manifest.get("config_sha256"), "config_sha256")
        if _digest(config_raw) != config_digest or _digest(repo.committed(subject, config_path)) != config_digest:
            raise DetectionError("config changed from subject or manifest binding")
        result["bindings"] = {
            "manifest_path": manifest_path,
            "manifest_sha256": _digest(manifest_raw),
            "proposal_sha256": manifest["proposal_sha256"],
            "report_md_sha256": manifest["report_md_sha256"],
            "evidence_class": manifest["evidence_class"],
            "config_sha256": config_digest,
            "file_count": len(bindings),
        }
        if repo.read(manifest_path) != manifest_raw:
            result.update(status="STOP", reasons=["CURRENT_MANIFEST_CHANGED_FROM_SUBJECT"])
            return result
        for path, expected in bindings.items():
            if _digest(repo.committed(subject, path)) != expected:
                raise DetectionError(f"subject manifest hash mismatch: {path}")
            if _digest(repo.read(path)) != expected:
                result.update(status="STOP", reasons=[f"CURRENT_BOUND_FILE_CHANGED: {path}"])
                return result
        review_path = f"research/agent_loop/reviews/{round_id}/{subject}.json"
        markdown_path = f"research/agent_loop/reviews/{round_id}/{subject}.md"
        json_present, md_present = repo.exists(review_path), repo.exists(markdown_path)
        result["review"].update(present=json_present or md_present, path=review_path,
                                markdown_present=md_present)
        if request.get("status") in ("STOP", "REVISE"):
            result.update(status=request["status"], reasons=["REQUEST_INDEX_HAS_STOP_OR_REVISE"])
            return result
        if not json_present:
            reason = "MARKDOWN_REVIEW_NOT_MACHINE_ACTIONABLE" if md_present else "REVIEW_ABSENT"
            result.update(status="WAITING_REVIEW", reasons=[reason])
            return result
        review = _json(repo.read(review_path), "review")
        decision = review.get("decision")
        result["review"]["decision"] = decision
        if decision in ("STOP", "REVISE"):
            result.update(status=decision, reasons=["UNVERIFIED_REVIEW_REQUESTS_STOP_OR_REVISE"])
            return result
        expected_review = {
            "schema_version": 1,
            "round_id": round_id,
            "subject_commit_sha": subject,
            "manifest_path": manifest_path,
            "manifest_sha256": _digest(manifest_raw),
            "proposal_sha256": manifest["proposal_sha256"],
            "report_md_sha256": manifest["report_md_sha256"],
            "evidence_class": manifest["evidence_class"],
            "mode": manifest["mode"],
            "repository": manifest["repository"],
            "config_sha256": config_digest,
        }
        mismatches = [key for key, value in expected_review.items() if review.get(key) != value]
        if mismatches:
            result.update(status="STOP", reasons=["REVIEW_BINDING_MISMATCH: " + ", ".join(mismatches)])
        elif decision == "APPROVE_ONE_STEP":
            result.update(status="APPROVAL_REQUIRES_MACHINE_GATE", reasons=[
                "DECLARED_APPROVAL_ONLY_SIGNATURE_IDENTITY_BUDGET_SCOPE_EXPIRATION_NOT_VERIFIED",
                "NO_EXECUTION_AUTHORITY_GRANTED",
            ])
        else:
            result.update(status="UNRESOLVED", reasons=["UNRECOGNIZED_REVIEW_DECISION"])
    except (DetectionError, OSError) as exc:
        result.update(status="UNRESOLVED", reasons=[str(exc)])
    return result


def detect(repo_root: Path | str, config_path: str = "research/agent_loop/config.json",
           requests_path: str = "research/agent_loop/requests.json") -> dict[str, Any]:
    """Return advisory JSON data; never mutate the repository or consume approval."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "detector_only": True,
        "status": "UNRESOLVED",
        "real_experiments_started": False,
        "real_experiments_disabled": True,
        "machine_gate_required": True,
        "chatgpt_woken": False,
        "review_generated": False,
        "reasons": [],
        "rounds": [],
    }
    repo = ReadOnlyRepository(Path(repo_root))
    try:
        config_raw = repo.read(config_path)
        config = _json(config_raw, "config")
        requests = _json(repo.read(requests_path), "requests")
        if config.get("schema_version") != 1 or requests.get("schema_version") != 1:
            raise DetectionError("unsupported config or requests schema_version")
        if config.get("ALLOW_REAL_EXPERIMENTS") is not False:
            raise DetectionError("ALLOW_REAL_EXPERIMENTS must be explicitly false")
        if not isinstance(config.get("enabled"), bool):
            raise DetectionError("config.enabled must be boolean")
        result["configured_enabled"] = config["enabled"]
        rounds = requests.get("rounds")
        if not isinstance(rounds, list):
            raise DetectionError("requests.rounds must be a list")
        identifiers = [item.get("round_id") for item in rounds if isinstance(item, dict)]
        if any(identifiers.count(identifier) > 1 for identifier in identifiers):
            raise DetectionError("duplicate round_id in requests")
        result["rounds"] = [inspect_round(repo, request, config_path, config_raw, config)
                            for request in rounds]
        result["status"] = max((item["status"] for item in result["rounds"]),
                               key=SEVERITY.__getitem__, default="NO_ROUNDS")
        result["reasons"] = ["READ_ONLY_DETECTOR_NO_REAL_TASK_STARTED"]
    except (DetectionError, OSError) as exc:
        result.update(status="STOP", reasons=[str(exc), "READ_FAILURE_FAIL_CLOSED"])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", default="research/agent_loop/config.json")
    parser.add_argument("--requests", default="research/agent_loop/requests.json")
    parser.add_argument("--output", type=Path, help="Optional explicit output; stdout is the default")
    args = parser.parse_args(argv)
    result = detect(args.repo_root, args.config, args.requests)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 2 if result["status"] in ("STOP", "UNRESOLVED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
