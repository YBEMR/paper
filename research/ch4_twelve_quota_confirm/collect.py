"""Use the frozen physical archive checks with the registered twelve-stream resource limits."""
import inspect
import json
import os
import shutil
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"ch4_quota_warm_confirm"))
import collect as frozen_collect

def main():
    root=Path(os.environ["WARM_ROOT"])
    registration=json.loads((root/"registration.json").read_bytes())
    pack=frozen_collect.archive
    pack.CASES=sorted(registration["cases"])
    # The smaller archive encoded the four-stream budget in two assertions.
    # Keep every deadline, energy, trace and ledger check; scale only those guards.
    source=inspect.getsource(pack.main)
    for old,new in (('res["actual_cpu_s"]<=1500','res["actual_cpu_s"]<=4500'),("total<=1440","total<=4320")):
        assert source.count(old)==1
        source=source.replace(old,new)
    namespace={}
    exec(compile(source,"<frozen archive, twelve-stream budgets>","exec"),pack.__dict__,namespace)
    pack.main=namespace["main"]
    frozen_collect.HERE=HERE
    frozen_collect.main()
    out=HERE/"results"
    shutil.copyfile(root/"registration.json",out/"accounts"/"registration.json")
    for case in pack.CASES:
        for path in (root/"formal"/case).glob("*/search/run.json"):
            target=out/"logs"/case/path.parent.parent.name/"search"/"run.json.gz"
            pack.zipped(path,target)

if __name__=="__main__":main()
