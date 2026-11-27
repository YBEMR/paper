"""Summarize the two observation cohorts, first handoffs, references, and finite lookahead work."""
import csv
import json
from collections import Counter
from itertools import chain
from statistics import median
from pathlib import Path

HERE=Path(__file__).resolve().parent
FOUR={"I03","I06","I07","I11"}
def read(path):return json.loads(path.read_bytes())
def csvrows(name):
    with (HERE/"tables"/(name+".csv")).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def emit(name,rows):
    with (HERE/"tables"/(name+".csv")).open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
def main():
    cases=csvrows("routes");findings=csvrows("mechanisms")
    arms=list(dict.fromkeys(r["arm"] for r in cases))
    cohorts=[]
    for m in arms:
        for focus in (True,False):
            subset=[r for r in cases if r["arm"]==m and (r["case"] in FOUR)==focus]
            ok=[r for r in subset if r["SAFE"]=="1"]
            direct=[r for r in ok if r["first_phase"]=="terminal"]
            cost=[x for x in findings if x["arm"]==m and (x["case"] in FOUR)==focus]
            cohorts.append(dict(arm=m,cohort="four_failures" if focus else "eight_controls",flows=len(subset),SAFE=len(ok),
                terminal_first=" ".join(r["case"] for r in direct),fallback_first=" ".join(r["case"] for r in ok if r["first_phase"]=="fallback"),
                no_SAFE=" ".join(r["case"] for r in subset if r["SAFE"]=="0"),
                successful_median_first_s=median(float(r["first_s"]) for r in ok) if ok else None,
                successful_min_slack_ms=min((float(r["slack_ms"]) for r in ok),default=None),
                total_construct_s=sum(float(r["construct_s"]) for r in subset),
                total_observed_slot_s=sum(float(r["completed_slot_s"]) for r in cost),actual_replacements=sum(int(r["slot_replacements"]) for r in cost),
                blocked_pairs=sum(int(r["blocked_pairs"]) for r in cost),legal_extensions=sum(int(r["repairs_to_legal"]) for r in cost)))
    emit("cohorts",cohorts)
    rows=[]
    for p in sorted((HERE/"offline").glob("*/window_*.json")):
        x=read(p);cand=x["minimum_candidates"];sl=x["blocked_request"];look=x["lookahead"];roll=x["rollback"]
        rows.append(dict(case=p.parent.name,changed_window=x["window"],first_violation=x["first_failure"],minimum_L1=x["min_L1"],
              assignments_tested=x["trials"],full_SAFE=sum(s["cert"]["status"]=="SAFE" for s in cand),ties=len(cand),
              min_J=min(s["cert"]["energy"] for s in cand),max_J=max(s["cert"]["energy"] for s in cand),
              first_request_index=sl["i"],deadline_tick=sl["deadline"],actual_finish_tick=sl["finish"],
              before_slack_ticks=sl["slack"],restored_min_ticks=min(s["request_after"]["slack"] for s in cand),
              look1_actions=look[0]["trials"] if look else None,look1_legal=look[0]["distinct_legal"] if look else None,
              look2_actions=look[1]["trials"] if len(look)>1 else None,look2_legal=look[1]["distinct_legal"] if len(look)>1 else None,
              rollback_work=" ".join(str(s["trials"]) for s in roll),rollback_recovered=" ".join(str(s["full_legal"]) for s in roll)))
    emit("witnesses",rows)
if __name__=="__main__":main()
