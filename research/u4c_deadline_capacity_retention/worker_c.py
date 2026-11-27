"""Only inputs, current beam and frozen physical interfaces are visible to the live scheduler."""
from collections import Counter
from time import process_time
import psutil
from foundation import *

class Unit(baseline.Unit):
    def generate(self,j,enrich):
        if enrich or not self.gen:return super().generate(j,enrich)
        b=self.b;found={}
        for p in b.layers[-1]:
            self.check()
            for pair in PAIRS:
                v,q,_=next(b.expand(p,j,[pair],[(0,0)],False))
                if not v.timing[-1]:found.setdefault(v.code,v)
                blocked=v.timing[6]<0
                if self.gen!="Small" and not blocked:continue
                offsets=finite_offsets(b,p,j,pair) if self.gen=="BlockedMix" else OFFSETS
                self.j.emit("supplement",j,self.parent_ids[p.code],pair,q,blocked)
                for child,_,_ in b.expand(p,j,[pair],[d for d in offsets if d!=(0,0)],False):
                    if not child.timing[-1]:found.setdefault(child.code,child)
        last=j+1==len(b.types)
        return sorted(found.values(),key=lambda v:(v.timing[4]+(v.timing[5] if last else 0),v.code))
    def select(self,j,ordered):
        start=perf_counter()
        base=super().select(j,ordered)
        # Terminal shortlist is audited by frozen lazy strict-proof reuse and full certification.
        if j+1==len(self.ends) or not ordered:return base
        n=self.ends[j-1] if j else 0
        front=Counter(v.code[:n] for v in ordered[:4])
        def allowed(v):
            par=v.code[:n]
            if j and front[par]>1:self.checked(par)
            return self.excluded(v.code) is None
        # A newly certified shorter proof can apply to a candidate accepted earlier in the scan.
        while any(self.excluded(v.code) is not None for v in base):
            base=[]
            for v in ordered:
                if allowed(v):base.append(v)
                if len(base)==4:break
        chosen=base;alternative=base[3] if len(base)==4 else None
        if len(base)==4 and self.keep:
            first={v.code for v in base[:3]}
            if self.keep=="Parent" and len({v.code[:n] for v in base})==1:
                possible=(v for v in ordered if v.code[:n]!=base[0].code[:n] and allowed(v))
                alternative=next(possible,base[3])
            elif self.keep=="Margin":
                index={}
                for i,v in enumerate(ordered):
                    if v.code in first or self.excluded(v.code) is not None:continue
                    if i%64==0:self.check()
                    index[v.code]=priority(margins(self.flow,v.code,j,n))
                candidates=sorted((v for v in ordered if v.code in index),key=lambda v:index[v.code])
                alternative=next((v for v in candidates if allowed(v)),base[3])
            chosen=[*base[:3],alternative]
        # Rescan if the changed slot's physical check newly disqualifies an earlier slot.
        if any(self.excluded(v.code) is not None for v in chosen):
            return self.select(j,[v for v in ordered if self.excluded(v.code) is None])
        self.j.emit("slot",j,[v.code for v in base],[v.code for v in chosen],perf_counter()-start)
        return chosen

if __name__=="__main__":
    case,arm,out,cpu,cap=sys.argv[1:];out=Path(out)
    psutil.Process().cpu_affinity([int(cpu)])
    begin=perf_counter();stack=u.stack();src.old.warm(stack);psutil.Process().cpu_affinity([int(cpu)])
    u.save(out/"ready.json",dict(warm_s=perf_counter()-begin,cpu=int(cpu)))
    parts=arm.split("+");obj=cases()[case];before=process_time()
    unit=Unit(obj,"C",out,stack,float(cap))
    unit.keep=next((x for x in parts if x in ("Parent","Margin")),None)
    unit.gen=next((x for x in parts if x in ("Small","BlockedSmall","BlockedMix")),None)
    try:unit.run(None);status="natural"
    except src.Cutoff:status="wall"
    unit.j.emit("return",status,unit.elapsed(),process_time()-before);unit.j.close()
    u.save(out/"finish.json",dict(status=status,wall_s=unit.elapsed(),cpu_s=process_time()-before))
