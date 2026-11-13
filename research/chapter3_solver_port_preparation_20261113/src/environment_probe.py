"""Read-only bounded inventory. Never creates a solver model/environment or reads credential values."""
import importlib.metadata as metadata,importlib.util,json,os,platform,sys
from pathlib import Path
TARGETS={'gurobipy','cplex','docplex','highspy','scipy','numpy','matlabengine'}
packages=[]
for d in metadata.distributions():
    name=d.metadata.get('Name','').lower()
    if name in TARGETS:
        packages.append(dict(name=name,version=d.version,location=str(d.locate_file(''))))
out=dict(python=sys.version,executable=sys.executable,platform=platform.platform(),packages=packages,
    importable={n:importlib.util.find_spec(n) is not None for n in ('gurobipy','cplex','docplex','highspy')},
    solver_models_created=0,license_sessions_started=0,optimization_calls=0)
print(json.dumps(out,ensure_ascii=True))
