"""Audited instance binding of the existing M2 source; no new search heuristic."""
from hashlib import sha256
from pathlib import Path
import types
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_m2(instance, source_sha):
    path = ROOT / "research/kim_multidnn_search_trial/solver.py"
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != source_sha:
        raise ValueError("Frozen M2 source drift")
    source = raw.decode()
    replacements = [
        ("self.requests[i],25,True", "self.requests[i],INSTANCE.ambient,True"),
        ("thermal_kwargs(events.PLATFORM,opp,25,True",
         "thermal_kwargs(events.PLATFORM,opp,INSTANCE.ambient,True"),
        ('choice["opps"],25)', 'choice["opps"],INSTANCE.ambient)'),
        ("self.scenes = make_scenes(case)", "self.scenes = INSTANCE.scenes"),
        ('physical["required"]==physical["completed"]==500',
         'physical["required"]==physical["completed"]==INSTANCE.required'),
        ('len(physical["scene_rows"])==4 and physical["scene_rows"][-1]["end_ns"]==10040000000',
         'len(physical["scene_rows"])==len(INSTANCE.scenes) and physical["scene_rows"][-1]["end_ns"]==INSTANCE.window_ns'),
        # All deployment minima receive physical certificates, for diagnostic
        # SAFE witnesses/count lower bounds; this does not change enumeration.
        ("selected=self.verify(leading)", "selected=self.verify(option)"),
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError(f"Unexpected M2 binding: {old}")
        source = source.replace(old, new)
    m = types.ModuleType("diagnostic_m2")
    m.__file__ = str(path)
    m.INSTANCE = instance
    exec(compile(source, str(path), "exec"), m.__dict__)
    instance.bind()
    m.events.PLATFORM = instance.platform
    m.events.FROZEN = instance.frozen
    m.joint.INITIAL = np.array(instance.initial, dtype=float)
    # Four scenes/27 clocks remain frozen; no general N-scene algorithm claim.
    if len(instance.scenes) != 4 or len(m.OPPS) != 27 or m.CATALOG != instance.order:
        raise ValueError("Unexpected frozen scope")
    return m, source, replacements
