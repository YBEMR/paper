"""Runtime identity without importing or initializing CPLEX."""
import importlib.metadata,platform,sys
def snapshot():
    return dict(python=sys.version,system=platform.system(),machine=platform.machine(),
                packages={p:importlib.metadata.version(p) for p in ('numpy','scipy','psutil','cplex')})
def verify_environment(expected):
    if snapshot()!=expected:raise ValueError('Python/package environment drift')
