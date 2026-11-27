"""Reconstruct actual retention, concrete deadline conflicts, physical proofs and all delivered SAFE identities."""
import gzip
import inspect
import json
import subprocess
from collections import Counter
from functools import lru_cache
import psutil
from foundation import *
import proof_check as oldcheck
from pack_c import pack,table

def physical_check(k,stack,arms):
    text=inspect.getsource(oldcheck.check)
    mark='for m in "RPDCH":'
    assert text.count(mark)==1
    env=dict(oldcheck.__dict__,HERE=HOME_C,RAW=OUT_C,active_arms=arms)
    exec(compile(text.replace(mark,"for m in active_arms:"),"<frozen physical checks, current archive>", "exec"),env)
    env["check"](k,stack)

def examine(k,stack,arms):
    o=cases()[k];base=HOME_C/"results"/k
    f=stack[0].Flow(o["word"],35,o["case"],OUT_C,frozen.A/"registration/inputs"/o["input"])
    b=Builder(f,f.eng);ns=[0,*limits(b)];summary=[];original={}
    @lru_cache(maxsize=4000)
    def ext(j,pair,q):return f.extension(b.types[j],*b.counts[j],*pair,*q)
    @lru_cache(maxsize=2000)
    def cap(c,j):return margins(f,c,j,ns[j])
    for m in ["C",*arms]:
        root=B_SRC/"results"/k if m=="C" else base
        run=read(root/f"runs/{m}.json");patients={};parents={};proofs=set()
        local={};supp=None;kept=[];blocks=repairs=0;diff=None;size_diff=None;visited=set()
        slot_info=None;retime=0.;replaced=0
        folder=base/"diagnostics";folder.mkdir(exist_ok=True)
        with gzip.open(folder/(m+"-blocks.jsonl.gz"),"wt",encoding="utf8") as file:
            def write(row):file.write(json.dumps(row,separators=(",",":"))+"\n")
            for ev in events(root,run):
                tag=ev[0]
                if tag=="parent":parents[ev[1]]=bytes.fromhex(ev[2])
                if tag=="strict_proof":proofs.add(bytes.fromhex(ev[1]))
                if tag=="q4_action":
                    _,pid,j,pair,q,delta,t=ev;par=parents[pid];code=par+ext(j,tuple(pair),tuple(q))
                    if not t[-1]:local.setdefault(code,t[4]+(t[5] if j+1==len(ns)-1 else 0))
                    if delta==[0,0]:
                        supp=None
                        patients[pid,j,tuple(pair)]=(code,t)
                    elif supp and (pid,j,tuple(pair))==supp[0] and not t[-1] and supp[1] is not None:
                        before,blocked=supp[1];idx=blocked["i"];l=ledger(f,code)
                        after=detail(f,code,idx,l)
                        assert l[0] and int(l[9])==t[6] and after["slack"]>=0
                        changed=np.frombuffer(code,np.uint8)[ns[j]:]!=np.frombuffer(before,np.uint8)[ns[j]:]
                        moved=[int(sum(changed&(b.types[j]==typ))) for typ in range(2)]
                        write(["legal_supplement",j+1,pid,pair,q,delta,sha(code),after,moved]);repairs+=1
                if tag=="supplement":
                    _,j,pid,pair,q,blocked=ev;key=(pid,j,tuple(pair));cfg,t=patients[key]
                    assert blocked==(t[6]<0)
                    bad=conflict(f,cfg) if blocked else None
                    assert bool(bad)==blocked
                    supp=(key,(cfg,bad) if blocked else None)
                    if blocked:
                        blocks+=1;write(["blocked",j+1,pid,pair,q,sha(cfg),bad])
                if tag=="slot":
                    _,j,old,new,dt=ev;retime+=dt;slot_info=(old,new)
                    if old!=new:replaced+=1
                    assert len(new)<=4 and old[:3]==new[:3]
                    if "Parent" in m and old!=new:
                        oldparents={bytes.fromhex(c)[:ns[j]] for c in old}
                        assert len(oldparents)==1 and bytes.fromhex(new[-1])[:ns[j]] not in oldparents
                if tag=="selection":
                    _,j,expanded,size,chosen=ev;key=j,expanded;visited.add(key)
                    assert size==len(local),(k,m,key,size,len(local))
                    order=sorted(local,key=lambda c:(local[c],c));ranks={c:i+1 for i,c in enumerate(order)}
                    last=j+1==len(ns)-1
                    if not last:
                        assert len(chosen)<=4 and all(not any(bytes.fromhex(c).startswith(p) for p in proofs) for c in chosen)
                    if slot_info and not last:assert slot_info[1]==chosen
                    slots=[]
                    for c in map(bytes.fromhex,chosen if not last else chosen[:4]):
                        slots.append(dict(code=c.hex(),parent=c[:ns[j]].hex(),rank=ranks[c],reference_int=local[c],**cap(c,j)))
                    record=dict(window=j+1,empty_extension=expanded,distinct=size,kept=slots,
                                distinct_parents=len({v["parent"] for v in slots}),observed_choices=chosen,
                                fourth_before=slot_info[0][3] if slot_info and len(slot_info[0])==4 else None)
                    kept.append(record)
                    if m=="C":original[key]=(size,chosen)
                    else:
                        ref=original.get(key)
                        if size_diff is None and (ref is None or size!=ref[0]):size_diff=j+1
                        if diff is None and (ref is None or chosen!=ref[1]):diff=j+1
                    local={};supp=None;slot_info=None
        if m!="C":
            # Stop before a complete pool is right-censored, not a selection divergence.
            censored=bool(run["receipt"]["status"]=="wall" and any(key not in visited for key in original))
        else:censored=False
        put(folder/(m+"-retention.json"),kept)
        summary.append(dict(case=k,arm=m,first_pool_size_diff=size_diff,first_selection_diff=diff,censored=censored,
                            slot_replacements=replaced,completed_slot_s=retime,blocked_pairs=blocks,
                            repairs_to_legal=repairs,observed_retention_layers=len(kept)))
    put(base/"diagnosis.json",summary)
    return summary
