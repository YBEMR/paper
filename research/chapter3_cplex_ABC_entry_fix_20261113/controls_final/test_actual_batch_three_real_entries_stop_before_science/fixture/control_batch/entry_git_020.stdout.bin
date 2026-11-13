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

