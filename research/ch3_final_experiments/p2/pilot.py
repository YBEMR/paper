"""Cold-slot machinery for an independently authorized caller. No live command-line entry."""
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import sys
from time import perf_counter

from search import Clock, inspect_kim, kim_pool, thermal_ga

SEED = 20261121
SLOTS = {
    "01": ("forward_flat_25C", ("A", "C"), "Kim-Adapt"),
    "02": ("forward_flat_25C", ("A", "C"), "Kim-Adapt+SAFE"),
    "03": ("reverse_flat_27p5C", ("A", "C", "D001", "D015"), "Kim-Adapt+SAFE"),
    "04": ("reverse_flat_27p5C", ("A", "C", "D001", "D015"), "Thermal-GA"),
}


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    with tmp.open("x", encoding="utf8") as stream:
        json.dump(data, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def worker(root, slot, out, start, factory=None):
    from evaluator import Evaluator
    for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["NUMBA_CACHE_DIR"] = str(out/"numba_cache")
    sys.dont_write_bytecode = True
    case, allowed, method = SLOTS[slot]
    clock = Clock(start, start+57)
    with (out/"events.jsonl").open("x", encoding="utf8") as stream:
        def emit(event, value):
            stream.write(json.dumps([clock.elapsed(), event, value], separators=(",", ":"),
                                    allow_nan=False)+"\n")
            stream.flush()
        try:
            ev = (factory or Evaluator)(root, case, allowed, emit)
            identity = dict(slot=slot, method=method, case=case, allowed=allowed, seed=SEED,
                            request_sha256=ev.identity, rng="CPython random.Random/MT19937",
                            python=sys.version, init_s=clock.elapsed())
            emit("identity", identity)
            if method == "Thermal-GA":
                summary = thermal_ga(ev.domain, ev.replay, SEED, clock, emit)
            else:
                pool, info = kim_pool(ev.domain, ev.proxy, SEED, Clock(start, start+40), emit)
                summary = inspect_kim(pool, method.endswith("+SAFE"), ev.replay, clock, emit)
                if clock.now() >= clock.end and not summary["attempts"]:
                    summary["reason"] = "timeout"
                summary["pool"] = info
            result = dict(state="finished", identity=identity, summary=summary,
                          compute_end_s=clock.elapsed())
        except Exception as exc:
            emit("fault", dict(error=type(exc).__name__, detail=str(exc)))
            result = dict(state="fault", error=type(exc).__name__, detail=str(exc), slot=slot)
        persist_start = perf_counter()
        os.fsync(stream.fileno())
    write_json(out/"worker.json", result)
    write_json(out/"persistence.json", dict(journal_sync_and_result_s=perf_counter()-persist_start,
                                           result_on_disk_s=perf_counter()-start))


def supervise(root, slot, ledger, approval_reference, factory=None):
    """Upstream caller validates authority and freeze. Exclusive ledger consumes a slot on any outcome."""
    if slot not in SLOTS or not approval_reference:
        raise ValueError("missing slot or external approval reference")
    start = perf_counter()
    out = Path(ledger)/slot
    out.mkdir(exist_ok=False)
    write_json(out/"reservation.json", dict(slot=slot, cap_s=60, approval=approval_reference,
                                            start_monotonic=start))
    proc = multiprocessing.get_context("spawn").Process(target=worker, args=(root, slot, out, start, factory))
    state = "fault"
    try:
        proc.start()
        proc.join(max(0., start+60-perf_counter()))
        if proc.is_alive() or perf_counter() >= start+60:
            state = "hard_timeout"
            if proc.is_alive():
                proc.kill()
                proc.join()
        elif proc.exitcode == 0 and (out/"worker.json").exists():
            state = json.loads((out/"worker.json").read_bytes())["state"]
    finally:
        if proc.pid is not None and proc.is_alive():
            proc.kill()
            proc.join()
        elapsed = perf_counter()-start
        # This supervisory receipt is outside the scientific worker's time allowance.
        payload = (out/"worker.json").read_bytes() if (out/"worker.json").exists() else b""
        receipt = dict(slot=slot, state=state, elapsed_s=elapsed, exitcode=proc.exitcode,
                       worker_sha256=sha256(payload).hexdigest() if payload else None)
        write_json(out/"receipt.json", receipt)
    return receipt
