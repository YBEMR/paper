"""Online routes use only frozen inputs, not an archived SAFE or HOT plan."""
from collections import Counter
from time import perf_counter,process_time
import psutil
from shared import *

class Unit(src.Unit):
    def remember(self,cfg,proof,origin):
        key=settled_key(cfg,proof["tick"],self.b)
        self.proofs.setdefault(key,(proof,origin))
        self.j.emit("strict_proof",key,proof,origin)
    def checked(self,code):
        if code not in self.checked_history:
            self.check()
            j=self.ends.index(len(code))+1
            cut=j*self.e.dur-5
            self.j.emit("open_start",code,cut,self.elapsed())
            start=perf_counter()
            evidence,upper,tr=open_proof(self.flow,code,cut)
            self.checked_history[code]=upper
            if evidence:
                self.remember(code,evidence,"open")
            self.j.emit("open_done",code,cut,upper,evidence,perf_counter()-start,
                        sha(tr.astype("<f8").tobytes()))
            self.check()
        return self.checked_history[code]
    def excluded(self,code):
        return next((k for k in self.proofs if code.startswith(k)),None)
    def generate(self,j,enrich):
        b=self.b;found={}
        for par in b.layers[-1]:
            self.check()
            for pair in PAIRS:
                delta=[(0,0)]
                if enrich:
                    delta=OFFSETS
                    if self.method in ("C","H"):
                        a,bb=b.counts[j]
                        x,y=b.e.quota(dict(f=par.timing[:2],k=par.timing[2:4]),j,pair,(a,bb))
                        delta=list(dict.fromkeys([*delta,*[(i-x,k-y) for i,k in extra(a,bb,x,y)]]))
                for v,_,_ in b.expand(par,j,[pair],delta,False):
                    if not v.timing[-1]:found.setdefault(v.code,v)
        last=j+1==len(b.types)
        def score(v):
            return (v.timing[4]+(v.timing[5] if last else 0),v.code)
        ordered=sorted(found.values(),key=score)
        if enrich and self.method=="H" and ordered:
            # A complete candidate uses its settled parent for ranking; terminal certificate cap is unchanged.
            def thermal(v):
                c=v.code[:self.ends[j-1]] if last and j else v.code
                return self.checked(c),score(v)
            ordered.sort(key=thermal)
        return ordered
    def select(self,j,ordered):
        last=j+1==len(self.b.types);limit=12 if last else 4
        if self.method=="R" or not j or last:
            return ordered[:limit]
        n=self.ends[j-1];front=Counter(v.code[:n] for v in ordered[:4])
        keep=[]
        for v in ordered:
            parent=v.code[:n]
            if front[parent]>1:self.checked(parent)
            key=self.excluded(v.code)
            if key is not None:
                self.j.emit("branch_skip",j,v.code,key)
                continue
            keep.append(v)
            if len(keep)==limit:break
        return keep
    def integrated(self):
        self.proofs={};self.checked_history={};used=False;top=[]
        with self.time("construct"):
            self.b=Builder(self.flow,self.e);self.ends=limits(self.b);self.observe_builder()
            for j in range(len(self.ends)):
                order=self.generate(j,False)
                top=self.select(j,order)
                self.j.emit("selection",j,False,len(order),[v.code for v in top])
                if not top and not used and self.method in ("D","C","H"):
                    used=True
                    self.j.emit("enrich_start",j,self.elapsed())
                    order=self.generate(j,True)
                    top=self.select(j,order)
                    self.j.emit("selection",j,True,len(order),[v.code for v in top])
                self.b.layers.append(top[:4])
                if not top:break
            self.store("base",dict(terminal=[v.code.hex() for v in top]))
        with self.time("terminal"):
            for i,v in enumerate(top,1):
                self.check()
                start=perf_counter();key=self.excluded(v.code)
                self.j.emit("reuse_test",i,key is not None,perf_counter()-start)
                if key is not None:
                    self.j.emit("terminal_skip",i,v.code,key);continue
                d,tr=self.certify(v,"terminal",i)
                if self.seed:break
                proof=hot(tr) if d["metrics"]["status"]=="HOT" else None
                if proof:self.remember(v.code,proof,d["plan_sha256"])
        if not self.seed:
            with self.time("fallback"):self.nt(True)
        if self.seed:
            cfg,d,tr=self.seed
            with self.time("group"):
                self.group((cfg,self.causal(self.flow,u.encoded(cfg)),d,tr),"adaptive","2",True)

if __name__=="__main__":
    case,method,out,cpu,cap=sys.argv[1:];out=Path(out)
    psutil.Process().cpu_affinity([int(cpu)])
    start=perf_counter();stack=u.stack();src.old.warm(stack)
    psutil.Process().cpu_affinity([int(cpu)])
    u.save(out/"ready.json",dict(warm_s=perf_counter()-start,cpu=int(cpu)))
    obj=cases()[case];cpu_start=process_time()
    unit=Unit(obj,method,out,stack,float(cap))
    try:unit.run(None);status="natural"
    except src.Cutoff:status="wall"
    unit.j.emit("return",status,unit.elapsed(),process_time()-cpu_start);unit.j.close()
    u.save(out/"finish.json",dict(status=status,wall_s=unit.elapsed(),cpu_s=process_time()-cpu_start))
