"""One CPLEX call, public observation and final receipt. Imported CPLEX is injected."""
from pathlib import Path
import json, math, os, re, time
import numpy as np
from core import save,sha,quota,finite_native,error_record,IntegrityError,WindowExpired,classify_native
from native_adapter import load,readback,compare,loaded_dll

def get_parameter(model,path):
    p=model.parameters
    for token in path.removeprefix('parameters.').split('.'): p=getattr(p,token)
    return p

def configure(model,plan):
    actual={str(p):v for p,v in model.parameters.get_all()}
    if actual!=plan['parameter_baseline']: raise IntegrityError('CPLEX parameter defaults drift')
    for path,value in plan['parameter_overrides'].items():
        if path!='timelimit': get_parameter(model,path).set(value)
    expected=dict(plan['parameter_baseline'])
    expected.update({'parameters.'+p:v for p,v in plan['parameter_overrides'].items() if p!='timelimit'})
    actual={str(p):v for p,v in model.parameters.get_all()}
    if actual!=expected: raise IntegrityError('CPLEX parameter readback drift')
    return actual

def array_archive(path,x):
    path=Path(path);tmp=path.with_name(path.name+'.partial')
    with tmp.open('xb') as f: np.save(f,np.asarray(x,dtype='<f8'),allow_pickle=False);f.flush();os.fsync(f.fileno())
    os.rename(tmp,path)
    return dict(file=path.name,sha256=sha(path),length=int(np.asarray(x).size))

class Events:
    def __init__(self,out,clock):
        self.out=Path(out);self.clock=clock;self.n=0
        self.file=(self.out/'events.jsonl').open('x',encoding='utf-8',newline='\n')
    def emit(self,kind,**value):
        self.n+=1
        self.file.write(json.dumps(dict(sequence=self.n,kind=kind,worker_elapsed_s=self.clock.elapsed,**value),allow_nan=False)+'\n');self.file.flush()
    def close(self): self.file.close()

class LogStream:
    def __init__(self,out,events): self.f=(Path(out)/'native.log').open('x',encoding='utf-8',newline='\n');self.events=events
    def write(self,text):
        self.f.write(text);self.f.flush();self.events.emit('native_log',text=text)
    def flush(self): self.f.flush()
    def close(self): self.f.close()

def read_value(fn):
    try:
        x=fn()
        if isinstance(x,float) and not math.isfinite(x): return dict(value=None,raw=repr(x),error='NONFINITE')
        return dict(value=x,error=None)
    except Exception as e: return dict(value=None,error=error_record(e))

def callback_class(base,out,clock,events):
    class Observe(base):
        def __call__(self):
            if clock.elapsed>=550:
                self.abort();return
            now=clock.elapsed
            incumbent=read_value(self.has_incumbent)
            objective=read_value(self.get_incumbent_objective_value) if incumbent['value'] else dict(value=None,error='NO_INCUMBENT')
            changed=objective['value'] is not None and objective['value']!=getattr(self,'last_objective',None)
            if now-getattr(self,'last_record',-1e30)<1 and not changed: return
            self.last_record=now;self.last_objective=objective['value']
            r=dict(incumbent=incumbent,incumbent_objective=objective,
                   best_bound=read_value(self.get_best_objective_value),nodes=read_value(self.get_num_nodes),
                   iterations=read_value(self.get_num_iterations),gap=read_value(self.get_MIP_relative_gap),vector=None)
            if changed:
                try:
                    x=np.asarray(self.get_incumbent_values(),dtype='<f8')
                    self.vector_no=getattr(self,'vector_no',0)+1
                    r['vector']=array_archive(Path(out)/('callback_vector_%06d.npy'%self.vector_no),x)
                except Exception as e: r['vector_error']=error_record(e)
            events.emit('mip_info_callback',**r)
    return Observe

def parse_observed_logs(rows):
    """Conservative parser: unknown wording remains UNKNOWN; never infer from bound."""
    buffer='';evidence=[];accepted=rejected=root=False
    for row in rows:
        event=row.get('event',{});stamp=row.get('parent_received_elapsed_s')
        if not isinstance(stamp,(int,float)) or not 0<=stamp<550 or event.get('kind')!='native_log': continue
        buffer+=event.get('text','')
        lines=buffer.split('\n');buffer=lines.pop()
        for line in lines:
            low=line.lower();tags=[]
            if ("mip start 'common_complete_x0' defined initial solution" in low or '1 of 1 mip starts provided solutions' in low):
                accepted=True;tags.append('MIP_START_ACCEPTED')
            if 'no solution found from 1 mip starts' in low or ('common_complete_x0' in low and ('infeasible' in low or 'rejected' in low)):
                rejected=True;tags.append('MIP_START_REJECTED')
            if 'root relaxation solution time' in low:
                root=True;tags.append('ROOT_LP_COMPLETED_IMPLYING_ENTERED')
            if tags or any(w in low for w in ('presolve','reduced mip','parallel mode','threads','root relaxation')):
                evidence.append(dict(line=line,received_elapsed_s=stamp,tags=tags))
    return dict(MIP_start_acceptance='CONFLICT' if accepted and rejected else ('ACCEPTED' if accepted else ('REJECTED' if rejected else 'UNKNOWN')),
                root_LP_entered='PASS' if root else 'UNKNOWN',root_LP_completed='PASS' if root else 'UNKNOWN',
                evidence=evidence,trailing_incomplete_line=buffer or None,internal_time_not_inferred=True)

