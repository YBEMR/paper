"""Compare the two native expansions on identical recorded parent states and OPP groups."""
import csv
import itertools
import math
import time
from types import FunctionType
import numpy as np
from method import ROOT,analytic_expand,f,m

def write(name,rows):
    with (ROOT/"diagnostic"/name).open("w",newline="") as stream:
        out=csv.DictWriter(stream,fieldnames=rows[0],lineterminator="\n")
        out.writeheader()
        out.writerows(rows)

class GroupView:
    def __init__(self,flow,group):
        self.flow=flow
        self.group=group
        self.calls={}
    def __getattr__(self,name):
        return getattr(self.flow,name)
    def candidates(self,*args):
        return iter(self.group)
    def ledger(self,cfg,*args):
        v=self.flow.ledger(cfg,*args)
        self.calls[cfg]=(bool(v[0]),float(v[1]),int(v[-1]))
        return v

def replay(expand,flow,parent,j,items):
    seen={}
    sampler=expand.__globals__["synthesize"]
    def observe(load,planes,pilots,balance,cost,a,b,k,**kw):
        seen.update(pilots=pilots,cost=cost.copy(),slots=k)
        return sampler(load,planes,pilots,balance,cost,a,b,k,**kw)
    fn=FunctionType(expand.__code__,dict(expand.__globals__,synthesize=observe))
    c=GroupView(flow,items)
    log=dict(actions=[],groups=[])
    _,done=fn(c,j,[parent],"NT",0,math.inf,log)
    assert done and len(log["groups"])==1
    byxy={}
    for row in log["actions"]:
        window,pid,g,n,x,y,key,pilot,original,status,energy,peak,risk,drain,slack=row
        assert status in ("valid","timing")
        byxy[(x,y)]=dict(valid=status=="valid",peak=peak,risk=risk,slack=slack,grid=500 if pilot and j==flow.windows-1 else 2500)
    return seen,byxy,c.calls

def measure(code,rows,groups):
    api=m.RUN[0]
    obj=next(o for o in m.u2.CASES if m.label(o)==code)
    flow=m.u2.make_flow(api,obj,ROOT/"diag_scratch"/code)
    fit=api.e.expand
    analytic=analytic_expand(fit)
    folder=ROOT/"paired_results"/code/"fit-60"
    for j in (0,flow.windows//2,flow.windows-1):
        p=f.read(folder/f"parent-{j}.json")
        assert p["j"]==j
        p["config"]=bytes.fromhex(p["config"]);p["temperature"]=np.array(p["temperature"])
        assert f.digest(p["config"])==p["id"]
        types,a,b=api.e.window_types(flow,j)
        for (g,n),group in itertools.groupby(flow.candidates(j,p),key=lambda t:t[0][:2]):
            items=list(group)
            sf,af,lf=replay(fit,flow,p,j,items)
            sb,ab,lb=replay(analytic,flow,p,j,items)
            assert sf["pilots"]==sb["pilots"] and sf["slots"]==sb["slots"]==len(af)==len(ab)
            choices=set(af)|set(ab)
            pilot=sf["pilots"][0]
            def cfg(xy):return p["config"]+flow.extension(types,a,b,g,n,*xy)
            def predict(coef,x,y):return coef[0]+coef[1]*x+coef[2]*y
            # Main-only cost is in exact scaled units. Center-relative error subtracts
            # the common prefix/CPU terms to compare within-group quota preferences.
            reference=lf[cfg(pilot)][1]
            scale=flow.eng.scale
            offset=reference-predict(sb["cost"],*pilot)/scale
            context=dict(case=code,window=j+1,parent=p["id"],gpu_opp=g,npu_opp=n)
            detail=[]
            for x,y in sorted(choices):
                xy=x,y;key=cfg(xy)
                if xy in af and xy in ab:
                    assert af[xy]==ab[xy] and lf[key]==lb[key]
                info=af[xy] if xy in af else ab[xy]
                legal,actual,slack=(lf if xy in af else lb)[key]
                assert legal==info["valid"] and slack==info["slack"]
                ea=predict(sb["cost"],x,y)/scale
                ef=float(predict(sf["cost"],x,y))
                detail.append(dict(**context,x=x,y=y,anchor=xy in sf["pilots"],fit_selected=xy in af,
                     analytic_selected=xy in ab,fifo_valid=legal,slack_ticks=slack,grid_ticks=info["grid"],
                     actual_ref_ledger_J=actual,fit_J=ef,analytic_main_J=ea,fit_error_J=ef-actual,
                     analytic_raw_difference_J=ea-actual,analytic_centered_error_J=ea+offset-actual,
                     risk_C=info["risk"],peak_C=info["peak"]))
            rows.extend(detail)
            def best(field):
                return min((r["actual_ref_ledger_J"] for r in detail if r[field] and r["fifo_valid"]),default=None)
            jf,jb=best("fit_selected"),best("analytic_selected")
            groups.append(dict(**context,slots=len(af),anchors=len(sf["pilots"]),common=len(set(af)&set(ab)),
                 set_equal=set(af)==set(ab),order_equal=list(af)==list(ab),
                 fit_valid=sum(v["valid"] for v in af.values()),analytic_valid=sum(v["valid"] for v in ab.values()),
                 best_fit_ref_J=jf,best_analytic_ref_J=jb,delta_best_ref_J=(jb-jf if jf is not None and jb is not None else None),
                 fit_coefficients=list(map(float,sf["cost"])),analytic_scaled_coefficients=list(map(int,sb["cost"])),
                 scale=scale))

def main():
    start=time.perf_counter()
    m.RUN=m.u2.stack()
    rows=[];groups=[]
    for code in ("A02","A06","C10","C11"):
        measure(code,rows,groups)
    dest=ROOT/"diagnostic";dest.mkdir(exist_ok=True)
    write("candidates.csv",rows)
    write("groups.csv",groups)
    assert len(groups)==4*3*30
    f.save(dest/"receipt.json",dict(groups=len(groups),candidates=len(rows),elapsed_s=time.perf_counter()-start,
                                    source="first encountered fit-60 parent at first, middle and terminal windows"))

if __name__=="__main__":main()
