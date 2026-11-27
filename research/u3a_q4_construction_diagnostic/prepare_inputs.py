"""Materialize only the pinned external blobs. Does not execute experimental code."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import re
import subprocess
import time
from urllib.request import urlopen

PINS = {
    "nt":"b95570f9ae5b0cdb26abcdf78701e12f1c644f40",
    "four":"96a13920a46f01b6a9710b88275d0ac08763db4b",
    "u1":"44e99658159ded9042fd47a5c448b5be5868bcdb",
    "u2":"c9aa84bc33e4554f0e18d31e15815c1063300b8d",
    "p1":"be641ce06a4f496d2b1f233a09bdfc3776738668",
}
FILTERS = {
    "nt":r"^research/(m1[^/]*/([^/]+\.py|SHA256SUMS)$|m1_transient_thermal_quota_20261126/(frozen|inputs)/|m1i_generalization/registration/(cases.json|inputs/))",
    "four":r"^research/chapter4_cross_analysis_v5/formal_runner/v1/",
    "u1":r"^research/u1_unified_diagnostic/interface.py$",
    "u2":r"^research/(u1_unified_diagnostic/interface.py$|u2_adaptive_groups/(common_u2.py$|tables/q4_causal.csv$|results/[ABC][0-9][0-9]/(archive.json|physical.tar.gz.part[0-9]+)$))",
    "p1":r"^research/cross_scene_taskflow_diagnostic/(heat.py|model.py|config/[^/]+)$",
}

def git_blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def prepare(repository,out):
    inputs=[]
    for tag,ref in PINS.items():
        for line in subprocess.check_output(["git","-C",str(repository),"ls-tree","-r",ref,"--","research"],encoding="utf8").splitlines():
            meta,path=line.split("\t",1)
            if re.match(FILTERS[tag],path):
                inputs.append((tag,ref,meta.split()[-1],path))
    def obtain(item):
        tag,ref,key,path=item
        target=out/tag/path
        if target.is_file() and git_blob(target.read_bytes())==key:return
        for attempt in range(4):
            try:
                with urlopen(f"https://raw.githubusercontent.com/YBEMR/paper/{ref}/{path}",timeout=120) as response:
                    body=response.read()
                if git_blob(body)!=key:raise ValueError("blob digest mismatch: "+path)
                break
            except (OSError,ValueError):
                if attempt==3:raise
                time.sleep(attempt+1)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(body)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(obtain,inputs))
    print(len(inputs),"verified pinned inputs")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("repository",type=Path,help="local repository containing the five commit trees")
    parser.add_argument("output",type=Path,help="directory to use as U3A_INPUTS")
    args=parser.parse_args()
    prepare(args.repository,args.output)
