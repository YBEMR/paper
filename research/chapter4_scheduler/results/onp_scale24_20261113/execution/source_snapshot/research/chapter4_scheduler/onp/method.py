"""Scoped provider injection into the unchanged blocking-method lifecycle.

Only one call may be active in a process. Formal arms run in separate serial
child processes. The original initializer, recorder, thermal evaluator, seen
cache, acceptance loop and root budget execute verbatim, never copied.
"""
from copy import deepcopy
from functools import partial
import hashlib
from pathlib import Path
from threading import Lock
import time

from ..blocking import method as frozen
from .packets import candidate_packets
from .prefilter import new_counts

LOCK = Lock()
ORIGINAL_SOURCE_IDENTITY = frozen.source_identity
RULE_VERSION = 'ON-P-exact-structural-necessary-conditions-v1'


def source_identity():
    sources = ORIGINAL_SOURCE_IDENTITY()
    here = Path(__file__).resolve().parent
    for path in sorted(here.glob('*.py')):
        sources[path.relative_to(here.parents[1]).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return sources


def execute_reconstruction(input_loader, workdir, *, bindings, seconds=300,
                           clock=time.monotonic, budget=None, allow_blocking_edges=True,
                           prefilter_enabled=True):
    if type(prefilter_enabled) is not bool:
        raise ValueError('boolean prefilter switch required')
    if not prefilter_enabled:
        return frozen.execute_reconstruction(input_loader, workdir, bindings=bindings,
            seconds=seconds, clock=clock, budget=budget, allow_blocking_edges=allow_blocking_edges)
    entered = clock()
    if budget is None:
        from timing import MethodBudget
        budget = MethodBudget(seconds, clock=clock)
        budget.start, budget.deadline = entered, entered + float(seconds)
    if not LOCK.acquire(blocking=False):
        raise RuntimeError('ONP_REQUIRES_ISOLATED_NONREENTRANT_PROCESS')
    names = ('candidate_packets', 'source_identity', 'RULE_VERSION', 'RULES')
    saved = {n: getattr(frozen, n) for n in names}
    counts = new_counts()
    try:
        frozen.candidate_packets = partial(candidate_packets, counts=counts)
        frozen.source_identity = source_identity
        frozen.RULE_VERSION = RULE_VERSION
        frozen.RULES = dict(deepcopy(saved['RULES']), prefilter='exact necessary conditions; no change to legal packet order')
        result = frozen.execute_reconstruction(input_loader, workdir, bindings=bindings,
            seconds=seconds, clock=clock, budget=budget, allow_blocking_edges=allow_blocking_edges)
        sidecar = dict(rule_version=RULE_VERSION, counts=dict(counts),
            prefilter_phases=['structural_prefilter_setup', 'structural_prefilter_check'],
            clock='All setup, checks and retained constructions use the same method root budget.',
            scope='Structural necessity only; complete original SAFE evaluation/strict acceptance unchanged.')
        frozen.original._save(Path(workdir) / 'prefilter.json', sidecar)
        return result
    finally:
        for name, value in saved.items():
            setattr(frozen, name, value)
        LOCK.release()
