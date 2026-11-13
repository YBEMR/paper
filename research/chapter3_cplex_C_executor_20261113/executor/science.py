"""Frozen saved matrices and original evaluator, invoked only after new approval."""
from fractions import Fraction
from pathlib import Path
import sys
import numpy as np
from scipy import sparse
from core import read,save,digest,IntegrityError,safe_interval
from transport_contract import MatrixPacket

def admit(packet,x,check=lambda:None):
    x=np.asarray(x)
    if x.dtype.kind!='f' or x.dtype.itemsize!=8 or x.shape!=(packet.n,) or not np.isfinite(x).all():
        return dict(passed=False,reason='SHAPE_DTYPE_OR_NONFINITE',rows={})
    rows={}
    def metric(label,v,scale):
        check();v=np.maximum(v,0.)
        if not np.isfinite(v).all() or not np.isfinite(scale).all(): raise IntegrityError('Nonfinite residual arithmetic')
        rows[label]=dict(max_absolute=float(v.max(initial=0)),max_normalized=float((v/scale).max(initial=0)),
                         worst_zero_based_index=int(np.argmax(v)) if len(v) else None)
    for key,rhs in [('A',packet.b),('Aeq',packet.beq)]:
        shape,r,c,d=getattr(packet,key);m=sparse.csr_matrix((d,(r,c)),shape=shape)
        z=m@x-rhs;v=np.abs(z) if key=='Aeq' else np.maximum(z,0)
        metric(key,v,1+np.abs(rhs)+abs(m)@np.abs(x))
    for key,v in [('lb',packet.lb-x),('ub',x-packet.ub)]:
        b=getattr(packet,key);finite=np.isfinite(b);metric(key,v[finite],1+np.abs(b[finite])+np.abs(x[finite]))
    integ=np.abs(x[packet.intcon]-np.rint(x[packet.intcon]));imax=float(integ.max(initial=0))
    return dict(passed=all(v['max_absolute']<=1e-9 and v['max_normalized']<=1e-9 for v in rows.values()) and imax<=1e-6,
                rows=rows,integer_max=imax,absolute_tolerance=1e-9,normalized_tolerance=1e-9,integer_tolerance=1e-6,
                exact_feasibility_certificate=False,repair_performed=False)

def schedule_key(candidate):
    return {s:sorted((r['stage_id'],r['unit'],r['opp'],str(Fraction(r['start_ms']))) for r in rows) for s,rows in candidate['scenes'].items()}

def decode(instance,options,x,validate):
    y=np.asarray(x)[:len(options)]
    if len(y)!=len(options) or not np.isfinite(y).all() or np.any(abs(y-np.rint(y))>1e-6) or np.any(y< -1e-6) or np.any(y>1+1e-6):
        raise ValueError('Nonbinary option vector; no repair')
    result={'scenes':{s['id']:[] for s in instance['scenarios']}}
    for o,v in zip(options,y):
        if round(float(v))==1:
            result['scenes'][o['scenario_id']].append(dict(stage_id=o['stage_instance_id'],unit=o['unit_id'],opp=o['opp_id'],start_ms=o['start_ms']))
    legality=validate(instance,result)
    if legality.get('state')!='SCHEDULE_VALID_THERMAL_UNCHECKED': raise ValueError('Independent legality rejected: '+str(legality.get('reason')))
    return result,legality

def exact_objective(packet,x):
    return sum((Fraction.from_float(float(c))*Fraction.from_float(float(v)) for c,v in zip(packet.c,x)),Fraction(0))

class Science:
    def __init__(self,root,plan,out,clock):
        self.root=Path(root);self.plan=plan;self.out=Path(out);self.clock=clock;self.evaluations=0
    def prepare(self):
        from scipy.io import loadmat
        from core import verify
        self.clock.check();verify(self.root,self.plan['evaluation_source_hashes'])
        source=self.root/'work/equality_pair_source/research/chapter3_experiments'
        sys.path.insert(0,str(source))
        from schedules import validate_schedule
        from thermal import evaluate_candidate
        from timing import MethodBudget
        self.validate=validate_schedule;self.evaluate_fn=evaluate_candidate
        self.budget=MethodBudget(590,clock=self.clock.now);self.budget.start=self.clock.start;self.budget.deadline=self.clock.start+590
        self.instance=read(self.root/'work/stable_expression/full/input_instance.json')
        self.config=read(self.root/'work/stable_expression/full/input_config.json')
        saved=self.root/'work/mechanism_trials_execution_v1/C_noheur'
        self.options=read(saved/'options.json');self.initial=read(saved/'initialization.json')['attempts'][0]['candidate']
        self.scenes=[s['id'] for s in self.instance['scenarios']]
        self.packets={}
        for name,spec in self.plan['matrices'].items():
            data=loadmat(self.root/spec['path'],variable_names=['c','A','b','Aeq','beq','lb','ub','intcon','x0'])
            p=MatrixPacket.read(data,intcon_base=spec['intcon_base'],sense='min',objective_constant=0.,column_ids=range(data['c'].size))
            if p.hashes()!=spec['canonical_arrays_sha256']: raise IntegrityError('Matrix hash drift: '+name)
            self.packets[name]=p;self.clock.check()
        self.old=self.packets['original'];self.new=self.packets['complement']
        cert=read(saved/'representation_certificate.json')
        if not all(v is True for v in cert['checks'].values()): raise IntegrityError('Projection certificate failed')
        if self.old.intcon.tolist()!=self.new.intcon.tolist() or self.old.intcon.tolist()!=list(range(len(self.options))): raise IntegrityError('Option/index identity')
        for name in ('c','lb','ub','x0'):
            if getattr(self.old,name).tobytes()!=getattr(self.new,name)[:self.old.n].tobytes(): raise IntegrityError('Original prefix changed')
        if np.any(self.new.c[self.old.n:]!=0): raise IntegrityError('Nonzero added objective')
        self.initial_admission=self.validate_vector(self.new.x0,'initial_admission.json')
        if not self.initial_admission['passed'] or not self.initial_admission['same_initial']: raise IntegrityError('Common initialization drift or rejected')
        save(self.out/'input_identity.json',dict(input=digest(self.instance),initial=digest(self.initial),matrices={k:v.hashes() for k,v in self.packets.items()},projection_checks=cert['checks'],source='frozen_saved_C'))
    def validate_vector(self,x,filename):
        self.clock.check();a=admit(self.new,x,self.clock.check);b=admit(self.old,np.asarray(x)[:self.old.n],self.clock.check)
        result=dict(passed=False,complement=a,original=b,legality=None,candidate=None,same_initial=None)
        if a['passed'] and b['passed']:
            try:
                candidate,legality=decode(self.instance,self.options,x,self.validate)
                result.update(passed=True,candidate=candidate,legality=legality,same_initial=schedule_key(candidate)==schedule_key(self.initial),
                    schedule_identity=digest(schedule_key(candidate)),objective_exact_binary64=str(exact_objective(self.new,x)))
            except ValueError as e: result['rejection']=str(e)
        result['completed_elapsed_s']=self.clock.elapsed;self.clock.check();save(self.out/filename,result);self.clock.check()
        return result
    def evaluate(self,candidate,name):
        if self.evaluations>=2: raise IntegrityError('Evaluation cap consumed')
        self.clock.check();self.evaluations+=1
        result=self.evaluate_fn(self.instance,candidate,self.config['accuracy_targets'],budget=self.budget)
        result['evidence_identity']=dict(input=digest(self.instance),candidate=digest(candidate))
        result['archived_elapsed_s']=self.clock.elapsed
        save(self.out/name,result);self.clock.check()
        return result
