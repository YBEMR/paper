"""Candidate wrapper-only fix, NOT integrated into frozen K155 execution.

Retry the replacement of THIS write's complete pending file for a bounded
time on Windows sharing/access rejection; never retry a method or a stale
pending file. Unrelated/permanent errors are raised and evidence is retained.
"""
import json
from pathlib import Path
import os
import time


def save(path,value,*,max_wait_s=1.,clock=time.monotonic,sleep=time.sleep,replace=os.replace):
    if not 0<=max_wait_s<=1.:raise ValueError('Only bounded <=1s wrapper I/O retry')
    path=Path(path);pending=path.with_suffix(path.suffix+'.pending')
    # Stale pending remains a hard error. It cannot be consumed as a new write.
    with pending.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False,default=str)
        stream.write('\n')
    start=clock();attempts=0
    while True:
        attempts+=1
        try:
            replace(pending,path)
            return {'attempts':attempts,'replace_wait_s':clock()-start}
        except PermissionError as exc:
            if getattr(exc,'winerror',None) not in (5,32):raise
            remaining=max_wait_s-(clock()-start)
            if remaining<=0:raise
            sleep(min(0.02,remaining))
