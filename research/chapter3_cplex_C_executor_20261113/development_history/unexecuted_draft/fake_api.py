"""Artificial four-column API double. No CPLEX import or optimizer."""
import copy,types
import numpy as np
from scipy import sparse
from transport_contract import MatrixPacket

class Pair:
    def __init__(self,ind,val):self.ind=list(ind);self.val=list(val)
class Vars:
    def add(self,**kw):self.d=copy.deepcopy(kw)
    def get_num(self):return len(self.d['obj'])
    def get_names(self):return self.d['names']
    def get_types(self):return list(self.d['types'])
    def get_lower_bounds(self):return self.d['lb']
    def get_upper_bounds(self):return self.d['ub']
class Rows:
    def __init__(self):self.rows=[];self.senses=[];self.rhs=[];self.names=[]
    def add(self,lin_expr,senses,rhs,names):
        self.rows.extend(copy.deepcopy(lin_expr));self.senses.extend(senses);self.rhs.extend(rhs);self.names.extend(names)
    def get_num(self):return len(self.rows)
    def get_names(self):return self.names
    def get_senses(self):return self.senses
    def get_rhs(self):return self.rhs
    def get_num_nonzeros(self):return sum(len(x.val) for x in self.rows)
    def get_rows(self,begin,end):return copy.deepcopy(self.rows[begin:end+1])
class Starts:
    effort_level=types.SimpleNamespace(check_feasibility=1)
    def __init__(self):self.count=0
    def add(self,pair,effort,name):self.pair=copy.deepcopy(pair);self.effort=effort;self.name=name;self.count+=1
    def get_num(self):return self.count
    def get_starts(self,index):return copy.deepcopy(self.pair),self.effort
    def get_names(self):return [self.name]
class Objective:
    sense=types.SimpleNamespace(minimize=1)
    def __init__(self,v):self.v=v
    def set_sense(self,x):self.s=x
    def set_offset(self,x):self.offset=x
    def get_sense(self):return self.s
    def get_offset(self):return self.offset
    def get_linear(self):return self.v.d['obj']
class Parameter:
    def __init__(self,name,value):self.name=name;self.value=value
    def __str__(self):return self.name
    def get(self):return self.value
    def set(self,v):self.value=v
class Parameters:
    def __init__(self):
        self.timelimit=Parameter('parameters.timelimit',1e75);self.threads=Parameter('parameters.threads',0)
    def get_all(self):return [(p,p.get()) for p in (self.timelimit,self.threads)]
class FakeCallbackBase:pass
class FakeModel:
    def __init__(self):
        self.variables=Vars();self.linear_constraints=Rows();self.MIP_starts=Starts();self.objective=Objective(self.variables)
        self.quadratic_constraints=self.indicator_constraints=self.SOS=types.SimpleNamespace(get_num=lambda:0)
        self.parameters=Parameters();self.calls=0;self.closed=False;self.status=107;self.error=None
        self.vector=np.array([0.,.25,.25,1.]);self.objective_value=.25;self.bound=.1;self.accept_start=True
        self.solution=types.SimpleNamespace(get_status=lambda:self.status,get_status_string=lambda:'time limit',is_primal_feasible=lambda:self.vector is not None,
            get_values=lambda:self.vector,get_objective_value=lambda:self.objective_value,
            MIP=types.SimpleNamespace(get_best_objective=lambda:self.bound,get_mip_relative_gap=lambda:.6),
            progress=types.SimpleNamespace(get_num_nodes_processed=lambda:3,get_num_iterations=lambda:42))
    def get_version(self):return 'FAKE_CONTROL'
    def set_log_stream(self,s):self.stream=s
    def set_results_stream(self,s):pass
    def set_warning_stream(self,s):pass
    def set_error_stream(self,s):pass
    def register_callback(self,c):self.callback_class=c
    def solve(self):
        self.calls+=1
        self.stream.write("MIP start 'common_complete_x0' defined initial solution with objective 0.25.\n" if self.accept_start else 'Warning: No solution found from 1 MIP starts.\n')
        self.stream.write('Root relaxation solution time = 0.01 sec.\n')
        if self.error:raise self.error
    def end(self):self.closed=True

def api(model):return types.SimpleNamespace(Cplex=lambda:model,SparsePair=Pair,infinity=1e20,callbacks=types.SimpleNamespace(MIPInfoCallback=FakeCallbackBase))
def packet():
    d=dict(c=np.array([0.,.5,.5,0.]),A=sparse.csr_matrix([[1.,1.5,0.,0.],[0.,1.25e-8,-1.25e-8,0.]]),
        Aeq=sparse.csr_matrix([[0.,1.,-1.,0.]]),b=np.array([1.375,1.4e-63]),beq=np.array([0.]),
        lb=np.array([0.,-5.,-np.inf,0.]),ub=np.array([1.,55.,np.inf,1.]),intcon=np.array([1.,4.]),x0=np.array([1.,.25,.25,0.]))
    return MatrixPacket.read(d,intcon_base=1,sense='min',objective_constant=0.,column_ids=range(4))
