"""Static request fixtures, archived comparisons and synthetic doubles only."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import execute
import unit

MANIFEST = unit.read(unit.HERE / "manifest.json")
SPECS = MANIFEST["cases"]
CASES = {c["id"]:c for c in unit.design.cases()}


class PressureTests(unittest.TestCase):
    def test_three_registered_absolute_streams(self):
        self.assertEqual(len(SPECS), 3)
        for spec in SPECS:
            with self.subTest(case=spec["id"]):
                scenes = unit.design.make_scenes(CASES[spec["id"]])
                self.assertEqual(unit.verify_stream(scenes, spec), spec["request_stream_sha256"])
                local = [[q.id,q.app,q.release_ns,q.deadline_ns] for s in scenes for q in s.requests]
                wrong = hashlib.sha256(json.dumps(local,separators=(",",":")).encode()).hexdigest()
                self.assertNotEqual(wrong, spec["request_stream_sha256"])
                shifted = [scenes[0], replace(scenes[1],start_ns=scenes[1].start_ns+1), *scenes[2:]]
                with self.assertRaisesRegex(ValueError, "digest"):
                    unit.verify_stream(shifted, spec)

    def test_selected_schedule_has_500_absolute_completions(self):
        scenes = unit.design.make_scenes(CASES[SPECS[1]["id"]])
        phases = [[SimpleNamespace(deadline_feasible=True,completions_ns={
            q.id:q.deadline_ns-31 for q in s.requests})] for s in scenes]
        rows = unit.completions(scenes, phases, [unit.events.OPPS[0]]*4)
        self.assertEqual([[r["request_id"],r["app_id"],r["release_ns"],r["deadline_ns"]]
                          for r in rows],unit.absolute_requests(scenes))
        self.assertTrue(all(r["completion_ns"] == r["deadline_ns"]-31 and r["slack_ns"] == 31 for r in rows))
        del phases[-1][0].completions_ns[scenes[-1].requests[-1].id]
        with self.assertRaisesRegex(ValueError,"coverage"):
            unit.completions(scenes,phases,[unit.events.OPPS[0]]*4)

    def test_temperature_guards(self):
        case = CASES[SPECS[0]["id"]]
        self.assertEqual(unit.check_thermal(case),27.5)
        with self.assertRaisesRegex(ValueError,"temperature"):
            unit.check_thermal(dict(case,ambient=25))
        with patch.object(unit.joint,"INITIAL",np.full(4,27.5)):
            with self.assertRaisesRegex(ValueError,"inlet"):
                unit.check_thermal(case)
        with self.assertRaisesRegex(ValueError,"ambient"):
            unit.build_tables([], "A", 25)

    def test_misbuilt_kernel_rejected_without_evaluation(self):
        sched = SimpleNamespace(deadline_feasible=True,duration_ns=np.array([1]),active_w=None,transfer_w=None)
        bad = SimpleNamespace(kw={"ambient_C":25},initial=unit.INITIAL)
        with patch.object(unit.events,"time_scene",return_value=sched), patch.object(unit,"compile_scene",return_value=bad):
            with self.assertRaisesRegex(ValueError,"compiled kernel"):
                unit.build_tables([None],"A",27.5)

    def test_six_archives_and_gate(self):
        for spec in SPECS:
            for d in ("A","C"):
                path = unit.RESEARCH.parent / spec["historical_ac"][d]["path"]
                with np.load(path,allow_pickle=False) as old:
                    s,e = old["status"],old["energy_j"]
                self.assertEqual(np.bincount(s,minlength=4).tolist(),[472392,0,59049,0])
                self.assertEqual(unit.compare_control(s,e,path),0.)
                e[np.flatnonzero(s)[0]] += .01
                with self.assertRaisesRegex(ValueError,"energy mismatch"):
                    unit.compare_control(s,e,path)
        jobs = MANIFEST["execution_order"]
        controls = [dict(**job,certificate="NO_SAFE",control_max_abs_energy_error_j=0.) for job in jobs[:6]]
        execute.gate(6,controls,jobs)
        with self.assertRaises(RuntimeError):
            execute.gate(6,controls[:-1],jobs)
        with self.assertRaises(RuntimeError):
            execute.gate(6,controls[:-1]+[dict(controls[-1],certificate="UNRESOLVED")],jobs)
        with self.assertRaises(RuntimeError):
            execute.gate(6,controls[:5]+[controls[0]],jobs)

    def test_production_path_with_stub_response_operators(self):
        # Only one dummy action per scene is enabled. No scheduler, compilation
        # or numerical thermal evaluator runs in this test.
        from tempfile import TemporaryDirectory
        from contextlib import ExitStack
        case = CASES[SPECS[0]["id"]]
        scenes = unit.design.make_scenes(case)
        inlets = []
        ambients = []
        local_flag = 1
        def schedule(platform, scene, deployment, opp):
            return SimpleNamespace(deadline_feasible=opp == unit.events.OPPS[0],
                duration_ns=np.array([1]),active_w=None,transfer_w=None,
                completions_ns={q.id:q.deadline_ns-31 for q in scene.requests})
        class FakeKernel:
            fallback_calls = 0
            def __init__(self, kw):
                self.kw, self.initial = kw, np.array(kw["initial_C"])
            def batch(self, entries):
                inlets.append(entries.tolist())
                return np.ones(len(entries)), entries+1., np.full(len(entries),local_flag,dtype=np.int8)
        def compile_stub(duration, activity, transfer, kw):
            ambients.append(kw["ambient_C"])
            return FakeKernel(kw)
        def replay(platform, scene_list, deployment, opps, ambient, **kwargs):
            self.assertEqual((ambient,kwargs),(27.5,dict(leakage=True,variation="base",reset=False)))
            records = [dict(scene=s.name,opp=opps[i],start_ns=s.start_ns,service_end_ns=s.service_end_ns,
                end_ns=s.end_ns,entry_c=[30.+i]*4,final_c=[31.+i]*4,
                deadline_ok=True,required=len(s.requests),min_slack_ns=31,energy_j=1.,
                peak_lower_c=[31.+i]*4,peak_upper_c=[31.+i]*4) for i,s in enumerate(scene_list)]
            if local_flag == 0:
                records[-1]["peak_lower_c"] = records[-1]["peak_upper_c"] = [81.]*4
            return dict(fully_replayed=True,deadline_ok=True,required=500,completed=500,
                thermal_status="SAFE" if local_flag else "VIOLATION",feasible=bool(local_flag),energy_j=4.,scene_rows=records,final_c=[34.]*4,
                peak_lower_c=records[-1]["peak_lower_c"],peak_upper_c=records[-1]["peak_upper_c"])
        with TemporaryDirectory() as temp, ExitStack() as stack:
            stack.enter_context(patch.object(unit.events,"time_scene",side_effect=schedule))
            stack.enter_context(patch.object(unit,"compile_scene",side_effect=compile_stub))
            probe = stack.enter_context(patch.object(unit.events,"replay_sequence",side_effect=replay))
            job = dict(deployment="D001",case_id=case["id"])
            result = unit.run_unit(MANIFEST,job,Path(temp))
            self.assertEqual(result["certificate"],"MIN_SAFE")
            self.assertEqual(len(unit.read(Path(temp)/"requests.json")),500)
            self.assertEqual(ambients,[27.5]*4)
            self.assertEqual(inlets,[[[30.+i]*4] for i in range(4)])
            probe.assert_called_once()
            result["physical"]["scene_rows"][1]["entry_c"] = [30.]*4
            with self.assertRaisesRegex(ValueError,"scene replay"):
                unit.verify_replay(result["physical"],unit.read(Path(temp)/"requests.json"),scenes,[unit.events.OPPS[0]]*4,1,4.)

            local_flag = 0
            probe.reset_mock()
            diagnostic = Path(temp)/"diagnostic"
            diagnostic.mkdir()
            result = unit.run_unit(MANIFEST,job,diagnostic)
            self.assertEqual((result["certificate"],result["selection_role"]),("NO_SAFE","diagnostic"))
            self.assertIsNone(result["strict_minimum_known_safe_j"])
            self.assertEqual(len(unit.read(diagnostic/"requests.json")),500)
            probe.assert_called_once()

    def test_batch_stops_before_expansion_after_control_error(self):
        from tempfile import TemporaryDirectory
        from contextlib import ExitStack
        records = []
        def dispatch(index, job, subject, digest):
            records.append(job)
            if index == 5:
                raise ValueError("reference mismatch")
            return dict(**job,certificate="NO_SAFE",control_max_abs_energy_error_j=0.)
        with TemporaryDirectory() as temp, ExitStack() as stack:
            raw = Path(temp)/"mock"
            stack.enter_context(patch.object(execute,"RAW",raw))
            stack.enter_context(patch.object(execute.sys,"argv",["test","--execute-approved","f"*40]))
            stack.enter_context(patch.object(execute,"committed_freeze",return_value="mock"))
            stack.enter_context(patch.object(execute,"verify_freeze",return_value=MANIFEST))
            stack.enter_context(patch.object(execute,"dispatch",side_effect=dispatch))
            with self.assertRaisesRegex(ValueError,"reference mismatch"):
                execute.main()
            self.assertEqual(records,MANIFEST["execution_order"][:6])
            self.assertEqual(execute.read(raw/"stop.json")["reason"],"STOP")
            with self.assertRaises(FileExistsError):
                execute.main()
            self.assertEqual(len(records),6)

    def test_worker_binds_head_and_exact_freeze_before_science(self):
        from contextlib import ExitStack
        import subprocess
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp, ExitStack() as stack:
            root = Path(temp).resolve()
            here = root / "research" / "fixture"
            here.mkdir(parents=True)
            path = here / "execution_freeze.json"
            frozen = b'{"mock":true}\n'
            path.write_bytes(frozen)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(root), "-c", "core.autocrlf=false",
                     "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "commit.gpgsign=false", *args], text=True).strip()

            git("init", "--quiet")
            git("add", "--", "research/fixture/execution_freeze.json")
            git("commit", "--quiet", "-m", "pin mock freeze")
            stale = git("rev-parse", "HEAD")
            git("commit", "--quiet", "--allow-empty", "-m", "advance mock head")
            subject = git("rev-parse", "HEAD")
            digest = hashlib.sha256(frozen).hexdigest()
            raw = here / "output"
            out = raw / "00"
            out.mkdir(parents=True)
            job = MANIFEST["execution_order"][0]
            stack.enter_context(patch.object(execute, "ROOT", root))
            stack.enter_context(patch.object(execute, "HERE", here))
            stack.enter_context(patch.object(execute, "RAW", raw))
            stack.enter_context(patch.dict(execute.os.environ, PRESSURE_UNIT_START="0"))
            inputs = stack.enter_context(patch.object(execute, "verify_freeze", return_value=MANIFEST))
            science = stack.enter_context(patch.object(unit, "run_unit", return_value={}))
            for label, pin, expected, disk, error in [
                ("stale HEAD", stale, digest, frozen, "checkout SHA"),
                ("wrong reservation digest", subject, "0"*64, frozen, "reservation freeze SHA256"),
                ("edited checkout", subject, digest, b'{"mock":false}\n', "differs from approved commit"),
                ("line endings", subject, digest, frozen.replace(b"\n", b"\r\n"), "differs from approved commit"),
            ]:
                with self.subTest(label=label):
                    path.write_bytes(disk)
                    execute.write(out / "reservation.json", dict(index=0, job=job, subject=pin, freeze_sha256=expected))
                    with self.assertRaisesRegex(RuntimeError, error):
                        execute.worker(0)
                    inputs.assert_not_called()
                    science.assert_not_called()
                    self.assertEqual({p.name for p in out.iterdir()}, {"reservation.json"})

            path.write_bytes(frozen)
            execute.write(out / "reservation.json", dict(index=0, job=job, subject=subject, freeze_sha256=digest))
            execute.worker(0)
            inputs.assert_called_once_with(frozen)
            science.assert_called_once_with(MANIFEST, job, out)
            self.assertEqual(execute.read(out / "result.json")["subject"], subject)
            self.assertTrue((out / "finished.json").is_file())

    def test_deadline_once_without_a_worker(self):
        import subprocess
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock
        with TemporaryDirectory() as temp, patch.object(execute,"RAW",Path(temp)):
            child = Mock()
            child.wait.side_effect = [subprocess.TimeoutExpired("mock",120), 1]
            with patch.object(execute.subprocess,"Popen",return_value=child) as spawn:
                with self.assertRaises(subprocess.TimeoutExpired):
                    execute.dispatch(0,MANIFEST["execution_order"][0],"f"*40,"mock")
                spawn.assert_called_once()
                child.kill.assert_called_once()
            ledger = [json.loads(line) for line in (Path(temp)/"ledger.jsonl").read_text().splitlines()]
            self.assertEqual([r["event"] for r in ledger],["reserve","close"])
            self.assertEqual((ledger[0]["cap_s"],ledger[1]["status"]),(120,"DEADLINE"))


if __name__ == "__main__":
    unittest.main()
