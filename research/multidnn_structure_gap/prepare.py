"""Input construction only. No scheduler, energy objective, or optimizer is called."""
from collections import Counter,defaultdict
from itertools import product
from pathlib import Path
from hashlib import sha256
import json
import shutil
from topology import *

def encoded(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def put(path,x):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(encoded(x)+b"\n")
def digest(p):return sha256(p.read_bytes()).hexdigest()
FAMILIES=[
 dict(id="pair_classifiers",models=["resnet18","mobilenet_v2"],period_ms=[20,40],deadline_ms=[20,30],
      scenes=[[0,1],[0]],durations_ms=[5000,5000]),
 dict(id="pair_mixed",models=["resnet18","yolov3"],period_ms=[20,40],deadline_ms=[20,40],
      scenes=[[0,1],[1]],durations_ms=[5000,5000]),
 dict(id="triple_mixed",models=["resnet18","mobilenet_v2","yolov2"],period_ms=[20,40,40],deadline_ms=[15,30,40],
      scenes=[[0,1],[1,2],[0,1,2]],durations_ms=[3200,3200,3600]),
 dict(id="quad_mixed",models=["resnet18","mobilenet_v2","yolov2tiny","yolov3"],period_ms=[20,40,40,80],deadline_ms=[20,30,40,60],
      scenes=[[0,1],[0,2,3],[1,2,3],[0,1,2,3]],durations_ms=[2480,2480,2480,2560])]
BASE=ROOT/"research/kim_synthetic_platform_v1/platform.json"

def domain(models,graphs):
    options=[list(assignments(graphs[m],diagnostic_cuts(graphs[m]))) for m in models]
    assert all(len(opts)==9 for opts in options)
    patterns=[]
    for opts in options:
        structs=sorted({tuple(("DLA" if r.startswith("DLA") else r,a,b) for r,a,b in opt) for opt in opts})
        patterns.append({p:i for i,p in enumerate(structs)})
    deployments={};rejected=0
    for choices in product(*options):
        slots=sum(r.startswith("DLA") for chain in choices for r,_,_ in chain)
        if slots>4:
            rejected+=1;continue
        name=f"S{len(deployments):05d}"
        genes=[patterns[i][tuple(("DLA" if r.startswith("DLA") else r,a,b) for r,a,b in chain)]
               for i,chain in enumerate(choices)]
        deployments[name]=dict(stages={str(i):c for i,c in enumerate(choices)},
                              per_app_candidate_ids=genes,resident_dla_stages=slots)
    return dict(models=models,search_order=list(deployments),deployments=deployments,
                cuts={m:diagnostic_cuts(graphs[m]) for m in models},physical_bindings=True,
                global_swap_reduction=False,rule="two topology-derived DLA-eligible cells plus mandatory GPU remainder; all 3^2 physical labels per app; coalesce equal neighbors; global resident DLA stages <=4",
                rejected_by_global_capacity=rejected,per_app_options=options)

def case(family,order,holdout=False):
    seq=list(range(len(family["scenes"])))
    if order=="reverse":seq.reverse()
    cid=("H_" if holdout else "")+family["id"]+"_"+order
    durations=[family["durations_ms"][j]*1_000_000 for j in seq]
    starts=[];requests=[];t=0
    periods=[p*1_000_000 for p in family["period_ms"]]
    deadlines=[int(d*1_000_000*(.75 if holdout else 1)) for d in family["deadline_ms"]]
    for j,duration in zip(seq,durations):
        starts.append([t,f"sc{j}"])
        for app in family["scenes"][j]:
            assert duration%periods[app]==0 and 0<deadlines[app]<=periods[app]
            for k,offset in enumerate(range(0,duration,periods[app])):
                requests.append([f"sc{j}.app{app}.{k:04d}",app,t+offset,t+offset+deadlines[app]])
        t+=duration
    requests.sort(key=lambda q:(q[2],q[0]))
    assert t==10_000_000_000
    initial=[30.]*4
    if holdout:
        old=json.loads((ROOT/"research/multidnn_model_review/inputs/preheat_state.json").read_bytes())
        initial=old["initial_c"]
    return dict(case_id=cid,family=family["id"],order=order,models=family["models"],
                periods_ns=periods,deadlines_ns=deadlines,required=len(requests),
                counts=[sum(q[1]==i for q in requests) for i in range(len(periods))],
                switches=starts,service_ns=t,window_ns=t+40_000_000,requests=requests,
                ambient_c=25.,initial_c=initial,holdout=holdout,
                domain_file="inputs/domains/"+family["id"]+".json",
                provenance="deterministic declared input; no outcome-dependent selection")

def main():
    graphs=catalog_graphs()
    for graph in graphs.values():validate_graph(graph)
    for name,graph in graphs.items():put(HERE/"inputs/graphs"/(name+".json"),graph)
    rows=[]
    for name,g in graphs.items():
        by_kind=Counter(o["kind"] for o in g["ops"])
        rows.append(dict(model=name,operators=len(g["ops"]),side=g["side"],parameters=g["parameters"],
           mac=g["mac"],traffic_bytes=g["traffic_bytes"],kinds=dict(by_kind),
           all_boundary_partition_count=full_count(g),diagnostic_cuts=diagnostic_cuts(g),
           grouped_convs=sum(o["kind"]=="conv_bn" and o["attrs"]["groups"]>1 for o in g["ops"]),
           static_operator_conditions="PASS in declared abstract rule",
           hardware_engine="UNVERIFIED",numerical_outputs="UNVERIFIED",measured_latency_power="UNAVAILABLE"))
    put(HERE/"inputs/model_audit.json",rows)
    main_ids=[];held=[]
    for family in FAMILIES:
        dom=domain(family["models"],graphs)
        put(HERE/"inputs/domains"/(family["id"]+".json"),dom)
        for order in ("forward","reverse"):
            data=case(family,order)
            put(HERE/"inputs/cases"/(data["case_id"]+".json"),data);main_ids.append(data["case_id"])
        data=case(family,"reverse",True)
        put(HERE/"inputs/holdout"/(data["case_id"]+".json"),data);held.append(data["case_id"])
    protocol=dict(schema="multidnn-structure-gap/v1",date="2026-11-23",
         base_commit="f4a0a081d90eae8f219f4638acac80b6dbd233e7",
         families=FAMILIES,main_cases=main_ids,unopened_holdout=held,
         methods=["M2-reference","Kim-Anytime+SAFE"],kim_seeds=[20261121,20261122,20261123],
         cap_s=120,admit_s=116,kim_generate_s=95,population=24,generations=64,
         cores=[0,2,4,6],queue_seed=826119,energy_tolerance_j=1e-7,
         metric="100*(Kim_SAFE_J - certified_same_domain_optimum_J)/Kim_SAFE_J",
         target_pct="3-5 is an aspiration, never a case inclusion/retention rule",
         no_certificate="report pending with incumbent and valid lower bound; never label best seen as optimum",
         decision="no new algorithm in this stage; assess conditional gap and mechanism only",
         model="structure-diverse synthetic FP16 DNN model; inherited hardware power/service/RC scalars; no measured-board claim",
         graph_scope="fixed NCHW batch1; eval-mode BN fold; ReLU6 retained; residual branches and grouped MAC retained; classifier emits logits",
         operator_rule_source="NVIDIA Jetson DLA documented necessary operator conditions; build/CBUF/formats unverified",
         exact_domain="all physical label combinations on two predeclared prefix cells; no global DLA symmetry reduction; not the unrestricted generator domain",
         full_domain="all declared fusion-safe boundaries, up to two DLA contiguous stages per app, four total resident stages; unsupported ops GPU; no arbitrary DAG launch times",
         stop="one formal batch; no retries, input retuning, extra seeds or time extension based on quality",
         timing="start before worker creation; all source checks, domain loading, events, proxy/thermal/kernels/queries/certificates included",
         holdout_policy="inputs frozen but not scheduled or evaluated in this stage")
    put(HERE/"protocol.json",protocol)
    sources=HERE/"sources";sources.mkdir(exist_ok=True)
    vision=Path("F:/Anaconda3/Lib/site-packages/torchvision")
    source_meta={}
    for relative in ("models/resnet.py","models/mobilenetv2.py","version.py"):
        src=vision/relative;dst=sources/(src.name+".txt")
        dst.write_bytes(src.read_bytes())
        source_meta[relative]=dict(sha256=digest(dst),
             url="https://github.com/pytorch/vision/blob/7af698794eded568735f9519593603c1ec889eba/torchvision/"+relative)
    licenses=list(vision.parent.glob("torchvision-*.dist-info/LICENSE"))
    if not licenses:licenses=list(vision.parent.glob("torchvision-*.dist-info/LICENSE*"))
    assert licenses
    (sources/"TORCHVISION_LICENSE.txt").write_bytes(licenses[0].read_bytes())
    put(sources/"audit.json",dict(sources=source_meta,reported_version="0.21.0+cpu",
         official_commit="7af698794eded568735f9519593603c1ec889eba",
         torch_runtime="UNAVAILABLE WinError126 torch_python.dll; graph reconstructed statically, not FX export",
         local_gpu="NVIDIA GeForce GTX 1650 Ti; not a DLA target",trtexec=None,
         resnet_weights="https://download.pytorch.org/models/resnet18-f37072fd.pth",
         mobile_weights="https://download.pytorch.org/models/mobilenet_v2-7ebf99e0.pth",
         weights_downloaded=False,weight_hash_checked=False,target_build=False,accuracy_checked=False,
         service_parameter_sha256=digest(BASE)))
    source_guard=json.loads((ROOT/"research/multidnn_model_review/frozen_sources.json").read_bytes())["sha256"]
    put(HERE/"frozen_old_sources.json",source_guard)
    put(HERE/"input_manifest.json",{p.relative_to(HERE).as_posix():digest(p)
        for p in sorted((HERE/"inputs").rglob("*.json"))})
    print("Frozen cases:",main_ids)
    print("Domain counts:",{f["id"]:len(domain(f["models"],graphs)["search_order"]) for f in FAMILIES})
    print("Models:",[(r["model"],r["mac"],r["all_boundary_partition_count"]) for r in rows])
if __name__=="__main__":main()
