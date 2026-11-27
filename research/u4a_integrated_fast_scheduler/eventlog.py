"""Append-only, recoverable telemetry. Each published length commits a complete record."""
import gzip
import marshal
import mmap
import struct
from pathlib import Path

class Journal:
    def __init__(self,out):
        self.out=out
        self.frames=0
        self.page=None
        self.page_size=1<<20
    def emit(self,*record):
        b=marshal.dumps(record,4)
        length=len(b)+4
        if self.page is None or self.pos+length>len(self.page):
            self.close()
            f=(self.out/f"journal-{self.frames:04d}.bin").open("x+b")
            size=max(self.page_size,4+length)
            f.truncate(size)
            self.page=mmap.mmap(f.fileno(),size)
            f.close()
            self.pos=4
            self.frames+=1
        start=self.pos
        struct.pack_into("<I",self.page,start,len(b))
        self.page[start+4:start+length]=b
        self.pos+=length
        struct.pack_into("<I",self.page,0,self.pos)
    def close(self):
        if self.page is not None:
            self.page.close()
            self.page=None

def records(data):
    n=struct.unpack_from("<I",data)[0]
    if n==0:return
    i=4
    while i<n:
        m=struct.unpack_from("<I",data,i)[0]
        yield marshal.loads(data[i+4:i+4+m])
        i+=4+m
    assert i==n
