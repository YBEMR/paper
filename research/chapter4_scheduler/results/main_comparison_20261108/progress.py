"""Read-only live progress, no source/evidence writes or research calls."""
from datetime import datetime, timezone
from pathlib import Path
from fractions import Fraction
import json

OUT=Path(__file__).resolve().parent
execution=OUT/"execution"
read=lambda p:json.loads(p.read_text())
plan=read(execution/"plan.json")
done=[];active=None
for slot in plan["slots"]:
    folder=execution/"calls"/slot["id"]
    if not folder.exists():break
    result=folder/"method_return.json"
    if result.exists():
        r=read(result)
        if (folder/"post_return.json").exists() or not r.get("has_SAFE_archive") or r.get("error"):
            done.append({"id":slot["id"],"terminal":r.get("terminal"),"SAFE":r.get("has_SAFE_archive"),
                         "counts":r.get("counts"),"energy_interval_J":r.get("energy_interval_J")})
            continue
    phase="post" if (folder/"post_claim.json").exists() else "method"
    path=folder/(phase+"_evaluation_journal.jsonl")
    attempts=returned=0;last=None
    if path.exists():
        with path.open() as stream:
            for line in stream:
                try:row=json.loads(line)
                except json.JSONDecodeError:continue
                attempts+=row["event"]=="START";returned+=row["event"]=="RETURN";last=row
    active={"id":slot["id"],"phase":phase,"evaluation_attempts":attempts,"returned_receipts":returned,
            "last_event_at_s":last.get("returned_at_s",last.get("started_at_s")) if last else None}
    break
print(json.dumps({"utc":datetime.now(timezone.utc).isoformat(),"completed_methods_and_required_posts":len(done),
       "active":active,"last_completed":done[-1] if done else None,
       "batch_return":read(execution/"batch_return.json") if (execution/"batch_return.json").exists() else None}),flush=True)
