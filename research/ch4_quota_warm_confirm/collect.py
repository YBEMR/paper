"""Collect already finished warm cells with the previous physical and deadline checks."""
import json,os,shutil,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"ch4_quota_transfer"))
import archive

def main():
    root=Path(os.environ["WARM_ROOT"])
    result=HERE/"results"
    prep=archive.read(root/"preparation_account.json")
    assert prep["passed"] and prep["actual_cpu_s"]<=240
    src=root/"preparation"
    gate=archive.read(src/"gate.json")
    assert gate["passed"] and len(gate["checks"])==2
    # The legacy collector accepts a setup receipt; bind it to this batch's actual preparation.
    setup=dict(preparation=prep,gate=gate,kernels=archive.read(src/"kernels.json"))
    archive.dump(root/"setup.json",setup)
    archive.ROOT=root
    archive.OUT=result
    archive.main()
    acct=archive.read(result/"budget.json")
    assert acct.pop("diagnostic_cpu_s")==0
    acct["preparation_cpu_s"]=prep["actual_cpu_s"]
    acct["preparation_limit"]=240
    archive.dump(result/"budget.json",acct)
    evidence=result/"accounts"
    evidence.mkdir(exist_ok=True)
    for folder in [root,src,*sorted((root/"formal").iterdir())]:
        for name in ("preparation_account.json","formal_account.json","gate.json","kernels.json","account.json","stop.json"):
            source=folder/name
            if source.exists():
                target=evidence/source.relative_to(root)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
    for path in (root/"guards").rglob("*.json"):
        target=evidence/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)

if __name__=="__main__":main()
