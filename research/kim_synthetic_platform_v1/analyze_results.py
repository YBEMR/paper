"""Summarize every paired candidate. This module only reads completed records."""
import argparse
import csv
import itertools
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
META = ("case_id", "window", "fps", "ambient_c", "leakage", "variation")
MODES = ("independent", "continuous")
NODES = ("cpu", "gpu", "dla0", "dla1")
COLORS = ("#b95236", "#167391", "#5e7949", "#7975a2")
EPS_J = 1e-9


def flag(value):
    if str(value).lower() in ("true", "1"):
        return True
    if str(value).lower() in ("false", "0"):
        return False
    raise ValueError(f"Not a boolean: {value!r}")


def finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Nonfinite measurement: {value!r}")
    return number


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def outcome(row):
    failures = []
    if not flag(row["deadline_ok"]):
        failures.append("deadline")
    if int(row["completed"]) != int(row["required"]):
        failures.append("unfinished_in_window")
    if row["thermal_status"] not in ("SAFE", "VIOLATION", "UNRESOLVED"):
        raise ValueError(f"Unexpected thermal status {row['thermal_status']}")
    if flag(row["thermal_ok"]) != (row["thermal_status"] == "SAFE"):
        raise ValueError("Thermal certificate and feasibility flag disagree")
    if not flag(row["thermal_ok"]):
        failures.append(row["thermal_status"].lower())
    return "+".join(failures) or "feasible"


def group_rows(rows):
    cases = defaultdict(dict)
    expected = {(mode, d, "".join(opp)) for mode in MODES for d in "AC"
                for opp in itertools.product("LMH", repeat=3)}
    for row in rows:
        case = tuple(row[k] for k in META)
        key = row["mode"], row["deployment"], row["opp"]
        if key in cases[case]:
            raise ValueError(f"Duplicate {case} {key}")
        finite(row["energy_j"])
        for node in NODES:
            finite(row[f"peak_{node}_c"])
        row["_status"] = outcome(row)
        cases[case][key] = row
    if not cases:
        raise ValueError("Empty candidate CSV")
    for case, records in cases.items():
        if set(records) != expected:
            raise ValueError(f"Incomplete action/response space in {case}")
        required = {int(r["required"]) for r in records.values()}
        if len(required) != 1:
            raise ValueError(f"Different workload sizes under {case}")
    return cases


def key_order(key):
    d, opp = key
    return (d, *("LMH".index(letter) for letter in opp))


def best(rows):
    allowed = [key for key, row in rows.items() if row["_status"] == "feasible"]
    if not allowed:
        return None, []
    minimum = min(float(rows[key]["energy_j"]) for key in allowed)
    tied = sorted((key for key in allowed if float(rows[key]["energy_j"]) <= minimum + EPS_J),
                  key=key_order)
    return tied[0], tied


def label(key):
    return "-".join(key) if key else ""


def compare(records, restriction=None):
    by_mode = {m: {(d, o): row for (mode, d, o), row in records.items()
                   if mode == m and (restriction is None or restriction(d, o))}
               for m in MODES}
    indep, physical = by_mode.values()
    i, ties_i = best(indep)
    c, ties_c = best(physical)
    summary = {}
    for prefix, key, table, ties in (("ind", i, indep, ties_i), ("cont", c, physical, ties_c)):
        summary.update({
            f"{prefix}_pick": label(key),
            f"{prefix}_deployment": key[0] if key else "",
            f"{prefix}_opp": key[1] if key else "",
            f"{prefix}_feasible_candidates": sum(r["_status"] == "feasible" for r in table.values()),
            f"{prefix}_tie_set": "|".join(map(label, ties)),
            f"{prefix}_predicted_j": float(table[key]["energy_j"]) if key else "",
            f"{prefix}_physical_status": physical[key]["_status"] if key else "no_selection",
            f"{prefix}_physical_j": float(physical[key]["energy_j"]) if key else "",
            f"{prefix}_physical_deadline_ok": physical[key]["deadline_ok"] if key else "",
            f"{prefix}_physical_completed": physical[key]["completed"] if key else "",
            f"{prefix}_physical_required": physical[key]["required"] if key else "",
            f"{prefix}_physical_thermal_status": physical[key]["thermal_status"] if key else "",
            f"{prefix}_history_j": float(physical[key]["energy_j"]) - float(indep[key]["energy_j"]) if key else "",
        })
        for node in NODES:
            summary[f"{prefix}_physical_peak_{node}_c"] = physical[key][f"peak_{node}_c"] if key else ""
    regret = ""
    if i is not None and c is not None and physical[i]["_status"] == "feasible":
        regret = float(physical[i]["energy_j"]) - float(physical[c]["energy_j"])
        if regret < -EPS_J * 1.01:
            raise ValueError("Physical selector worse than admissible candidate")
    if i is None and c is None:
        change, why = "neither_selected", "no_feasible_action"
    elif i is None:
        change, why = "continuous_only", "independent_rejects_all"
    elif c is None:
        change, why = "independent_only", "no_continuously_feasible_action"
    elif i == c:
        change, why = "none", "same_action"
    else:
        change = "deployment" if i[0] != c[0] else "frequency_only"
        why = []
        if physical[i]["_status"] != "feasible":
            why.append("ind_pick_fails_replay:" + physical[i]["_status"])
        if indep[c]["_status"] != "feasible":
            why.append("cont_pick_previously_rejected:" + indep[c]["_status"])
        if i in ties_c or c in ties_i:
            why.append("energy_tie")
        if not why:
            why.append("energy_order_on_two_common_feasible_actions")
        why = "|".join(why)
    # Never treat a replay-infeasible selection's lower energy as a saving.
    summary.update(change=change, reason=why, physical_regret_j=regret,
                   physical_regret_pct=(100*regret/float(physical[i]["energy_j"])
                                        if regret != "" and float(physical[i]["energy_j"]) > 0 else ""))
    return summary


