"""Losslessly expand archived periodic schedules. No new simulation."""
from pathlib import Path
import gzip,json,csv,argparse
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser()
p.add_argument("schedule_id",help="e.g. a123_D017_LHH")
p.add_argument("--frames",type=int,required=True,choices=[1,62,63])
p.add_argument("--output",type=Path,required=True)
a=p.parse_args()
with gzip.open(HERE/"raw/schedules.jsonl.gz","rt") as f:
    s=next(json.loads(x) for x in f if json.loads(x)["id"]==a.schedule_id)
assert s["deadline_ok"],"Do not replicate an unfinished/late frame as an empty-queue frame"
inp=json.loads((HERE/"inputs.json").read_bytes())
assert a.frames==1 or a.frames in inp["loads"][s["load"]]["frames"]
a.output.mkdir(parents=True,exist_ok=False)
jobs=[];rows=[]
for frame in range(a.frames):
    off=frame*40_000_000
    for q in s["requests"]:
        jobs.append(dict(id=f"f{frame:04d}"+q["id"][5:],app=q["app"],
            release_ns=q["release_ns"]+off,deadline_ns=q["deadline_ns"]+off,
            completion_ns=s["completions_ns"][q["id"]]+off))
    for r in s["rows"]:
        rows.append(dict(r,request=f"f{frame:04d}"+r["request"][5:],
            start_ns=r["start_ns"]+off,end_ns=r["end_ns"]+off))
for name,data in [("requests.csv",jobs),("stages.csv",rows)]:
    with (a.output/name).open("x",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print(dict(requests=len(jobs),stages=len(rows),source="archived exact periodic translation"))
