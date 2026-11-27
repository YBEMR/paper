"""Bounded enumeration over the frozen quota and frequency domain."""
from dataclasses import dataclass
from itertools import product
from functools import lru_cache
import numpy as np
from numba import njit

from planning import bits, choices
from planner import mappings
from suffix import Boundary, Timing


@lru_cache(maxsize=512)
def recipes(n, half, dev):
    return np.asarray(choices(n, half, dev, "E"), dtype=np.int64)


@njit(cache=True)
def scan(ids, dev, recipes_, start, old, cap, target, ready, limits, lengths, inc):
    size = len(recipes_)
    own = np.ones(size, np.bool_)
    margin = np.empty(size, np.int64)
    cost = np.zeros(size)
    ends = np.empty(size, np.int64)
    last = np.empty(size, np.int64)
    for j, (cut, first, second) in enumerate(recipes_):
        t, k = start, old
        for pos, i in enumerate(ids):
            f = first if pos < cut else second
            b = 10 * dev + f
            t = max(ready[i], t + 5 * (f != k)) + lengths[i, b]
            own[j] &= t <= limits[i]
            cost[j] += inc[i, b] + .0015 * (k != f)
            k = f
        margin[j] = cap - 5 * (k != target) - t
        cost[j] += .0015 * (k != target)
        ends[j], last[j] = t, k
    return own, margin, cost, ends, last


@dataclass(frozen=True)
class Leg:
    hint: float
    patch: bytes
    end: tuple
    margin: tuple
    fixed: bool

    @property
    def gap(self):
        return max(0, -min(self.margin))


def distinct(rows, limit):
    out = {}
    for row in rows:
        out.setdefault(row.patch, row)
        if len(out) == limit:
            break
    return list(out.values())


def shortlist(rows, blocked=False):
    rank = lambda r: (r.hint, r.patch)
    if blocked:
        rows = [r for r in rows if r.gap and r.hint < -1e-12]
        if not rows:
            return []
        by_gap = sorted(rows, key=lambda r: (r.gap, r.hint, r.patch))
        return distinct([min(rows, key=rank), *by_gap], 2)
    legal = sorted((r for r in rows if not r.gap), key=rank)
    return distinct([*legal[:3], *[r for r in legal if r.fixed][:2], *legal], 5)


