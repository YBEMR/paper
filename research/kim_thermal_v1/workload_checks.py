"""Independent scheduling fixture, fault and predeclared pair checks."""
from collections import Counter
from fractions import Fraction
import json

from workload import cases, scenes, schedule, tail_segments


def checks():
    scene = {"id":"manual", "duration_ms":100,
             "requests":[{"id":"A0","app":"A","release_ms":0,"deadline_ms":95},
                         {"id":"B0","app":"B","release_ms":0,"deadline_ms":121}]}
    high = schedule(scene,"HHH")
    expected = {
        "A.pre":(0,10),"A.main":(10,40),"A.post":(40,45),
        "B.pre":(0,15),"B.main":(40,75),"B.post":(75,81)}
    observed = {r["stage"]:(r["start_ms"],r["end_ms"]) for r in high["rows"]}
    assert observed == expected and high["legal"] and high["completions"] == {"A0":45,"B0":81}
    assert all(set(s["domain_opps"].values()) == {"H"} for s in high["segments"])
    last_active = [k for k,v in high["segments"][-1]["activity_by_node_W"].items() if Fraction(v)]
    assert high["segments"][-1]["baseline_by_power_group_W"] == {"CPU":"13/10","GPU":"9/10","NPU":"3/5"}
    assert not last_active and sum(Fraction(s["duration_ms"]) for s in high["segments"]) == 100
    assert tail_segments()[0]["domain_opps"] == {"CPU":"L","GPU":"L","NPU":"L"}
    assert schedule(scene,"LML")["reason"] == "INVALID_CONFIG"
    request = {"id":"A0","app":"A","release_ms":3,"deadline_ms":Fraction(131,2)}
    exact = {"id":"manual","duration_ms":80,"requests":[request]}
    good = schedule(exact,"LLL")
    assert good["legal"] and good["completions"] == {"A0":65.5}
    request["deadline_ms"] -= Fraction(1,10**18)
    assert schedule(exact,"LLL")["reason"] == "DEADLINE"
    request["deadline_ms"] = 100
    overrun = schedule({**exact,"duration_ms":65},"LLL")
    assert overrun["reason"] == "BOUNDARY_UNFINISHED" and overrun["completions"] == {"A0":65.5}
    assert len(overrun["segments"]) == 0

    pairs = {}
    for case in cases():
        catalog = scenes(case["load"], case["seed"])
        requests = Counter((scene, r["id"],r["release_ms"],r["deadline_ms"]) for scene in case["sequence"]
                           for r in catalog[scene]["requests"])
        assert len(case["sequence"]) == 8
        assert sum(requests.values()) == (18 if case["load"]=="light" else 36)
        key = (case["load"],case["seed"],case["state"])
        pairs.setdefault(key,[]).append(requests)
    assert len(pairs)==12 and all(len(p)==2 and p[0] == p[1] for p in pairs.values())
    return {"tests_passed":["shared NPU contention and predecessor readiness, compared to hand timeline",
                            "all domain frequencies pinned including completely idle GPU",
                            "tail returns all domains to low", "middle level rejected",
                            "exact deadline equality accepted and 1e-18 ms stricter deadline rejected",
                            "segment boundary overrun reports actual completion; no continuation",
                            "12 matched order pairs preserve every request, release and deadline"],
            "manual_HHH_stage_intervals_ms":observed, "manual_release_3_LLL_finish_ms":65.5,
            "pairs":len(pairs), "tasks_by_load":{"light":18,"heavy":36}}


if __name__ == "__main__":
    print(json.dumps(checks(),ensure_ascii=False,indent=2))