def main():
    psutil.Process().cpu_affinity([8]);stack=u.stack()
    decision=read(HOME_C/"joint_decision.json");arms=[*ARMS,"Control"]
    if decision["eligible"]:arms.append(decision["arm"])
    oldsources=read(B_SRC/"sources.json")
    idx=read(Path(os.environ["U3B_SRC"])/"registration/frozen_sources.json")
    for item in idx["files"]:
        assert sha((Path(os.environ["U3A_INPUTS"])/item["tree"]/item["path"]).read_bytes())==item["sha256"]
    for directory,pin in [(B_SRC,"c6d1a32f0dc378b80130a8280aca1b7dd9dd5773"),(frozen.A,oldsources["pins"]["u4a"]),(Path(os.environ["U3B_SRC"]),oldsources["pins"]["u3b"])]:
        assert subprocess.check_output(["git","-C",str(directory),"rev-parse","HEAD"]).decode().strip()==pin
        assert not subprocess.check_output(["git","-C",str(directory),"diff","HEAD","--","."])
    put(HOME_C/"sources.json",dict(**oldsources,u4b="c6d1a32f0dc378b80130a8280aca1b7dd9dd5773",inputs_checked=len(cases())))
    rows=[]
    for k in (*FOUR,*[k for k in cases() if k not in FOUR]):
        base=HOME_C/"results"/k
        if not (base/"verified.json").exists():physical_check(k,stack,arms)
        if not (base/"diagnosis.json").exists():examine(k,stack,arms)
        rows.extend(read(base/"diagnosis.json"))
    table("mechanisms",rows)
    for k in FOUR:
        root=HOME_C/"offline"/k
        for pp in root.rglob("plan.json"):
            folder=pp.parent;body=read(pp);d=read(folder/"certificate.json")
            assert sha(u.raw(body))==folder.name==d["plan_sha256"]
            with np.load(folder/"trace.npz") as data:tr=data["events"]
            m=d["metrics"];ej=float(tr[:,26:30].sum()+.3*tr[-1,1]/10000)
            assert m["E_bounds"][0]<=ej<=m["E_bounds"][1] and m["status"]=="SAFE" and max(m["peak_hi"])<=80 and m["min_deadline_slack_ms"]>=0
if __name__=="__main__":main()
