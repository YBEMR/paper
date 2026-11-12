"""Fresh model construction and exact complement projection; no optimizer."""
from contextlib import contextmanager
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import sys

ARMS = ('A', 'B', 'C')

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), default=str).encode()).hexdigest()

def require(condition, message):
    if not condition: raise ValueError(message)

def load_science(workspace):
    workspace = Path(workspace)
    sys.path.insert(0, str(workspace/'work/equality_pair_source/research/chapter3_experiments'))
    sys.path.insert(0, str(workspace/'work/stable_expression'))
    import milp, complement_gate
    return milp, complement_gate

def flags(base, arm):
    require(arm in ARMS, 'Unknown arm')
    return dict(base, propagate_support=arm!='A', prune_joint_states=arm=='C')

@contextmanager
def track_gates(milp):
    """Capture actual conditional API arguments, without changing any row arithmetic."""
    old_le, old_affine = milp.Model.conditional_le, milp.Model.affine_conditional_eq
    tables = {}
    def record(model, first, gate):
        # Probe models clear/reuse their rows; only the returned full model is certified.
        table = tables.setdefault(model, {})
        for i in range(first, len(model.rows)): table[i] = int(gate)
    def le(model, row, rhs, gate, tag):
        first=len(model.rows); out=old_le(model,row,rhs,gate,tag); record(model,first,gate); return out
    def affine(model,target,sources,coefficients,gate,tag):
        first=len(model.rows); out=old_affine(model,target,sources,coefficients,gate,tag)
        record(model,first,gate); return out
    milp.Model.conditional_le, milp.Model.affine_conditional_eq = le, affine
    try: yield tables
    finally: milp.Model.conditional_le, milp.Model.affine_conditional_eq = old_le, old_affine

def build(milp, instance, config, base, arm, budget):
    with track_gates(milp) as tables:
        model=milp.build_model(instance,config,budget=budget,include_physics=True,**flags(base,arm))
        gates=tables[model]
        require(set(gates)=={i for i,r in enumerate(model.rows) if 'big_M' in r}, 'Conditional row coverage')
    require(digest(model.instance)==digest(instance), 'Physical input changed')
    return model,gates

def export(model,x0):
    import numpy as np
    out=model.as_solver_dict()
    for k in ('A','Aeq'): out[k]=out[k].tocsc()
    out['intcon']=out['intcon'].astype(np.int64)
    out['x0']=np.asarray(x0,dtype=np.float64)
    return out

def certify(cg,old,gates,budget):
    budget.check()
    new,cert=cg.transform(old,row_gates=gates,gate_columns=sorted(set(gates.values())),mode='split_constant_v1')
    budget.check()
    # transform already invokes the independently assembled inverse-substitution checker.
    require(all(cert['checks'].values()),'Exact projection failed')
    return new,cert

def reduction_audit(model,config,arm,budget):
    from inputs import expand_options
    from option_support import verify_option_support_report
    before=[o for o in expand_options(model.instance,config,budget=budget)
            if F(o['end_ms'])<=F(o['request_deadline_ms'])]
    if arm=='A':
        require(before==model.options,'A is not the full deadline-filtered domain')
        support={'passed':True,'removed_by_support':0}
    else:
        from control import ScopedCorrectnessError
        try:
            support=verify_option_support_report(model.instance,before,model.options,
                                                model.preprocessing['option_support'],budget)
        except ValueError as e:raise ScopedCorrectnessError(str(e),['B','C']) from e
    joint=None
    if arm=='C':
        from reduction_replay import replay_joint
        from control import ScopedCorrectnessError
        try:joint=replay_joint(model,budget)
        except ValueError as e:raise ScopedCorrectnessError(str(e),['C']) from e
    return dict(passed=True,deadline_options=len(before),retained_options=len(model.options),
        support=support,joint=joint,scope='Integer schedules and unchanged physical semantics; not cross-arm fractional LP equality')