class Native:
    def __init__(self,api,plan,out,clock,events):
        self.api=api;self.plan=plan;self.out=Path(out);self.clock=clock;self.events=events
        self.model=None;self.stream=None;self.calls=0;self.closed=False
    def prepare(self,packet):
        self.clock.check();self.model=self.api.Cplex()
        self.stream=LogStream(self.out,self.events)
        for name in ('set_log_stream','set_results_stream','set_warning_stream','set_error_stream'): getattr(self.model,name)(self.stream)
        version=self.model.get_version();dll=loaded_dll()
        r=self.plan['native_runtime']
        if version!=r['cplex_version'] or os.path.normcase(os.path.realpath(dll))!=os.path.normcase(os.path.realpath(r['dll_path'])) or sha(dll)!=r['dll_sha256']:
            raise IntegrityError('Native version or DLL drift')
        save(self.out/'runtime.json',dict(engine_version=version,dll=dll,dll_sha256=sha(dll)))
        def progress(kind,**kw): self.events.emit(kind,**kw)
        load(self.model,self.api,packet,self.clock.check,progress)
        q,invariants=readback(self.model,self.api,packet,self.clock.check,progress)
        comparison=compare(packet,q,invariants);save(self.out/'readback.json',comparison)
        if not comparison['passed']: raise IntegrityError('Native roundtrip failed')
        params=configure(self.model,self.plan);save(self.out/'parameters_before_quota.json',params)
        self.model.register_callback(callback_class(self.api.callbacks.MIPInfoCallback,self.out,self.clock,self.events))
    def solve_once(self,plan_hash):
        if self.calls: raise IntegrityError('One solve already consumed')
        self.clock.check(550)
        t=self.clock.elapsed;n=quota(t)
        if n<30:
            save(self.out/'allocation.json',dict(allocation_elapsed_s=t,native_seconds=n,skipped=True));return None
        get_parameter(self.model,'timelimit').set(float(n))
        params={str(p):v for p,v in self.model.parameters.get_all()}
        expected=dict(self.plan['parameter_baseline']);expected.update({'parameters.'+k:(float(n) if k=='timelimit' else v) for k,v in self.plan['parameter_overrides'].items()})
        if params!=expected: raise IntegrityError('Final parameter snapshot mismatch')
        save(self.out/'parameters_at_solve.json',params)
        self.clock.check(550)
        save(self.out/'allocation.json',dict(allocation_elapsed_s=t,native_seconds=n,dispatch_elapsed_s=self.clock.elapsed,skipped=False))
        self.calls+=1;self.events.emit('solve_entered',native_seconds=n)
        error=None;reserve=bytearray(4*1024*1024)
        try: self.model.solve()  # The sole scientific optimization call in this package.
        except Exception as e:
            reserve=None
            if isinstance(e,MemoryError):os.write(2,b'D283 native MemoryError caught; original exception follows in native_error.json\n')
            error=error_record(e);save(self.out/'native_error.json',error)
        finally:reserve=None
        returned=self.clock.elapsed;self.events.emit('solve_returned',error=error)
        s=self.model.solution
        r=dict(plan_sha256=plan_hash,solve_calls=self.calls,returned_elapsed_s=returned,error=error,vector=None)
        for k,fn in [('status',s.get_status),('status_string',s.get_status_string),('primal_feasible',s.is_primal_feasible),
                     ('objective',s.get_objective_value),('best_bound',s.MIP.get_best_objective),('gap',s.MIP.get_mip_relative_gap),
                     ('nodes',s.progress.get_num_nodes_processed),('iterations',s.progress.get_num_iterations)]: r[k]=read_value(fn)
        if returned<550 and r['primal_feasible']['value'] is True:
            try:
                x=np.asarray(s.get_values(),dtype='<f8')
                if x.size and x.ndim==1 and np.isfinite(x).all(): r['vector']=array_archive(self.out/'final_vector.npy',x)
                else:r['vector_error']='EMPTY_OR_NONFINITE_NATIVE_VECTOR'
            except Exception as e:r['vector_error']=error_record(e)
        r['native_exit_category']=classify_native(r['status']['value'],error)
        r['finite_native_lower_bound']=finite_native(r['best_bound']['value'])
        r['finite_native_upper_bound']=finite_native(r['objective']['value']) if r['primal_feasible']['value'] is True else None
        gap=finite_native(r['gap']['value']);r['finite_native_gap']=gap if gap is not None and gap>=0 else None
        r['published_elapsed_s']=self.clock.elapsed
        save(self.out/'native_response.json',r)
        return r
    def close(self):
        if self.model is not None: self.model.end();self.model=None
        if self.stream is not None:self.stream.close();self.stream=None
        self.closed=True
