"""Trusted-Python worker file boundary. NOT an OS/native security sandbox."""
import os,sys
from pathlib import Path

class BoundaryDenied(PermissionError): pass

def install_worker_boundary(bundle,output,*,stdlib_roots=()):
    bundle,output=Path(bundle).resolve(),Path(output).resolve()
    libs=[Path(p).resolve() for p in stdlib_roots]
    read_roots=[bundle,output,*libs]
    events=[]
    def inside(path,root):
        try: path.relative_to(root); return True
        except ValueError: return False
    def resolve(path):
        if isinstance(path,int): return None  # existing inherited pipes/stdout
        if not isinstance(path,(str,bytes,os.PathLike)): raise BoundaryDenied('BAD_FILE_PATH')
        return Path(os.fsdecode(path)).resolve()
    def deny(event,target):
        events.append({'event':event,'target':str(target)}); raise BoundaryDenied('WORKER_BOUNDARY_DENIED:'+event)
    def hook(event,args):
        if event=='open':
            p=resolve(args[0])
            if p is None: return
            mode=args[1]; flags=args[2] if len(args)>2 else 0
            write=(isinstance(mode,str) and any(v in mode for v in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            allowed=[output] if write else read_roots
            if not any(inside(p,root) for root in allowed): deny(event,p)
        elif event in ('os.listdir','os.scandir'):
            p=resolve(args[0])
            if p is not None and not any(inside(p,root) for root in read_roots): deny(event,p)
        elif event in ('os.remove','os.rmdir','os.mkdir','os.rename'):
            paths=args[:2] if event=='os.rename' else args[:1]
            for x in paths:
                p=resolve(x)
                if p is not None and not inside(p,output): deny(event,p)
        elif event.startswith(('subprocess.','socket.','ctypes.')) or event in ('os.system','os.exec','os.posix_spawn','os.spawn','os.link','os.symlink','os.chdir','winreg.OpenKey','winreg.ConnectRegistry'):
            deny(event,'NATIVE_PROCESS_NETWORK_OR_EXTERNAL_STATE')
    sys.addaudithook(hook)
    return events
