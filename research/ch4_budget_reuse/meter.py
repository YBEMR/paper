"""Exclusive wall clock buckets and exact time-boundary snapshots in each worker."""
from collections import Counter
from contextlib import contextmanager
import gzip
import json
from time import perf_counter


def compact(obj):
    return json.dumps(obj,separators=(",",":"),allow_nan=False)


class Meter:
    def __init__(self,start):
        self.start=self.last=start
        self.label="initialization"
        self.seconds=Counter()
        self.counts=Counter()
        self.boundaries={}
        self.edges=iter((5,10,20,116))
        self.edge=next(self.edges,None)

    def tick(self):
        now=perf_counter()
        while self.edge is not None and self.start+self.edge <= now:
            point=self.start+self.edge
            self.seconds[self.label]+=point-self.last
            self.last=point
            self.boundaries[str(self.edge)]=[dict(self.seconds),dict(self.counts)]
            self.edge=next(self.edges,None)
        self.seconds[self.label]+=now-self.last
        self.last=now
        return now-self.start

    @contextmanager
    def doing(self,label):
        self.tick()
        old,self.label=self.label,label
        try:
            yield
        finally:
            self.tick()
            self.label=old

    def snapshot(self):
        self.tick()
        return [dict(self.seconds),dict(self.counts)]


class Log:
    def __init__(self,path,meter):
        self.file=gzip.open(path,"wb",compresslevel=1)
        self.m=meter
        self.n=0

    def add(self,value):
        with self.m.doing("logging"):
            self.file.write((compact(value)+"\n").encode())
            self.n+=1

    def close(self):
        with self.m.doing("logging"):
            self.file.close()
