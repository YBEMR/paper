"""Reason-gated local recovery and matched pilot. The target remains pinned in every arm."""
import hashlib
import itertools
import random_order as random
import time
from fractions import Fraction as Q
from model import DOM, Invalid, transitions
from heat import evaluate
from search import (Expired,check,eligible_gaps,gridpoints,ordinary,prefer,ranges,rebuild,
                    thermal_order,timing)


def targets(p,rows):
    ranked=[]
    for i in range(1,p.n,3):
        u,k,_=rows[i]
        def activity(opt):
            w,f=opt
            idle,_,busy,_=p.exact[p.kinds[i],w,f]
            # Positive reference-temperature main activity saving, excluding handoffs.
            # For ranking use rounded complete occupied (incl. handoff) energy below
            # only for full acceptance, here compute-only duration is exact.
            return (busy-idle)*p.compute[p.kinds[i],w,f]/1000
        options=[(activity((u,k))-activity(op),op) for op in p.options[i] if op[0]!=u or op[1]<k]
        if options:
            gain,opt=max(options,key=lambda x:(x[0],-x[1][0],-x[1][1]))
            if gain>0: ranked.append((-gain,i,opt))
    return [(i,opt,float(-g)) for g,i,opt in sorted(ranked)]


def screen(p,plan,end):
    rows,low=plan
    found=[];checked=[]
    for i,opt,gain in targets(p,rows)[:8]:
        rec=dict(stage=i,opt=opt,potential_J=gain,starts_checked=0,policies_checked=0)
        checked.append(rec)
        try:
            check(end)
            spans=list(ranges(p,rows,i,opt))
            rec["legal_hold_ranges"]=spans
            if not spans:
                rec["reason"]="TIME_DOMAIN_EMPTY"
                # A concrete heat witness after repairing time, if available.
                chosen=[i]+timing(p,rows,i,opt)[:4]
                rng=random.Random(101);witness=None
                for _ in range(32):
                    check(end)
                    alt=rebuild(p,plan,chosen,rng,pinned=(i,opt),finite=True)
                    if alt:
                        ans=evaluate(p,alt,cert=True)
                        if ans["status"]=="HOT":
                            witness=alt;break
                if witness: rec["hot_plan"]=[witness[0],sorted(witness[1])]
                found.append(rec)
            else:
                rec["reason"]="UNRESOLVED"
                witness=None;safe=False;unresolved=False
                total=sum(b-a+1 for a,b in spans)
                rec["legal_start_count"]=total
                # Across the full 0.1-ms domain and all permitted gap controls.
                # Any safe witness disproves blocking. Timeout is explicitly undecided.
                for a,b in spans:
                    for t in range(a,b+1):
                        check(end);cand=rows.copy();cand[i]=(*opt,t)
                        rec["starts_checked"]+=1
                        gaps=eligible_gaps(p,cand)
                        for h in range(len(gaps)+1):
                            for mask in itertools.combinations(gaps,h):
                                check(end)
                                alt=(cand,frozenset(mask));ans=evaluate(p,alt,cert=True)
                                rec["policies_checked"]+=1
                                if ans["status"]=="SAFE": safe=True;break
                                if ans["status"]=="HOT" and witness is None: witness=alt
                                if ans["status"] not in ("SAFE","HOT"): unresolved=True
                            if safe: break
                        if safe: break
                    if safe: break
                if safe: rec["reason"]="FEASIBLE_AT_OTHER_START_OR_POLICY"
                elif not unresolved and witness:
                    rec["reason"]="HEAT_DOMAIN_EXHAUSTED"
                    rec["hot_plan"]=[witness[0],sorted(witness[1])]
                    found.append(rec)
            if len(found)==2: break
        except Expired:
            rec["budget_exhausted"]=True;break
    return checked,found


def neighbors(p,base,record):
    rows=base[0];i=record["stage"];opt=tuple(record["opt"])
    time_list=timing(p,rows,i,opt)
    hp=record.get("hot_plan")
    hot_list=[];hot=None
    if hp:
        bad=([tuple(x) for x in hp[0]],frozenset(map(tuple,hp[1])))
        hot=evaluate(p,bad,cert=True,trace=True)
        if hot["status"]=="HOT": hot_list=thermal_order(p,bad[0],i,hot)
    local=ordinary(p,rows,i,5,None)[1:]
    rand=random.Random(102).sample([j for j in range(p.n) if j!=i],min(4,p.n-1))
    count=min(4,len(hot_list),len(time_list),len(local),len(rand))
    mix=time_list[:count//2]
    mix=mix+[j for j in hot_list if j not in mix][:count-len(mix)]
    groups={"B0":[],"B1":time_list[:count],"B2":hot_list[:count],"B3":mix,
            "B4a":local[:count],"B4b":rand[:count],"B5":[]}
    return groups,time_list,hot_list,hot


def compare(p,base,record,group,tr,orderlog):
    gs,ts,hs,hot=neighbors(p,base,record)
    i=record["stage"];opt=tuple(record["opt"])
    chosen=[i,*gs[group]];rng=random.Random(101)
    info=dict(members=chosen.copy(),common_extra_count=len(gs["B3"]),target=i,opp=opt,
              reason=record["reason"],heat_evidence=bool(hot and hot["status"]=="HOT"))
    if hot:
        info["violation"]={k:hot[k] for k in ("hotspot","peak_tick","peak_lo","peak_hi")}
    it=0
    try:
        while True:
            check(tr.end);it+=1
            alt=rebuild(p,base,chosen,rng,pinned=(i,opt),finite=True)
            orderlog["moves"].append([i,chosen.copy()])
            ans=tr.consider(alt,force=True) if alt else None
            if group=="B5" and len(chosen)<5 and (not alt or ans and ans["status"]=="HOT"):
                ranking=ts if not alt else hs
                item=next((j for j in ranking if j not in chosen),None)
                if item is not None: chosen.append(item)
            if group=="B0" and not list(ranges(p,base[0],i,opt)): break
    except Expired: pass
    info["members_final"]=chosen
    return info


def pilot(p,base,method,records,tr,orderlog):
    from search import eta
    rng=random.Random(101)
    # One common target list, local solver, control domain and strict acceptance.
    # Direct A+B and delta share the same initial level allocation / LFT sweep.
    if method!="LNS":
        end=tr.end
        tr.end=tr.start+.2*(end-tr.start)
        try: eta(p,base,tr)
        except Expired: pass
        finally: tr.end=end
    relations={}
    if method=="DELTA":
        for record in records:
            groups,*_=neighbors(p,base,record)
            relations[record["stage"]]=groups["B3"]
    ranked=targets(p,base[0])
    if not ranked: return
    n=0
    while True:
        check(tr.end)
        i,opt,_=ranked[n%len(ranked)];n+=1
        current=tr.plan or base
        members=relations.get(i,ordinary(p,current[0],i,5,rng)[1:])
        chosen=[i,*members]
        alt=rebuild(p,current,chosen,rng,pinned=(i,opt),finite=True)
        orderlog["moves"].append([i,chosen])
        if alt: tr.consider(alt)
