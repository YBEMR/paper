"""Fresh input-to-delivery worker. Only the window selection of the local search changes."""
import os
import sys
from pathlib import Path
from time import perf_counter, process_time
from types import FunctionType

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/"u3b_blockage_triggered_quota"
sys.path.insert(0,str(OLD))
import worker as frozen
import local_search
from location import select


class Route(frozen.Route):
    def store(self,name,data):
        if name=="location":
            assert self.location["selected_w"]==data["selected_w"]
            data=self.location
        super().store(name,data)

    def repair(self,ctx,mode,anchor,cert,trace):
        assert ctx is self and mode=="oo"
        if not all(row["status"]=="HOT" for row in self.attempts):
            return False
        chosen,self.location = select(self,self.locator,anchor,cert,trace)
        # Bind the chosen index into the unchanged frozen generation/ordering/early-stop loop.
        body=local_search.thermal_block
        ns=dict(body.__globals__,anchor_window=lambda *_:(chosen,[]))
        return FunctionType(body.__code__,ns)(self,"oo",anchor,cert,trace)


def main():
    out=Path(sys.argv[1])
    tag,method=sys.argv[2:4]
    process=frozen.psutil.Process()
    process.cpu_affinity([4])
    setup=perf_counter()
    stack=frozen.u.stack()
    frozen.warm(stack)
    frozen.u.save(out/"ready.json",dict(warm_s=perf_counter()-setup,affinity=process.cpu_affinity(),pid=os.getpid()))
    start=perf_counter()
    frozen.u.save(out/"start.json",dict(clock=start))
    cpu=process_time()
    reg=(OLD if tag=="C10" else HERE)/"registration"
    frozen.u.REG=stack[0].REG=reg
    frozen.u.CASES=frozen.u.read(reg/"cases.json")
    ctx=Route(tag,"terminal" if method=="terminal" else "oo",out,start)
    ctx.locator=method
    frozen.thermal_block=ctx.repair
    status=ctx.run(stack)
    if status=="HOT" and any(r["status"]!="HOT" for r in ctx.attempts):
        status="NO_CERTIFIED_SAFE"
    ctx.store("delivery",dict(status=status,attempts=ctx.attempts,stages=ctx.stages,
              local_replays=ctx.b.replays,cpu_s=process_time()-cpu))
    end=perf_counter()
    ctx.store("finish",dict(wall_s=end-start,clock=end))

if __name__=="__main__":
    main()
