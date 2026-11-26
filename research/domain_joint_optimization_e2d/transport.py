"""One pinned worker per run; durable per-command handoff and timed pipe messages."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import psutil
from design_d import clock

def worker_entry(pipe,cpu):
    import traceback
    entered=clock()
    psutil.Process().cpu_affinity([cpu])
    try:
        pipe.send(("boot",{"entered":entered,"pid":os.getpid()}))
        t=clock()
        from engine_d import Engine,LocalDeadline
        loaded=clock();engine=Engine();ready=clock()
        pipe.send(("ready",dict(import_s=loaded-t,assets_s=ready-loaded,at=ready,
                                peak_bytes=psutil.Process().memory_info().peak_wset)))
        while True:
            cmd=pipe.recv()
            if cmd is None:return
            kind,job,variant,journal=cmd
            engine.variant=variant
            with open(journal,"xb",buffering=0) as f:
                count=0
                def transmit(msg):
                    nonlocal count
                    if msg[0] in ("cert","rights"):
                        b=(json.dumps(msg,allow_nan=False,default=str,separators=(",",":"))+"\n").encode()
                        assert f.write(b)==len(b)
                        count+=1
                    else:pipe.send(msg)
                try:
                    engine.execute(transmit,kind,job)
                    status="COMPLETE"
                except LocalDeadline:status="TIME_LIMIT"
            pipe.send(("done",status,count,clock()))
    except (EOFError,BrokenPipeError):pass
    except Exception:pipe.send(("error",traceback.format_exc()))
    finally:pipe.close()

class Channel:
    def __init__(self,cpu,log,folder,variant):
        self.cpu=cpu;self.log=log;self.variant=variant
        self.folder=folder/"handoff";self.folder.mkdir()
        self.child=None;self.pipe=None;self.serial=0;self.init_failures=0

    def open(self,end):
        if self.child is not None:return True
        if clock()>=end:return False
        ctx=mp.get_context("spawn");self.pipe,other=ctx.Pipe()
        self.child=ctx.Process(target=worker_entry,args=(other,self.cpu),daemon=True)
        began=clock();self.child.start();other.close()
        self.log("worker_start",pid=self.child.pid,creation_s=clock()-began,at=began)
        while self.pipe.poll(max(0,end-clock())):
            packet=self.pipe.recv();at=clock()
            if packet[0]=="error":raise RuntimeError(packet[1])
            if packet[0]=="ready":
                self.log("worker_ready",pid=self.child.pid,ready_s=at-began,ipc_s=at-packet[1]["at"],**packet[1])
                return True
            assert packet[0]=="boot",packet
            self.log("worker_boot",interpreter_s=packet[1]["entered"]-began,**packet[1])
        self.init_failures+=1
        self.log("initialization_timeout",seconds=clock()-began)
        self.close(True)
        if self.init_failures>=2:raise RuntimeError("repeated worker initialization deadline")
        return False

    def close(self,force=False):
        if self.child is None:return
        t=clock();pid=self.child.pid
        if not force and self.child.is_alive():
            self.pipe.send(None);self.child.join(.35)
        if self.child.is_alive():self.child.terminate();self.child.join(.30)
        if self.child.is_alive():self.child.kill();self.child.join(.35)
        assert not self.child.is_alive(),"worker still alive"
        self.log("worker_exit",pid=pid,code=self.child.exitcode,cleanup_s=clock()-t,deadline=force)
        self.child.close();self.pipe.close();self.child=self.pipe=None

    def call(self,op,job,limit,receive):
        # Recovery initialization also consumes this command's wall allocation.
        started=clock()
        if not self.open(limit-1.35):return "INITIALIZATION_DEADLINE"
        if clock()>=limit-1.1:return "TIME_LIMIT"
        self.serial+=1
        path=self.folder/(f"{self.serial:05d}.jsonl")
        t=clock();self.pipe.send((op,job,self.variant,str(path)));sent=clock()
        self.log("dispatch",serial=self.serial,op=op,send_s=sent-t,started=started,deadline=limit)
        count=None;status="WORKER_DEADLINE"
        while self.pipe.poll(max(0,limit-1.0-clock())):
            packet=self.pipe.recv()
            if packet[0]=="error":raise RuntimeError(packet[1])
            if packet[0]=="done":
                _,status,count,done=packet
                self.log("command_done",serial=self.serial,op=op,reply_s=clock()-done)
                break
            assert packet[0]=="note",packet[0]
            receive("note",packet[1],limit)
            if clock()>=limit-1.0:break
        if count is None:self.close(True)
        # A single writer publishes complete records before signaling done.
        # If a worker is terminated, recover the committed prefix. An incomplete
        # record is an unresolved handoff and stops the batch.
        data=path.read_bytes() if path.exists() else b""
        assert not data or data.endswith(b"\n"),"incomplete certificate handoff"
        lines=data.splitlines()
        assert count is None or count==len(lines)
        for line in lines:
            kind,record=json.loads(line)
            receive(kind,record,limit)
        self.log("handoff",serial=self.serial,op=op,records=len(lines),ack=count,sha256=__import__("hashlib").sha256(data).hexdigest(),
                 status=status,elapsed=clock()-started)
        return status
