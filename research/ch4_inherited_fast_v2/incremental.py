"""Exact event-boundary continuation of the frozen Numba integrator."""
import ctypes
import hashlib
import inspect
import time
from pathlib import Path

import numpy as np
from numba import njit

HEAT_BLOB = "69bef3c1917b874a9ceacf2ecaabfe14addfbd7e"
VECTORS = ("x", "maxima", "upper", "mins", "minlo", "node_time", "energy", "bases", "temps")
STATE_WIDTH = 4*len(VECTORS) + 3


@njit
def common_rows(left, right):
    for i in range(min(len(left), len(right))):
        for j in range(14):
            if left[i, j] != right[i, j]:
                return i
    return min(len(left), len(right))


def continuation(original, library):
    func = original.py_func
    source_bytes = Path(inspect.getsourcefile(func)).read_bytes()
    assert hashlib.sha1(b"blob "+str(len(source_bytes)).encode()+b"\0"+source_bytes).hexdigest() == HEAT_BLOB
    code = inspect.getsource(func)
    def change(before, after):
        nonlocal code
        assert code.count(before) == 1, before
        code = code.replace(before, after)
    change("@njit(cache=True)", "@njit")
    change("resets, rigorous):", "resets, rigorous, start_index, traces, states):")
    change("    traces=np.zeros((n,17))", "    init_start=native_ns()")
    restore = ["    if start_index:", "        previous=states[start_index-1]"]
    save = ["        write_start=native_ns()"]
    for i, variable in enumerate(VECTORS):
        section = f"{4*i}:{4*i+4}"
        restore.append(f"        {variable}=previous[{section}].copy()")
        save.append(f"        states[l,{section}]={variable}")
    restore.extend(["        round_T=previous[36]", "        round_E=previous[37]",
                    "        panels=int(previous[38])", "    saved_ns=float(native_ns()-init_start)", "    for l in range(start_index,n):"])
    save.extend(["        states[l,36]=round_T","        states[l,37]=round_E","        states[l,38]=panels",
                 "        saved_ns+=native_ns()-write_start"])
    change("    for l in range(n):", "\n".join(restore))
    change("        traces[l,16]=round_T", "        traces[l,16]=round_T\n"+"\n".join(save))
    change("energy,bases,temps,traces,panels)", "energy,bases,temps,traces,panels),saved_ns")
    native_ns = ctypes.CDLL(str(library)).checkpoint_ns
    native_ns.argtypes = []
    native_ns.restype = ctypes.c_uint64
    scope = dict(func.__globals__, native_ns=native_ns)
    exec(compile(code,"<frozen heat with boundary state>","exec"),scope)
    return scope["integrate"]


class Integration:
    def __init__(self, mode, original, resume, domain):
        self.mode, self.original, self.resume = mode, original, resume
        self.domain = domain
        self.history = []
        self.storage = 0
        self.latest = None

    def __call__(self, events, initial, G, cap, ta, resets, rigorous):
        assert rigorous and events.dtype == np.float64 and events.shape[1] == 14
        self.rows = len(events)
        self.reused = 0
        self.source = None
        timer = time.perf_counter
        if self.mode == "full":
            tick = timer()
            self.latest = self.original(events, initial, G, cap, ta, resets, rigorous)
            self.times["integrate"] += timer()-tick
            return self.latest
        tick = timer()
        key = (self.domain, initial.tobytes(), G.tobytes(), cap.tobytes(), np.float64(ta).tobytes(),
               resets.dtype.str, resets.tobytes(), rigorous)
        physical = events.view(np.uint64)
        previous = None
        for i,(scope, old, states, trace, origin) in enumerate(self.history):
            if scope != key:
                continue
            n = common_rows(physical, old)
            if n > self.reused:
                self.reused, self.source, previous = n, origin, (states, trace)
                if n == len(events):
                    break
        self.times["identity"] += timer()-tick
        tick = timer()
        if self.reused == len(events) and len(previous[0]) == len(events):
            states, trace = previous
        else:
            states = np.empty((len(events),STATE_WIDTH))
            trace = np.empty((len(events),17))
            if previous:
                n = self.reused
                states[:n] = previous[0][:n]
                trace[:n] = previous[1][:n]
        self.times["checkpoint"] += timer()-tick
        tick = timer()
        self.latest, save_ns = self.resume(events, initial, G, cap, ta, resets, rigorous,
                                           self.reused, trace, states)
        elapsed = timer()-tick
        self.times["integrate"] += elapsed-save_ns*1e-9
        self.times["checkpoint"] += save_ns*1e-9
        if self.reused < len(events):
            tick = timer()
            old = physical.copy()
            self.history.append((key,old,states,trace,self.ordinal))
            self.storage += old.nbytes + states.nbytes + trace.nbytes
            self.times["checkpoint"] += timer()-tick
        return self.latest
