"""Verify Git blob identity without running a solver or altering frozen data."""
import hashlib,json,subprocess
from pathlib import Path
here=Path(__file__).resolve().parent;repo=here.parents[1];lab=repo.parent
def tree(ref,*args):
    result=subprocess.check_output(["git","-C",str(repo),"ls-tree","-r",ref,"--",*args]).decode()
    return {line.split("\t")[1]:line.split("\t")[0].split()[-1] for line in result.splitlines()}
def digest(data):return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
def main():
    nt="b95570f9ae5b0cdb26abcdf78701e12f1c644f40";gen="85969e8ed78cbab4d693122819ebe866e0721bb7"
    four="96a13920a46f01b6a9710b88275d0ac08763db4b";driver="798f5586acedf0936e2786e1ca226992fab7a0ac"
    manifest={}
    for role,root,ref,parts in (
            ("search",lab/"U3a_inputs/nt",nt,["research"]),
            ("registration",lab/"U3a_inputs/nt",gen,["research/m1i_generalization/registration"]),
            ("physical",lab/"U3a_inputs/four",four,["research/chapter4_cross_analysis_v5/formal_runner/v1"]),
            ("driver",repo,driver,["research/ch3_integrated_quality_v1","research/ch3_integrated_quality_v2","research/ch3_integrated_quality_v3","research/m6a_global_frequency_mapping","research/u1_unified_diagnostic/interface.py","research/u2_adaptive_groups/common_u2.py"])):
        seen={}
        for rel,h in tree(ref,*parts).items():
            p=root/rel
            if not p.is_file():continue
            if role=="search" and (not rel.startswith("research/m1") or (p.suffix!=".py" and "/frozen/" not in rel and "/inputs/" not in rel)):continue
            if role=="driver" and p.suffix not in (".py",".cpp") and "/tables/" not in rel and p.name!="receipt.json":continue
            assert digest(p.read_bytes())==h,(role,rel)
            seen[rel]=h
        assert seen
        manifest[role]=dict(commit=ref,files=seen)
    assert "research/m1e_thermal_quota_ablation/experiment.py" in manifest["search"]["files"]
    assert len([x for x in manifest["registration"]["files"] if "/inputs/" in x])>=12
    (here/"sources.json").write_text(json.dumps(manifest,sort_keys=True,indent=1)+"\n",encoding="utf8")
if __name__=="__main__":main()
