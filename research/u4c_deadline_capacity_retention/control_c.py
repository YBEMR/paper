"""One contemporaneous unmodified C control per input. Exact baseline worker, separate receipt label."""
import inspect
from concurrent.futures import ThreadPoolExecutor
from foundation import *
import batch_control as controller

def group(ids,unit):
    lanes={}
    for k in ids:
        cpu=read(B_SRC/"results"/k/"runs/C.json")["receipt"]["cpu"]
        lanes.setdefault(cpu,[]).append(k)
    def lane(item):
        cpu,ids=item
        for k in ids:unit(cases()[k],"Control",cpu,10)
    with ThreadPoolExecutor(max_workers=len(lanes)) as pool:list(pool.map(lane,lanes.items()))
if __name__=="__main__":
    assert all((OUT_C/(k+"-"+m)/"receipt.json").exists() for k in cases() for m in ARMS)
    source=inspect.getsource(controller.unit);cmd='str(HERE/"experiment.py"),o["id"],method'
    assert source.count(cmd)==1
    env=dict(controller.__dict__,worker_path=str(B_SRC/"routes.py"))
    exec(compile(source.replace(cmd,'worker_path,o["id"],"C"'),"<identical frozen C, distinct receipt>","exec"),env)
    group(FOUR,env["unit"])
    group([k for k in cases() if k not in FOUR],env["unit"])
