"""Only the correctness gate has access to the supplied witness decisions."""
from assets import ROOT,check_inputs,problem,assemble,idle_plan,assess,write,utc,time,git
import traceback
STRING="N0N00NN00N0N00NN00N00N0N11N10NN00N0N00N0N00N0N00N0N00N0N00N0N00N0N00N0N0000N00N0"
TARGET={"S16":1.303331605,"S32":2.132078715,"S80":4.673909248}
def main():
    receipt=ROOT/"witness_gate.json"
    with receipt.open("x") as f: f.write("{}")
    begin=time.perf_counter()
    info=dict(utc=utc(),freeze=git("rev-parse","HEAD"),witnesses={},status="RUNNING")
    try:
        check_inputs()
        for name,target in TARGET.items():
            p=problem(name)
            if name=="S80":
                assert len(STRING)==len(p.req)==80
                cfg=[(3,0) if c=="N" else (2,int(c)) for c in STRING]
            else:
                bs=[r["request"] for r in p.req if r["kind"]=="B"]
                ids=bs[:3] if name=="S16" else [31]
                assert set(ids)<=set(bs)
                cfg=[(3,0) if r["kind"]=="A" or r["request"] in ids else (2,0) for r in p.req]
            k,c=assess(p,idle_plan(p,assemble(p,cfg)))
            m=c["metrics"]; info["witnesses"][name]=dict(plan=k,reference_J=c["E35_J"],energy_J=m["E_J"],
                    bounds=m["E_bounds"],status=m["status"],peak_C=max(m["peak_hi"]),slack_ms=m["min_deadline_slack_ms"],
                    switches=m["switch_count"],exact_components=c["ref_components"])
            assert m["status"]=="SAFE" and abs(m["E_J"]-target)<=1e-8
            if name=="S80":assert abs(c["E35_J"]-4.454541731)<=1e-8
        info["status"]="PASS"
    except BaseException:
        info.update(status="STOP",error=traceback.format_exc());raise
    finally:
        info.update(end=utc(),elapsed_s=time.perf_counter()-begin);write(receipt,info)
if __name__=="__main__":main()
