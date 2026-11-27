"""Offline comparisons; only past HOT receipts are eligible references for each rank."""
import csv
import gzip
import json
import os
import zlib
from collections import Counter, defaultdict
from functools import lru_cache
from itertools import accumulate
from pathlib import Path
from archive_audit import A, HERE, LAB, OUT, FOCUS, common, np, raw, read, sha, table, workload

def profiles():
    p = Path(os.environ.get("U3A_INPUTS", LAB/"U3a_inputs"))/"four/research/chapter4_cross_analysis_v5/formal_runner/v1/p1/config"
    lengths = {}
    for name in ("gpu_profiles", "cpu_npu_profiles"):
        with (p/(name+".csv")).open() as f:
            for row in csv.DictReader(f):
                device = 2 if name=="gpu_profiles" else 3 if row["domain"]=="npu" else 1
                lengths[row["stage"],device,int(row["k"])]=int(row["ticks"])
    return lengths

def block_reader(phys):
    index = json.loads(gzip.decompress((phys/"block-index.json.gz").read_bytes()))
    parts = read(phys/"manifest.json")["parts"]
    @lru_cache(None)
    def part(i):
        b=(phys/parts[i]["name"]).read_bytes()
        assert sha(b)==parts[i]["sha256"]
        return b
    @lru_cache(400)
    def block(key):
        i,s,n=index[key]; b=zlib.decompress(part(i)[s:s+n]); assert sha(b)==key
        return b
    return block

def signature(code, split, lengths):
    lo=0; profile=[]; dist=[]; busy=[]
    for types in split:
        hist=Counter(zip(types, code[lo:lo+len(types)]))
        f=sorted(set(k for _,k in hist))
        shares=[sum(n for (typ,k),n in hist.items() if typ==v and k>=10)/types.count(v) for v in (0,1)]
        ticks=[sum(n*lengths["AB"[typ]+".main",2+(k>=10),k%10] for (typ,k),n in hist.items() if (k>=10)==d)
               for d in (0,1)]
        profile.append((f,shares)); busy.append(ticks)
        dist.append([[typ,k,n] for (typ,k),n in sorted(hist.items())]); lo+=len(types)
    return profile,dist,busy

