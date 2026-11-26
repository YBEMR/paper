"""Offline exact W4 regeneration on every observed parent, plus recorded checks at wider widths."""
from bisect import bisect_left
from collections import Counter,defaultdict
from functools import lru_cache
from itertools import combinations
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

from batch import ROOT,RAW
os.environ.setdefault("M1G_RAW",str(ROOT/"audit_work"))
from framework import CORE,Profile,case_for,e,inputs,np,reference

DATA=ROOT/"data/pools"


def dump(path, rows):
    if not rows:
        return
    opener=gzip.open if path.suffix==".gz" else open
    with opener(path,"wt",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(rows)


def stage(path):
    with gzip.open(path,"rt",encoding="utf8") as f:
        return json.load(f)


def group_rows(rows,index):
    groups=defaultdict(list)
    for row in rows:
        groups[index(row)].append(row)
    return groups


def audit_keys(case,j,parent,pool,lookup,limits):
    kinds,a,b=e.window_types(case,j)
    left=len(parent["config"])
    load={}
    for idx,s in pool.items():
        cfg=s["config"];g,n,x,y=s["action"]
        assert cfg.startswith(parent["config"]) and cfg[left:]==case.extension(kinds,a,b,g,n,x,y) and e.digest(cfg)==idx
        if (g,n) not in load:
            load[g,n]=e.load_planes(case,j,parent,g,n,a,b)
        planes=load[g,n]
        ordinary=float(max(planes[:,0]+planes[:,1:]@(x,y)))
        # Independently rerun the exact M1-g lookup: full FIFO followed by a slice,
        # and explicit per-request sums instead of action quota multiplication.
        ledger=case.ledger(cfg,0,case.p.horizon,10000,False,False)
        assert ledger[0]
        late=int(np.sum(ledger[5][left:len(cfg)]>limits[left:len(cfg)]))
        codes=np.frombuffer(cfg[left:],dtype=np.uint8)
        s["keys"]={"NT":s["risk"],"NC":ordinary,
            "ZQ-Beam":(int(s["peak"]>80),int(lookup[0][codes].sum())),
            "LQ-Beam":(late,int(lookup[1][codes].sum()))}


def normalized(k):
    return tuple(k) if isinstance(k,(list,tuple)) else round(float(k),11)


def choose(pool, keys, composite_options=None):
    order=sorted(pool,key=lambda i:(round(float(pool[i]["energy"]),11),pool[i]["config"]))
    if not order:
        return [],{}
    E={i:round(float(pool[i]["energy"]),11) for i in order}
    D={i:round(float(pool[i]["drain"]),11) for i in order}
    R={i:normalized(keys[i]) for i in order}
    def less(values):
        ordered=sorted(values.values())
        return {i:bisect_left(ordered,k) for i,k in values.items()}
    er,dr,rr=map(less,(E,D,R))
    picked=[order[0]]
    for measure in (D,R,{i:er[i]+dr[i]+rr[i] for i in order}):
        if len(picked)==len(order):
            break
        picked.append(min((i for i in order if i not in picked),key=lambda i:(measure[i],E[i],pool[i]["config"])))
    if composite_options is not None:
        # Only the third seat can be additionally excluded. The first two
        # compromise choices after the shared seats suffice for this control.
        eligible=(i for i in order if i not in picked[:2])
        composite_options.extend(sorted(eligible,key=lambda i:(er[i]+dr[i]+rr[i],E[i],pool[i]["config"]))[:2])
    return picked,{i:(er[i],dr[i],rr[i]) for i in picked}


def seat_table(case,scope,j,parents,pool,actual,seats,comparisons):
    sid=hashlib.sha256(("/".join(parents)).encode()).hexdigest()
    selected={}; compromise={}
    for m in CORE:
        keys={i:s["keys"][m] for i,s in pool.items()}
        compromise[m]=[]
        ids,ranks=choose(pool,keys,compromise[m])
        selected[m]=ids
        for slot,idx in enumerate(ids,1):
            er,dr,rr=ranks[idx]
            seats.append(dict(case=case,scope=scope,window=j+1,pool=sid,parents="/".join(parents),policy=m,
                        observed_paths="/".join(actual),n=len(pool),slot=slot,id=idx,risk=json.dumps(keys[idx]),
                        energy_less=er,drain_less=dr,risk_less=rr,rank_sum=er+dr+rr))
    for a,b in combinations(CORE,2):
        first,second=selected[a],selected[b]
        assert first[:2]==second[:2]
        alternative=next((i for i in compromise[a] if i not in second[:3]),None)
        comparisons.append(dict(case=case,scope=scope,window=j+1,pool=sid,left=a,right=b,n=len(pool),
                  comparable3=len(first)>=3,changed3=first[2:3]!=second[2:3],
                  comparable4=len(first)>=4,changed4=first[3:4]!=second[3:4],changed_set=set(first)!=set(second),
                  change_from_third_exclusion=len(first)>=4 and alternative!=first[3],
                  change_from_composite_risk=len(first)>=4 and alternative!=second[3]))
    return selected


def fingerprint(actions,groups):
    raw=[r[:12]+r[13:] if isinstance(r,list) else list(r[:12])+list(r[13:]) for r in actions]
    calibration=[{k:v for k,v in g.items() if k!="end_s"} for g in groups]
    return hashlib.sha256(e.p1.raw([raw,calibration])).hexdigest()


def fixed(case,folder,dest):
    paths={m:stage(folder/m/"w4.json.gz") for m in CORE}
    actions={m:group_rows(log["actions"],lambda r:(r[0]-1,r[1])) for m,log in paths.items()}
    groups={m:group_rows(log["groups"],lambda r:(r["window"]-1,r["parent"])) for m,log in paths.items()}
    profile=Profile(case.p)
    limits=np.asarray(reference(case.p,profile))[1::3]
    lookup=[]
    for modes in (profile.order["main"],profile.li_modes("main")):
        ranks=np.zeros(13,dtype=int)
        for rank,(u,k) in enumerate(modes):
            ranks[k+(10 if u==3 else 0)]=rank
        lookup.append(ranks)
    root=e.initial(case)
    states={root["id"]:root}
    parents=[];seats=[];comparisons=[];candidates=[];terminals=[]
    for j in range(case.windows):
        final=j+1==case.windows
        pools={}
        observed=defaultdict(list)
        for m in CORE:
            ordered=tuple(paths[m]["beam"][j-1]) if j else (root["id"],)
            observed[ordered].append(m)
        for pid in dict.fromkeys(p for group in observed for p in group):
            actual=[m for group,methods in observed.items() if pid in group for m in methods]
            log=dict(actions=[],groups=[])
            pool,complete=e.expand(case,j,[states[pid]],"NT",perf_counter(),float("inf"),log)
            assert complete
            pools[pid]=pool
            sign=fingerprint(log["actions"],log["groups"])
            counts=Counter(r[9] for r in log["actions"])
            for m in actual:
                src=actions[m][j,pid]
                assert fingerprint(src,groups[m][j,pid])==sign,(case.label,m,j,pid)
            parents.append(dict(case=case.label,window=j+1,parent=pid,observed="/".join(actual),
                         candidates=len(log["actions"]),valid=counts["valid"],timing=counts["timing"],
                         duplicate=counts["duplicate"],groups=len(log["groups"]),generation_sha256=sign))
            if final or not pool:
                continue
            audit_keys(case,j,states[pid],pool,lookup,limits)
            for m in actual:
                for row in actions[m][j,pid]:
                    if row[9]=="valid":
                        assert normalized(row[12])==normalized(pool[row[6]]["keys"][m])
            for idx,s in pool.items():
                k=s["keys"]
                candidates.append(dict(window=j+1,parent=pid,id=idx,action="/".join(map(str,s["action"])),
                            E35=s["energy"],drain=s["drain"],peak=s["peak"],NT=k["NT"],NC=k["NC"],
                            Z_unsafe=k["ZQ-Beam"][0],Z_sum=k["ZQ-Beam"][1],L_violations=k["LQ-Beam"][0],L_sum=k["LQ-Beam"][1]))
            seat_table(case.label,"parent",j,(pid,),pool,actual,seats,comparisons)
        next_states={}
        for ordered,methods in observed.items():
            pool={i:s for p in ordered for i,s in pools[p].items()}
            assert len(pool)==sum(len(pools[p]) for p in ordered)
            if final:
                sorted_ids=sorted(pool,key=lambda i:(pool[i]["peak"]>80,max(0,pool[i]["peak"]-80),
                                                    round(pool[i]["energy"],11),pool[i]["config"]))
                for m in methods:
                    run=json.loads((folder/m/"run.json").read_bytes())
                    assert run["stages"][0]["terminal"]==len(sorted_ids)
                    ids=[r["id"] for r in run["records"][:4]]
                    assert ids==sorted_ids[:4]
                    terminals.append(dict(case=case.label,method=m,terminal=len(sorted_ids),top4="/".join(ids)))
            else:
                selected=seat_table(case.label,"actual_pool",j,ordered,pool,methods,seats,comparisons)
                for m in methods:
                    assert selected[m]==paths[m]["beam"][j],(case.label,m,j)
                    next_states.update({i:pool[i] for i in selected[m]})
        states=next_states
    for name,rows in (("generation",parents),("seats",seats),("comparisons",comparisons),("features",candidates),("terminal",terminals)):
        dump(dest/(name+".csv.gz"),rows)


def wider(case,folder,dest):
    # Hash every completed parent on every logged width; validate actual full
    # selections from the recorded inputs, including width>4 energy fill.
    witness={};reports=[];overlaps=Counter()
    root=e.initial(case)
    @lru_cache(None)
    def extension(j,g,n,x,y):
        return case.extension(*e.window_types(case,j),g,n,x,y)
    for method in CORE:
        run=json.loads((folder/method/"run.json").read_bytes())
        for record in run["stages"]:
            width=record["width"];log=stage(folder/method/f"w{width}.json.gz")
            action=group_rows(log["actions"],lambda r:(r[0]-1,r[1]))
            group=group_rows(log["groups"],lambda r:(r["window"]-1,r["parent"]))
            parents={root["id"]:b""}
            for j in range(len(log["beam"])+int(record["terminal"]>0)):
                pool={};keys={}
                for pid,cfg in parents.items():
                    rows=action[j,pid]
                    signing=fingerprint(rows,group[j,pid])
                    key=(j,pid)
                    if key in witness:
                        prior,methods=witness[key]
                        assert signing==prior
                        for m in methods:
                            if m!=method:
                                overlaps[tuple(sorted((method,m)))]+=1
                        methods.add(method)
                    else:
                        witness[key]=(signing,{method})
                    for r in rows:
                        if r[9]=="valid":
                            child=cfg+extension(j,*r[2:6])
                            assert e.digest(child)==r[6] and r[6] not in pool
                            pool[r[6]]=dict(config=child,energy=r[10],drain=r[13],peak=r[11])
                            keys[r[6]]=r[12]
                if j==case.windows-1:
                    assert len(pool)==record["terminal"]
                    terminal=sorted(pool,key=lambda i:(pool[i]["peak"]>80,max(0,pool[i]["peak"]-80),round(pool[i]["energy"],11),pool[i]["config"]))
                    for r in run["records"]:
                        if r["width"]==width:
                            assert terminal[r["rank"]-1]==r["id"]
                    break
                chosen,_=choose(pool,keys)
                expected=list(chosen)
                energy=sorted(pool,key=lambda i:(round(pool[i]["energy"],11),pool[i]["config"]))
                expected.extend([i for i in energy if i not in chosen][:width-len(chosen)])
                assert expected==log["beam"][j]
                parents={i:pool[i]["config"] for i in expected}
            reports.append(dict(case=case.label,method=method,width=width,complete_open=len(log["beam"]),
                                complete_terminal=int(record["terminal"]>0),terminal=record["terminal"]))
    cross=[dict(case=case.label,window=j+1,parent=p,fingerprint=h,distinct_methods=len(ms),
                methods="/".join(sorted(ms))) for (j,p),(h,ms) in witness.items()]
    dump(dest/"all_width_stages.csv.gz",reports)
    dump(dest/"all_width_parent_fingerprints.csv.gz",cross)


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument("index",type=int)
    i=parser.parse_args().index
    _,src=inputs()[i]
    case=case_for(src)
    dest=DATA/src.stem;dest.mkdir(parents=True,exist_ok=True)
    folder=RAW/f"lane{i%7}/engine/runs"/src.stem
    fixed(case,folder,dest)
    wider(case,folder,dest)
    print("AUDITED",src.stem,flush=True)


if __name__=="__main__":
    main()
