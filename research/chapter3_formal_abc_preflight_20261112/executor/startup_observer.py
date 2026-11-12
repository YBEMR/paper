"""Passive timing wrappers, preserving arguments, return values, polling and errors."""
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def observe_startup(bridge, clock, records):
    subprocess_module=bridge.subprocess
    reader=bridge._read_json_until
    def timed(label,function,*args,**kwargs):
        start=clock();row=dict(phase=label,start_monotonic=start)
        try:
            return function(*args,**kwargs)
        except BaseException as error:
            row['exception']=type(error).__name__
            raise
        finally:
            row['end_monotonic']=clock();row['elapsed_s']=row['end_monotonic']-start
            records.append(row)
    class Proxy:
        def __getattr__(self,name):return getattr(subprocess_module,name)
        def Popen(self,*args,**kwargs):return timed('Popen_return',subprocess_module.Popen,*args,**kwargs)
    def traced_reader(path,*args,**kwargs):
        if Path(path).name=='ready.json':return timed('READY_read_wait',reader,path,*args,**kwargs)
        return reader(path,*args,**kwargs)
    bridge.subprocess=Proxy();bridge._read_json_until=traced_reader
    try:yield
    finally:
        bridge.subprocess=subprocess_module;bridge._read_json_until=reader
