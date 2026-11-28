"""Split wall time into non-overlapping components, including unobserved cutoff tails."""
import gzip
import json
from collections import Counter
from pathlib import Path
from collect import as_csv, spans
from summarize import HERE, read


def log(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in gzip.decompress(path.read_bytes()).splitlines() if x.endswith(b"}")]


def main():
    ledger = []
    for r in read("cells"):
        cap = int(r["cap"])
        charged = float(r["total_s"])
        arm = {"B":"N", "C":"O"}[r["arm"]]
        folder = HERE/"results"/r["case"]/f"r{r['rep']}-{arm}-{cap}"
        receipt = json.loads(gzip.decompress((folder/"receipt.json.gz").read_bytes()))
        sc, rf = [log(folder/(s+".jsonl.gz")) for s in ("search","refine")]
        stop = min(charged, receipt["search"]["supervisor_t"], cap-3 if receipt["post"] else cap)
        def amount(name):
            return float(r[name] or 0)
        components = {
            "instance_s":spans(sc,"instance",stop),
            "quota_generation_s":amount("generator_s"),
            "calibration_excluding_replay_s":amount("calibration_s"),
            "pilot_replay_s":amount("pilot_fifo_s"),
            "ordinary_replay_s":amount("fifo_s")-amount("pilot_fifo_s"),
            "heat_prediction_s":amount("heat_s"),
            "search_certificate_s":amount("search_cert_s"),
            "mapping_selection_s":amount("selection_s"),
            "physical_handoff_s":amount("handoff_s"),
            "returned_dp_s":amount("dp_returned_s"),
            "dp_certificate_s":amount("dp_cert_s")
        }
        residual_build = amount("build_s") - sum(components[k] for k in (
            "quota_generation_s","calibration_excluding_replay_s","pilot_replay_s","ordinary_replay_s","heat_prediction_s"))
        components["other_construction_and_unsampled_tail_s"] = residual_build
        components["other_delivery_and_unreturned_work_s"] = charged - sum(components.values())
        assert min(components.values()) >= -1e-7
        assert abs(sum(components.values())-charged) < 1e-8
        started = sum(e["event"]=="begin" and e.get("task") in ("search_cert","dp_cert") and e["t"]<=cap for e in sc+rf)
        item = {k:r[k] for k in ("case","arm","cap","rep","total_s")}
        item.update(cert_started=started,cert_delivered=int(r["cert_count"]),**components)
        ledger.append(item)
    as_csv(HERE/"tables/ledger.csv",ledger)


if __name__ == "__main__":
    main()
