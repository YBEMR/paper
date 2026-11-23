"""Necessary interface/graph/algebra checks only; no optimizer is run."""
import os
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):os.environ[k]="1"
import json
from dataclasses import asdict
from math import prod
from time import perf_counter
from unittest.mock import patch
import numpy as np
from model import *
from topology import catalog_graphs,validate_graph,assignments,diagnostic_cuts,profiles
from exact import enumerate_sequences,decode

def main():
    start=perf_counter();notes=[]
    graphs=catalog_graphs()
    for g in graphs.values():validate_graph(g)
    # Independently count trained convolution + BN + classifier parameters.
    assert graphs["resnet18"]["parameters"]==11689512
    assert graphs["mobilenet_v2"]["parameters"]==3504872
    # Frozen YOLO stage costs are bit-for-bit unchanged at ALL 27 OPPs.
    old=read(ROOT/"research/kim_multidnn_expansion/expanded_input.json")
    adapted=dict(old,graphs=graphs,applications=[dict(a,model=["yolov2","yolov2tiny","yolov3tiny","yolov3"][a["id"]]) for a in old["applications"]])
    platform=read(ROOT/"research/kim_synthetic_platform_v1/platform.json")
    for opp in OPPS:
        a=profiles.build_chains(platform,old,"D005",opp)
        b=service.build_chains(platform,adapted,"D005",opp)
        assert a==b
    # Complete original 500-request thermal certificate.
    original=prior.Instance("balanced_forward_reference_start")
    original.bind()
    with patch.object(events,"build_chains",profiles.build_chains):
        p0=events.replay_sequence(original.platform,original.scenes,"D005",["LLL","LLL","LHL","LHL"],25)
    events.FROZEN=adapted
    with patch.object(events,"build_chains",service.build_chains):
        p1=events.replay_sequence(original.platform,original.scenes,"D005",["LLL","LLL","LHL","LHL"],25)
    assert p0==p1 and abs(p1["energy_j"]-43.11068823143108)<1e-7
    notes.append(dict(test="original_500_full_replay",physical=p1))
    # Whole-window scalar replay vs generalized affine join, for two topological
    # policies and two fixed OPPs per scene, including deadline-invalid sequences.
    inst=Instance("pair_classifiers_forward")
    ev=Physical(inst)
    dep0=inst.order[0]
    dep1=next(d for d in inst.order if all(c[0][0]==f"DLA{i%2}" and len(c)==2
         for i,c in enumerate(inst.domain["deployments"][d]["stages"].values())))
    count=0
    for dep in (dep0,dep1):
        tables=[]
        for j in range(len(inst.scenes)):
            row=[None]*27
            for i in (0,26):
                sched=ev._bound_schedule(ev.platform,ev.scenes[j],dep,OPPS[i])
                if sched.deadline_feasible:
                    kw=events.thermal_kwargs(ev.platform,OPPS[i],25,True,"base")
                    row[i]=joint_thermal.compile_scene(sched.duration_ns*1e-9,sched.active_w,sched.transfer_w,kw)
            tables.append(row)
        codes,energy,state,depth=enumerate_sequences(tables,inst.initial,True,lambda:None)
        for code,e,status in zip(codes,energy,state):
            ix=decode(code,len(tables));r=ev.replay(dep,ix);proof=ev.evidence(dep,ix)
            assert abs(r.energy_j-e)<1e-7
            assert {"SAFE":1,"VIOLATION":2,"UNRESOLVED":3}[r.status]==int(status)
            assert r.completed==inst.required and proof["physical"]["scene_rows"][-1]["end_ns"]==10_040_000_000
            count+=1
        ecode,values,_,_=enumerate_sequences(tables,inst.initial,False,lambda:None)
        assert np.array_equal(ecode,codes) and np.max(abs(values-energy))<1e-7
    assert count==8
    # Kim bindings cover 2/3/4 applications and scene counts without changed operators.
    bindings=[]
    for case in read(HERE/"protocol.json")["main_cases"]:
        inst=Instance(case);m,runner,binding=bind_kim(inst);domain=m.Domain(inst.domain,inst.order)
        assert set(domain.encode)==set(inst.order)
        assert len(domain.options)==len(inst.case["models"])+1
        bindings.append(dict(case_id=case,requests=inst.required,domain=len(inst.order),binding=binding))
    # BN fold algebra (not an FP16 model accuracy or hardware execution test).
    rng=np.random.default_rng(123);x=rng.normal(size=11);w=rng.normal(size=11)
    mean,var,gamma,beta=.2,.7,1.2,-.1;eps=1e-5
    direct=gamma*(np.dot(w,x)-mean)/np.sqrt(var+eps)+beta
    folded=np.dot(w*gamma/np.sqrt(var+eps),x)+beta-mean*gamma/np.sqrt(var+eps)
    assert abs(direct-folded)<1e-12
    report=dict(status="PASS",elapsed_s=perf_counter()-start,scope="static topology + retained old physics + eight tiny join witnesses; no search pilot",
         full_model_outputs="UNVERIFIED",target_DLA_build="UNVERIFIED",old_stage_opps=27,
         tiny_scalar_vs_affine=8,original_replay_equal=True,tests=notes,bindings=bindings,
         parameter_counts_match=True,bn_algebra=True)
    (HERE/"checks.json").write_bytes(encoded(report)+b"\n")
    print("PASS",dict(old_stage_opps=27,tiny_join_witnesses=count,cases=len(bindings)))
if __name__=="__main__":main()