class Space:
    def __init__(self, eng, code, state, timing, emit):
        self.eng, self.code, self.tm, self.emit = eng, code, timing, emit
        self.bound = Boundary(eng, code, state, timing)
        self.groups = [np.asarray(g) for g in eng.groups]
        self.kinds = np.asarray(eng.kindidx)
        self.release = np.array([r["release_tick"] for r in eng.p.req])
        self.inc = np.array([[eng.inc[t, 2 + int(k >= 10), k % 10] / eng.scale
                              for k in range(13)] for t in "AB"])[self.kinds]

    def splice(self, win, patch, base=None):
        ids = self.groups[win]
        base = self.code if base is None else base
        return base[:ids[0]] + patch + base[ids[-1] + 1:]

    def score(self, win, stop, patch, entry=None):
        ids = np.arange(self.groups[win][0], self.groups[stop][-1] + 1)
        code = np.frombuffer(patch, np.uint8)
        cost = self.inc[ids, code].sum()
        for d in range(2):
            prev = self.bound.limits(d, win)[1] if entry is None else entry[d][1]
            nxt = self.bound.limits(d, stop)[3]
            freq = code[(code >= 10) == d] % 10
            cost += .0015 * np.count_nonzero(np.diff(np.r_[prev, freq, nxt]))
        return float(cost)

    def leg_pool(self, win, label, entry=None, keep_blocked=False):
        ids = self.groups[win]
        base = self.bound.parent[ids]
        current = base.tobytes()
        reference = self.score(win, win, current, entry)
        cache, candidates = {}, {}
        raw_pairs = 0
        self.emit("open", label=label, win=win, entry=entry, noop=current.hex(),
                  parent_reference=reference, keep_blocked=keep_blocked)
        for tag, mapped in mappings("E", base, self.kinds[ids], self.release[ids] % 10000):
            devices, refs = [], []
            for d in range(2):
                ix = ids[mapped == d]
                key = (d, ix.tobytes())
                if key not in cache:
                    start, old, cap, target, nxt = self.bound.limits(d, win)
                    if entry is not None:
                        start, old = entry[d]
                    n = len(ix)
                    half = int(np.searchsorted(self.release[ix], win * 10000 + 5000))
                    recipe = recipes(n, half, d)
                    own, margin, cost, ends, last = scan(
                        ix, d, recipe, start, old, cap, target, self.tm.ready,
                        self.tm.limits, self.tm.lengths, self.inc)
                    valid = own & (margin >= 0)
                    fixed = (recipe[:, 0] == 0) | (recipe[:, 0] == half)
                    kept = []
                    for mask in (valid, valid & fixed):
                        good = np.flatnonzero(mask)
                        kept.extend(good[np.argsort(cost[good], kind="stable")[:4]].tolist())
                    bad = np.flatnonzero(own & ~valid)
                    if keep_blocked and len(bad):
                        kept.extend(bad[np.argsort(cost[bad], kind="stable")[:2]].tolist())
                        kept.extend(bad[np.lexsort((bad, cost[bad], -margin[bad]))[:2]].tolist())
                    opts = []
                    kept = list(dict.fromkeys(kept))
                    for j in kept:
                        cut, first, second = recipe[j]
                        freq = np.where(np.arange(n) < cut, first, second).astype(np.uint8) + 10*d
                        opts.append((freq, cost[j], int(ends[j]), int(last[j]), int(margin[j]), bool(fixed[j])))
                    ref = len(cache)
                    cache[key] = ref, opts
                    self.emit("device", label=label, id=ref, dev=d, ids=ix.tolist(), half=half,
                              start=start, old=old, cap=cap, target=target, next=nxt, raw=len(recipe),
                              own=bits(own), valid=bits(valid), kept=kept)
                ref, opts = cache[key]
                devices.append(opts)
                refs.append(ref)
            self.emit("mapping", label=label, tag=tag, devices=refs)
            for a, b in product(*devices):
                raw_pairs += 1
                patch = np.empty_like(base)
                patch[~mapped], patch[mapped] = a[0], b[0]
                key = patch.tobytes()
                if key == current or key in candidates:
                    continue
                candidates[key] = Leg(float(a[1]+b[1]-reference), key, ((a[2], a[3]), (b[2], b[3])),
                                      (a[4], b[4]), a[5] and b[5])
        legal = shortlist(candidates.values())
        blocked = shortlist(candidates.values(), blocked=True) if keep_blocked else []
        potential = sum(r.gap > 0 and r.hint < -1e-12 for r in candidates.values())
        self.emit("shortlist", label=label, win=win, pairs=raw_pairs, unique=len(candidates),
                  trigger_candidates=potential, valid=sum(not r.gap for r in candidates.values()),
                  legal=[r.patch.hex() for r in legal], blocked=[
                      dict(patch=r.patch.hex(), delta=r.hint, margin=r.margin, end=r.end) for r in blocked])
        return legal, blocked

    def paired(self, win, front, rear, role):
        patch = front.patch + rear.patch
        lo, hi = self.groups[win][0], self.groups[win+1][-1]+1
        code = self.code[:lo] + patch + self.code[hi:]
        hint = self.score(win, win+1, patch) - self.score(win, win+1, self.code[lo:hi])
        ok, miss, over = self.tm.check(code)
        meta = dict(role=role, win=win, front=front.patch.hex(), rear=rear.patch.hex(),
                    front_margin=front.margin, front_end=front.end, hint=float(hint),
                    rear_generator_margin=rear.margin)
        self.emit("pair", **meta, legal=bool(ok), first_miss=int(miss), over=int(over))
        return (code, meta) if ok else None

    def joint(self, method):
        windows = [self.leg_pool(w, f"base-{w}", keep_blocked=True) for w in range(len(self.groups))]
        pairs = {}
        for w, (legal, blocked) in enumerate(windows[:-1]):
            fronts = blocked if method == "J" else [*legal, *blocked]
            for index, f in enumerate(fronts):
                if method == "J":
                    rear, _ = self.leg_pool(w+1, f"regen-{w}-{index}", entry=f.end)
                else:
                    rear = [*windows[w+1][0], *windows[w+1][1]]
                for b in rear:
                    item = self.paired(w, f, b, method)
                    if item:
                        pairs.setdefault(item[0], item[1])
        return sorted(pairs.items(), key=lambda x: (x[1]["hint"], x[0]))
