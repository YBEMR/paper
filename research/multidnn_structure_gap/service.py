"""Frozen additive arithmetic/traffic service law; new graphs, unchanged hardware scalars."""
from math import ceil,prod
from functools import lru_cache
from topology import load_ops
from profiles import fixed_clocks,live_bytes,build_chains as old_chains
from events import Stage

def build_chains(platform,frozen,deployment,opp):
    indices=fixed_clocks(platform,opp)
    clock,service=platform["clock"],platform["service"]
    ratio={d:clock["mhz"][d][i]/clock["mhz"][d][-1] for d,i in indices.items()}
    factor={d:ratio[d]*(clock["volt"][d][i]/clock["volt"][d][-1])**2 for d,i in indices.items()}
    result={}
    for app in frozen["applications"]:
        key=str(app["id"]);g=frozen["graphs"][app["model"]];ops=load_ops(g)
        cpu=service["CPU"];side=g["side"]
        pre=cpu["pre_setup_ms"]+cpu["pre_ms_per_megapixel"]*side**2/1e6
        if g["profile_kind"]=="detection":
            boxes=sum(prod(ops[h].shape) for h in g["heads"])//85
            post=cpu["post_setup_ms"]+cpu["post_ms_per_box"]*boxes
        else:
            # Task returns 1000 logits; no invented detector boxes/NMS.
            post=cpu["post_setup_ms"]
        def cpu_stage(name,ms):
            alpha=cpu[name+"_freq_fraction"]
            return Stage(f"app{key}.{name}",app["cpu_core"],ceil(ms*1e6*(1-alpha+alpha/ratio["CPU"])),
                         cpu[name+"_active_W_H"]*factor["CPU"])
        def transfer(name,n):
            x=service["XFER"]
            return Stage(f"app{key}.{name}","XFER",ceil(x["setup_us"]*1000+n/x["bytes_per_ns"]),x["active_W"])
        chain=[cpu_stage("pre",pre),transfer("input",side**2*g["channels"]*2)]
        for resource,first,last in frozen["deployments"][deployment]["stages"][key]:
            domain="DLA" if resource.startswith("DLA") else resource
            device=service[domain];section=ops[first:last+1]
            t=device["setup_us"]*1000+sum(o.mac for o in section)/(device["mac_per_ns_H"]*ratio[domain])+sum(o.traffic_bytes for o in section)/device["bytes_per_ns"]
            chain.append(Stage(f"app{key}.{resource}[{first}-{last}]",resource,ceil(t),device["active_W_H"]*factor[domain]))
            chain.append(transfer(f"after_{last}",live_bytes(ops,g["heads"],last,2)))
        chain.append(cpu_stage("post",post))
        result[app["id"]]=chain
    return result
