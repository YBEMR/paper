"""Audit the actual Q4 shortlist under causal FIFO. No enumeration, beam or optimizer calls."""
import json
import tarfile
import tempfile
from pathlib import Path
from common_u2 import *
from review_u2 import DEST,TABLE,emit,unpack

def main():
    decisions=[];ends=[];st=stack()
    with tempfile.TemporaryDirectory() as area:
        area=Path(area);extra=area/"additional_certificates";extra.mkdir()
        for obj in CASES:
            code=obj["case"].split("_")[0]
            with tempfile.TemporaryDirectory() as tmp:
                root,_,_=unpack(DEST/code,Path(tmp))
                for rep in (1,2,3):
                    cell=root/f"r{rep}"/"Q4";calls=lines(cell/"certs.jsonl")
                    info=dict(case=code,rep=rep)
                    if not calls:
                        ends.append(dict(info,status="NO_CONSTRUCTION"));continue
                    source=cell/"evidence"/obj["case"]
                    audits=read(cell.parent/"Q4_causal_audit/audit.json")
                    causal_archive=cell.parent/"Q4_causal_audit/evidence"/obj["case"]
                    seedplan=read(source/calls[0]["plan"]/"plan.json")
                    base=tuple(tuple(row[:2]) for row in seedplan["rows"][1::3])
                    flow=make_flow(st[0],obj,extra/code)
                    eng=st[1].Engine(obj["case"],extra/code)
                    def build(c):
                        r=st[3](flow,encoded(c));assert r is not None
                        return r,eng.build(c,r)
                    def cert(c,r,b):
                        body=dict(case=obj["case"],rows=b["rows"],low=sorted(b["low"]))
                        key=sha(raw(body))
                        for store_dir in (causal_archive,extra/code/"evidence"/obj["case"]):
                            d=store_dir/key
                            if (d/"certificate.json").exists():
                                data=read(d/"certificate.json");tp=d/"trace.npz"
                                if tp.exists():
                                    with np.load(tp,allow_pickle=False) as a:return data,a["events"].copy()
                                records=block_index[tp.relative_to(root).as_posix()]
                                import zlib
                                arr=np.frombuffer(b"".join(zlib.decompress((root/"event_blocks"/k).read_bytes()) for k in records["blocks"]),dtype="<f8").reshape(records["shape"])
                                assert sha(arr.tobytes())==records["sha256"];return data,arr
                        return eng.cert(c,r,b)
                    block_index={v["path"]:v for v in read(root/"event_index.json") if "blocks" in v}
                    current,trace=cert(base,*build(base))
                    assert current["plan_sha256"]==audits[0]["causal"]
                    native_end=read(cell/"rounds.json") if (cell/"rounds.json").exists() else {}
                    valid=(calls[0]["status"]==current["metrics"]["status"])
                    for z,pool in zip(native_end.get("rounds",[]),lines(cell/"pools.jsonl")):
                        if not valid:break
                        candidates=[]
                        for x in pool["candidates"]:
                            nc=list(base)
                            for i in x["ids"]:nc[i]=(x["unit"],x["new_opp"])
                            nc=tuple(nc);r,b=build(nc)
                            candidates.append(dict(c=nc,r=r,b=b,ids=x["ids"]))
                        candidates.sort(key=lambda a:(a["r"]["cost"]+a["r"]["tail"],a["ids"][0],a["c"]))
                        chosen=[]
                        if candidates:
                            chosen.append(candidates[0])
                            t=min(candidates,key=lambda a:(eng.temp_estimate(a["b"]["ev"],trace),a["ids"][0],a["c"]))
                            if t is not chosen[0]:chosen.append(t)
                        accepted=[]
                        for a in chosen:
                            d,tr=cert(a["c"],a["r"],a["b"]);metrics=d["metrics"]
                            if metrics["status"]=="SAFE" and metrics["E_bounds"][1]<current["metrics"]["E_bounds"][0]:
                                accepted.append((metrics["E_bounds"][1],d["plan_sha256"],a,d,tr))
                        ids=None
                        if accepted:
                            _,_,act,current,trace=min(accepted,key=lambda x:x[:2]);base=act["c"];ids=act["ids"]
                        evaluated=z.get("evaluated",[])
                        native_ids=next((x["ids"] for x in evaluated if x["plan"]==z.get("accepted")),None)
                        valid=ids==native_ids
                        decisions.append(dict(info,round=z["turn"]+1,shortlist=len(candidates),native_selected=[x["ids"] for x in evaluated],
                            causal_selected=[a["ids"] for a in chosen],same_selected=[a["ids"] for a in chosen]==[x["ids"] for x in evaluated],
                            same_accepted=valid,native_accepted=native_ids,causal_accepted=ids))
                    ends.append(dict(info,status="PATH_VERIFIED" if valid else "DIVERGENCE",cert_status=current["metrics"]["status"],
                        causal_J=current["metrics"]["E_J"],native_J=native_end.get("final",{}).get("metrics",{}).get("E_J",calls[0]["J"]),
                        comparable_timing=False))
        emit("q4_choice_audit",decisions);emit("q4_causal_endpoints",ends)
        output=DEST/"mechanism_witness";output.mkdir(exist_ok=True)
        ds=list(extra.rglob("certificate.json"));save(output/"q4_audit.json",dict(rounds=len(decisions),endpoints=len(ends),
            changed_selected=sum(not x["same_selected"] for x in decisions),changed_accepted=sum(not x["same_accepted"] for x in decisions),
            extra_certificates=len(ds),search_calls=0))
        if ds:
            with tarfile.open(output/"q4-extra.tar.gz.part000","w:gz") as tar:tar.add(extra,arcname="q4-extra")
if __name__=="__main__":main()
