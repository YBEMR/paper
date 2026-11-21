"""Read only completed journal lines from one cold slot, including after process interruption."""
import json
from pathlib import Path

from search import paired


def summarize(directory):
    directory = Path(directory)
    receipt = json.loads((directory/"receipt.json").read_bytes())
    summary = dict(state=receipt["state"], checks_started=0, checks_completed=0,
                   ga_unique_started=0, ga_unique_completed=0, proxy_completed=0,
                   witnesses=[], pool=None, identity=None, generations=[], check_seconds=[],
                   proxy_compute_s=0., ga_replay_s=0., worker_elapsed_s=receipt["elapsed_s"])
    path = directory/"events.jsonl"
    if not path.exists():
        return summary
    with path.open("rb") as stream:
        for raw in stream:
            if not raw.endswith(b"\n"):
                break
            at, event, value = json.loads(raw)
            if at >= 60:
                break
            if event == "identity":
                summary["identity"] = value
            elif event == "kim_pool":
                summary["pool"] = value
            elif event == "setfreq" and not value["hit"]:
                summary["proxy_completed"] += 1
                summary["proxy_compute_s"] += value["compute_s"]
            elif event == "check_start":
                summary["checks_started"] += 1
            elif event == "ga_start":
                summary["ga_unique_started"] += 1
            elif event == "ga_generation":
                summary["generations"].append(value)
            elif event in ("ga_position", "kim_check"):
                if event == "kim_check":
                    summary["checks_completed"] += 1
                    summary["check_seconds"].append(value["seconds"])
                    key = [value["dep"], *value["opps"]]
                else:
                    if value["hit"]:
                        continue
                    summary["ga_unique_completed"] += 1
                    summary["ga_replay_s"] += value["seconds"]
                    key = value["genome"]
                if value["result"]["status"] == "SAFE":
                    summary["witnesses"].append(dict(at_s=value["at_s"], genome=key,
                                                     energy_j=value["result"]["energy_j"]))
    return summary


def paired_slots(left, right):
    if not all(r["state"] == "finished" and r["identity"] and r["pool"] for r in (left,right)):
        return False
    a, b = left["identity"], right["identity"]
    return ({a["method"], b["method"]} == {"Kim-Adapt","Kim-Adapt+SAFE"} and
            all(a[k] == b[k] for k in ("case","allowed","seed","request_sha256","rng","python")) and
            paired(left["pool"], right["pool"]))
