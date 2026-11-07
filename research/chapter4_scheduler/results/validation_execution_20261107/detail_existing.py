"""Algebra and integrity checks on saved six-slot results; no physical calls."""
from datetime import datetime,timezone,timedelta
from fractions import Fraction as F
from pathlib import Path
import sys,time
OUT=Path(__file__).resolve().parent
REPO=OUT.parents[3]
sys.path[:0]=[str(REPO),str(REPO/"research/chapter3_experiments")]
from research.chapter4_scheduler.validation.run import read,save,sha,digest,verify


def main():
    began=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    plan=read(OUT/"plan.json");verify(plan);summary=read(OUT/"summary.json")
    if not summary["read_only_audit"]["passed"]:raise ValueError("Read-only receipt audit failed")
    old=read(REPO/"research/chapter4_scheduler/results/validation_design_20261107/static_run.json")["protected_after_sha256"]
    old_mismatches=[p for p,h in old.items() if sha(REPO/p)!=h]
    if old_mismatches:raise ValueError(old_mismatches)
    details=[]
    for row in summary["rows"]:
        d=OUT/"calls"/row["id"];r=read(d/"method/result.json");initial=r["initial_safe_snapshot"]
        current=initial;trajectory=[]
        for packet in r["graph_proposals"]:
            if not packet["strict_accepted"]:continue
            target=next(e for e in r["evaluations"] if e["candidate_sha256"]==packet["candidate_sha256"])
            old_energy=current["receipt"]["weighted_energy_J"];new_energy=target["receipt"]["weighted_energy_J"]
            if not F(new_energy[1])<F(old_energy[0]):raise ValueError("Non-strict recorded acceptance")
            trajectory.append({"from_candidate_sha256":current["candidate_sha256"],"to_candidate_sha256":packet["candidate_sha256"],
                "energy_before_J":old_energy,"energy_after_J":new_energy,
                "saving_lower_J":str(F(old_energy[0])-F(new_energy[1])),
                "energy_target":packet["energy_target"],"extra_edges":packet["additional_reversed_edges"],
                "formed_at_s":target["receipt"]["completed_at_elapsed_s"],"orientation":packet["orientation"],"template":packet["template"]})
            current=target
        old_rows={(sid,a["stage_id"]):a for sid,rs in initial["candidate"]["scenes"].items() for a in rs}
        changes=[{"scene":sid,"stage":a["stage_id"],"before":old_rows[(sid,a["stage_id"])] ,"after":a}
            for sid,rs in r["safe_candidate"]["scenes"].items() for a in rs if a!=old_rows[(sid,a["stage_id"])]]
        if any(a["before"]["unit"]!=a["after"]["unit"] for a in changes):raise ValueError("Unexpected deployment change")
        post=read(d/"post_receipt.json")
        details.append({"id":row["id"],"method_started":read(d/"method_started.json"),"method_return":read(d/"method_return.json"),
            "post_started":read(d/"post_started.json"),"post_return":read(d/"post_return.json"),
            "post_energy_exactly_equal":list(map(F,post["weighted_energy_J"]))==list(map(F,r["evaluation"]["weighted_energy_J"])),
            "component_savings_J":{k:[str(F(row["initial_parts_J"][k][0])-F(row["final_parts_J"][k][1])),
                str(F(row["initial_parts_J"][k][1])-F(row["final_parts_J"][k][0]))] for k in row["initial_parts_J"]},
            "changes":changes,"trajectory":trajectory,"unchanged_scenes":[sid for sid in r["safe_candidate"]["scenes"]
                if r["safe_candidate"]["scenes"][sid]==initial["candidate"]["scenes"][sid]],
            "structural_attempts":len(r["reconstruction_attempts"]),
            "deadline_rejections":sum(bool(p["deadline_violations"]) for p in r["reconstruction_attempts"]),
            "receipt_state_counts":{state:sum(e["receipt"]["state"]==state for e in r["evaluations"])
                for state in set(e["receipt"]["state"] for e in r["evaluations"])},
            "raw_formal_experiment_result_flag":r["evaluation"]["formal_experiment_result"],
            "raw_coverage_complete_flag":r["coverage_complete"]})
    end=datetime.now(timezone.utc)
    record={"started_utc":started,"ended_utc":end.isoformat(),"ended_client_time":end.astimezone(timezone(timedelta(hours=8))).isoformat(),
        "wall_s":time.monotonic()-began,"frozen_identities_verified":len(plan["source_sha256"]),
        "old_protected_files_verified":len(old),"old_mismatches":old_mismatches,
        "new_HEFT_or_thermal_calls":0,"details":details}
    save(OUT/"detail_audit.json",record)
    print({"frozen":len(plan["source_sha256"]),"old_protected":len(old),"all_posts_same_energy":all(d["post_energy_exactly_equal"] for d in details),
        "trajectories":{d["id"]:[float(F(t["saving_lower_J"]))*1000 for t in d["trajectory"]] for d in details},"new_physical_calls":0})


if __name__=="__main__":main()
