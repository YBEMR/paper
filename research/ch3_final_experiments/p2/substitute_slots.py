"""Exercise all four cold process slots using synthetic scores and classifications only."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pilot import SLOTS, supervise
from read_pilot import paired_slots, summarize
from search import Domain, Result


class Substitute:
    def __init__(self, root, case, allowed, emit):
        catalog = json.loads((Path(root)/"research/kim_multidnn_expansion/catalog.json").read_bytes())
        self.domain = Domain(catalog, allowed)
        self.identity = "SUBSTITUTE/" + case

    def proxy(self, dep, scene, idx):
        return float(1+self.domain.rank[dep]+scene+idx)

    def replay(self, dep, indices):
        peak = 81. if dep == "A" else 79.
        status = "VIOLATION" if peak > 80 else "SAFE"
        return Result(status,500,1.,float(10+sum(indices)),(peak,)*4,(peak,)*4)


def exercise(root, ledger):
    summaries, outputs = {}, {}
    for slot in SLOTS:
        receipt = supervise(root, slot, ledger, "SUBSTITUTE-ONLY", Substitute)
        if receipt["state"] != "finished":
            raise RuntimeError(receipt)
        info = summarize(ledger/slot)
        summaries[slot] = info
        stored = json.loads((ledger/slot/"worker.json").read_bytes())
        outcome = stored["summary"]
        row = dict(method=stored["identity"]["method"], synthetic_stop=outcome["reason"],
                   synthetic_winner=outcome["winner"], cold_wall_s=receipt["elapsed_s"],
                   synthetic_init_s=stored["identity"]["init_s"])
        if slot != "04":
            pool = info["pool"]
            row.update(pool_sha256=pool["pool_sha256"], ordered_pool=pool["pool"],
                       unique_deployments=pool["unique_deployments"], counts=pool["counts"],
                       checks=info["checks_completed"])
        else:
            row.update(unique_started=info["ga_unique_started"],unique_completed=info["ga_unique_completed"],
                       generations=outcome["generations"],positions=outcome["positions"],hits=outcome["hits"])
        outputs[slot] = row
    if not paired_slots(summaries["01"],summaries["02"]):
        raise AssertionError("paired substitute pool differs")
    if (outputs["01"]["checks"],outputs["02"]["checks"]) != (1,2):
        raise AssertionError("unexpected paired fallback trace")
    if outputs["04"]["positions"] != 128 or outputs["04"]["unique_completed"]+outputs["04"]["hits"] != 128:
        raise AssertionError("unique/cached replay accounting differs")
    return dict(kind="SUBSTITUTE_ONLY", scientific_calls=0, paired_pool=True, slots=outputs)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source-root",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    with TemporaryDirectory() as directory:
        result=exercise(a.source_root.resolve(), Path(directory))
    with a.report.open("x",encoding="utf8",newline="\n") as f:
        f.write(json.dumps(result,indent=2,allow_nan=False)+"\n")
