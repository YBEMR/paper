"""Exactly one fresh process per timed slot; the parent supplies its absolute start."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
from time import perf_counter

from meter import Log,Meter,compact

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CFG=json.loads((HERE/"config.json").read_bytes())


def write(path,obj):
    data=(compact(obj)+"\n").encode()
    path.write_bytes(gzip.compress(data,compresslevel=2,mtime=0) if path.suffix==".gz" else data)


def work(args):
    import psutil
    proc=psutil.Process()
    proc.cpu_affinity([CFG["core"]])
    m=Meter(args.start)
    src=args.source.resolve()
    sys.path[:0]=[str(src/"research/ch3_cooperative_cuts"),str(src/"research/ch3_final_experiments/p2"),
                  str(ROOT/"research/ch3_energy_repair"),str(ROOT/"research/ch3_algorithm_selection")]
    from loads import install
    from catalog_ext import make_domain
    from optimizer import Explorer
    from allocation import CostAllocation
    from evaluation import Evaluation
    import search
    dest=HERE/"units"/args.slot
    pin=json.loads((HERE/"identity.json").read_bytes())
    for name,sha in pin.items():
        root=ROOT if name.startswith(("research/ch3_energy_repair/","research/ch3_algorithm_selection/")) else src
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha:
            raise ValueError("Input identity differs: "+name)
    domain=make_domain(src)
    if domain.size!=4319803: raise ValueError("Invalid domain")
    flow,events=Log(dest/"flow.jsonl.gz",m),Log(dest/"events.jsonl.gz",m)
    ev=Evaluation(src,f"forward_flat_{args.temp}C",domain.stages,args.arm,m,flow,CFG)
    install(ev,args.load)
    ev.identify()
    cfg=json.loads((ROOT/"research/ch3_energy_repair/config.json").read_bytes())
    starts=["A","C"]+random.Random(args.seed).sample([d for d in domain.legacy_ids if d not in ("A","C")],6)
    events.add([m.tick(),"identity",dict(context=ev.context,domain=domain.size,anchors=starts,
                optimizer_config=cfg,arm=args.arm,load=args.load,temp=args.temp,seed=args.seed)])
    def emit(kind,payload,when=None):
        if kind=="parent": ev.post_start=True
        now=m.tick()
        events.add([now if when is None else when,kind,payload])
        if kind=="incumbent":
            events.add([now,"incumbent_cost",[payload[0],m.snapshot()]])
    begin=m.tick()
    m.label="search_control" if not args.fixed else "trace_io_and_control"
    winner=None
    if args.fixed:
        comparisons=Log(dest/"comparison.jsonl.gz",m)
        checked=0
        truncated=False
        with gzip.open(HERE/"units"/args.fixed/"flow.jsonl.gz","rt",encoding="utf8") as original:
            for line in original:
                seq,kind,params,_,end,expected=json.loads(line)
                if end>20: break
                if perf_counter()-args.start>=119.5:
                    truncated=True
                    break
                if kind=="proxy":
                    actual=ev.proxy(*params)
                elif kind=="deadline":
                    d,j,i=params
                    sched=ev._bound_schedule(ev.platform,ev.scenes[j],d,ev.opps[i])
                    actual=[bool(sched.deadline_feasible),int(sched.min_slack_ns)]
                elif kind=="full":
                    from dataclasses import asdict
                    d,idx=params
                    answer=ev.replay(d,idx)
                    actual=[asdict(answer),ev._physical[d,tuple(idx)]["scene_rows"]]
                else: raise ValueError(kind)
                # Compare all clock indices, request counts, slack, entry/exit temperatures, both peak
                # bounds and thermal classifications. JSON normalizes tuple/list representations.
                ok=compact(actual)==compact(expected)
                comparisons.add([seq,kind,params,end,m.tick(),ok])
                if not ok: raise ValueError(f"Fixed flow disagreement at {seq} {kind}: {params}")
                checked+=1
        comparisons.close()
        summary=dict(checked=checked,truncated=truncated)
    else:
        cls=CostAllocation if args.arm=="C" else Explorer
        engine=cls(ev,domain,args.seed,"energy_only",cfg,search.Clock(args.start,args.start+116),emit)
        for method,category in [("neighborhood","candidate_generation"),("rank","candidate_ranking"),
                                ("setfreq","setfreq_control"),("parent","parent_selection")]:
            original=getattr(engine,method)
            def timed(*a,_fn=original,_cat=category,**kw):
                with m.doing(_cat): return _fn(*a,**kw)
            setattr(engine,method,timed)
        summary=engine.run(starts)
        winner=summary["winner"]
    search_end=m.tick()
    m.label="closeout"
    if winner:
        proof=ev.certificate(winner)
        with m.doing("logging"): write(dest/"selection.json.gz",proof)
    events.close()
    flow.close()
    metrics=m.snapshot()
    mem=proc.memory_info()
    write(dest/"result.json",dict(slot=args.slot,arm=args.arm,load=args.load,temp=args.temp,seed=args.seed,
          fixed=bool(args.fixed),startup_s=begin,search_end_s=search_end,summary=summary,
          context=ev.context,counts=dict(ev.counters),meter=metrics,boundaries=m.boundaries,
          lru={n:getattr(ev,n).cache_info()._asdict() for n in ("_schedule","_proxy","_chain","_stages","_chain_cost")},
          peak_rss_bytes=getattr(mem,"peak_wset",mem.rss),peak_cache_array_bytes=ev.max_bytes,
          peak_cache_entries=ev.max_entries,gate_cold_counts=sorted(ev.gate_shapes),flow_rows=flow.n))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--start",type=float,required=True)
    parser.add_argument("--load",required=True)
    parser.add_argument("--temp",type=int,required=True)
    parser.add_argument("--seed",type=int,required=True)
    parser.add_argument("--arm",choices="ABC",required=True)
    parser.add_argument("--slot",required=True)
    parser.add_argument("--fixed")
    work(parser.parse_args())
