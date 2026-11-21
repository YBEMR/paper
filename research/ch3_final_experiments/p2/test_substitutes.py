"""Run with --source-root PATH (repository root containing frozen research/). Zero science."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import evaluator
import pilot
from read_pilot import summarize
import search as s


class Timer:
    def __init__(self):
        self.t = 0
        self.clock = s.Clock(0, 60, lambda: self.t)


def quiet(*args):
    pass


def result(status):
    if status == "DEADLINE":
        return s.Result(status, 150, -3., None, None, None, ("late-a",))
    bounds = {"SAFE": (78, 80), "VIOLATION": (81, 82), "UNRESOLVED": (79, 81)}
    lo, hi = bounds[status]
    return s.Result(status, 500, 1., 50., (lo,)*4, (hi,)*4)


def candidates():
    return [s.Candidate(dep, (0,)*4, (float(i),)*4) for i, dep in enumerate(("A","C","D001","D015"))]


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT/"research/kim_multidnn_expansion/catalog.json").read_bytes())
        self.domain = s.Domain(self.catalog, ("C", "A", "D015", "D001"))
        self.timer = Timer()

    def test_all_bindings_and_capacity(self):
        full = s.Domain(self.catalog, self.catalog["search_order"])
        self.assertEqual(len(full.encode), 81)
        self.assertEqual(len({c[:4] for c in full.decode}), 31)
        for dep, chrom in full.encode.items():
            self.assertEqual(full.decode[chrom], dep)
            self.assertNotIn((*chrom[:4], 99), full.decode)
        for dep in self.domain.order:
            self.assertEqual(self.domain.encode[dep], full.encode[dep])
        for rejected in self.catalog["rejected_structures"]:
            self.assertNotIn(tuple(rejected["per_app_candidate_ids"]), [c[:4] for c in full.decode])
        with self.assertRaises(ValueError):
            s.Domain(self.catalog, ("X",))

    def test_kim_genetic_operators(self):
        rng = random.Random(13)
        full = s.Domain(self.catalog, self.catalog["search_order"])
        counts = Counter()
        children = {full.child("A", "D015", rng, counts) for _ in range(500)}
        self.assertTrue(children <= set(full.order))
        self.assertGreater(len(children), 2)
        self.assertGreater(counts["illegal_offspring"], 0)
        # Force crossover without mutation, then a single forced binding mutation.
        a, b = next((dep, other) for dep in full.order for other in full.order
                    if dep != other and full.encode[dep][:4] == full.encode[other][:4])
        forced = Mock()
        forced.random.side_effect = [0., 1., 1., 0.]
        forced.choice.side_effect = lambda options: options[-1] if len(options)==2 else full.encode[b][-1]
        self.assertEqual(full.child(a, b, forced, counts), b)
        forced.randrange.return_value = 4
        forced.choice.side_effect = lambda options: full.encode[b][-1]
        self.assertEqual(full.child(a, a, forced, counts), b)

    def test_setfreq_original_flow(self):
        path = []
        def observe(idx):
            opp = s.OPPS[idx]
            path.append(opp)
            if opp == "HLH":
                return None
            return 1. if opp == "LHL" else 10.
        idx, energy = s.setfreq(observe)
        self.assertEqual(path, ["HHH","HMH","HLH","HMH","MMH","LMH","LMH","LMM","LML",
                                "LHL","LML","LLL","HLL","MLL","LLL","LLH","LLM","LLL"])
        self.assertEqual((s.OPPS[idx], energy), ("LHL", 1.))
        self.assertEqual(s.setfreq(lambda _: 3.)[0], s.OPPS.index("HHH"))
        self.assertEqual(s.setfreq(lambda _: None), (None, float("inf")))
        path.clear()
        s.setfreq(lambda i: path.append(s.OPPS[i]) or (None if s.OPPS[i]=="LHL" else 1.))
        self.assertEqual(path[path.index("LHL")+1], "HHL")

    def test_lexicase_and_tolerance(self):
        a, b, c, _ = candidates()
        a = replace(a, scores=(1.,9.,1.,9.))
        b = replace(b, scores=(9.,1.,9.,1.))
        c = replace(c, opps=(None,0,0,0), scores=(float("inf"),0.,0.,0.))
        rng = random.Random(2)
        self.assertEqual({s.lexicase([a,b,c], rng) for _ in range(50)}, {"A","C"})
        worse = replace(b, opps=(None,None,0,0))
        self.assertEqual(s.lexicase([c,worse], rng), c.dep)
        near = replace(b, scores=tuple(x + 5e-10 for x in a.scores))
        self.assertEqual({s.lexicase([a,near], rng) for _ in range(50)}, {"A","C"})
        tied = replace(a, scores=(4.+5e-10,0.,0.,0.))
        self.assertEqual([x.dep for x in s.ranked([replace(b,scores=(4.,0.,0.,0.)),tied],self.domain)], ["A","C"])

    def test_same_pool_and_small_enum(self):
        def proxy(d,j,i):
            return self.domain.rank[d] + j + i/1000
        args = self.domain, proxy, 20261121, self.timer.clock, quiet
        p, i = s.kim_pool(*args)
        other, j = s.kim_pool(*args)
        self.assertTrue(s.paired(i,j))
        self.assertEqual(p,other)
        ref = s.setfreq_enum(self.domain, proxy)
        self.assertEqual(p[0],ref[0])
        self.assertEqual(i["counts"]["positions"],32)
        self.assertGreater(i["counts"]["deployment_hits"],0)
        self.assertFalse(s.paired(i, {**j, "pool":j["pool"][::-1]}))
        self.assertEqual(s.kim_pool(self.domain,lambda *args:None,1,self.timer.clock,quiet)[0],[])

    def test_generation_cutoff_excludes_partial_deployment(self):
        def slow(*args):
            self.timer.t += 1
            return 1.
        pool, info = s.kim_pool(self.domain,slow,1,s.Clock(0,3,lambda:self.timer.t),quiet)
        self.assertEqual((pool, info["reason"]), ([], "generation_cutoff"))
        self.assertEqual(info["counts"]["proxy_started"],3)
        self.assertEqual(info["counts"]["proxy_completed"],2)

    def test_safe_fallback_table(self):
        a,b,c,d = candidates()
        for pool, enhanced, statuses, reason, winner, dup in [
                ([a,b],False,["VIOLATION"],"first_only",None,0),
                ([a,b],True,["SAFE"],"first_safe","A",0),
                ([a,a,b,c,d],True,["VIOLATION","UNRESOLVED","SAFE"],"first_safe","D001",1),
                ([a,b,c,d],True,["DEADLINE","UNRESOLVED","VIOLATION"],"k_limit",None,0),
                ([a,b],True,["VIOLATION","UNRESOLVED"],"exhausted",None,0),
                ([],True,[],"empty_pool",None,0)]:
            with self.subTest(reason=reason):
                replay = Mock(side_effect=list(map(result,statuses)))
                summary = s.inspect_kim(pool, enhanced, replay, self.timer.clock, quiet)
                self.assertEqual((summary["reason"],summary["duplicates"]), (reason,dup))
                self.assertEqual(summary["winner"][0] if winner else summary["winner"],winner)
                self.assertEqual(replay.call_count,len(statuses))
                self.assertEqual([x["result"]["status"] for x in summary["attempts"]],statuses)

    def test_timeout_or_fault_never_certifies(self):
        def slow(*args):
            self.timer.t = 60
            return result("SAFE")
        summary = s.inspect_kim(candidates(), True, slow, self.timer.clock, quiet)
        self.assertEqual((summary["reason"],summary["winner"],summary["checks_started"]),("timeout",None,1))
        with self.assertRaises(ValueError):
            replace(result("UNRESOLVED"), status="SAFE")
        with self.assertRaises(ValueError):
            replace(result("SAFE"), energy_j=float("nan"))
        with self.assertRaises(ValueError):
            s.inspect_kim(candidates(),True,Mock(side_effect=ValueError("fault")),Timer().clock,quiet)

    def test_thermal_ga_generations_and_cache(self):
        visited, events = [], []
        def replay(dep, opps):
            self.assertIn(dep,self.domain.order)
            self.assertTrue(len(opps)==4 and all(0<=i<27 for i in opps))
            visited.append((dep,*opps))
            return replace(result("SAFE"), energy_j=float(sum(opps)))
        out = s.thermal_ga(self.domain,replay,7,self.timer.clock,lambda e,v:events.append((e,v)))
        self.assertEqual(out["positions"],128)
        self.assertEqual(out["completed_generations"],8)
        self.assertEqual(out["unique_started"],len(set(visited)))
        self.assertEqual(out["unique_completed"],len(visited))
        self.assertEqual(128,len(visited)+out["hits"])
        self.assertGreaterEqual(out["hits"],7)
        self.assertEqual(out["winner"],min(visited,key=lambda k:(sum(k[1:]),k)))
        logs = [v for e,v in events if e=="ga_generation"]
        self.assertEqual([v["gen"] for v in logs],list(range(8)))
        slots = [v for e,v in events if e=="ga_position"]
        for gen in range(1,8):
            self.assertEqual(slots[16*gen]["genome"],logs[gen-1]["best"])

    def test_thermal_deadline_retains_only_completed_witness(self):
        def slow(*args):
            self.timer.t += 20
            return result("SAFE")
        out=s.thermal_ga(self.domain,slow,7,self.timer.clock,quiet)
        self.assertEqual((out["reason"],out["unique_started"],out["unique_completed"]),("timeout",3,2))
        self.assertEqual((out["first_safe_s"],out["completed_generations"]), (20,0))
        self.assertIsNotNone(out["winner"])
        statuses=["UNRESOLVED","DEADLINE","VIOLATION","SAFE"]
        self.assertEqual(sorted(statuses,key=lambda st:s.thermal_rank((("A",0,0,0,0),result(st)))),statuses[::-1])


class FrozenContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unit=evaluator.load_frozen(ROOT)

    def test_identity_in_both_cases_and_drift_rejected(self):
        for case, allowed, _ in pilot.SLOTS.values():
            with patch.object(self.unit.events,"time_scene",side_effect=AssertionError("science forbidden")), \
                 patch.object(self.unit.events,"evaluate_thermal",side_effect=AssertionError("science forbidden")):
                ev=evaluator.Evaluator(ROOT,case,allowed,quiet)
                self.assertEqual(ev.identity,evaluator.CASES[case][3])
                self.assertEqual(ev.scenes[-1].end_ns,10040000000)
                spec=dict(request_stream_sha256="changed",scene_order=[],frames_in_execution_order=[])
                with self.assertRaisesRegex(ValueError,"absolute request digest"):
                    self.unit.verify_stream(ev.scenes,spec)

    def test_proxy_arguments_and_deadline_short_circuit(self):
        ev=evaluator.Evaluator(ROOT,*pilot.SLOTS["01"][:2],quiet)
        import numpy as np
        sched=SimpleNamespace(deadline_feasible=True,duration_ns=np.array([40_000_000]),
                              active_w=[2],transfer_w=[3])
        with patch.object(ev.events,"time_scene",return_value=sched), \
             patch.object(ev.events,"evaluate_thermal",return_value={"energy_J":2.5}) as th:
            self.assertEqual(ev.proxy("A",3,0),2.5)
            args,kw=th.call_args
            self.assertEqual((list(args[0]),args[1],kw["transfer_W"]),([.04],[2],[3]))
            self.assertEqual((list(kw["initial_C"]),kw["ambient_C"]),([30.]*4,25.))
            sched.deadline_feasible=False
            self.assertIsNone(ev.proxy("A",3,0))
            self.assertEqual(th.call_count,1)

    def test_archived_certificate_through_adapter(self):
        out=[]
        ev=evaluator.Evaluator(ROOT,*pilot.SLOTS["03"][:2],lambda e,v:out.append(v))
        fixture=ROOT/"research/kim_pressure_feasibility/raw_execution/07"
        raw=json.loads((fixture/"result.json").read_bytes())
        arrivals=json.loads((fixture/"requests.json").read_bytes())
        dep=raw["deployment"]
        self.assertEqual((raw["request_sha256"],raw["case_id"]),(ev.identity,pilot.SLOTS["03"][0]))
        def schedule(platform,scene,dep,opp):
            return SimpleNamespace(deadline_feasible=True,completions_ns={
                row["request_id"]:row["completion_ns"]-scene.start_ns for row in arrivals if row["scene"]==scene.name})
        def check(physical):
            with patch.object(ev.events,"replay_sequence",return_value=physical) as rp, \
                 patch.object(ev.events,"time_scene",side_effect=schedule), \
                 patch.object(ev.events,"evaluate_thermal",side_effect=AssertionError("science forbidden")):
                r=ev.replay(dep,tuple(s.OPPS.index(x) for x in raw["selection"]["opps"]))
                self.assertEqual(rp.call_args.kwargs,dict(leakage=True,variation="base",reset=False))
                return r
        physical=raw["physical"]
        r=check(physical)
        self.assertEqual(r.status,"SAFE")
        self.assertEqual((r.completed,r.energy_j),(500,physical["energy_j"]))
        self.assertEqual(out[-1]["completions"],arrivals)
        changed=deepcopy(physical)
        changed["energy_j"]-=1
        with self.assertRaises(ValueError):
            check(changed)
        changed=deepcopy(physical)
        changed["scene_rows"][1]["entry_c"][0]+=1
        with self.assertRaises(ValueError):
            check(changed)
        changed=deepcopy(physical)
        changed["scene_rows"][-1]["end_ns"]-=40000000
        with self.assertRaises(ValueError):
            check(changed)
        changed=deepcopy(physical)
        changed.update(thermal_status="UNRESOLVED",feasible=False)
        changed["peak_upper_c"][0]=81.
        changed["scene_rows"][-1]["peak_upper_c"][0]=81.
        self.assertEqual(check(changed).status,"UNRESOLVED")
        partial=dict(required=500,completed=12,deadline_ok=False,thermal_status="NOT_EVALUATED",
                     feasible=False,fully_replayed=False,energy_j=None,min_slack_ms=-.5,
                     scene_rows=[dict(deadline_ok=False,scene="sc3",opp="MHM",late_ids=["f0187-a3"])])
        self.assertIsNone(check(partial).energy_j)
        partial["scene_rows"][0]["late_ids"]=["alien"]
        with self.assertRaises(ValueError):
            check(partial)

    def test_frozen_continuous_replay_with_substitute_physics(self):
        import numpy as np
        ev=evaluator.Evaluator(ROOT,*pilot.SLOTS["03"][:2],quiet)
        fixture=ROOT/"research/kim_pressure_feasibility/raw_execution/07"
        archived=json.loads((fixture/"result.json").read_bytes())
        arrivals=json.loads((fixture/"requests.json").read_bytes())
        records=archived["physical"]["scene_rows"]
        def schedule(platform,scene,dep,opp):
            requests=[r for r in arrivals if r["scene"]==scene.name]
            return SimpleNamespace(deadline_feasible=True,min_slack_ns=min(r["slack_ns"] for r in requests),
                                   completions_ns={r["request_id"]:r["completion_ns"]-scene.start_ns for r in requests},
                                   duration_ns=np.array([scene.duration_ns]),active_w=[],transfer_w=[])
        calls=[]
        def sample(duration,active,transfer_W,**kw):
            r=records[len(calls)]
            self.assertEqual(list(kw["initial_C"]),r["entry_c"])
            self.assertEqual(kw["ambient_C"],27.5)
            calls.append(float(sum(duration)))
            return dict(energy_J=r["energy_j"], final_C=r["final_c"], peak_upper_C=r["peak_upper_c"],
                        peak_lower_C=r["peak_lower_c"], thermal_status=r["thermal_status"])
        with patch.object(ev.events,"time_scene",side_effect=schedule), \
             patch.object(ev.events,"evaluate_thermal",side_effect=sample):
            r=ev.replay(archived["deployment"],tuple(s.OPPS.index(x) for x in archived["selection"]["opps"]))
        self.assertEqual(len(calls),4)
        self.assertAlmostEqual(sum(calls),10.04)
        self.assertEqual((r.energy_j,r.status,r.completed),(archived["physical"]["energy_j"],"SAFE",500))


class SupervisorTests(unittest.TestCase):
    def test_hard_stop_consumes_slot_and_kills_child(self):
        process=Mock()
        process.pid=123
        process.exitcode=-1
        process.is_alive.side_effect=[True,True,False]
        with tempfile.TemporaryDirectory() as directory, patch.object(pilot.multiprocessing,"get_context") as ctx:
            ctx.return_value.Process.return_value=process
            receipt=pilot.supervise("unused","01",directory,"SUBSTITUTE-ONLY",Mock())
            self.assertEqual(receipt["state"],"hard_timeout")
            process.kill.assert_called_once()
            with self.assertRaises(FileExistsError):
                pilot.supervise("unused","01",directory,"SUBSTITUTE-ONLY",Mock())
            self.assertEqual(summarize(Path(directory)/"01")["witnesses"],[])

    def test_interrupted_journal_and_late_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/"receipt.json").write_text('{"state":"hard_timeout","elapsed_s":60.0}')
            record=dict(dep="C",opps=[0]*4,result=dict(status="SAFE",energy_j=5.),seconds=1.,at_s=40.)
            rows=[[39.,"check_start",{}],[40.,"kim_check",record],[60.,"kim_check",record]]
            (path/"events.jsonl").write_bytes(("".join(json.dumps(r)+"\n" for r in rows)+"[broken").encode())
            observed=summarize(path)
            self.assertEqual((observed["checks_started"],observed["checks_completed"]),(1,1))
            self.assertEqual(len(observed["witnesses"]),1)
            (path/"events.jsonl").write_bytes(b"[broken")
            self.assertEqual(summarize(path)["witnesses"],[])


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-root",type=Path,required=True)
    args,rest=parser.parse_known_args()
    ROOT=args.source_root.resolve()
    unittest.main(argv=[sys.argv[0],*rest],verbosity=2)
