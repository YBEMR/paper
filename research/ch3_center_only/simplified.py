"""Only the frozen NT expansion is replaced. Bind ledger and ranking helpers from that version."""
from itertools import groupby
from time import perf_counter as clock

import numpy as np
from method import analytic_plane
from common import digest, load_planes, window_types
from sampler import synthesize
from study import WINDOW


def expand(c, j, parents, method, start, deadline, log):
    assert method == "NT"
    lo = j * WINDOW
    final = j + 1 == c.windows
    right = c.p.horizon if final else lo + WINDOW
    types, a, b = window_types(c, j)
    pool = {}
    for parent in parents:
        for (g, n), group in groupby(c.candidates(j, parent), key=lambda item: item[0][:2]):
            if clock() >= deadline:
                return pool, False
            original = {tuple(action[2:]): ext for action, ext in group}
            load = load_planes(c, j, parent, g, n, a, b)
            center = c.eng.quota(parent, j, (g, n), (a, b))
            xs = np.arange(a + 1)
            balance = (load[1, 0] - load[0, 0] + (load[1, 1] - load[0, 1]) * xs) / (load[0, 2] - load[1, 2])
            cost = analytic_plane(c.eng, a, b, g, n)
            chosen = synthesize(load, np.empty((0, 3)), [center], balance, cost, a, b, len(original))
            for xy in original:
                if len(chosen) == len(original):
                    break
                if xy not in chosen:
                    chosen.append(xy)
            assert len(set(chosen)) == len(original) == len(chosen)
            for x, y in chosen:
                xy = (x, y)
                ext = original.get(xy)
                if ext is None:
                    ext = c.extension(types, a, b, g, n, x, y)
                cfg = parent["config"] + ext
                key = digest(cfg)
                action = (g, n, x, y)
                info = (j+1, parent["id"], *action, key, xy == center, xy in original)
                if key in pool:
                    log["actions"].append((*info, "duplicate", None, None, None, None, None))
                    continue
                ledger = c.ledger(cfg, lo, right, 2500, final, True)
                if not ledger[0]:
                    log["actions"].append((*info, "timing", None, None, None, None, int(ledger[-1])))
                    continue
                energy = ledger[1] + (c.base*c.p.horizon/WINDOW if final else 0.)
                temp, peak = parent["temperature"], parent["peak"]
                risk = max(load[:, 0] + load[:, 1:] @ xy)
                means = ledger[8]
                widths = np.minimum(2500, right-lo-2500*np.arange(len(means)))/WINDOW
                for mean, dt in zip(means, widths):
                    temp = c.propagate(temp, mean, dt)
                    peak = max(peak, max(temp))
                risk = peak if final else max(peak, max(c.propagate(temp, means[:4].mean(axis=0), 1.)))
                drain = max(max(ledger[2]), max(ledger[6]+c.args[4][:len(cfg)]))
                state = dict(config=cfg, id=key, f=tuple(map(int, ledger[2])),
                             k=tuple(map(int, ledger[3])), temperature=temp,
                             peak=peak, risk=risk, energy=energy, drain=drain, slack=int(ledger[-1]),
                             action=action, parent=parent["id"])
                pool[key] = state
                log["actions"].append((*info, "valid", energy, peak,
                                       risk, drain, state["slack"]))
            log["groups"].append(dict(window=j+1, parent=parent["id"], g=g, n=n, slots=len(original),
                                      calibration=None, end_s=clock()-start))
    return pool, True
