"""Generate every stage from the fixed topology, operation counts and one OPP."""
from dataclasses import dataclass
from functools import lru_cache
from math import ceil, prod

from events import Stage


@dataclass(frozen=True)
class Op:
    inputs: tuple
    shape: tuple
    mac: int
    traffic_bytes: int


@lru_cache(maxsize=8)
def graph_features(blocks, side, input_channels, element_bytes):
    """Expand the reference Darknet parser's separate activation layers."""
    raw_input = (side, side, input_channels)
    ops, original_ends, heads = [], [], []

    def shape(index):
        return raw_input if index == -1 else ops[index].shape

    def add(inputs, output, mac=0, weight_count=0):
        total_values = sum(prod(shape(j)) for j in inputs) + prod(output) + weight_count
        ops.append(Op(tuple(inputs), output, mac, element_bytes * total_values))

    def original_layer(idx, offset):
        return original_ends[idx + offset if offset < 0 else offset]

    for i, (kind, *values) in enumerate(blocks):
        prev = len(ops)-1
        h, w, c = shape(prev)
        if kind == "conv":
            channels, kernel, stride, activation = values
            out = (ceil(h/stride), ceil(w/stride), channels)
            weights = kernel*kernel*c*channels
            add([prev], out, out[0]*out[1]*weights, weights)
            if activation:
                add([len(ops)-1], out)
        elif kind == "pool":
            _, stride = values
            add([prev], (ceil(h/stride), ceil(w/stride), c))
        elif kind == "route":
            sources = [original_layer(i, offset) for offset in values]
            shapes = [shape(j) for j in sources]
            if any(s[:2] != shapes[0][:2] for s in shapes):
                raise ValueError("route spatial extent differs")
            add(sources, (*shapes[0][:2], sum(s[2] for s in shapes)))
        elif kind == "shortcut":
            other = original_layer(i, values[0])
            if shape(other) != (h, w, c):
                raise ValueError("residual extent differs")
            add([prev, other], (h, w, c))
        elif kind in ("upsample", "reorg"):
            factor = values[0]
            out = (h*factor, w*factor, c) if kind == "upsample" else (h//factor, w//factor, c*factor**2)
            add([prev], out)
        elif kind in ("region", "yolo"):
            add([prev], (h, w, c))
            heads.append(len(ops)-1)
        else:
            raise ValueError(f"unknown operation {kind}")
        original_ends.append(len(ops)-1)
    return tuple(ops), tuple(heads)


def live_bytes(ops, heads, cut, scalar_bytes):
    """Distinct outputs needed after the cut, including heads consumed in post."""
    required = {j for op in ops[cut+1:] for j in op.inputs if 0 <= j <= cut}
    required.update(j for j in heads if j <= cut)
    return scalar_bytes * sum(prod(ops[j].shape) for j in required)


def fixed_clocks(platform, opp):
    clock = platform["clock"]
    if len(opp) != 3 or any(level not in clock["levels"] for level in opp):
        raise ValueError("expected CPU/GPU/DLA level triplet")
    return dict(zip(clock["domain_order"], (clock["levels"].index(x) for x in opp)))


def build_chains(platform, frozen, deployment, opp):
    indices = fixed_clocks(platform, opp)
    clock, service, image = (platform[k] for k in ("clock", "service", "image"))
    ratio, active_factor = {}, {}
    for domain, level in indices.items():
        freq, volt = clock["mhz"][domain], clock["volt"][domain]
        ratio[domain] = freq[level]/freq[-1]
        active_factor[domain] = ratio[domain]*(volt[level]/volt[-1])**2
    chains = {}
    for app in frozen["applications"]:
        key = str(app["id"])
        blocks = platform["architecture_reference"]["graphs"][key]["blocks"]
        ops, heads = graph_features(tuple(tuple(row) for row in blocks), image["side"],
                                    image["channels"], image["bytes_per_scalar"])
        if len(ops) != app["layers"]:
            raise ValueError(f"reference topology count mismatch for app {key}")
        boxes_times_width = sum(prod(ops[j].shape) for j in heads)
        boxes, rem = divmod(boxes_times_width, image["coco_classes"]+5)
        if rem:
            raise ValueError("unexpected head size")
        cpu = service["CPU"]
        pre_ms = cpu["pre_setup_ms"] + cpu["pre_ms_per_megapixel"]*image["side"]**2/1e6
        post_ms = cpu["post_setup_ms"] + cpu["post_ms_per_box"]*boxes
        def cpu_stage(name, ms):
            alpha = cpu[name+"_freq_fraction"]
            t = ms*1e6*(1-alpha+alpha/ratio["CPU"])
            return Stage(f"app{key}.{name}", app["cpu_core"], ceil(t),
                         cpu[name+"_active_W_H"]*active_factor["CPU"])
        def transfer(name, n_bytes):
            x = service["XFER"]
            t = x["setup_us"]*1000 + n_bytes/x["bytes_per_ns"]
            return Stage(f"app{key}.{name}", "XFER", ceil(t), x["active_W"])
        chain = [cpu_stage("pre", pre_ms),
                 transfer("input", image["side"]**2*image["channels"]*image["bytes_per_scalar"])]
        for resource, first, last in frozen["deployments"][deployment]["stages"][key]:
            domain = "DLA" if resource.startswith("DLA") else resource
            device = service[domain]
            section = ops[first:last+1]
            mac = sum(op.mac for op in section)
            traffic = sum(op.traffic_bytes for op in section)
            t = (device["setup_us"]*1000 + mac/(device["mac_per_ns_H"]*ratio[domain]) +
                 traffic/device["bytes_per_ns"])
            chain.append(Stage(f"app{key}.{resource}[{first}-{last}]", resource, ceil(t),
                               device["active_W_H"]*active_factor[domain]))
            chain.append(transfer(f"after_{last}", live_bytes(ops, heads, last, image["bytes_per_scalar"])))
        chain.append(cpu_stage("post", post_ms))
        chains[app["id"]] = chain
    return chains


def thermal_kwargs(platform, opp, ambient_C, leakage, variation):
    indices = fixed_clocks(platform, opp)
    therm, pw = platform["thermal"], platform["power"]
    factor = therm["resistance_multipliers"][variation]
    ambient_g = therm["ambient_conductance_W_K"]
    couplings = therm["pair_conductance_W_K"]
    g = [[((ambient_g[i]+sum(couplings[i])) if i == j else -couplings[i][j])/factor
          for j in range(4)] for i in range(4)]
    def node_values(field):
        values = [pw[field][domain][indices[domain]] for domain in ("CPU", "GPU", "DLA")]
        return [*values[:2], *(values[2]*fraction for fraction in pw["DLA_node_weights"])]
    return dict(capacity_J_K=therm["capacity_J_K"], conductance_W_K=g,
                idle_W=node_values("idle_by_domain_W"),
                slope_W_K=node_values("temp_slope_domain_W_K") if leakage else [0.0]*4,
                board_W=pw["board_W"], board_heat_fraction=pw["board_heat_fraction"],
                transfer_heat_fraction=pw["transfer_heat_fraction"], ambient_C=ambient_C,
                reference_C=therm["reference_C"], initial_C=therm["initial_C"], limits_C=therm["limits_C"])
