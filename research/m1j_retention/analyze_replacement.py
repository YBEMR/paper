"""Summarize all four registered methods from this batch's lossless per-run records."""
import csv
import gzip
import hashlib
import itertools
import json
import statistics
import tarfile
from collections import Counter
from pathlib import Path

from paths_j import DATA, I, METHODS, REG, inputs, write_json
import analyze as frozen

CUTS = frozen.CUTS
PAIRS = (("NT", "NT-S"), ("NC", "NC-S"), ("NT", "NC"), ("NT-S", "NC-S"),
         ("NT", "NC-S"), ("NT-S", "NC"))
GROUPS = ("all", "A", "B", "C")


def members(path):
    with tarfile.open(path, "r|xz") as archive:
        for item in archive:
            if item.isfile():
                yield item.name, archive.extractfile(item).read()


def run_records(case, evidence=DATA / "evidence"):
    return {name.split("/")[0]: json.loads(body)
            for name, body in members(evidence / case / "runs.tar.xz")}


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def physical_check(c, runs):
    folder = DATA / "evidence" / c["case"]
    receipt = json.loads((folder / "receipt.json").read_bytes())
    assert receipt["case"] == c["case"] and len(runs) == receipt["runs"] == 12
    for name, expected in receipt["files"].items():
        assert file_hash(folder / name) == expected, (folder, name)
    with gzip.open(folder / "event_index.csv.gz", "rt") as source:
        index = {row["plan"]: row for row in csv.DictReader(source)}
    seen = set()
    for name, body in members(folder / "physical.tar.xz"):
        ident, kind = name.split("/")
        column = {"plan.json":"plan_file_sha256", "certificate.json":"certificate_file_sha256"}[kind]
        assert hashlib.sha256(body).hexdigest() == index[ident][column]
        if kind == "plan.json":
            assert hashlib.sha256(body.strip()).hexdigest() == ident
        else:
            assert json.loads(body)["plan_sha256"] == ident
        assert (ident, kind) not in seen
        seen.add((ident, kind))
    calls = [r for run in runs.values() for r in run["records"]]
    assert len(calls) == receipt["certificates"]
    assert len(seen) == 2 * receipt["unique_plans"] == 2 * len(index)
    assert {r["cert"]["plan_sha256"] for r in calls} == set(index)
    for rec in calls:
        m = rec["cert"]["metrics"]
        assert m["E_bounds"][0] <= m["E_J"] <= m["E_bounds"][1]
        assert m["min_deadline_slack_ms"] >= 0
        if m["status"] == "SAFE":
            assert max(m["peak_hi"]) <= 80 and min(m["minimum_lo"]) >= 20
    volume = json.loads((folder / "event_volume.json").read_bytes())
    assert volume["verified_unique_plans"] == len(index)
    return len(index)


def match_fixed(case, runs):
    previous = run_records(case, I / "data/evidence")
    matches = []
    for method, rep in itertools.product(("NT", "NC"), (1, 2, 3)):
        tag = f"r{rep}-{method}"
        def fixed(run):
            return [r for r in run["records"] if r["width"] == 4 and r["end_s"] <= 60][:4]
        now, old = fixed(runs[tag]), fixed(previous[tag])
        for i, (a, b) in enumerate(zip(now, old), 1):
            ma, mb = a["cert"]["metrics"], b["cert"]["metrics"]
            matches.append(dict(case=case, method=method, repeat=rep, slot=i,
                                plan=a["cert"]["plan_sha256"], historical_plan=b["cert"]["plan_sha256"],
                                same_plan=a["cert"]["plan_sha256"]==b["cert"]["plan_sha256"],
                                same_config=a["id"]==b["id"], same_status=ma["status"]==mb["status"],
                                energy_diff_J=ma["E_J"]-mb["E_J"],
                                peak_diff_C=max(ma["peak_hi"])-max(mb["peak_hi"]),
                                slack_diff_ms=ma["min_deadline_slack_ms"]-mb["min_deadline_slack_ms"]))
    return matches


