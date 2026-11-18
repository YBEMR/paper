"""Read V1's archived deadlines and nominal energies; never run a physical evaluation."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "kim_thermal_v1" / "raw"
ORIGINAL = (1, 0, 2)  # CPU/GPU/NPU string indices: original traversal starts at GPU
REVERSE = ORIGINAL[::-1]
CONFIGS = tuple("".join(parts) for parts in product("LH", repeat=3))
TOL = 1e-10


def traversal(scores, order):
    state = list("HHH")
    visits = []
    for _ in range(2):
        for domain in order:
            for level in "HL":
                state[domain] = level
                cfg = "".join(state)
                visits.append(cfg)
                if scores[cfg] is None:
                    if level == "L":
                        state[domain] = "H"
                    break
    return visits


def summarize(visits, scores):
    valid = [c for c in visits if scores[c] is not None]
    chosen = min(valid, key=scores.get)  # Python min retains the first minimum
    return {"cfg": chosen, "nominal_J": scores[chosen], "visits": visits,
            "distinct_checks": len(set(visits)), "distinct_valid": len(set(valid))}


def run():
    records = [json.loads(f.read_bytes()) for f in sorted(RAW.glob("*.json"))]
    assert len(records) == 24
    tables = {}
    repetitions = Counter()
    for record in records:
        case, a = record["case"], record["methods"]["A"]
        for scene, row, decisions in zip(case["sequence"], a["diagnostic"], a["decisions"], strict=True):
            key = (case["load"], case["seed"], scene)
            scores = {r["cfg"]: r["kim_score_J"] if r["deadline_ok"] else None for r in row}
            assert set(scores) == set(CONFIGS)
            repetitions[key] += 1
            if key in tables:
                assert tables[key]["scores"] == scores and tables[key]["original"]["cfg"] == decisions["selected"]
                continue
            original, reverse = (traversal(scores, order) for order in (ORIGINAL, REVERSE))
            assert original == [item["cfg"] for item in decisions["trials"]]
            pathsets = {"original": original, "reverse": reverse, "combined": original+reverse, "full": list(CONFIGS)}
            row = {label: summarize(path, scores) for label, path in pathsets.items()}
            assert row["original"]["cfg"] == decisions["selected"]
            values = sorted(v for v in scores.values() if v is not None)
            tables[key] = {"load": key[0], "seed": key[1], "scene": key[2], "scores": scores, **row,
                           "tied_minima": [cfg for cfg, value in scores.items()
                                           if value is not None and abs(value-values[0]) <= TOL],
                           "second_margin_J": values[1]-values[0] if len(values)>1 else None}
    archive_checks = []
    for record in records:
        case = record["case"]
        predicted = [tables[case["load"],case["seed"],s]["combined"]["cfg"] for s in case["sequence"]]
        row = {"id": case["id"], "predicted_nominal_path": predicted}
        for label in ("B", "D"):
            method = record["methods"][label]
            if method["feasible"]:
                assert predicted == method["path"] and len(method["stages"]) == len(predicted)
                row[label] = {"status": method["status"], "matches_all_steps": True,
                              "steps_checked": len(predicted), "energy_J_from_existing_path": method["energy_J"]}
            else:
                assert not method["path"]
                first_legal = [r for r in method["diagnostic"][0] if r["deadline_ok"]]
                assert first_legal and not any(r["safe"] for r in first_legal)
                row[label] = {"status": method["status"], "steps_checked": 0,
                              "first_scene_all_deadline_legal_unsafe": True,
                              "unreached_after_first_scene": True}
        archive_checks.append(row)
    assert len(tables) == 24 and all(n==8 for n in repetitions.values())
    labels = ("original","reverse","combined","full")
    counts = {label: {"hits": sum(row[label]["cfg"] in row["tied_minima"] for row in tables.values()),
                      "visits":sum(len(row[label]["visits"]) for row in tables.values()),
                      "distinct_checks":sum(row[label]["distinct_checks"] for row in tables.values()),
                      "distinct_valid":sum(row[label]["distinct_valid"] for row in tables.values())}
              for label in labels}
    return {"source_commit":"5004ed72b95e1d32cf6e7b2c1c3a716ce6759af8",
            "tie_tolerance_J":TOL, "ordering":"CPU/GPU/NPU config; original traverses GPU/CPU/NPU",
            "deduplication":"load, seed, scene; eight occurrences each", "counts":counts,
            "tables":[tables[k] for k in sorted(tables)], "archive_path_checks":archive_checks}


if __name__ == "__main__":
    report = run()
    (HERE / "kim_search_replay.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")

