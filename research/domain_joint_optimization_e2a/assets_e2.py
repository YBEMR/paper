"""Artifact access for E2-a. All writes stay in its own directory."""
import csv,gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
from importlib.metadata import version

HERE=Path(__file__).resolve().parent
E1=HERE.parent/"domain_joint_optimization_e0_e1"
REPO=HERE.parents[1]
BASE="57feace657d4ecd495df3b1211ec42161cfee763"
sys.path.insert(0,str(E1))
from common import OLD,FOLLOW,DOM,MEMBERS,raw,sha,decode,obj,archived
from compact import Layout
from inputs import restore
from model import Problem,transitions,independent_events
from heat import evaluate
import numpy as np

def read(path):return json.loads((HERE/path).read_bytes())
def write(path,obj):
    p=HERE/path;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp");tmp.write_bytes(raw(obj)+b"\n");tmp.replace(p)
def csv_rows(path):
    with (HERE/path).open(encoding="utf8",newline="") as f:return list(csv.DictReader(f))
def table(path,rows):
    p=HERE/path;p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",encoding="utf8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def region(name):
    r=restore(read(E1/"regions.json")["regions"][name]);p=Problem(r["case"])
    return p,archived(p.case)[1],r
def store(p,plan):
    b=raw(obj(p.case,plan));key=sha(b);path=HERE/"plans"/(key+".json.gz")
    if not path.exists():
        path.parent.mkdir(exist_ok=True);path.write_bytes(gzip.compress(b,mtime=0))
    return key
def certify(p,plan):
    key=store(p,plan);receipt=HERE/"certificates"/(key+".json")
    if receipt.exists():return key,read(receipt)["metrics"]
    m=evaluate(p,plan,cert=True,trace=True);ev=np.array(m.pop("events"))
    receipt.parent.mkdir(exist_ok=True)
    np.savez_compressed(receipt.with_suffix(".npz"),events=ev)
    write(receipt,dict(sha=key,case=p.case,metrics=m,columns=31))
    return key,m
def score(p,plan):
    return Layout(p,plan[0]).components(plan[1])
def git(*args):return subprocess.check_output(["git",*args],cwd=REPO)
