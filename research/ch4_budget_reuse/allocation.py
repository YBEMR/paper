"""The single optional allocation variant. All other operators come from the frozen Explorer."""
import search
from optimizer import Explorer


class CostAllocation(Explorer):
    def fill(self,parent,pool,energy,ranked,reserved):
        remaining=[k for k in ranked if k not in reserved]
        limit=self.cfg["proposals"]-len(reserved)
        if limit<=1 or len(remaining)<=limit:
            return remaining[:limit]
        base=0.
        rows=self.ev._physical[parent[0],tuple(parent[1:])]["scene_rows"]
        ref=self.ev.platform["thermal"]["reference_C"]
        for j,i in enumerate(parent[1:]):
            joules,_,slope,_=self.profile(parent[0],j,i)
            temps=[(a+b)*.5-ref for a,b in zip(rows[j]["entry_c"],rows[j]["final_c"])]
            base+=joules+self.span[j]*sum(x*y for x,y in zip(slope,temps))
        fixed=remaining[:1]
        tail=remaining[1:]
        for risk in (False,True):
            positions=[]
            ordered=[]
            for pos,k in enumerate(tail):
                if energy[k][0]!=risk: continue
                quote=self.ev.cost(k)
                if quote is None or quote[0]<=0: continue
                positions.append(pos)
                ordered.append((max(base-energy[k][1],0.)/quote[0],pos,k))
            if len(positions)>1 and any(v[0]>0 for v in ordered):
                for pos,item in zip(positions,sorted(ordered,key=lambda x:(-x[0],x[1],x[2]))):
                    tail[pos]=item[2]
        chosen=(fixed+tail)[:limit]
        self.emit("allocation",[parent,remaining[:limit],chosen])
        return chosen

    def run(self,starts):
        it=0
        try:
            for dep in starts:
                self.setfreq(dep,"initial")
            while True:
                self.clock.check()
                parent=self.parent(it)
                if parent is None or (it+1)%self.cfg["restart_period"]==0:
                    self.setfreq(self.rng.choice(self.domain.order),"restart")
                if parent is not None:
                    pool=self.neighborhood(parent,it)
                    energy,_,target,predicted=self.rank(parent,pool)
                    ranked=sorted(pool,key=energy.get)
                    reserved=[]
                    for accept in (lambda k:pool[k]=="dvfs",lambda k:pool[k]=="exchange",
                                   lambda k:pool[k] not in ("dvfs","exchange")):
                        k=next((k for k in ranked if accept(k)),None)
                        if k is not None: reserved.append(k)
                    with self.ev.m.doing("allocation_rule"):
                        chosen=reserved+self.fill(parent,pool,energy,ranked,set(reserved))
                    self.emit("parent",[parent,target,len(pool),len(chosen)])
                    for k in chosen:
                        self.evaluate(k,pool[k],parent,target,dict(
                            rule="operator_reservation" if k in reserved else "fill",
                            estimated_j=energy[k][1],predicted_target_peak_c=predicted[k]))
                    unmapped=next((k[0] for k in ranked if k[0] not in self.mapped),None)
                    if unmapped is not None: self.setfreq(unmapped,"setfreq",parent)
                it+=1
        except search.Cutoff:
            pass
        return dict(winner=self.best,first_safe_s=self.first,best_s=self.best_time,rounds=it,
                    unique=len(self.seen),counts=dict(self.counts),stop="admission_cutoff")