def compare(case, rank, cfg, feats, tr, cert, metrics, earlier):
    rows=[]; rank_hit={}
    events=np.ascontiguousarray(tr[:,:14])
    for src in earlier:
        if src["status"] != "HOT":
            continue
        f0=src["features"]; freq=all(a[0]==b[0] for a,b in zip(f0,feats))
        delta=max(abs(x-y) for a,b in zip(f0,feats) for x,y in zip(a[1],b[1]))
        near=freq and delta<=.05+1e-12
        node=metrics["hotspot"]; peak=max(metrics["peak_hi"]); tick=metrics["peak_tick"][node]
        w=min(len(feats),int(tick//10000)+1)
        retrospective=near and node==src["node"] and w==src["hot_window"] and abs(peak-src["peak"])<=.25
        a,b=src["events"],events
        n=min(len(a),len(b))
        mismatch=np.flatnonzero((a[:n].view("<u8")!=b[:n].view("<u8")).any(axis=1))
        shared=int(mismatch[0]) if len(mismatch) else n
        proof=src["proof"]
        proven=bool(proof and shared>=proof["rows"])
        if proven:
            i=proof["rows"]-1; d=proof["node"]
            assert tr[i,18+d]-tr[i,30]>80 and cert["status"]=="HOT"
        rows.append(dict(case=case,rank=rank,earlier_rank=src["rank"],plan=cert["plan"],source=src["plan"],
                         status=cert["status"],same_used_frequencies=freq,max_quota_share_delta=delta,
                         visible_similar=near,delta_peak_C=peak-src["peak"],same_peak_window=(w==src["hot_window"]),
                         same_hotspot=(node==src["node"]),retrospectively_similar=retrospective,
                         shared_request_prefix=common(cfg,src["code"]),shared_event_rows=shared,
                         shared_until_tick=int(events[shared-1,1]) if shared else 0,
                         exact_full_events=shared==len(a)==len(b),prior_proven_HOT=proven))
        for key, matched in (("visible",near),("retrospective",retrospective),("strict",proven)):
            if matched:
                rank_hit.setdefault(key,src["rank"])
    return rows,rank_hit

def physics():
    lengths=profiles(); pools=json.loads(gzip.decompress((OUT/"base_pools.json.gz").read_bytes()))
    poolrows=[]; identities=[]; pairs=[]; bounds=[]; protected=[]; classified=[]; coverage=[]
    for o in read(A/"registration/cases.json"):
        c=o["id"]; root=A/"results"/c
        base=read(root/"runs/Base.json")
        first=next((x for x in base["certificates"] if x["phase"]=="terminal" and x["status"]=="SAFE"),None)
        if not c.startswith("I") and not (first and first["n"]>1):
            continue
        inp,split,_=workload(o); cuts=list(accumulate(map(len,split)))
        refs=defaultdict(set)
        for method in ("Base","Ordinary","Previous","Source","NT10","NT60"):
            p=root/"runs"/(method+".json")
            if p.exists():
                for x in read(p)["certificates"]:
                    if x["phase"] in ("terminal","repair","fallback","nt","group"):
                        refs[x["plan"]].add(method)
        phys=root/"physical"; block=block_reader(phys); records={}; known=defaultdict(list)
        with gzip.open(phys/"plans.jsonl.gz","rb") as f:
            for line in f:
                item=json.loads(line); cert=item["certificate"]; key=cert["plan_sha256"]
                assert sha(raw(item["plan"]))==key
                code=bytes((r[0]-2)*10+r[1] for r in item["plan"]["rows"][1::3])
                if refs[key]:
                    known[code].append((key,cert["metrics"]["status"],sorted(refs[key])))
                if any(key==x["plan"] for x in base["certificates"] if x["phase"]=="terminal"):
                    records[key]=(item,code)
        if c in pools:
            bs=pools[c]; ranked=[bytes.fromhex(x) for x in bs["ranked"]]; tested=bs["certs"]
            for i,cfg in enumerate(ranked,1):
                found=known[cfg]
                label=found[0][1] if len(found)==1 else "unknown"
                coverage.append(dict(case=c,rank=i,config=sha(cfg),in_shortlist=i<=12,
                                     within_Base=i<=len(tested),archived_compatible_status=label,source=found))
            poolrows.append(dict(case=c,legal_terminal=len(ranked),distinct=len(set(ranked)),shortlist=len(bs["shortlist"]),
                                 base_certified=len(tested),archived_known=sum(len(known[q])==1 for q in ranked),
                                 unknown=sum(len(known[q])!=1 for q in ranked),
                                 unique_ancestors_by_window=[len({cfg[:n] for cfg in ranked}) for n in cuts]))
        else:
            tested=[x for x in base["certificates"] if x["phase"]=="terminal"]
        earlier=[]
        for cert in tested:
            key=cert["plan"]; r,cfg=records[key]; rank=cert["n"]; m=r["certificate"]["metrics"]
            tr_bytes=b"".join(block(h) for h in r["blocks"]); assert sha(tr_bytes)==r["trace_sha256"]
            tr=np.frombuffer(tr_bytes,"<f8").reshape(r["shape"])
            ev=np.ascontiguousarray(tr[:,:14]); ehash=sha(ev.tobytes())
            feat,hist,busy=signature(cfg,split,lengths)
            tests,hits=compare(c,rank,cfg,feat,tr,cert,m,earlier)
            pairs.extend(tests)
            lower=tr[:,18:22]-tr[:,30:31]
            pos=np.flatnonzero(lower.max(axis=1)>80)
            proof=None
            if len(pos) and m["status"]=="HOT":
                i=int(pos[0]); node=int(np.argmax(lower[i]))
                # Certified global extrema stay in the frozen model domain for this entire plan.
                if min(m["minimum_lo"])>=20 and max(m["peak_hi"])<=100:
                    proof=dict(rows=i+1,tick=int(tr[i,1]),node=node,lower=float(lower[i,node]),
                               events_sha256=sha(ev[:i+1].tobytes()))
            node=m["hotspot"]; win=min(len(feat),int(m["peak_tick"][node]//10000)+1)
            identities.append(dict(case=c,rank=rank,plan=key,config=sha(cfg),events=ehash,trajectory=r["trace_sha256"],
                                   event_rows=len(tr),node=node,hot_window=win,peak_hi=max(m["peak_hi"]),
                                   status=m["status"],input=o["input_sha256"],frequency_type_histograms=hist,
                                   gpu_npu_work_ticks=busy,hot_witness=proof))
            classified.append(dict(case=c,rank=rank,plan=key,status=cert["status"],kernel_s=cert["kernel_s"],
                                   call_s=cert.get("call_s"),visible_ref=hits.get("visible"),
                                   retrospective_ref=hits.get("retrospective"),strict_ref=hits.get("strict")))
            if first and first["plan"]==key and rank>1:
                protected.append(dict(source="U4-a",case=c,rank=rank,plan=key,status=cert["status"],
                                      visible_ref=hits.get("visible"),strict_ref=hits.get("strict")))
            earlier.append(dict(rank=rank,status=m["status"],plan=key,code=cfg,features=feat,events=ev,
                                peak=max(m["peak_hi"]),node=node,hot_window=win,proof=proof))
            plan=r["plan"]["rows"]; main=plan[1::3]; posts=[v[2] for v in plan[2::3]]
            ends=[v[2]+lengths[inp[i]["kind"]+".main",v[0],v[1]] for i,v in enumerate(main)]
            assert sorted(range(len(cfg)),key=lambda i: (ends[i],i))==sorted(range(len(cfg)),key=posts.__getitem__)
            for j,n in enumerate(cuts[:-1],1):
                boundary=int(inp[n]["release_tick"]); lo=min(posts[n:]); next_end=min(ends[n:])
                bounds.append(dict(case=c,rank=rank,window=j,parent_requests=n,
                                   old_post_started_before_release=sum(t<boundary for t in posts[:n]),
                                   old_main_ended_by_release=sum(t<=boundary for t in ends[:n]),
                                   actually_inserted_before_old=sum(t>lo for t in posts[:n]),
                                   old_main_ends_tied_with_first_new=sum(t==next_end for t in ends[:n])))
    c3=Path(os.environ.get("U3C_SRC",LAB/"U3c_worktree/research/u3c_thermal_localization_validation"))
    with (c3/"tables/flows.csv").open(encoding="utf8") as f:
        for v in csv.DictReader(f):
            if v["terminal_SAFE"] and int(v["tried"])>1:
                protected.append(dict(source="U3-c",case=v["case"],rank=v["tried"],plan=v["terminal_SAFE"],status="SAFE"))
    for name,rows in (("pool_sizes",poolrows),("pool_labels",coverage),("terminal_identities",identities),
                      ("terminal_pairs",pairs),("terminal_cost",classified),("cpu_boundaries",bounds),
                      ("protected_alternatives",protected)):
        table(name,rows)
