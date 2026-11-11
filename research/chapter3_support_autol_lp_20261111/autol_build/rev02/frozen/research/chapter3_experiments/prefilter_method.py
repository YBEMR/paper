"""Deadline-prefilter pair over the unchanged full formal MILP lifecycle.

Both calls rebuild the complete shared-deployment problem and independently
construct/admit their own seed.  The only construction switch is the existing
``build_model(prefilter_deadlines=...)``; physical envelopes are rebuilt after
filtering, so the exported floating matrices need not be row-equivalent.
Importing this module runs neither a solver nor a research workload.
"""
from functools import partial
import json
import os
from pathlib import Path
import time

from formal_milp import execute_formal_milp
from matlab_bridge import MatlabSession
from milp import build_model


VARIANTS = ('current', 'prefilter')


def execute_prefilter_method(input_loader, out, *, seconds, variant='prefilter',
                             clock=time.monotonic, model_builder=build_model,
                             session_factory=MatlabSession):
    """Fresh full-chain call; caller supplies its separately authorized budget.

    Four existing strengthening flags, bounded initialization, admitted x0,
    conditional thermal feedback, MATLAB options and complete independent
    evaluation are inherited from ``execute_formal_milp``. No fixed deployment,
    scene decomposition, warm witness, candidate or cache is supplied here.
    Injected factories are only for correctness checks, as in the parent entry.
    """
    if variant not in VARIANTS:
        raise ValueError('variant must be current or prefilter')
    enabled = variant == 'prefilter'
    result = execute_formal_milp(input_loader, out, seconds=seconds,
        feedback_kind='conditional', clock=clock,
        model_builder=partial(model_builder, prefilter_deadlines=enabled),
        session_factory=session_factory)
    # Fixed archival labels only; no evidence is computed after method stop.
    result.update(preprocessing_variant=variant, prefilter_deadlines=enabled)
    path = Path(out)/'result.json'
    temporary = path.with_name(path.name+f'.{os.getpid()}.prefilter.tmp')
    temporary.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                     allow_nan=False)+'\n').encode('utf-8'))
    os.replace(temporary, path)
    return result
