"""Cross-check actual FIFO moments with P1 event records on the two temperature triplets."""
import json
import os
from pathlib import Path
from design import ROOT,REG,write_json,sha

def main():
    out=ROOT/"work"/"probe"
    os.environ["M1G_RAW"]=str(out/"warm")
    from adapter import flow,np
    from heat import integrate
    cases=json.loads((REG/"cases.json").read_bytes())["cases"]
    streams={c["flow"] for c in cases if c["group"]=="D"}
    results=[]
    for name in sorted(streams):
        sigs=set()
        for item in (i for i in cases if i["flow"]==name):
            c=flow(item,out)
            # Deterministic test stimulus: dispatch at maximum OPP to the earliest finishing accelerator.
            # It is independent of temperature and is never supplied to a search.
            f=[5,5];codes=[]
            for j,kind in enumerate(c.eng.types):
                end=[max(c.eng.a[j],f[d])+c.eng.length[kind,u,k] for d,(u,k) in enumerate(((2,9),(3,2)))]
                d=min(range(2),key=end.__getitem__)
                f[d]=end[d];codes.append((9,12)[d])
            config=bytes(codes)
            cert,arr=c.certify(config)
            sig=sha(arr[:,:14].tobytes());sigs.add(sig)
            L=c.ledger(config,0,c.p.horizon,2500,True,True)
            assert L[0]
            errors=[];state=c.p.initial.copy();moment_error=0.
            for i,m in enumerate(L[8]):
                t=i*2500;end=min(t+2500,c.p.horizon)
                weights=np.maximum(0,np.minimum(end,arr[:,1])-np.maximum(t,arr[:,0]))
                assert weights.sum()==end-t
                av=weights@arr[:,2:10]/(end-t)
                moment_error=max(moment_error,float(max(abs(av-m))))
                assert moment_error<1e-11
                ev=np.array([[t,end,*m,*m[:4]]])
                precise=integrate(ev,state,c.p.G,c.p.cap,float(c.p.ta),np.array([],np.int64),True)[-2][0,4:8]
                state=c.propagate(state,m,(end-t)/10000)
                errors.append(max(abs(precise-state)))
            assert max(errors)<1e-8
            assert np.array_equal(arr[0,14:18],c.p.initial) and np.array_equal(arr[1:,14:18],arr[:-1,18:22])
            assert arr[-1,1]==c.p.horizon and len(codes)==item["requests"]
            results.append(dict(case=c.label,flow=name,ta=c.p.ta,requests=len(codes),probe_cfg=sha(config),
                                event_input_sha256=sig,max_moment_error=moment_error,max_bin_end_error_K=max(errors),
                                ref_E35_J=cert["E35_J"],continuous_E_J=cert["metrics"]["E_J"],
                                p1_plan=cert["plan_sha256"],actual_event_rows=len(arr)))
        assert len(sigs)==1
    write_json(REG/"checks"/"physical_triplets.json",results)
    print("verified event source and continuous boundary state",len(results))
if __name__=="__main__": main()