def pair_table(rows, keys, valid):
    grouped = {}
    for row in rows:
        grouped.setdefault(tuple(row[k] for k in keys), {})[row["method"]] = row
    out = []
    for key, arms in grouped.items():
        assert set(arms) == set(METHODS)
        for left, right in PAIRS:
            a, b = arms[left], arms[right]
            result, saving = frozen.compare(a,b,valid)
            out.append(dict(dict(zip(keys,key)),left=left,right=right,left_E_J=a["SAFE_J"],
                            right_E_J=b["SAFE_J"],left_n=a.get("n_SAFE", int(a["SAFE_J"] is not None)),
                            right_n=b.get("n_SAFE", int(b["SAFE_J"] is not None)),result=result,saving_pct=saving))
    return out


def interactions(rows, keys, valid):
    grouped = {}
    for r in rows:
        grouped.setdefault(tuple(r[k] for k in keys), {})[r["method"]]=r
    out = []
    for group, arms in grouped.items():
        a, b, c, d = (arms[m] for m in METHODS)
        flags = [int(valid(r)) for r in (a,b,c,d)]
        item = dict(dict(zip(keys,group)),coverage_interaction=flags[0]-flags[1]-flags[2]+flags[3],
                    all_four=all(flags),thermal_gain_J=None,load_gain_J=None,
                    interaction_J=None,interaction_pct=None,retention_main_J=None,thermal_main_J=None,lower_J=None,upper_J=None)
        if all(flags):
            t = b["SAFE_J"]-a["SAFE_J"]
            n = d["SAFE_J"]-c["SAFE_J"]
            item.update(thermal_gain_J=t,load_gain_J=n,interaction_J=t-n,
                        interaction_pct=100*(t-n)/d["SAFE_J"],retention_main_J=(t+n)/2,
                        thermal_main_J=((c["SAFE_J"]-a["SAFE_J"])+(d["SAFE_J"]-b["SAFE_J"]))/2,
                        lower_J=b["lo"]-a["hi"]-d["hi"]+c["lo"],
                        upper_J=b["hi"]-a["lo"]-d["lo"]+c["hi"])
        out.append(item)
    return out


def summary(medians, paired, joint):
    coverage, contrast, interaction = [], [], []
    for group, cut in itertools.product(GROUPS, CUTS):
        def chosen(r):
            return r["regime"]==cut and (group=="all" or r["group"]==group)
        for method in METHODS:
            sub = [r for r in medians if chosen(r) and r["method"]==method]
            coverage.append(dict(group=group,regime=cut,method=method,flows=len(sub),
                                 reliable=sum(r["reliable"] for r in sub),
                                 **{f"safe_{i}_of_3":sum(r["n_SAFE"]==i for r in sub) for i in range(4)},
                                 **{k:frozen.med(sub,k) for k in ("first_SAFE_s","build_s","cert_write_s","certs")}))
        for a,b in PAIRS:
            sub=[r for r in paired if chosen(r) and (r["left"],r["right"])==(a,b)]
            cnt=Counter(r["result"] for r in sub)
            v=[r["saving_pct"] for r in sub if r["saving_pct"] is not None]
            contrast.append(dict(group=group,regime=cut,left=a,right=b,flows=len(sub),paired=len(v),
                            mean_pct=statistics.mean(v) if v else None,median_pct=statistics.median(v) if v else None,
                            **{k:cnt[k] for k in ("win","tie","loss","only_left","only_right","neither")}))
        sub=[r for r in joint if chosen(r)]
        complete=[r for r in sub if r["all_four"]]
        interaction.append(dict(group=group,regime=cut,flows=len(sub),four_safe=len(complete),
                       coverage_sum=sum(r["coverage_interaction"] for r in sub),
                       coverage_mean=statistics.mean(r["coverage_interaction"] for r in sub),
                       positive=sum(r["lower_J"]>0 for r in complete),negative=sum(r["upper_J"]<0 for r in complete),
                       overlap_zero=sum(r["lower_J"]<=0<=r["upper_J"] for r in complete),
                       **{f"mean_{k}":statistics.mean(r[k] for r in complete) if complete else None
                          for k in ("thermal_gain_J","load_gain_J","interaction_J","interaction_pct","retention_main_J","thermal_main_J")},
                       median_interaction_pct=statistics.median(r["interaction_pct"] for r in complete) if complete else None))
    return coverage,contrast,interaction


