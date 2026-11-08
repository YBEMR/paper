"""Pinned-input and artificial explicit-fork checks; no real thermal/search."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from research.chapter4_scheduler.tests.test_method import FakeClock
from research.chapter4_scheduler.tests.test_graph_core import fixture
from research.chapter4_scheduler.blocking.core import reconstruct
from research.chapter4_scheduler.blocking.method import candidate_packets,energy_targets
from research.chapter4_scheduler import graph_core
from heuristic_common import decode_plan,plan_from_candidate
from schedules import validate_schedule
from timing import MethodBudget
from thermal import Exhausted
from .input import load_c01,SOURCE,SOURCE_SHA256


def fork_fixture():
    specs=[{"id":"fork.root","unit":"CPU1","start":"0"},
           {"id":"fork.left","unit":"CPU1","start":"5","duration_L":"10"},
           {"id":"fork.right","unit":"CPU2","start":"5"},
           {"id":"fork.join","unit":"GPU0","start":"10"},
           {"id":"side.first","unit":"NPU0","start":"0"},
           {"id":"side.last","unit":"NPU0","start":"5"}]
    for item in specs:item.update(opp="H",activity_H="3",activity_L="1")
    dependencies=[("fork.root","fork.left"),("fork.root","fork.right"),
                  ("fork.left","fork.join"),("fork.right","fork.join"),("side.first","side.last")]
    instance,candidate=fixture(specs,dependencies=dependencies,second_scene=True)
    for scene in instance["scenarios"]:
        sid=scene["id"];ids={s["id"]:sid+"::"+s["id"] for s in scene["stage_instances"]}
        groups={"fork":[],"side":[]}
        for stage in scene["stage_instances"]:
            old=stage["id"];group=old.split(".")[0]
            stage.update(id=ids[old],request_id=sid+"::"+group)
            groups[group].append(ids[old])
        scene["requests"]=[{"id":sid+"::"+group,"release_ms":"0","deadline_ms":"100","stage_instance_ids":members} for group,members in groups.items()]
        scene["dependencies"]=[[ids[a],ids[b]] for a,b in scene["dependencies"]]
        for row in candidate["scenes"][sid]:row["stage_id"]=ids[row["stage_id"]]
    return instance,candidate


class InputTests(unittest.TestCase):
    def setUp(self):
        self.clock=FakeClock();self.budget=MethodBudget(30,clock=self.clock)

    def test_exact_original_input_with_all_modes_and_scenes(self):
        value=json.loads(SOURCE.read_bytes());config,instance=load_c01(self.budget)
        self.assertEqual(config,value["config"]);self.assertEqual(instance,value["instance"])
        self.assertEqual(len(instance["stage_modes"]),8)
        self.assertEqual(sum(map(len,instance["stage_modes"].values())),72)
        self.assertEqual([len(s["stage_instances"]) for s in instance["scenarios"]],[6,6])

    def test_instance_horizon_not_legacy_default_and_root_unchanged(self):
        self.clock.now+=7;root=(self.budget.start,self.budget.deadline,self.budget.clock)
        config,instance=load_c01(self.budget)
        self.assertEqual(instance["window_ms"],"230");self.assertEqual(config["defaults"]["window_ms"],"400")
        self.assertEqual(root,(self.budget.start,self.budget.deadline,self.budget.clock));self.assertEqual(self.budget.elapsed,7)

    def test_loading_and_hash_checks_are_charged_to_original_root(self):
        original=Path.read_bytes
        def delayed(path):self.clock.now+=2;return original(path)
        with patch.object(Path,"read_bytes",delayed):load_c01(self.budget)
        self.assertEqual(self.budget.elapsed,2)

    def test_expired_root_does_not_read_input(self):
        self.clock.now=1030
        with patch.object(Path,"read_bytes",side_effect=AssertionError("NO_READ_AFTER_CUTOFF")),self.assertRaises(Exhausted):load_c01(self.budget)

    def test_changed_input_or_reference_payload_rejected_before_export(self):
        for raw in (SOURCE.read_bytes()+b" ",b'{"candidate":{}}'):
            with self.subTest(raw_length=len(raw)),tempfile.TemporaryDirectory(dir="/tmp",prefix="MOCK_ONLY-C01-input-") as tmp:
                path=Path(tmp)/"input.json";path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,"FILE_DRIFT"):load_c01(self.budget,source=path)

    def test_only_candidate_free_common_input_is_read(self):
        paths=[];original=Path.read_bytes
        def read(path):
            paths.append(path.resolve());self.assertEqual(path.resolve(),SOURCE.resolve());return original(path)
        with patch.object(Path,"read_bytes",read),patch("p0_batch.run_p0.fresh_input",side_effect=AssertionError("NO_ABAC_LOADER")):
            load_c01(self.budget)
        self.assertEqual(paths,[SOURCE.resolve()])

    def test_calls_return_independent_objects_without_shared_mapping(self):
        config,a=load_c01(self.budget);expected=deepcopy(a);a["stage_modes"].clear();config["platform"].clear()
        config,b=load_c01(self.budget);self.assertEqual(b,expected);self.assertTrue(config["platform"])
        self.assertNotIn("fixed_deployment",b);self.assertNotIn("formal_initial_solution",b)

    def test_shared_identity_and_subset_legal_support_preserved(self):
        config,i=load_c01(self.budget)
        first,second=i["scenarios"]
        shared=lambda s:{r["shared_stage_id"] for r in s["stage_instances"]}
        self.assertEqual(shared(first)&shared(second),{"L1.s0001","L1.s0002","L1.s0003","L1.s0004"})
        self.assertEqual({m["unit_id"] for m in i["stage_modes"]["S2.s0001"]},{"CPU1","CPU2"})
        self.assertEqual({m["unit_id"] for m in i["stage_modes"]["L1.s0002"]},{"CPU1","CPU2","GPU0","NPU0"})
        self.assertTrue(all({m["opp_id"] for m in modes}=={"L","M","H"} for modes in i["stage_modes"].values()))


class ExplicitForkTests(unittest.TestCase):
    def setUp(self):
        self.instance,self.candidate=fork_fixture();self.budget=MethodBudget(30,clock=FakeClock())
        self.assertEqual(validate_schedule(self.instance,self.candidate)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")

    def test_fork_join_propagates_both_parents_without_three_stage_template(self):
        packet=reconstruct(self.instance,self.candidate,"S0",["S0::fork.left"],{"S0::fork.left":"L"},budget=self.budget)
        self.assertEqual(packet["state"],"COMPLETE_LEGAL_CANDIDATE",packet)
        self.assertGreaterEqual(F(packet["start_ms"]["S0::fork.join"]),max(F(packet["end_ms"]["S0::fork.left"]),F(packet["end_ms"]["S0::fork.right"])))
        actual={(e["from"],e["to"]) for e in packet["edges"] if "task_dependency" in e["reasons"]}
        self.assertEqual(actual,{tuple(e) for e in self.instance["scenarios"][0]["dependencies"]})
        self.assertEqual(packet["candidate"]["scenes"]["S1"],self.candidate["scenes"]["S1"])

    def test_shared_CPU_domain_remains_a_resource_with_different_OPPs(self):
        packet=reconstruct(self.instance,self.candidate,"S0",["S0::fork.left"],{"S0::fork.left":"L"},budget=self.budget)
        self.assertTrue(any("shared_domain_different_opp" in e["reasons"] for e in packet["edges"]))
        self.assertGreaterEqual(F(packet["start_ms"]["S0::fork.right"]),F(packet["end_ms"]["S0::fork.left"]))

    def test_reversing_resource_order_never_deletes_mandatory_DAG_edge(self):
        p=reconstruct(self.instance,self.candidate,"S0",["S0::fork.root","S0::fork.left"],{},orientation="reverse",budget=self.budget)
        self.assertEqual(p["state"],"RECONSTRUCTION_REJECTED");self.assertEqual(p["reason"],"SKELETON_DIRECTED_CYCLE")
        self.assertTrue(any(e["from"]=="S0::fork.root" and e["to"]=="S0::fork.left" and "task_dependency" in e["reasons"] for e in p["edges"]))

    def test_missing_branch_or_early_join_is_illegal(self):
        missing=deepcopy(self.candidate);missing["scenes"]["S0"]=[r for r in missing["scenes"]["S0"] if r["stage_id"]!="S0::fork.right"]
        self.assertEqual(validate_schedule(self.instance,missing)["reason"],"INCOMPLETE_STAGE_COVERAGE")
        early=deepcopy(self.candidate);next(r for r in early["scenes"]["S0"] if r["stage_id"]=="S0::fork.join")["start_ms"]="5"
        self.assertEqual(validate_schedule(self.instance,early)["reason"],"DEPENDENCY_VIOLATION")

    def test_shared_deployment_is_still_required_across_scenes(self):
        wrong=deepcopy(self.candidate);next(r for r in wrong["scenes"]["S1"] if r["stage_id"]=="S1::fork.join")["unit"]="NPU0"
        self.assertEqual(validate_schedule(self.instance,wrong)["reason"],"SHARED_DEPLOYMENT_MISMATCH")

    def test_original_decoder_accepts_explicit_diamond_and_request_groups(self):
        plan=plan_from_candidate(self.instance,self.candidate,budget=self.budget)
        decoded=decode_plan(self.instance,plan,budget=self.budget)
        self.assertIsNotNone(decoded);self.assertEqual(validate_schedule(self.instance,decoded)["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")
        self.assertEqual(len(decoded["scenes"]["S0"]),6)

    def test_original_target_and_packet_generation_preserve_full_graph(self):
        targets=energy_targets(self.instance,self.candidate,self.budget)
        self.assertTrue(targets);packets=[]
        generator=candidate_packets(self.instance,self.candidate,self.budget)
        for _ in range(4):
            p=next(generator,None)
            if p is None:break
            packets.append(p);self.assertEqual(validate_schedule(self.instance,p["candidate"])["state"],"SCHEDULE_VALID_THERMAL_UNCHECKED")
            self.assertEqual({sid:len(rows) for sid,rows in p["candidate"]["scenes"].items()},{"S0":6,"S1":6})
        self.assertTrue(packets)


if __name__=="__main__":unittest.main()
