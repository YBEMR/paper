"""Artificial launcher checks; no subprocess, workload, or thermal evaluation."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from . import run as launcher


class LauncherTests(TestCase):
    def test_success_consumes_four_fresh_slots_once(self):
        self.exercise(False)

    def test_post_failure_stops_without_retry_or_next_claim(self):
        self.exercise(True)

    def exercise(self, fail_post):
        with tempfile.TemporaryDirectory(dir="/tmp", prefix="mock-mechanism-launcher-") as tmp:
            out = Path(tmp)
            slots = [{"id": str(i), "case": case, "allow_blocking_edges": enabled}
                     for i, (case, enabled) in enumerate(launcher.ORDER)]
            launcher.save(out / "plan.json", {"slots": slots, "budgets": {"calendar_s": 1800}})
            def fake_process(cmd, **kwargs):
                slot = cmd[cmd.index("--slot")+1]
                folder = out / "calls" / slot
                phase = cmd[4]
                if phase == "worker":
                    launcher.save(folder / "method_return.json", {"safe": True})
                return SimpleNamespace(returncode=int(fail_post and phase == "post"), stdout="ARTIFICIAL", stderr="")
            with patch.object(launcher, "verify"), \
                    patch.object(launcher.subprocess, "run", side_effect=fake_process) as process, \
                    patch("builtins.print"):
                failed = launcher.run(out)
            self.assertEqual(bool(failed), fail_post)
            self.assertEqual(process.call_count, 2 if fail_post else 8)
            result = launcher.read(out / "batch_return.json")
            self.assertEqual(len(result["consumed_method_slots"]), 1 if fail_post else 4)
            if fail_post:
                self.assertFalse((out / "calls/1").exists())
            with patch.object(launcher, "verify"), self.assertRaises(FileExistsError):
                launcher.run(out)
