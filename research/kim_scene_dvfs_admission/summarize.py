"""Export the six method decisions with shared and method-specific costs separated."""
import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(raw, name):
    return json.loads((raw/name).read_text(encoding="utf-8"))


def summarize(raw):
    records=read(raw,"decisions.json")
    timing=read(raw,"timing.json")
    counts=read(raw,"counts.json")
    diagnostics=read(raw,"comparison_sets.json")
    for record in records:
        ambient, method=record["ambient"],record["method"]
        times=[x for x in timing["by_environment_deployment"] if x["ambient"]==ambient]
        groups=[x for x in counts if x["ambient"]==ambient]
        if method=="fixed":
            candidates=54
            admitted=sum(x["fixed_safe"] for x in groups)
        elif method=="independent":
            candidates=2*27**4
            admitted=sum(x["reset_feasible"] for x in diagnostics if x["ambient"]==ambient)
        else:
            candidates=2*27**4
            admitted=sum(x["safe"] for x in groups)
        p=record["physical"]
        yield dict(ambient_c=ambient,method=method,deployment=record["deployment"],
                   sc0_to_sc3=" ".join(record["opps"] or []),
                   estimated_energy_j=record["predicted_j"],
                   replay_status=(p["thermal_status"] if p else "NO_SELECTION"),
                   deadline_ok=(p["deadline_ok"] if p else None),
                   completed=(p["completed"] if p else None),required=500,
                   physical_energy_j=(p["energy_j"] if p else None),
                   **{f"peak_{node}_c":(p["peak_upper_c"][i] if p else None)
                      for i,node in enumerate(("cpu","gpu","dla0","dla1"))},
                   min_slack_ms=(p["min_slack_ms"] if p else None),
                   switches=(p["switches"] if p else None),
                   full_action_space=candidates,admissible_in_method_model=admitted,
                   search_s=sum(t[method+"_search_s"] for t in times),
                   shared_event_scheduling_s=timing["shared_scheduling_s"],
                   shared_thermal_compile_s=sum(t["compile_s"] for t in times),
                   select_and_replay_s=record["selection_and_replay_s"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw",type=Path,default=HERE/"raw")
    parser.add_argument("--output",type=Path,default=HERE/"summary.csv")
    args=parser.parse_args()
    rows=list(summarize(args.raw))
    with args.output.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
