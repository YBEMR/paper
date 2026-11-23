"""Static FP16 inference graphs from pinned TorchVision topology; no timing fit."""
from dataclasses import dataclass,asdict
from math import prod,ceil
from pathlib import Path
import json
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/"research/kim_synthetic_platform_v1"))
import profiles

@dataclass(frozen=True)
class Op:
    name:str
    kind:str
    inputs:tuple
    shape:tuple
    mac:int
    traffic_bytes:int
    parameters:int=0
    attrs:dict|None=None

class Graph:
    def __init__(self,name,side=224):
        self.name,self.side=name,side
        self.ops=[];self.boundaries=[];self.heads=[]
    def shape(self,i):
        return (self.side,self.side,3) if i==-1 else self.ops[i].shape
    def add(self,name,kind,inputs,shape,mac=0,weights=0,parameters=0,**attrs):
        traffic=2*(sum(prod(self.shape(i)) for i in inputs)+prod(shape)+weights)
        self.ops.append(Op(name,kind,tuple(inputs),tuple(shape),mac,traffic,parameters,attrs))
        return len(self.ops)-1
    def conv(self,x,c,k,s,name,groups=1,activation=None):
        h,w,inc=self.shape(x)
        assert inc%groups==0 and c%groups==0
        out=((h+2*(k//2)-k)//s+1,(w+2*(k//2)-k)//s+1,c)
        weights=k*k*(inc//groups)*c
        # Eval-mode BN is algebraically folded into this convolution. Its
        # learned parameter count remains distinct from fused inference traffic.
        x=self.add(name,"conv_bn",(x,),out,prod(out)*k*k*(inc//groups),
                   weights+c,weights+2*c,kernel=k,stride=s,padding=k//2,
                   groups=groups,in_channels=inc,out_channels=c,bn_folded=True)
        if activation:
            x=self.add(name+"."+activation,activation,(x,),out,clip=6 if activation=="relu6" else None)
        return x
    def close(self,x):
        self.boundaries.append(x)
        return x
    def result(self,expected):
        parameters=sum(o.parameters for o in self.ops)
        assert parameters==expected,(self.name,parameters,expected)
        return dict(name=self.name,side=self.side,channels=3,scalar_bytes=2,
                    ops=[asdict(o) for o in self.ops],heads=self.heads,module_boundaries=self.boundaries,
                    boundaries=[i for i in range(len(self.ops)-1)
                                if not(self.ops[i].kind=="conv_bn" and self.ops[i+1].kind in ("relu","relu6"))],
                    parameters=parameters,mac=sum(o.mac for o in self.ops),
                    traffic_bytes=sum(o.traffic_bytes for o in self.ops),
                    profile_kind="classification",accuracy_status="unmeasured; topology/FP16 only")

def resnet18():
    g=Graph("resnet18")
    x=g.conv(-1,64,7,2,"stem.conv",activation="relu")
    h,w,c=g.shape(x)
    x=g.close(g.add("stem.pool","pool",(x,),((h+1)//2,(w+1)//2,c),kernel=3,stride=2,padding=1,mode="max"))
    for stage,c in enumerate((64,128,256,512)):
        for block in range(2):
            name=f"layer{stage+1}.{block}";s=2 if stage and block==0 else 1
            identity=x
            y=g.conv(x,c,3,s,name+".conv1",activation="relu")
            y=g.conv(y,c,3,1,name+".conv2")
            if s!=1 or g.shape(identity)[2]!=c:
                identity=g.conv(identity,c,1,s,name+".downsample")
            assert g.shape(y)==g.shape(identity)
            y=g.add(name+".add","add",(y,identity),g.shape(y))
            x=g.close(g.add(name+".relu","relu",(y,),g.shape(y)))
    x=g.add("avgpool","global_avg",(x,),(1,1,512),kernel=7)
    x=g.add("fc","linear",(x,),(1,1,1000),512*1000,512*1000+1000,512*1000+1000)
    g.heads=[x]
    return g.result(11689512)

def mobilenet_v2():
    g=Graph("mobilenet_v2")
    x=g.close(g.conv(-1,32,3,2,"features.0",activation="relu6"))
    setting=((1,16,1,1),(6,24,2,2),(6,32,3,2),(6,64,4,2),(6,96,3,1),(6,160,3,2),(6,320,1,1))
    index=1
    for expansion,c,repeats,stride in setting:
        for j in range(repeats):
            s=stride if j==0 else 1
            inp=g.shape(x)[2];hidden=inp*expansion;identity=x
            name=f"features.{index}";index+=1
            if expansion!=1:
                x=g.conv(x,hidden,1,1,name+".expand",activation="relu6")
            x=g.conv(x,hidden,3,s,name+".depthwise",groups=hidden,activation="relu6")
            x=g.conv(x,c,1,1,name+".project")
            if s==1 and inp==c:
                x=g.add(name+".add","add",(identity,x),g.shape(x))
            g.close(x)
    x=g.close(g.conv(x,1280,1,1,"features.18",activation="relu6"))
    x=g.add("avgpool","global_avg",(x,),(1,1,1280),kernel=7)
    x=g.add("classifier","linear",(x,),(1,1,1000),1280*1000,1280*1000+1000,1280*1000+1000)
    g.heads=[x]  # Dropout is identity in evaluation; flatten is a metadata alias.
    return g.result(3504872)

def yolo(key,name):
    platform=json.loads((ROOT/"research/kim_synthetic_platform_v1/platform.json").read_bytes())
    blocks=platform["architecture_reference"]["graphs"][str(key)]["blocks"]
    old,heads=profiles.graph_features(tuple(tuple(r) for r in blocks),256,3,2)
    kinds=[]
    for r in blocks:
        kinds.append(r[0])
        if r[0]=="conv" and r[-1]:kinds.append("activation")
    ops=[Op(f"layer{i}",k,o.inputs,o.shape,o.mac,o.traffic_bytes,attrs={"legacy":True}) for i,(k,o) in enumerate(zip(kinds,old))]
    boundaries=[i for i in range(len(ops)-1) if not(kinds[i]=="conv" and kinds[i+1]=="activation")]
    return dict(name=name,side=256,channels=3,scalar_bytes=2,ops=[asdict(o) for o in ops],heads=list(heads),
                boundaries=boundaries,parameters=None,mac=sum(o.mac for o in ops),traffic_bytes=sum(o.traffic_bytes for o in ops),
                profile_kind="detection",legacy_app=key,accuracy_status="inherits frozen graph abstraction; unmeasured")

def load_ops(graph):
    return tuple(profiles.Op(tuple(o["inputs"]),tuple(o["shape"]),o["mac"],o["traffic_bytes"]) for o in graph["ops"])

def basic_dla(op):
    kind=op["kind"];a=op["attrs"] or {}
    if a.get("legacy"):
        return kind in {"conv","activation","pool","shortcut"}
    if kind=="conv_bn":
        return (1<=a["kernel"]<=32 and 1<=a["stride"]<=8 and 0<=a["padding"]<a["kernel"]
                and 1<=a["groups"]<=8192 and 1<=a["in_channels"]<=8192 and 1<=a["out_channels"]<=8192)
    if kind in ("relu","add"):return True
    if kind=="relu6":return a["clip"]==6
    if kind=="pool":return 1<=a["kernel"]<=8 and 1<=a["stride"]<=16 and 0<=a["padding"]<=7
    return False  # Classifier pooling/flatten/FC stays GPU in this model.

def catalog_graphs():
    return {g["name"]:g for g in [resnet18(),mobilenet_v2(),yolo(0,"yolov2"),yolo(1,"yolov2tiny"),
                                 yolo(2,"yolov3tiny"),yolo(3,"yolov3")]}

def cells(graph,cuts):
    assert sorted(set(cuts))==cuts
    ends=cuts+[len(graph["ops"])-1]
    starts=[0]+[c+1 for c in cuts]
    return list(zip(starts,ends))

def assignments(graph,cuts,max_slots=2):
    """All cell labels, coalescing equal adjacent labels. No DLA-swap quotient."""
    segments=cells(graph,cuts)
    def recurse(i,chain,slots):
        if i==len(segments):
            yield chain
            return
        first,last=segments[i]
        resources=["GPU"]
        if last!=len(graph["ops"])-1 and all(basic_dla(o) for o in graph["ops"][first:last+1]):
            resources+=["DLA0","DLA1"]
        for resource in resources:
            same=bool(chain) and chain[-1][0]==resource
            count=slots+(resource.startswith("DLA") and not same)
            if count>max_slots:continue
            updated=[list(x) for x in chain]
            if same:updated[-1][2]=last
            else:updated.append([resource,first,last])
            yield from recurse(i+1,updated,count)
    yield from recurse(0,[],0)

def full_count(graph):
    """Count all abstract legal partitions at declared operator/fusion boundaries."""
    cuts=graph["boundaries"];segments=cells(graph,cuts)
    state={("",0):1}
    for first,last in segments:
        new={}
        rs=["GPU"]+(["DLA0","DLA1"] if last!=len(graph["ops"])-1 and
                   all(basic_dla(o) for o in graph["ops"][first:last+1]) else [])
        for (old,slots),count in state.items():
            for resource in rs:
                n=slots+(resource.startswith("DLA") and old!=resource)
                if n<=2:new[resource,n]=new.get((resource,n),0)+count
        state=new
    return sum(state.values())

def diagnostic_cuts(graph):
    prefix=next((i for i,o in enumerate(graph["ops"]) if not basic_dla(o)),len(graph["ops"]))-1
    boundaries=[b for b in graph.get("module_boundaries",graph["boundaries"]) if b<=prefix]
    assert len(boundaries)>=2
    last=boundaries[-1]
    middle=boundaries[(len(boundaries)-1)//2]
    assert middle<last<len(graph["ops"])-1
    return [middle,last]

def validate_graph(graph):
    n=len(graph["ops"])
    for i,o in enumerate(graph["ops"]):
        assert o["inputs"] and all(-1<=j<i for j in o["inputs"])
        assert len(o["shape"])==3 and all(x>0 for x in o["shape"])
        assert o["mac"]>=0 and o["traffic_bytes"]>0
        if o["kind"] in ("add","shortcut"):
            assert all(tuple(graph["ops"][j]["shape"])==tuple(o["shape"]) for j in o["inputs"])
    # Verify all crossing live tensors, including residual branches and output heads.
    ops=load_ops(graph)
    for b in graph["boundaries"]:
        live={j for o in ops[b+1:] for j in o.inputs if 0<=j<=b}|{j for j in graph["heads"] if j<=b}
        assert profiles.live_bytes(ops,graph["heads"],b,2)==2*sum(prod(ops[j].shape) for j in live)
    for chain in assignments(graph,diagnostic_cuts(graph)):
        assert chain[0][1]==0 and chain[-1][2]==n-1
        assert all(a[2]+1==b[1] for a,b in zip(chain,chain[1:]))
        assert sum(sum(o.mac for o in ops[a:b+1]) for _,a,b in chain)==graph["mac"]
