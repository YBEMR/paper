"""Join frozen settings to per-run measurements after summarize.py verifies the archives."""
import csv
import tarfile

from run_formal import HERE, config, records


def kim_completed_generations():
    counts = {}
    # A partially visited generation can contain 24 started positions.
    # Only the end-of-generation event establishes that all positions finished.
    for path in sorted((HERE / "archives").glob("*.tar.xz")):
        with tarfile.open(path, "r|xz") as archive:
            for member in archive:
                unit, _, name = member.name.partition("/")
                if name != "events.jsonl" or int(unit[1:]) % 3 == 2:
                    continue
                stream = archive.extractfile(member)
                counts[unit] = sum(b',"kim_generation",' in line for line in stream)
    return counts


def main():
    results = records(HERE / "tables" / "run_results.csv")
    generations = kim_completed_generations()
    output = []
    for row in results:
        case, method = row["case"], row["method"]
        size = int(row["domain"])
        domain = "all 81 representatives (catalog.search_order)" if size == 81 else "A|C|D001|D015"
        actual = dict(group=row["group"], case=case, method=method, seed=row["seed"],
                      deployments_allowed=size, domain=domain, source=row["source"],
                      outcome=row["outcome"], wall_s=row["wall_s"])
        if row["unit"]:
            rule = config((case, size, method, int(row["seed"])))
            checks = row["checks"]
            ga = method == "Thermal-GA"
            actual.update(unit=row["unit"], population=rule["population"],
                          max_generations=rule["max_generations"],
                          completed_generations=row["generations"] if ga else generations[row["unit"]],
                          search_positions=row["total_positions"], kim_distinct_deployments=row["unique_deployments"],
                          max_fallbacks=rule["max_fallbacks"], max_total_checks=rule["max_total_checks"],
                          kim_checks_completed=checks, kim_fallbacks_completed=max(0, int(checks)-1) if checks else "",
                          wall_cap_s=rule["wall_cap_s"], generation_cutoff_s=rule["generation_cutoff_s"],
                          accept_cutoff_s=rule["accept_cutoff_s"], stop_rule=rule["stop_rule"],
                          generation_stop=row["pool_stop"] if not ga else row["stop"], final_stop=row["stop"])
        else:
            actual.update(stop_rule="reuse archived same-domain exact certificate", final_stop=row["stop"])
        output.append(actual)
    if len(output) != 96 or len({r["unit"] for r in output if r.get("unit")}) != 90:
        raise ValueError("Expected 90 randomized runs and six deterministic references")
    target = HERE / "formal_experiment_config_actual.csv"
    fields = list(dict.fromkeys(key for row in output for key in row))
    with target.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)


if __name__ == "__main__":
    main()
