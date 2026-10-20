"""Compare identical small-fixture row assembly, never a research case/solve.

The reference is archived from Git. cProfile includes its instrumentation cost.
Recursive storage counts unique Python objects retained by rows and named
caches, not process peak memory, native allocators or a general scaling claim.
"""
import argparse
from collections import Counter
import cProfile
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import pstats
import sys
import time

from inputs import load_config
from run_milp_precheck import fixtures
from run_construction_precheck import reference_sources, source_snapshot
from thermal import Budget, I
import milp

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def retained(objects):
    seen=set(); types=Counter()
    def visit(value):
        if id(value) in seen: return 0
        seen.add(id(value)); types[type(value).__name__] += 1
        total=sys.getsizeof(value)
        if isinstance(value, dict):
            total+=sum(visit(k)+visit(v) for k,v in value.items())
        elif isinstance(value, (list,tuple,set)):
            total+=sum(visit(v) for v in value)
        elif isinstance(value,F): total+=visit(value.numerator)+visit(value.denominator)
        elif isinstance(value,I): total+=visit(value.lo)+visit(value.hi)
        return total
    return {'unique_python_bytes':visit(objects),'object_counts':dict(types)}


def measured(operation):
    profile=cProfile.Profile(); start=time.perf_counter()
    profile.runcall(operation)
    elapsed=time.perf_counter()-start
    hot=[]
    for (file,line,name),(_,calls,own,total,_) in pstats.Stats(profile).stats.items():
        hot.append({'file':file,'line':line,'name':name,'calls':calls,'own_s':own,'cumulative_s':total})
    return {'profiled_s':elapsed,'top_20':sorted(hot,key=lambda r:r['cumulative_s'],reverse=True)[:20]}


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    hashes=source_snapshot(out); old,reference=reference_sources(out)
    config=load_config(); instance,starts=fixtures(config)['chain_fractional']
    # Actual chain fixture yields the integer control rows and active option
    # list used below. All times/powers come unchanged from this fixture.
    source=old.build_model(instance,config,starts=starts,include_physics=False,budget=Budget(seconds=600))
    tags={'unit_mutex','domain_unique/upper','domain_unique/lower','start_or_lower',
          'start_or_upper','idle_hold_upper','idle_hold_lower','active_locks_opp',
          'joint_unique/upper','joint_unique/lower','joint_marginal/upper','joint_marginal/lower'}
    controls=[({i:int(v) for i,v in r['coef'].items()},I(*r['rhs_interval']),r['tag'])
              for r in source.rows if r['tag'] in tags]
    assert controls and all(all(float(v)==r['coef'][i] for i,v in row.items())
                           for row, r in zip([a for a,_,_ in controls],[r for r in source.rows if r['tag'] in tags]))
    meta=next(iter(source.scenes.values()))
    active=max(meta['active'],key=len)
    powers={y:F(o['activity_power_W']) for o,y in active}
    output={}; models={}
    for label,module in [('reference',old),('current',milp)]:
        model=module.Model(instance,Budget(seconds=600))
        for i in range(len(source.names)): model.var(str(i),integer=True)
        target=model.var('activity_target',0,max(powers.values(),default=F(0)))
        def control():
            for _ in range(20):
                for row,rhs,tag in controls: model.le(row,rhs,tag)
        control_stats=measured(control)
        control_count=len(model.rows)
        control_storage=retained(model.rows)
        def activity():
            if hasattr(model,'activity_export'):
                exports={y:model.activity_export(y,p) for y,p in powers.items()}
                for _ in range(2000): model.activity_power_eq(target,list(powers),exports)
            else:
                for _ in range(2000): model.eq({target:1,**{y:-p for y,p in powers.items()}},0,'activity_power')
        activity_stats=measured(activity)
        cache_names=['_row_rhs_exports','_activity_exports','_fraction_exports',
                     '_fraction_negatives','_coefficient_exports','_bound_signatures','_bound_magnitudes']
        caches={k:getattr(model,k,{}) for k in cache_names}
        output[label]={'control':control_stats,'control_rows':control_count,'control_storage':control_storage,
                       'activity':activity_stats,'activity_rows':len(model.rows)-control_count,
                       'all_rows_storage':retained(model.rows),
                       'rows_plus_named_caches_storage':retained([model.rows,caches]),
                       'rows':len(model.rows),'nonzeros':model.row_nonzeros}
        models[label]=model
    equivalent=models['reference'].rows==models['current'].rows
    after={path:hashlib.sha256((REPO/path).read_bytes()).hexdigest() for path in hashes}
    result={'reference':reference,'scope':'same small chain fixture control rows repeated 20 times, activity equality 2000 times; no solve',
            'same_raw_rows':equivalent,'source_stable':hashes==after,'source_sha256':hashes,
            'source_sha256_after':after,'results':output,'formal_comparison':False}
    (out/'profile.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{f:v for f,v in r.items() if f not in ('control','activity')} |
                        {'control_s':r['control']['profiled_s'],'activity_s':r['activity']['profiled_s']}
                      for k,r in output.items()},indent=2))
    if not equivalent or hashes!=after: raise RuntimeError('row/profile identity failed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out)
