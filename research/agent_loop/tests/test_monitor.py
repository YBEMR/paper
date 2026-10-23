"""Detector tests use isolated TEST_ONLY Git repositories, never live reviews."""

import contextlib
import hashlib
import io
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.request


SOURCE = Path(__file__).resolve().parents[1] / "monitor.py"
monitor = types.ModuleType("agent_loop_monitor_under_test")
monitor.__file__ = str(SOURCE)
# Avoid generating a __pycache__ in the shared repository during tests.
exec(compile(SOURCE.read_text(encoding="utf-8"), str(SOURCE), "exec"), monitor.__dict__)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class WorkflowStaticTests(unittest.TestCase):
    """Regression checks for runner context placement; no Actions are triggered."""

    def setUp(self):
        self.workflow = (SOURCE.parents[2] / ".github/workflows/agent-loop-watch.yml").read_text(encoding="utf-8")

    def test_runner_context_is_not_used_before_steps(self):
        steps = re.search(r"(?m)^    steps:\s*$", self.workflow)
        self.assertIsNotNone(steps)
        # GitHub's context table excludes `runner` from jobs.<job_id>.env.
        self.assertNotRegex(self.workflow[:steps.start()], r"\$\{\{\s*runner[.\[]")

    def test_detector_and_artifact_share_runner_temporary_output(self):
        commands = re.findall(r"(?m)^\s+run:\s*(.+)$", self.workflow)
        self.assertEqual(commands, [
            'python3 -B research/agent_loop/monitor.py --repo-root "$GITHUB_WORKSPACE" '
            '--output "$RUNNER_TEMP/agent-loop-status.json" '
            "${{ github.event_name == 'schedule' && '--skip-if-disabled' || '' }}"
        ])
        # runner is allowed in jobs.<job_id>.steps.with, where upload reads it.
        self.assertIn("path: ${{ runner.temp }}/agent-loop-status.json", self.workflow)
        self.assertNotIn("AGENT_LOOP_OUTPUT", self.workflow)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-loop-monitor-TEST_ONLY-",
                                              dir=os.environ.get("AGENT_LOOP_TEST_TMP"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.round_id = "TEST-ONLY-fixture-001"
        self.base = "research/agent_loop"
        self.manifest_path = f"{self.base}/rounds/{self.round_id}/manifest.json"
        self.proposal_path = f"{self.base}/rounds/{self.round_id}/next_proposal.json"
        self.report_path = f"{self.base}/rounds/{self.round_id}/report.md"
        self.config = {
            "schema_version": 1, "enabled": False, "ALLOW_REAL_EXPERIMENTS": False,
            "mode": "TEST_ONLY", "repository": {"remote_url": "https://example.invalid/TEST-ONLY/repo"},
        }
        self.put_json(f"{self.base}/config.json", self.config)
        self.put_json(self.proposal_path, {"mode": "TEST_ONLY", "command": "NEVER_EXECUTE_TEST_FIXTURE"})
        self.put(self.report_path, b"TEST ONLY: synthetic report, no experiment.\n")
        self.put("inputs/fixture.txt", b"synthetic fixture input\n")
        self.manifest = {
            "schema_version": 1, "round_id": self.round_id,
            "repository": self.config["repository"]["remote_url"], "mode": "TEST_ONLY", "evidence_class": "TEST_ONLY",
            "config_sha256": digest(self.read(f"{self.base}/config.json")),
            "proposal_path": self.proposal_path, "proposal_sha256": digest(self.read(self.proposal_path)),
            "report_md_path": self.report_path, "report_md_sha256": digest(self.read(self.report_path)),
            "source_files": {"inputs/fixture.txt": digest(self.read("inputs/fixture.txt"))},
            "evidence_files": {},
        }
        self.put_json(self.manifest_path, self.manifest)
        self.request = {"round_id": self.round_id, "subject_commit_sha": None,
                        "manifest_path": self.manifest_path, "status": "WAITING_REVIEW"}
        self.write_requests()
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "TEST_ONLY subject fixture")
        self.subject = self.git("rev-parse", "HEAD").strip()
        self.request["subject_commit_sha"] = self.subject
        self.write_requests()
        self.review_path = f"{self.base}/reviews/{self.round_id}/{self.subject}.json"

    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "user.name=TEST_ONLY fixture", "-c", "user.email=test@example.invalid",
             "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={self.root / 'NO_HOOKS'}", *args],
            cwd=self.root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, shell=False,
        )
        return result.stdout

    def put(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def put_json(self, relative, value):
        self.put(relative, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())

    def read(self, relative):
        return (self.root / relative).read_bytes()

    def write_requests(self):
        self.put_json(f"{self.base}/requests.json", {"schema_version": 1, "rounds": [self.request]})

    def review(self, decision="APPROVE_ONE_STEP", **changes):
        # An intentionally unsigned TEST_ONLY declaration; it cannot authorize anything.
        value = {
            "schema_version": 1, "mode": "TEST_ONLY", "round_id": self.round_id,
            "subject_commit_sha": self.subject, "repository": self.config["repository"]["remote_url"],
            "manifest_path": self.manifest_path, "manifest_sha256": digest(self.read(self.manifest_path)),
            "proposal_sha256": self.manifest["proposal_sha256"],
            "report_md_sha256": self.manifest["report_md_sha256"],
            "config_sha256": self.manifest["config_sha256"], "evidence_class": "TEST_ONLY",
            "decision": decision, "signature": None,
        }
        value.update(changes)
        self.put_json(self.review_path, value)

    def detect(self):
        return monitor.detect(self.root)

    def assert_status(self, expected):
        result = self.detect()
        self.assertEqual(result["status"], expected, result)
        self.assertTrue(result["detector_only"])
        self.assertTrue(result["machine_gate_required"])
        self.assertFalse(result["real_experiments_started"])
        self.assertFalse(result["chatgpt_woken"])
        self.assertFalse(result["review_generated"])
        return result

    def test_unpublished_subject_never_approves(self):
        self.request["subject_commit_sha"] = None
        self.write_requests()
        self.assert_status("UNPUBLISHED_WAITING_REVIEW")

    def test_missing_review_waits(self):
        result = self.assert_status("WAITING_REVIEW")
        self.assertFalse(result["rounds"][0]["review"]["present"])

    def test_markdown_alone_cannot_approve(self):
        self.put(self.review_path[:-5] + ".md", b"TEST ONLY: approved=true, no authority\n")
        self.assert_status("WAITING_REVIEW")

    def test_unsigned_declaration_still_requires_gate(self):
        self.review()
        result = self.assert_status("APPROVAL_REQUIRES_MACHINE_GATE")
        self.assertFalse(result["rounds"][0]["review"]["verified"])
        self.assertNotEqual(result["status"], "READY")

    def test_review_commit_moves_head_without_invalidating_subject(self):
        self.review()
        self.git("add", ".")
        self.git("commit", "-qm", "TEST_ONLY review declaration and subject pointer")
        self.assertNotEqual(self.git("rev-parse", "HEAD").strip(), self.subject)
        result = self.assert_status("APPROVAL_REQUIRES_MACHINE_GATE")
        self.assertEqual(result["rounds"][0]["subject_commit_sha"], self.subject)

    def test_local_replace_refs_cannot_reinterpret_fixed_subject(self):
        self.review()
        original_manifest = self.read(self.manifest_path)
        self.manifest["fixture_annotation"] = "replacement object must not be read"
        self.put_json(self.manifest_path, self.manifest)
        self.git("add", ".")
        self.git("commit", "-qm", "TEST_ONLY replacement object")
        replacement = self.git("rev-parse", "HEAD").strip()
        self.git("replace", self.subject, replacement)
        self.put(self.manifest_path, original_manifest)
        self.assert_status("APPROVAL_REQUIRES_MACHINE_GATE")

    def test_changed_report_invalidates_original_declaration(self):
        self.review()
        self.put(self.report_path, b"TEST ONLY changed report\n")
        self.assert_status("STOP")

    def test_changed_proposal_invalidates_original_declaration(self):
        self.review()
        self.put_json(self.proposal_path, {"command": "NEVER_EXECUTE_CHANGED_FIXTURE"})
        self.assert_status("STOP")

    def test_changed_manifest_invalidates_original_declaration(self):
        self.review()
        self.manifest["unused_annotation"] = "changed fixture"
        self.put_json(self.manifest_path, self.manifest)
        self.assert_status("STOP")

    def test_changed_source_invalidates_original_declaration(self):
        self.review()
        self.put("inputs/fixture.txt", b"different synthetic input")
        self.assert_status("STOP")

    def test_changed_config_fails_closed(self):
        self.review()
        self.config["fixture_annotation"] = "changed config"
        self.put_json(f"{self.base}/config.json", self.config)
        self.assert_status("UNRESOLVED")

    def test_bound_file_missing_fails_closed(self):
        (self.root / self.report_path).unlink()
        self.assert_status("UNRESOLVED")

    def test_boolean_approved_is_not_a_decision(self):
        self.review(decision=None, approved=True)
        self.assert_status("UNRESOLVED")

    def test_wrong_subject_review_is_not_bound(self):
        self.review(subject_commit_sha="a" * 40)
        self.assert_status("STOP")

    def test_stop_and_revise_are_conservative_even_unsigned(self):
        for decision in ("STOP", "REVISE"):
            with self.subTest(decision=decision):
                self.review(decision=decision)
                self.assert_status(decision)

    def test_request_stop_or_revise_cannot_be_bypassed_by_approval(self):
        self.review()
        for status in ("STOP", "REVISE"):
            with self.subTest(status=status):
                self.request["status"] = status
                self.write_requests()
                self.assert_status(status)

    def test_bad_config_or_index_json_stops(self):
        for path in (f"{self.base}/config.json", f"{self.base}/requests.json"):
            with self.subTest(path=path):
                original = self.read(path)
                self.put(path, b"{ truncated")
                self.assert_status("STOP")
                self.put(path, original)

    def test_bad_review_json_is_unresolved(self):
        self.put(self.review_path, b"{ truncated")
        self.assert_status("UNRESOLVED")

    def test_duplicate_json_fields_are_not_accepted(self):
        self.put(self.review_path, b'{"decision":"STOP","decision":"APPROVE_ONE_STEP"}')
        self.assert_status("UNRESOLVED")

    def test_subject_must_be_a_commit_not_a_tree(self):
        self.request["subject_commit_sha"] = self.git("rev-parse", "HEAD^{tree}").strip()
        self.write_requests()
        self.assert_status("UNRESOLVED")

    def test_path_traversal_in_manifest_request_fails_closed(self):
        for path in ("../secret", "F:/outside", "a\\b", "a//b", "/absolute"):
            with self.subTest(path=path):
                self.request["manifest_path"] = path
                self.write_requests()
                self.assert_status("UNRESOLVED")

    def test_enabling_real_experiments_stops_detector(self):
        self.config["ALLOW_REAL_EXPERIMENTS"] = True
        self.put_json(f"{self.base}/config.json", self.config)
        self.assert_status("STOP")

    def test_detector_does_not_write_worktree_or_git_directory(self):
        self.review()
        self.put("unrelated_dirty.txt", b"must remain byte-for-byte unchanged\n")
        def snapshot():
            return {str(path.relative_to(self.root)): digest(path.read_bytes())
                    for path in self.root.rglob("*") if path.is_file()}
        before = snapshot()
        self.assert_status("APPROVAL_REQUIRES_MACHINE_GATE")
        self.assertEqual(snapshot(), before)

    def test_no_network_or_research_subprocess_is_called(self):
        self.review()
        real_run = subprocess.run
        commands = []
        def read_only_git(command, **kwargs):
            commands.append(command)
            self.assertEqual(command[0], "git")
            self.assertEqual(command[1:6], ["--no-replace-objects", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false"])
            self.assertTrue(command[6] in ("show", "cat-file"), command)
            self.assertFalse(kwargs.get("shell", False))
            return real_run(command, **kwargs)
        with patch.object(monitor.subprocess, "run", side_effect=read_only_git), \
                patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")), \
                patch.object(urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
            self.assert_status("APPROVAL_REQUIRES_MACHINE_GATE")
        self.assertGreater(len(commands), 0)

    def test_cli_stdout_and_explicit_output_match(self):
        destination = self.root / "explicit-detector-output.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = monitor.main(["--repo-root", str(self.root), "--output", str(destination)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), json.loads(destination.read_text()))
        self.assertEqual(json.loads(stdout.getvalue())["status"], "WAITING_REVIEW")

    def test_disabled_polling_does_not_read_requests_or_git(self):
        self.put("inputs/fixture.txt", b"changed synthetic input")
        # Manual inspection still catches drift even when execution is disabled.
        self.assert_status("STOP")
        (self.root / self.base / "requests.json").unlink()
        with patch.object(monitor.subprocess, "run", side_effect=AssertionError("Git forbidden")), \
                patch.object(monitor.ReadOnlyRepository, "read", return_value=json.dumps(self.config).encode()) as read:
            result = monitor.detect(self.root, skip_if_disabled=True)
        read.assert_called_once_with(f"{self.base}/config.json")
        self.assertEqual(result["status"], "DISABLED")
        self.assertEqual(result["rounds"], [])
        self.assertFalse(result["configured_enabled"])
        self.assertFalse(result["real_experiments_started"])
        self.assertTrue(result["machine_gate_required"])

    def test_disabled_polling_still_rejects_invalid_or_unsafe_config(self):
        path = f"{self.base}/config.json"
        invalid = [b"{ truncated", b'{"enabled":false,"enabled":true}']
        for key, value in (("schema_version", 2), ("enabled", "false"),
                           ("enabled", None), ("ALLOW_REAL_EXPERIMENTS", True)):
            invalid.append(json.dumps({**self.config, key: value}).encode())
        for raw in invalid:
            with self.subTest(raw=raw):
                self.put(path, raw)
                self.assertEqual(monitor.detect(self.root, skip_if_disabled=True)["status"], "STOP")

    def test_enabled_polling_still_checks_round_drift(self):
        self.config["enabled"] = True
        self.put_json(f"{self.base}/config.json", self.config)
        self.manifest["config_sha256"] = digest(self.read(f"{self.base}/config.json"))
        self.put_json(self.manifest_path, self.manifest)
        self.git("add", ".")
        self.git("commit", "-qm", "TEST_ONLY enabled detector fixture")
        self.request["subject_commit_sha"] = self.git("rev-parse", "HEAD").strip()
        self.write_requests()
        self.assertEqual(monitor.detect(self.root, skip_if_disabled=True)["status"], "WAITING_REVIEW")
        self.put("inputs/fixture.txt", b"changed synthetic input")
        result = monitor.detect(self.root, skip_if_disabled=True)
        self.assertEqual(result["status"], "STOP")
        self.assertIn("CURRENT_BOUND_FILE_CHANGED: inputs/fixture.txt", result["rounds"][0]["reasons"])

    def test_cli_disabled_polling_writes_status_and_exits_successfully(self):
        self.put("inputs/fixture.txt", b"changed synthetic input")
        destination = self.root / "disabled-detector-output.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = monitor.main(["--repo-root", str(self.root), "--skip-if-disabled",
                                 "--output", str(destination)])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result, json.loads(destination.read_text()))
        self.assertEqual(result["status"], "DISABLED")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(monitor.main(["--repo-root", str(self.root)]), 2)


if __name__ == "__main__":
    unittest.main()
