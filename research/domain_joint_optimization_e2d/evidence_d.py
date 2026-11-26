"""Audit each frozen branch, ordered certificate transfer and module interval."""
import collections
import gzip
import json
from design_d import core_kind,sha,read

def check_jobs(folder,events,variant):
    groups=collections.defaultdict(list)
    for e in events:
        if e["it"] is not None:groups[e["it"]].append(e)
    local=[];aux=[];modules=[];certificates=0
    for n,ev in sorted(groups.items()):
        pick=lambda code:[v for v in ev if v["event"]==code]
        sub,=pick("subproblem")
        route,=pick("route");kind=core_kind(variant,n,route["grant"])
        assert route["module"]==kind and route["source"]==sub["source"]
        assert route["compact_enabled"]==(variant!="NoAux")
        local.append(sub["elapsed"])
        for label,status,total in sub["phases"]:
            if label=="auxiliary":
                assert n%4!=3;aux.append(total)
        for region in pick("core_region"):
            assert region["origin"]==kind and region["mode"]==(3 if n%4==3 else 1)
            assert len(region["sf"])<=12 and len(region["st"])<=24
        begins=pick("module_begin");ends=pick("module_end")
        for b in begins:
            mod=b["module"]
            if mod=="hint":assert n%4!=3
            elif mod=="aux_cp":assert n%4!=3 and variant!="NoAux"
            else:assert mod==kind
            match=[v for v in ends if v["module"]==mod]
            if match:
                assert len(match)==1
                dur=match[0]["seconds"];censored=False
            else:
                # Worker completion was preempted. Bound elapsed wall time by
                # the parent's observed termination, in the same clock domain.
                kill=next(v for v in pick("worker_exit") if v["deadline"] and v["t"]>=b["t"])
                # Monotonic offsets are recorded for both streams; use parent
                # receipt-to-termination for the explicitly censored observation.
                dur=max(0,kill["t"]-b["t"]);censored=True
            modules.append(dict(it=n,cycle=sub["cycle"],module=mod,seconds=dur,censored=censored))
        transferred=[];grants={}
        dispatch={x["serial"]:x for x in pick("dispatch")}
        for h in pick("handoff"):
            path=folder/"handoff"/(f"{h['serial']:05d}.jsonl")
            buf=path.read_bytes() if path.exists() else b""
            assert sha(buf)==h["sha256"]
            msgs=[json.loads(l) for l in buf.splitlines()]
            assert len(msgs)==h["records"] and h["ack"] in (len(msgs),None)
            for typ,v in msgs:
                cutoff=dispatch[h["serial"]]["deadline"]
                if typ=="rights":
                    if v["at"]<=cutoff:
                        grants.setdefault("hint" if v["stage"]=="hint" else "cp",v)
                else:
                    assert typ=="cert" and v["source"]==sub["source"]
                    transferred.append((v["sha"],v["stage"],v["at"]<=cutoff))
        assert route["grant"]==grants.get("cp",grants.get("hint"))
        received=[(v["sha"],v["stage"],v["on_time"]) for v in pick("certificate")]
        assert received==transferred
        sig={(v["stage"],v["sha"]) for v in pick("certificate") if v["on_time"] and v["metrics"]["status"]=="SAFE"}
        assert all((k,h) in sig for k,h,_,_ in sub["improvements"])
        assert sub["adopted"]==(sub["improvements"][-1][1] if sub["improvements"] else None)
        certificates+=len(received)
    assert list(sorted(groups))==list(range(len(groups)))
    assert max(local,default=0)<=30 and max(aux,default=0)<=11
    boots=[v for v in events if v["event"]=="worker_ready"]
    starts=[v for v in events if v["event"]=="worker_start"]
    exits=[v for v in events if v["event"]=="worker_exit"]
    assert len(starts)==len(exits) and sorted(v["pid"] for v in starts)==sorted(v["pid"] for v in exits)
    return dict(local_count=len(local),local_max=max(local,default=0),aux_max=max(aux,default=0),
            initialized=len(boots),restarts=max(0,len(starts)-1),
            initialization_timeouts=sum(v["event"]=="initialization_timeout" for v in events),
            ready=boots,creation=starts,termination=exits,certificates=certificates,modules=modules,
            send_s=sum(v["send_s"] for v in events if v["event"]=="dispatch"),
            reply_s=sum(v["reply_s"] for v in events if v["event"]=="command_done"))
