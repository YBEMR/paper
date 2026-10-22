"""Bounded wrapper-only atomic replace retry; never retry a research call."""
import json
import os
from pathlib import Path
import time


def save(path,value,*,max_wait_s=1.,clock=time.monotonic,sleep=time.sleep,replace=os.replace):
    if not 0<=max_wait_s<=1.:raise ValueError('Wrapper IO retry must be bounded by 1s')
    path=Path(path);pending=path.with_suffix(path.suffix+'.pending')
    with pending.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False,default=str)
        stream.write('\n')
    start=clock();attempts=0
    while True:
        attempts+=1
        try:
            replace(pending,path)
            return {'attempts':attempts,'replace_wait_s':clock()-start}
        except PermissionError as error:
            if getattr(error,'winerror',None) not in (5,32):raise
            remaining=max_wait_s-(clock()-start)
            if remaining<=0:raise
            sleep(min(.02,remaining))


def read_small(path):
    # Close the read handle BEFORE JSON parsing; only compact status, not ledger.
    data=Path(path).read_bytes()
    if len(data)>65536:raise ValueError('Supervisor status exceeds compact contract')
    return json.loads(data.decode('utf-8'))