def main():
    cases=inputs()
    slots=frozen.readcsv(REG/"rotation.csv")
    marks,calls,improvements,stages,matches=[],[],[],[],[]
    unique=0
    for c in cases:
        runs=run_records(c["case"])
        unique+=physical_check(c,runs)
        matches.extend(match_fixed(c["case"],runs))
        for slot in (s for s in slots if s["case"]==c["case"]):
            run=runs[f"r{slot['repeat']}-{slot['method']}"]
            for acc,part in zip((marks,calls,improvements,stages),frozen.one(c,slot,run),strict=True):
                acc.extend(part)
    assert len(marks)==576
    medians=[]
    for c, m, cut in itertools.product(cases,METHODS,CUTS):
        sub=[r for r in marks if (r["case"],r["method"],r["regime"])==(c["case"],m,cut)]
        assert len(sub)==3
        n=sum(r["SAFE_J"] is not None for r in sub)
        medians.append(dict(group=c["group"],case=c["case"],flow=c["flow"],regime=cut,method=m,n_SAFE=n,
                       reliable=n>=2,**{k:frozen.med(sub,k) for k in ("SAFE_J","lo","hi","peak_C","slack_ms",
                       "first_SAFE_s","build_s","cert_write_s","certs","min_cert_peak_C")}))
    keys=["group","case","flow","regime"]
    paired=pair_table(medians,keys,lambda r:r["reliable"])
    repeated=pair_table(marks,keys+["repeat"],lambda r:r["SAFE_J"] is not None)
    joint=interactions(medians,keys,lambda r:r["reliable"])
    joint_rep=interactions(marks,keys+["repeat"],lambda r:r["SAFE_J"] is not None)
    coverage,contrast,gs=summary(medians,paired,joint)
    assert (len(medians),len(paired),len(repeated),len(joint),len(joint_rep))==(192,288,864,48,144)
    for filename,rows in (("repetitions.csv",marks),("medians.csv",medians),("paired_cases.csv",paired),
                          ("paired_repeats.csv",repeated),("interactions.csv",joint),("interactions_repeats.csv",joint_rep),
                          ("group_coverage.csv",coverage),("group_contrasts.csv",contrast),("group_interactions.csv",gs),
                          ("calls.csv.gz",calls),("improvements.csv",improvements),("stages.csv",stages),
                          ("historical_fixed.csv",matches)):
        frozen.write(DATA/filename,rows)
    fin=[r for r in marks if r["regime"]=="60s"]
    used=sum(r["ontime"] for r in calls)
    write_json(DATA/"batch_receipt.json",dict(trajectories=len(fin),budget_core_seconds=8640,
               measured_wall_sum_s=sum(r["wall_s"] for r in fin),calls=len(calls),ontime=used,late=len(calls)-used,
               unique_plans=unique,checkpoints=len(marks),fixed_under_four=sum(r["certs"]<4 for r in marks if r["regime"]=="W4/K4"),
               historical_checked=len(matches),historical_same_plan=sum(r["same_plan"] for r in matches),
               historical_same_status=sum(r["same_status"] for r in matches),
               maximum_historical_energy_difference_J=max(abs(r["energy_diff_J"]) for r in matches),
               statuses=dict(Counter(r["status"] for r in calls)),stops=dict(Counter(r["stop"] for r in fin))))
    print((DATA/"batch_receipt.json").read_text())


if __name__=="__main__":
    main()