def summarize(cases):
    all_choices, by_deployment, by_frequency = [], [], []
    for case, records in cases.items():
        meta = dict(zip(META, case))
        all_choices.append({**meta, **compare(records)})
        for d in "AC":
            by_deployment.append({**meta, "deployment": d,
                                  **compare(records, lambda dep, opp: dep == d)})
        for levels in itertools.product("LMH", repeat=3):
            opp = "".join(levels)
            scans = compare(records, lambda dep, o: o == opp)
            def gap(mode):
                return (float(records[mode, "C", opp]["energy_j"])
                        - float(records[mode, "A", opp]["energy_j"]))
            by_frequency.append({
                **meta, "opp": opp, **scans,
                "ind_C_minus_A_j": gap("independent"),
                "cont_C_minus_A_j": gap("continuous"),
                "H_C_minus_H_A_j": gap("continuous") - gap("independent"),
                **{f"{m}_{d}_status": records[m, d, opp]["_status"] for m in MODES for d in "AC"},
            })
    return all_choices, by_deployment, by_frequency


def render(cases, decisions, trajectory, folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams.update({"svg.fonttype": "none", "svg.hashsalt":"kim-synth-v1",
                         "font.family":"DejaVu Sans", "font.size":9,
                         "axes.spines.top":False, "axes.spines.right":False})
    def save(fig, name):
        fig.savefig(folder / name, metadata={"Date":None}, bbox_inches="tight")
        plt.close(fig)

    primary = [r for r in decisions if r["window"] == "10s" and r["variation"] == "base"
               and r["leakage"] == "on"]
    primary.sort(key=lambda r:(float(r["ambient_c"]), float(r["fps"])))
    if not primary:
        raise ValueError("Missing 10-second base cases with active thermal leakage")
    pos = list(range(len(primary)))
    ticks = [f"{int(float(r['ambient_c']))} °C\n{r['fps']} FPS" for r in primary]
    fig, ax = plt.subplots(figsize=(8.0,3.8), layout="constrained")
    for prefix, dx, color, legend in [
            ("ind", -0.18, "#427591", "Independent selection, continuous replay"),
            ("cont", 0.18, "#c7824f", "Continuous selection, continuous replay")]:
        for j, row in enumerate(primary):
            admissible = row[f"{prefix}_physical_status"] == "feasible"
            if admissible:
                ax.bar(j+dx, row[f"{prefix}_physical_j"], width=.32, color=color)
                ax.text(j+dx,row[f"{prefix}_physical_j"],row[f"{prefix}_deployment"],
                        ha="center",va="bottom",fontsize=7)
            else:
                ax.scatter(j+dx,0,marker="x",color=color)
        ax.plot([],[],color=color,lw=7,label=legend)
    ax.set(xticks=pos, xticklabels=ticks, ylabel="Board energy over full window (J)",
           title="10-second service | feasible selections on continuous replay")
    ax.set_ylim(bottom=0,top=max(1,ax.get_ylim()[1]*1.07))
    ax.grid(axis="y",alpha=.18)
    ax.legend(loc="upper left",bbox_to_anchor=(0,-.23),ncol=2,frameon=False,fontsize=8)
    if any(r[k+"_physical_status"] != "feasible" for r in primary for k in ("ind","cont")):
        fig.text(.98,.98,"× no feasible replay / selection",ha="right",va="top",fontsize=7)
    save(fig,"energy.svg")

    fig, axes = plt.subplots(1,2,figsize=(9,3.5),sharey=True,layout="constrained")
    for ax, deployment in zip(axes,"AC"):
        for mode, dx, color in (("independent",-.18,"#427591"),("continuous",.18,"#c7824f")):
            counts = []
            for row in primary:
                group = cases[tuple(row[k] for k in META)]
                counts.append(sum(r["_status"] == "feasible" for (m,d,o),r in group.items()
                                  if m == mode and d == deployment))
            ax.bar([p+dx for p in pos],counts,width=.32,color=color,label=mode.capitalize())
        ax.set(title="Resident deployment "+deployment,xticks=pos,xticklabels=ticks,ylim=(0,28),
               yticks=[0,5,10,15,20,25,27])
        ax.grid(axis="y",alpha=.18)
    axes[0].set_ylabel("Admissible clock triplets (of 27)")
    axes[1].legend(frameon=False,loc="upper left",bbox_to_anchor=(0,-.23),ncol=2)
    fig.suptitle("10-second service | deadline and continuous-temperature certificates")
    save(fig,"feasibility.svg")

    # Show the same predeclared action in both cases, even when the pair is infeasible.
    key_by_id = {k[0]:dict(zip(META,k)) for k in cases}
    tracks = defaultdict(list)
    for row in trajectory:
        m = key_by_id[row["case_id"]]
        if (m["variation"] == "base" and m["leakage"] == "on" and m["window"] == "10s"
                and float(m["fps"]) == 25 and row["opp"] == "HHH"):
            tracks[float(m["ambient_c"]),row["deployment"],row["mode"]].append(row)
    ambients = sorted({key[0] for key in tracks})
    if ambients != [25,30]:
        raise ValueError("Missing specified 25/30 C representative trajectories")
    fig, axes = plt.subplots(2,2,figsize=(10,6),sharex=True,layout="constrained")
    for ri, ambient in enumerate(ambients):
        for ci, dep in enumerate("AC"):
            ax = axes[ri,ci]
            for mode, style in (("independent",":"),("continuous","-")):
                track = sorted(tracks[ambient, dep, mode],key=lambda r:float(r["t_s"]))
                if not track:
                    if mode == "continuous":
                        raise ValueError(f"Missing continuous trajectory {ambient} {dep}")
                    continue
                ts = [float(r["t_s"]) for r in track]
                for node,color in zip(NODES,COLORS):
                    ax.plot(ts,[float(r[node+"_c"]) for r in track],color=color,lw=1.1,ls=style)
            ax.set(title=f"{ambient:g} °C ambient · deployment {dep}")
            ax.grid(alpha=.16)
            if ci == 0: ax.set_ylabel("Temperature (°C)")
            if ri == 1: ax.set_xlabel("Elapsed time (s)")
    handles = [Line2D([],[],color=c,label=n.upper()) for n,c in zip(NODES,COLORS)]
    handles.append(Line2D([],[],color="#444",ls="-",label="Continuous"))
    if any(k[-1] == "independent" and rows for k,rows in tracks.items()):
        handles.append(Line2D([],[],color="#444",ls=":",label="Independent"))
    fig.legend(handles=handles,loc="outside lower center",ncol=len(handles),frameon=False)
    fig.suptitle("Fixed H/H/H clocks · 25 FPS · 10-second service with full evaluation tail")
    save(fig,"temperature.svg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=HERE)
    parser.add_argument("--no-figures",action="store_true")
    args = parser.parse_args()
    folder = args.root
    cases = group_rows(read_csv(folder / "raw" / "candidates.csv"))
    decisions, deployments, frequencies = summarize(cases)
    write_csv(folder / "decisions.csv",decisions)
    write_csv(folder / "deployment_choices.csv",deployments)
    write_csv(folder / "matched_frequencies.csv",frequencies)
    if not args.no_figures:
        figs = folder / "figures"
        figs.mkdir(exist_ok=True)
        render(cases,decisions,read_csv(folder / "raw" / "traces.csv"),figs)
    print(f"{len(cases)} conditions, {len(deployments)} per-deployment choices, "
          f"{len(frequencies)} same-clock contrasts")


if __name__ == "__main__":
    main()
