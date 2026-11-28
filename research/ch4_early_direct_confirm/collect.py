"""Read-only reconstruction of online deliveries. Physical blobs are verified after packing."""
import os,sys,struct,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"ch4_quota_transfer"))
import archive as a
ROOT=Path(os.environ["WARM_ROOT"])
OUT=a.OUT=HERE/"results"
CASES=("A02","B07","C11","C12")
def main():
    OUT.mkdir(exist_ok=True)
    registry=a.S/"nt/research/m1i_generalization/registration"
    objs={r["case"].split("_")[0]:r for r in a.read(registry/"cases.json")["cases"] if r["ambient"]==35}
    for p in [*ROOT.glob("*account.json"),ROOT/"admission.json",*ROOT.glob("guards/**/*.json"),*ROOT.glob("preparation/*.json"),
              *ROOT.glob("admission/*/*.json*"),*ROOT.glob("admission/*/stderr.log"),*ROOT.glob("admission/*/registration/input*.*")]:
        a.zipped(p,OUT/"audit"/(str(p.relative_to(ROOT))+".gz"))
    neutral=a.Physical(OUT/"physical"/"neutral")
    for receipt in (ROOT/"admission").glob("*/receipt.json"):
        directory=receipt.parent
        obj=a.read(directory/"registration/input.json")
        data=directory/"registration/inputs/neutral.csv"
        assert a.sha(data.read_bytes())==obj["input_sha256"]
        a.zipped(data,OUT/"audit"/"neutral.csv.gz")
        for name in ("search","early","refine"):
            for event in a.logs(directory/(name+".jsonl")):
                if event["event"]!="certificate":continue
                p=event["point"]
                source=directory/event.get("stage","search/physical")/"evidence"/obj["case"]/p["plan"]
                neutral.add(source,p,obj)
    neutral.finish()
    cells=[];certs=[];steps=[];maps=[];early_events=[];late_count=0
    for case in CASES:
        obj=objs[case]
        src=registry/"inputs"/obj["input"]
        assert a.sha(src.read_bytes())==obj["input_sha256"]
        a.zipped(src,OUT/"inputs"/(case+".csv.gz"))
        a.dump(OUT/"inputs"/(case+".json"),obj)
        physical=a.Physical(OUT/"physical"/case)
        core=set();prev_end=0
        for file in sorted((ROOT/"formal"/case).glob("*/receipt.json"),key=lambda p:a.read(p)["order"]):
            d=file.parent;rc=a.read(file);cap=rc["bound"];split=cap-(5 if cap==60 else 3)
            meta=dict(case=case,rep=rc["rep"],arm=rc["arm"],cap=cap)
            core.add(rc["core"])
            assert rc["start"]>=prev_end and len(core)==1
            prev_end=rc["start"]+rc["wall"]
            sc,ed,rf,ps=[a.logs(d/(name+".jsonl")) for name in ("search","early","refine","pause")]
            assert all(e["request_sha"]==obj["input_sha256"] for e in sc if "request_sha" in e)
            first=next((e["t"] for e in sc if e["event"]=="certificate" and e["point"]["status"]=="SAFE" and e["t"]<=cap),None)
            cut=split if first is not None and first<split else cap
            start=ps[0] if ps else {};resume=next((p for p in ps if p["event"]=="resume"),{})
            assert bool(ps)==(meta["arm"]=="B" and first is not None and first<=14)
            if ps: assert len(ps)==2 and resume["pid"]==start["pid"]
            events=sorted([(e["t"],stream,e) for stream,raw in (("search",sc),("early",ed),("tail",rf)) for e in raw if e["event"]=="certificate"],key=lambda r:r[0])
            best=None;plans={};last=None;direct=None;search_count=0;after=0;early_gain=None
            for t,stream,e in events:
                p=e["point"];stage=e.get("stage","search/physical")
                if t>{"search":cut,"early":start.get("until",0),"tail":cap}[stream]:late_count+=1;continue
                mapping=physical.add(d/stage/"evidence"/obj["case"]/p["plan"],p,obj)
                row=dict(**meta,t=t,stream=stream,stage=stage,plan=p["plan"],mapping=mapping,status=p["status"],J=p["J"],lo=p["bounds"][0],hi=p["bounds"][1],peak_C=p["peak"],slack_ms=p["slack"])
                certs.append(row)
                if stream=="search":
                    plans[p["plan"]]=row;search_count+=1
                    if resume and t>resume["t"]:after+=1
                if stream=="early":
                    assert plans[start["seed"]]["mapping"]==mapping
                    direct=row
                if row["status"]=="SAFE" and (best is None or row["hi"]<best["lo"]):
                    if stream=="early":early_gain=best["J"]-row["J"]
                    best=row;last=t;steps.append(row)
            select=next((e for e in rf if e["event"]=="end" and e.get("task")=="selection" and e["t"]<=cap),{})
            seeds=select.get("seeds",[])
            seedmaps=([plans[start["seed"]]["mapping"]] if ps else [])+[plans[k]["mapping"] for k in seeds]
            assert len(set(seedmaps))==len(seedmaps)<=4
            if select.get("eligible"):assert any(plans[k]["status"]=="HOT" for k in seeds)
            done=any(e["event"]=="stage_end" and e["t"]<=start.get("until",0) for e in ed)
            if ps:
                early_events.append(dict(**meta,seed=start["seed"],delivery=first,start=start["start_s"],end=resume["t"],until=start["until"],occupied_s=resume["elapsed_s"],rc=resume["rc"],
                    stage_complete=int(done),certificate=direct["plan"] if direct else None,strict_gain_J=early_gain,seed_J=plans[start["seed"]]["J"],result_J=direct["J"] if direct else None,
                    resume_incumbent=resume["incumbent"],remaining_search_certs=after))
                maps.append(dict(**meta,slot="early",seed=start["seed"],mapping=seedmaps[0],status="SAFE",start=start["start_s"],finished=int(done),delivered=int(bool(direct))))
            for i,k in enumerate(seeds,1):
                rank=4 if plans[k]["status"]=="HOT" else i
                hits=[e for e in rf if e.get("rank")==rank and e["t"]<=cap]
                proposals=[r for r in certs if all(r[z]==meta[z] for z in meta) and r["stage"]==f"map{rank}/direct"]
                assert all(r["mapping"]==plans[k]["mapping"] for r in proposals)
                maps.append(dict(**meta,slot="tail"+str(rank),seed=k,mapping=plans[k]["mapping"],status=plans[k]["status"],
                    start=next((e["t"] for e in hits if e["event"]=="map_start"),None),finished=int(any(e["event"]=="stage_end" for e in hits)),delivered=int(bool(proposals))))
            counts=struct.unpack("=4q",(d/"counts.bin").read_bytes())
            end=rc["charged"]
            stop=min(cut,end)
            late_dp=sum(e["elapsed_s"] for p in d.glob("map*/events.jsonl") for e in a.logs(p) if e["kind"]=="dp" and e["t"]<=cap)
            early_dp=sum(e["elapsed_s"] for e in a.logs(d/"early/events.jsonl") if e["kind"]=="dp" and e["t"]<=start.get("until",0))
            cells.append(dict(**meta,order=rc["order"],core=rc["core"],stop=rc["reason"],wall=rc["wall"],charged=end,cpu_s=rc["cpu_s"],safe=int(bool(best)),first=first,last=last,J=best["J"] if best else None,
                lo=best["lo"] if best else None,hi=best["hi"] if best else None,plan=best["plan"] if best else None,final_stage=best["stage"] if best else None,
                triggered=int(bool(ps)),early_finished=int(done),early_occupied_s=resume.get("elapsed_s"),early_improvement_J=early_gain,
                search_certs=search_count,search_after_resume=after if ps else None,tail_nominees=len(seeds),tail_finished=sum(e["event"]=="stage_end" and e["t"]<=cap for e in rf),
                generated=counts[0],evaluated=counts[1],legal=counts[2],propagations=counts[3],layers=sum(e["complete"] for e in a.logs(d/"layers.jsonl")),
                search_construct_s=a.spans(sc,"construct",stop),search_cert_s=a.spans(sc,"search_cert",stop),instance_s=a.spans(sc,"instance",stop),
                early_handoff_s=a.spans(ed,"handoff",start.get("until",0)),early_dp_completed_s=early_dp,early_cert_s=a.spans(ed,"dp_cert",start.get("until",0)),
                tail_selection_s=a.spans(rf,"selection",end),tail_handoff_s=a.spans(rf,"handoff",end),tail_dp_completed_s=late_dp,tail_cert_s=a.spans(rf,"dp_cert",end)))
            for p in [*d.glob("*.json*"),*d.glob("*.bin"),d/"stderr.log",*d.glob("search/run.json"),*d.glob("map*/events.jsonl"),*d.glob("early/events.jsonl")]:
                a.zipped(p,OUT/"logs"/case/d.name/(str(p.relative_to(d))+".gz"))
        physical.finish()
        print("verified",case,len(physical.plans),flush=True)
    for name,rows in (("cells",cells),("certificates",certs),("steps",steps),("mapping_slots",maps),("early_events",early_events)):
        a.table(name,rows)
    budget=dict(prep=a.read(ROOT/"preparation_account.json"),formal=a.read(ROOT/"formal_account.json"),units=len(cells),
                summed_nominal=sum(r["cap"] for r in cells),charged=sum(r["charged"] for r in cells),late=late_count,
                per_lane={c:a.read(ROOT/"formal"/c/"account.json") for c in CASES})
    assert budget["units"]==36 and budget["summed_nominal"]==1200 and budget["formal"]["cpu_s"]<=1300 and budget["prep"]["cpu_s"]<=240
    a.dump(OUT/"budget.json",budget)
if __name__=="__main__":main()
