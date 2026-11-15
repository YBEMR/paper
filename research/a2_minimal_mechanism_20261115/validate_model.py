"""Analytic validation of conservation and event timing; no fit to desired outcomes."""
from pathlib import Path
import json
import numpy as np
from scipy.linalg import expm
from model import pack,cycle,initial_states,sequence

ROOT=Path(__file__).resolve().parent
def main():
    p=pack(json.loads((ROOT/'protocol.json').read_text(encoding='utf-8'))['base'])
    st,reason=initial_states(p);assert st is not None,reason
    checks=[]
    q=p.copy();q[11]=0
    expected=q[7]*q[21]+q[8]*q[22]+(q[9]+q[5])*q[23]+2*q[20]
    ev=[cycle(q,*st[0],a,False,False,False) for a in range(9)]
    err=max(abs(v[0]-expected) for v in ev);assert err<1e-9
    checks.append({'name':'all offsets equal under fixed work and constant leakage, no contention/host cost','max_error_J':err})
    v=cycle(p,*st[0],0,False,True,False)
    finish=p[21]*p[12]+p[22]-p[21]
    overlap=p[21]*p[12]
    dyn=(p[7]+p[8])*p[21]*(p[13]*p[12]+1-p[13])+p[8]*(p[22]-p[21])
    assert abs(v[7]-finish)<1e-10 and abs(v[12]-overlap)<1e-10 and abs(v[1]-dyn)<1e-9
    checks.append({'name':'analytic overlap work conservation','expected_finish_B_s':finish,'observed':v[7]})
    for action in [7,8]:
        v=cycle(p,*st[0],action,False,True,False)
        assert abs(max(v[6:8])-sum(p[21:23]))<1e-10 and v[12]==0
    checks.append({'name':'serial event starts at actual completion','status':'PASS'})
    q=p.copy();q[20]=0;q[21:23]=10;q[23]=.1
    M=np.array([[-1/q[1]/q[3],1/q[1]/q[3]],[1/q[1]/q[4],-(1/q[1]+1/q[2])/q[4]]])
    b=np.array([(q[7]+q[8]+q[5]+q[11])/q[3],(q[9]-q[10]+q[0]/q[2])/q[4]])
    steady=np.linalg.solve(-M,b);expected=steady+expm(M*q[23])@(st[0]-steady)
    v=cycle(q,*st[0],0,False,False,False)
    err=float(np.max(abs(v[10:12]-expected)));assert err<2e-7
    checks.append({'name':'independent matrix-exponential two-node RC solution','max_error_C':err})
    ev=[cycle(p,*s,a) for s in st for a in range(9)]
    err=max(abs(v[16]) for v in ev);assert err<1e-8
    component=max(abs(v[0]-sum(v[1:6])) for v in ev);assert component<1e-10
    checks.append({'name':'input energy minus external dissipation equals heat rejected plus stored heat','max_residual_J':err})
    checks.append({'name':'energy accounting components sum','max_residual_J':component})
    q=p.copy();q[6]=0
    carry=sequence(q,st[0],0,0.,0,0,12,False,False)
    reset=sequence(q,st[0],0,0.,0,0,12,True,False)
    assert np.max(abs(carry[:,4]-reset[:,4]))<1e-9
    checks.append({'name':'temperature cannot change energy when thermal-power feedback and throttle absent','status':'PASS'})
    result={'status':'PASS','scope':'Analytic arithmetic, physics conservation and event handling; not hardware calibration','checks':checks}
    (ROOT/'validation_model.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
