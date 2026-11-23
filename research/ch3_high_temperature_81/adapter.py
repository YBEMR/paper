"""The original M2 algorithm, with explicit audited binding of the experiment ambient."""
from hashlib import sha256
from pathlib import Path
import types

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def load_m2(ambient, expected):
    path=ROOT/"research/kim_multidnn_search_trial/solver.py"
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=expected:
        raise ValueError("M2 source changed")
    source=raw.decode()
    replacements=[
        ("self.requests[i],25,True", "self.requests[i],AMBIENT,True"),
        ("thermal_kwargs(events.PLATFORM,opp,25,True", "thermal_kwargs(events.PLATFORM,opp,AMBIENT,True"),
        ('choice["opps"],25)', 'choice["opps"],AMBIENT)'),
    ]
    for before,after in replacements:
        if source.count(before)!=1:
            raise ValueError("unexpected temperature binding")
        source=source.replace(before,after)
    module=types.ModuleType("m2_ambient_bound")
    module.__file__=str(path)
    module.AMBIENT=ambient
    exec(compile(source,str(path),"exec"),module.__dict__)
    return module,source
