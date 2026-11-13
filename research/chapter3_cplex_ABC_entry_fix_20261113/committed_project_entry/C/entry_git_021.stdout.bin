"""Owned Windows Job: hard committed-memory cap, no breakaway, kill on close."""
import ctypes as c
from ctypes import wintypes as w

class IO(c.Structure):
    _fields_=[(n,c.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
class Basic(c.Structure):
    _fields_=[('process_time',c.c_longlong),('job_time',c.c_longlong),('flags',w.DWORD),
              ('min_ws',c.c_size_t),('max_ws',c.c_size_t),('active_limit',w.DWORD),
              ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
class Extended(c.Structure):
    _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),('job_memory',c.c_size_t),
              ('peak_process_memory',c.c_size_t),('peak_job_memory',c.c_size_t)]
class Accounting(c.Structure):
    _fields_=[('user_time',c.c_longlong),('kernel_time',c.c_longlong),('period_user',c.c_longlong),
        ('period_kernel',c.c_longlong),('page_faults',w.DWORD),('total_processes',w.DWORD),
        ('active_processes',w.DWORD),('terminated_processes',w.DWORD)]

class Job:
    def __init__(self,memory_limit,active_limit=1):
        self.k=c.WinDLL('kernel32',use_last_error=True)
        specs={'CreateJobObjectW':([c.c_void_p,w.LPCWSTR],w.HANDLE),
            'SetInformationJobObject':([w.HANDLE,c.c_int,c.c_void_p,w.DWORD],w.BOOL),
            'QueryInformationJobObject':([w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p],w.BOOL),
            'AssignProcessToJobObject':([w.HANDLE,w.HANDLE],w.BOOL),
            'TerminateJobObject':([w.HANDLE,w.UINT],w.BOOL),'CloseHandle':([w.HANDLE],w.BOOL)}
        for name,(args,restype) in specs.items():
            f=getattr(self.k,name);f.argtypes=args;f.restype=restype
        self.h=self.k.CreateJobObjectW(None,None)
        if not self.h:raise c.WinError(c.get_last_error())
        info=Extended();info.basic.flags=0x2000|0x200|0x100|0x8
        info.basic.active_limit=active_limit;info.job_memory=memory_limit;info.process_memory=memory_limit
        try:
            self.ok(self.k.SetInformationJobObject(self.h,9,c.byref(info),c.sizeof(info)))
            got=self.limits()
            if got['job_memory']!=memory_limit or got['flags']!=info.basic.flags or got['active_limit']!=active_limit:
                raise RuntimeError('Windows Job limit readback drift')
        except BaseException:
            self.close();raise
    @staticmethod
    def ok(result):
        if not result:raise c.WinError(c.get_last_error())
    def assign(self,p):self.ok(self.k.AssignProcessToJobObject(self.h,int(p._handle)))
    def terminate(self):self.ok(self.k.TerminateJobObject(self.h,70))
    def limits(self):
        x=Extended();self.ok(self.k.QueryInformationJobObject(self.h,9,c.byref(x),c.sizeof(x),None))
        return dict(flags=int(x.basic.flags),active_limit=int(x.basic.active_limit),job_memory=int(x.job_memory),
            process_memory=int(x.process_memory),peak_job_memory=int(x.peak_job_memory),peak_process_memory=int(x.peak_process_memory))
    def accounting(self):
        x=Accounting();self.ok(self.k.QueryInformationJobObject(self.h,1,c.byref(x),c.sizeof(x),None))
        return dict(active_processes=int(x.active_processes),total_processes=int(x.total_processes),
            terminated_processes=int(x.terminated_processes),user_cpu_s=x.user_time/1e7,kernel_cpu_s=x.kernel_time/1e7)
    def close(self):
        if self.h:self.ok(self.k.CloseHandle(self.h));self.h=None
